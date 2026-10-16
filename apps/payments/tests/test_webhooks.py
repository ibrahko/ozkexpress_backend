"""
Tests du webhook de paiement : seul un message authentifié par le provider
peut marquer une transaction comme payée.
`manage.py test apps.payments`
"""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.payments.models import PaymentProvider, PaymentStatus, PaymentType, Transaction
from apps.payments.services import PaymentService

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
WAVE_SECRET = "wave_test_secret"


def wave_signature(body: bytes, secret=WAVE_SECRET, timestamp=None):
    t = str(int(timestamp if timestamp is not None else time.time()))
    sig = hmac.new(secret.encode(), t.encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


@override_settings(CACHES=LOCMEM_CACHE, WAVE_WEBHOOK_SECRET=WAVE_SECRET, STRIPE_WEBHOOK_SECRET="")
class WebhookTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client_user = User.objects.create_user(phone="+22370000200", user_type="client")

    def make_tx(self, provider, reference="ME-TEST00000001", **kwargs):
        return Transaction.objects.create(
            client=self.client_user,
            provider=provider,
            payment_type=PaymentType.SERVICE_DELIVERY,
            amount=Decimal("1925"),
            reference=reference,
            status=PaymentStatus.PROCESSING,
            **kwargs,
        )

    def post(self, slug, payload, **headers):
        body = json.dumps(payload).encode()
        return self.api.generic(
            "POST", f"/api/v1/payments/webhook/{slug}/", body,
            content_type="application/json", **headers,
        ), body

    def status_of(self, tx):
        tx.refresh_from_db()
        return tx.status

    # ── L'ancienne faille : un simple POST avec la référence suffisait ──
    def test_webhook_forge_sans_signature_refuse(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        for slug in ("wave", "orange"):
            response, _ = self.post(slug, {"reference": tx.reference, "order_id": tx.reference})
            self.assertEqual(response.status_code, 403, slug)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    def test_provider_inconnu(self):
        response, _ = self.post("paypal", {})
        self.assertEqual(response.status_code, 404)

    # ── Wave ──
    def wave_payload(self, tx, amount="1925", status="succeeded"):
        return {
            "type": "checkout.session.completed",
            "data": {"id": "cos-123", "client_reference": tx.reference,
                     "payment_status": status, "amount": amount, "currency": "XOF"},
        }

    def send_wave(self, payload, signature=None):
        body = json.dumps(payload).encode()
        return self.api.generic(
            "POST", "/api/v1/payments/webhook/wave/", body, content_type="application/json",
            HTTP_WAVE_SIGNATURE=signature or wave_signature(body),
        )

    def test_wave_signature_valide_marque_paye_une_seule_fois(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        response = self.send_wave(self.wave_payload(tx))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status_of(tx), PaymentStatus.COMPLETED)
        self.assertEqual(tx.provider_transaction_id, "cos-123")

        replay = self.send_wave(self.wave_payload(tx))
        self.assertEqual(replay.data["detail"], "Déjà traité.")

    def test_wave_mauvaise_signature(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        body = json.dumps(self.wave_payload(tx)).encode()
        response = self.send_wave(self.wave_payload(tx), signature=wave_signature(body, secret="faux"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    def test_wave_signature_trop_ancienne(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        body = json.dumps(self.wave_payload(tx)).encode()
        old = wave_signature(body, timestamp=time.time() - 3600)
        self.assertEqual(self.send_wave(self.wave_payload(tx), signature=old).status_code, 403)

    def test_wave_montant_incoherent(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        response = self.send_wave(self.wave_payload(tx, amount="100"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    def test_wave_paiement_echoue_ignore(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        response = self.send_wave(self.wave_payload(tx, status="failed"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    @override_settings(WAVE_WEBHOOK_SECRET="")
    def test_wave_non_configure_refuse(self):
        tx = self.make_tx(PaymentProvider.WAVE)
        self.assertEqual(self.send_wave(self.wave_payload(tx)).status_code, 503)

    # ── Orange Money ──
    def test_orange_jeton_valide(self):
        tx = self.make_tx(PaymentProvider.ORANGE_MONEY, provider_response={"notif_token": "secret-tok"})
        response, _ = self.post("orange", {"status": "SUCCESS", "notif_token": "secret-tok", "txnid": "MP1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status_of(tx), PaymentStatus.COMPLETED)

    def test_orange_jeton_invalide(self):
        tx = self.make_tx(PaymentProvider.ORANGE_MONEY, provider_response={"notif_token": "secret-tok"})
        response, _ = self.post("orange", {"status": "SUCCESS", "notif_token": "devine", "txnid": "MP1"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    def test_orange_echec_ignore(self):
        tx = self.make_tx(PaymentProvider.ORANGE_MONEY, provider_response={"notif_token": "secret-tok"})
        response, _ = self.post("orange", {"status": "FAILED", "notif_token": "secret-tok"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status_of(tx), PaymentStatus.PROCESSING)

    # ── Stripe ──
    def test_stripe_non_configure_refuse(self):
        response, _ = self.post("stripe", {"type": "payment_intent.succeeded"})
        self.assertEqual(response.status_code, 503)


class InitiateDoesNotLeakSecretsTests(TestCase):
    def test_notif_token_garde_cote_serveur(self):
        user = User.objects.create_user(phone="+22370000201", user_type="client")
        tx = Transaction.objects.create(
            client=user, provider=PaymentProvider.ORANGE_MONEY,
            payment_type=PaymentType.SERVICE_DELIVERY, amount=Decimal("1925"),
            reference="ME-TEST00000002",
        )
        provider_reply = {"pay_token": "pt-1", "payment_url": "https://om/pay", "notif_token": "secret-tok"}
        with mock.patch(
            "apps.payments.services.OrangeMoneyProvider.initiate", return_value=provider_reply
        ), mock.patch("apps.payments.services.OrangeMoneyProvider.__init__", return_value=None):
            result = PaymentService.initiate_payment(tx)

        self.assertNotIn("notif_token", result)
        self.assertEqual(result["payment_url"], "https://om/pay")
        tx.refresh_from_db()
        self.assertEqual(tx.provider_response["notif_token"], "secret-tok")
        self.assertEqual(tx.provider_transaction_id, "pt-1")
        self.assertEqual(tx.status, PaymentStatus.PROCESSING)
