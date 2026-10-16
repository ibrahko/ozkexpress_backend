"""
Tests du back-office : chaque page d'admin s'affiche et les actions métier
(validation/suspension, retraits, annulation) respectent les règles.
`manage.py test apps.backoffice`
"""
from decimal import Decimal

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.disputes.models import Dispute
from apps.payments.models import PaymentProvider, Wallet, WithdrawalRequest
from apps.services.models import PaymentMethod, RequestStatus, Zone, ZoneDistance
from apps.services.tests.test_status_transitions import make_courier, make_delivery, make_driver
from apps.workforce.models import WorkerDocument, WorkerStatus, WorkerSuspended

LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
WITHDRAWAL = WithdrawalRequest.WithdrawalStatus


def seed():
    """Un jeu de données qui touche chaque écran du back-office."""
    client = User.objects.create_user(phone="+22370000300", user_type="client", first_name="Awa")
    courier = make_courier()
    driver = make_driver()
    delivery = make_delivery(client, payment_method=PaymentMethod.WAVE)
    delivery.accept(courier)
    delivery.mark_pickup()
    delivery.mark_in_progress()
    delivery.mark_delivered()
    make_delivery(client)  # une commande en attente
    WorkerDocument.objects.create(
        content_type=ContentType.objects.get_for_model(courier), object_id=courier.pk,
        doc_type="driver_license", file="worker_documents/permis.pdf",
    )
    a = Zone.objects.create(name="Quartier Test A", commune="Commune I", center=Point(-7.977, 12.674, srid=4326))
    b = Zone.objects.create(name="Quartier Test B", commune="Commune II", center=Point(-7.972, 12.635, srid=4326))
    ZoneDistance.objects.create(zone_from=a, zone_to=b, road_km=Decimal("5.70"))
    WithdrawalRequest.objects.create(
        wallet=Wallet.objects.get(user=courier.user), amount=Decimal("1000"),
        provider=PaymentProvider.ORANGE_MONEY, phone_number="+22371000001",
    )
    Dispute.objects.create(opened_by=client, reason="late_delivery", description="Retard", service_request=delivery)
    return courier, driver


@override_settings(CACHES=LOCMEM_CACHE)
class AdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(phone="+22379999999", password="test-pass-123")
        seed()

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_tableau_de_bord(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "À traiter")
        self.assertContains(response, "Retraits à traiter")

    def test_toutes_les_pages_admin_s_affichent(self):
        for model, model_admin in admin.site._registry.items():
            info = (model._meta.app_label, model._meta.model_name)
            with self.subTest(model=model._meta.label):
                changelist = self.client.get(reverse("admin:%s_%s_changelist" % info))
                self.assertEqual(changelist.status_code, 200)
                obj = model.objects.first()
                if obj is not None:
                    change = self.client.get(reverse("admin:%s_%s_change" % info, args=[obj.pk]))
                    self.assertEqual(change.status_code, 200)
                if model_admin.has_add_permission(self._request()):
                    add = self.client.get(reverse("admin:%s_%s_add" % info))
                    self.assertEqual(add.status_code, 200)

    def test_recherche_coursier_par_telephone(self):
        url = reverse("admin:couriers_courier_changelist") + "?q=71000001"
        self.assertContains(self.client.get(url), "+22371000001")

    def test_page_de_connexion_sans_compte(self):
        self.client.logout()
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)

    def _request(self):
        from django.test import RequestFactory
        request = RequestFactory().get("/")
        request.user = self.admin_user
        return request


@override_settings(CACHES=LOCMEM_CACHE)
class AdminActionsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(phone="+22379999998", password="test-pass-123")
        self.client.force_login(self.admin_user)
        self.courier, self.driver = seed()

    def run_action(self, model, action, objects):
        info = (model._meta.app_label, model._meta.model_name)
        return self.client.post(
            reverse("admin:%s_%s_changelist" % info),
            {"action": action, "_selected_action": [str(o.pk) for o in objects]},
            follow=True,
        )

    # ── Retraits ──
    def test_approuver_un_retrait_debite_le_portefeuille_une_seule_fois(self):
        withdrawal = WithdrawalRequest.objects.get()
        wallet = withdrawal.wallet
        self.assertEqual(wallet.balance, Decimal("1525"))

        self.run_action(WithdrawalRequest, "approve", [withdrawal])
        self.run_action(WithdrawalRequest, "approve", [withdrawal])  # double clic

        wallet.refresh_from_db()
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WITHDRAWAL.APPROVED)
        self.assertEqual(wallet.balance, Decimal("525"))
        self.assertEqual(wallet.total_withdrawn, Decimal("1000"))

        self.run_action(WithdrawalRequest, "mark_paid", [withdrawal])
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WITHDRAWAL.PAID)

    def test_retrait_superieur_au_solde_refuse(self):
        withdrawal = WithdrawalRequest.objects.get()
        withdrawal.amount = Decimal("5000")
        withdrawal.save()
        response = self.run_action(WithdrawalRequest, "approve", [withdrawal])
        self.assertContains(response, "Solde insuffisant")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WITHDRAWAL.PENDING)
        self.assertEqual(withdrawal.wallet.balance, Decimal("1525"))

    def test_refuser_un_retrait_ne_touche_pas_au_solde(self):
        withdrawal = WithdrawalRequest.objects.get()
        self.run_action(WithdrawalRequest, "reject", [withdrawal])
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WITHDRAWAL.REJECTED)
        self.assertEqual(withdrawal.wallet.balance, Decimal("1525"))

    # ── Coursiers ──
    def test_suspension_empeche_de_se_remettre_en_ligne(self):
        from apps.couriers.models import Courier
        self.run_action(Courier, "suspend_workers", [self.courier])
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.status, WorkerStatus.SUSPENDED)

        with self.assertRaises(WorkerSuspended):
            self.courier.go_online()
        # Une déconnexion (WebSocket) ne lève pas la suspension
        self.courier.go_offline()
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.status, WorkerStatus.SUSPENDED)

        self.run_action(Courier, "approve_workers", [self.courier])
        self.courier.refresh_from_db()
        self.assertEqual(self.courier.status, WorkerStatus.OFFLINE)
        self.courier.go_online()
        self.assertEqual(self.courier.status, WorkerStatus.ONLINE)

    def test_coursier_suspendu_ne_peut_pas_accepter(self):
        from rest_framework.test import APIClient
        from apps.services.models import ServiceRequest
        self.courier.suspend()
        pending = ServiceRequest.objects.get(status=RequestStatus.PENDING)
        api = APIClient()
        api.force_authenticate(self.courier.user)
        response = api.post(f"/api/v1/services/{pending.pk}/accept/")
        self.assertEqual(response.status_code, 403)

    # ── Commandes ──
    def test_annulation_support_respecte_la_machine_a_etats(self):
        from apps.services.models import ServiceRequest
        delivered = ServiceRequest.objects.get(status=RequestStatus.DELIVERED)
        pending = ServiceRequest.objects.get(status=RequestStatus.PENDING)
        response = self.run_action(ServiceRequest, "cancel_orders", [delivered, pending])

        delivered.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(delivered.status, RequestStatus.DELIVERED)  # refusée
        self.assertEqual(pending.status, RequestStatus.CANCELLED)
        self.assertContains(response, "1 commande(s) annulée(s)")
        self.assertContains(response, "Transition impossible")

    def test_documents_verifies_par_l_admin(self):
        doc = WorkerDocument.objects.get()
        self.run_action(WorkerDocument, "verify_documents", [doc])
        doc.refresh_from_db()
        self.assertTrue(doc.is_verified)
        self.assertEqual(doc.verified_by, self.admin_user)
