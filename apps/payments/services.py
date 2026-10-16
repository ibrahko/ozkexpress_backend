import hashlib
import hmac
import json
import time
import uuid
import requests
import logging
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from django.conf import settings
from .models import Transaction, PaymentProvider, PaymentStatus

logger = logging.getLogger(__name__)


def generate_reference() -> str:
    return f"ME-{uuid.uuid4().hex[:12].upper()}"


class BasePaymentProvider(ABC):
    @abstractmethod
    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        pass

    @abstractmethod
    def verify(self, transaction_id: str) -> dict:
        pass


class OrangeMoneyProvider(BasePaymentProvider):
    def __init__(self):
        self.api_url = settings.ORANGE_MONEY_API_URL
        self.client_id = settings.ORANGE_MONEY_CLIENT_ID
        self.client_secret = settings.ORANGE_MONEY_CLIENT_SECRET

    def _get_token(self) -> str:
        response = requests.post(
            f"{self.api_url}/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        token = self._get_token()
        response = requests.post(
            f"{self.api_url}/orange-money-webpay/dev/v1/webpayment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "merchant_key": self.client_id,
                "currency": currency,
                "order_id": reference,
                "amount": amount,
                "return_url": f"{settings.APP_BASE_URL}/payments/callback/orange/",
                "cancel_url": f"{settings.APP_BASE_URL}/payments/cancel/orange/",
                "notif_url": f"{settings.APP_BASE_URL}/api/v1/payments/webhook/orange/",
                "lang": "fr",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def verify(self, transaction_id: str) -> dict:
        token = self._get_token()
        response = requests.get(
            f"{self.api_url}/orange-money-webpay/dev/v1/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


class WaveProvider(BasePaymentProvider):
    def __init__(self):
        self.api_url = settings.WAVE_API_URL
        self.api_key = settings.WAVE_API_KEY

    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        response = requests.post(
            f"{self.api_url}/checkout/sessions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "amount": str(amount),
                "currency": currency,
                "client_reference": reference,
                "success_url": f"{settings.APP_BASE_URL}/payments/callback/wave/",
                "error_url": f"{settings.APP_BASE_URL}/payments/cancel/wave/",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def verify(self, transaction_id: str) -> dict:
        response = requests.get(
            f"{self.api_url}/checkout/sessions/{transaction_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


class StripeProvider(BasePaymentProvider):
    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency.lower(),
            metadata={"reference": reference},
        )
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}

    def verify(self, transaction_id: str) -> dict:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        intent = stripe.PaymentIntent.retrieve(transaction_id)
        return {"status": intent.status}


class PaymentService:
    _providers = {
        PaymentProvider.ORANGE_MONEY: OrangeMoneyProvider,
        PaymentProvider.WAVE: WaveProvider,
        PaymentProvider.STRIPE: StripeProvider,
    }

    @classmethod
    def get_provider(cls, provider: str) -> BasePaymentProvider:
        provider_class = cls._providers.get(provider)
        if not provider_class:
            raise ValueError(f"Provider inconnu: {provider}")
        return provider_class()

    # Champs de la réponse provider à ne jamais renvoyer au client : le notif_token
    # Orange authentifie les webhooks, le divulguer permettrait de les forger.
    _SECRET_FIELDS = {"notif_token"}

    @classmethod
    def initiate_payment(cls, transaction: Transaction) -> dict:
        if transaction.provider == PaymentProvider.CASH:
            transaction.mark_completed(provider_tx_id="CASH")
            return {"method": "cash", "status": "completed"}

        provider = cls.get_provider(transaction.provider)
        try:
            result = provider.initiate(
                amount=int(transaction.amount),
                currency=transaction.currency,
                phone=transaction.phone_number,
                reference=transaction.reference,
            )
        except Exception as e:
            logger.error("Erreur paiement %s: %s", transaction.reference, str(e))
            transaction.mark_failed(str(e))
            raise

        # Conserver côté serveur les identifiants qui serviront à authentifier le webhook
        transaction.status = PaymentStatus.PROCESSING
        transaction.provider_response = result
        transaction.provider_transaction_id = str(
            result.get("id") or result.get("payment_intent_id") or result.get("pay_token") or ""
        )
        transaction.save(update_fields=["status", "provider_response", "provider_transaction_id"])
        return {k: v for k, v in result.items() if k not in cls._SECRET_FIELDS}

    @staticmethod
    def complete_from_webhook(transaction: Transaction, provider_tx_id: str, payload: dict) -> bool:
        """
        Marque la transaction payée une seule fois, même si le provider renvoie
        le webhook plusieurs fois en parallèle. Retourne False si déjà traitée.
        """
        from django.utils import timezone
        updated = Transaction.objects.filter(
            pk=transaction.pk,
            status__in=[PaymentStatus.PENDING, PaymentStatus.PROCESSING],
        ).update(
            status=PaymentStatus.COMPLETED,
            provider_transaction_id=provider_tx_id or transaction.provider_transaction_id,
            provider_response={**(transaction.provider_response or {}), "webhook": payload},
            completed_at=timezone.now(),
        )
        return bool(updated)


class WebhookError(Exception):
    """Webhook refusé : non authentifié, incohérent ou provider non configuré."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class WebhookVerifier:
    """
    Authentifie un webhook de paiement AVANT de toucher à une transaction.
    Rien dans le corps de la requête n'est cru sur parole : chaque provider
    prouve l'origine du message (signature HMAC Wave, signature Stripe, ou
    jeton secret Orange connu seulement du serveur), puis le montant est
    comparé à celui de la transaction quand le provider le transmet.

    verify() retourne (transaction, provider_tx_id, payload) si le paiement est
    confirmé, ou None si l'événement est authentique mais ne confirme rien
    (paiement échoué, autre type d'événement).
    """

    SLUGS = {
        "orange": PaymentProvider.ORANGE_MONEY,
        "orange_money": PaymentProvider.ORANGE_MONEY,
        "wave": PaymentProvider.WAVE,
        "stripe": PaymentProvider.STRIPE,
    }
    WAVE_TOLERANCE_SECONDS = 300

    @classmethod
    def verify(cls, slug: str, headers, raw_body: bytes):
        provider = cls.SLUGS.get(slug)
        if provider is None:
            raise WebhookError("Provider inconnu.", 404)
        handler = {
            PaymentProvider.ORANGE_MONEY: cls._orange,
            PaymentProvider.WAVE: cls._wave,
            PaymentProvider.STRIPE: cls._stripe,
        }[provider]
        return handler(headers, raw_body)

    # ── Orange Money : le notif_token reçu doit être celui stocké à l'initiation ──
    @classmethod
    def _orange(cls, headers, raw_body):
        payload = cls._json(raw_body)
        token = str(payload.get("notif_token") or "")
        if not token:
            raise WebhookError("notif_token manquant.", 403)
        transaction = Transaction.objects.filter(
            provider=PaymentProvider.ORANGE_MONEY,
            provider_response__notif_token=token,
        ).first()
        if transaction is None:
            raise WebhookError("notif_token invalide.", 403)
        if payload.get("status") != "SUCCESS":
            return None
        return transaction, str(payload.get("txnid", "")), payload

    # ── Wave : en-tête Wave-Signature "t=<timestamp>,v1=<hmac>" sur timestamp + corps ──
    @classmethod
    def _wave(cls, headers, raw_body):
        secret = settings.WAVE_WEBHOOK_SECRET
        if not secret:
            raise WebhookError("Webhook Wave non configuré.", 503)
        timestamp, signatures = None, []
        for part in headers.get("Wave-Signature", "").split(","):
            key, _, value = part.strip().partition("=")
            if key == "t":
                timestamp = value
            elif key == "v1":
                signatures.append(value)
        if not timestamp or not signatures:
            raise WebhookError("Signature Wave absente.", 403)
        try:
            age = abs(time.time() - int(timestamp))
        except ValueError:
            raise WebhookError("Signature Wave invalide.", 403)
        if age > cls.WAVE_TOLERANCE_SECONDS:
            raise WebhookError("Signature Wave expirée.", 403)
        expected = hmac.new(
            secret.encode(), timestamp.encode() + raw_body, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise WebhookError("Signature Wave invalide.", 403)

        payload = cls._json(raw_body)
        data = payload.get("data") or {}
        if payload.get("type") != "checkout.session.completed" or data.get("payment_status") != "succeeded":
            return None
        transaction = cls._get(data.get("client_reference"), PaymentProvider.WAVE)
        cls._check_amount(transaction, data.get("amount"))
        return transaction, str(data.get("id", "")), payload

    # ── Stripe : vérification officielle de la signature ──
    @classmethod
    def _stripe(cls, headers, raw_body):
        import stripe
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            raise WebhookError("Webhook Stripe non configuré.", 503)
        try:
            event = stripe.Webhook.construct_event(
                raw_body, headers.get("Stripe-Signature", ""), secret
            )
        except Exception:  # ValueError (JSON) ou SignatureVerificationError
            raise WebhookError("Signature Stripe invalide.", 403)
        if event["type"] != "payment_intent.succeeded":
            return None
        intent = event["data"]["object"]
        transaction = cls._get((intent.get("metadata") or {}).get("reference"), PaymentProvider.STRIPE)
        cls._check_amount(transaction, intent.get("amount_received"))
        return transaction, str(intent.get("id", "")), json.loads(raw_body)

    # ── Utilitaires ──
    @staticmethod
    def _json(raw_body):
        try:
            return json.loads(raw_body or b"{}")
        except ValueError:
            raise WebhookError("Corps JSON invalide.")

    @staticmethod
    def _get(reference, provider):
        if not reference:
            raise WebhookError("Référence manquante.")
        try:
            return Transaction.objects.get(reference=reference, provider=provider)
        except Transaction.DoesNotExist:
            raise WebhookError("Transaction introuvable.", 404)

    @staticmethod
    def _check_amount(transaction, amount):
        try:
            paid = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            raise WebhookError("Montant invalide.")
        if paid != transaction.amount:
            logger.warning(
                "Webhook %s : montant %s ≠ attendu %s", transaction.reference, paid, transaction.amount
            )
            raise WebhookError("Montant incohérent.")
