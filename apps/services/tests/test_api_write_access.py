"""
Tests des accès en écriture de l'API :
- un coursier ou chauffeur ne peut pas changer son propre statut (suspension),
- les commandes et courses ne se modifient ni ne se suppriment par PUT/PATCH/DELETE.
`manage.py test apps.services.tests.test_api_write_access`
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.services.models import RequestStatus, RideRequest, ServiceRequest
from apps.services.tests.test_security import deliver_fully
from apps.services.tests.test_status_transitions import (
    DROPOFF, PICKUP, make_courier, make_delivery, make_driver,
)
from apps.workforce.models import WorkerStatus

# Throttling DRF sans Redis local
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class WorkerCannotChangeOwnStatusTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def check_me(self, worker, url):
        worker.suspend()
        self.api.force_authenticate(worker.user)

        response = self.api.patch(url, {"status": "active", "is_available": True, "vehicle_color": "Rouge"}, format="json")

        self.assertEqual(response.status_code, 200)
        worker.refresh_from_db()
        self.assertEqual(worker.status, WorkerStatus.SUSPENDED)  # suspension intacte
        self.assertFalse(worker.is_available)
        self.assertEqual(worker.vehicle_color, "Rouge")  # les champs autorisés restent modifiables
        self.assertEqual(self.api.post(url.replace("me/", "go_online/")).status_code, 403)

    def test_coursier_suspendu_ne_peut_pas_se_reactiver(self):
        self.check_me(make_courier(), "/api/v1/couriers/me/")

    def test_chauffeur_suspendu_ne_peut_pas_se_reactiver(self):
        self.check_me(make_driver(), "/api/v1/drivers/me/")

    def test_fiche_ni_creee_ni_supprimee_par_l_api(self):
        courier = make_courier()
        self.api.force_authenticate(courier.user)
        detail = f"/api/v1/couriers/{courier.pk}/"
        self.assertEqual(self.api.delete(detail).status_code, 405)
        self.assertEqual(self.api.put(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.api.post("/api/v1/couriers/", {}, format="json").status_code, 405)
        self.assertEqual(self.api.get(detail).status_code, 200)


@override_settings(CACHES=LOCMEM_CACHE)
class OrdersAreNotEditableTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client_user = User.objects.create_user(phone="+22370000400", user_type="client")
        self.courier = make_courier()

    def assert_locked(self, user, url):
        self.api.force_authenticate(user)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.api, method)(url, {"delivery_address": "Ailleurs"}, format="json")
                self.assertEqual(response.status_code, 405)

    def test_coursier_ne_peut_ni_modifier_ni_supprimer_une_commande_en_attente(self):
        pending = make_delivery(self.client_user)
        self.assert_locked(self.courier.user, f"/api/v1/services/{pending.pk}/")
        pending.refresh_from_db()
        self.assertEqual(pending.status, RequestStatus.PENDING)
        self.assertEqual(pending.delivery_address, "Zone Industrielle")

    def test_client_ne_peut_pas_effacer_une_commande_livree(self):
        delivered = make_delivery(self.client_user)
        deliver_fully(delivered, self.courier)
        self.assert_locked(self.client_user, f"/api/v1/services/{delivered.pk}/")
        self.assertTrue(ServiceRequest.objects.filter(pk=delivered.pk).exists())

    def test_courses_verrouillees_aussi(self):
        ride = RideRequest.objects.create(
            client=self.client_user,
            pickup_address="A", pickup_location=PICKUP,
            dropoff_address="B", dropoff_location=DROPOFF,
            estimated_price=Decimal("1925"), distance_km=Decimal("5.68"),
        )
        self.assert_locked(make_driver().user, f"/api/v1/rides/{ride.pk}/")
        self.assert_locked(self.client_user, f"/api/v1/rides/{ride.pk}/")
        self.assertTrue(RideRequest.objects.filter(pk=ride.pk).exists())

    def test_lecture_et_actions_toujours_possibles(self):
        pending = make_delivery(self.client_user)
        self.api.force_authenticate(self.client_user)
        self.assertEqual(self.api.get(f"/api/v1/services/{pending.pk}/").status_code, 200)
        self.assertEqual(self.api.get("/api/v1/services/").status_code, 200)
        self.assertEqual(self.api.post(f"/api/v1/services/{pending.pk}/cancel/").status_code, 200)
