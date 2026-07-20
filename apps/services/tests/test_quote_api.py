"""
Tests des endpoints /services/zones/, /services/quote/ et de la validation
des coordonnées (anti-(0,0)). Nécessite la base de test PostGIS :
`manage.py test apps.services.tests.test_quote_api`
"""
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.accounts.models import User

DJELIBOUGOU = {"lat": 12.6740, "lng": -7.9770}
ZONE_INDUSTRIELLE = {"lat": 12.6350, "lng": -7.9720}

# Le throttling DRF s'appuie sur le cache Redis ; en test on utilise
# un cache mémoire pour ne pas dépendre d'un serveur Redis local.
LOCMEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
}


def make_client_user(phone="+22370000001"):
    return User.objects.create_user(phone=phone, user_type="client")


@override_settings(CACHES=LOCMEM_CACHE)
class QuoteApiTests(APITestCase):
    def setUp(self):
        self.user = make_client_user()
        self.client.force_authenticate(self.user)

    def test_quote_livraison(self):
        res = self.client.post(
            reverse("service-quote"),
            {"pickup": DJELIBOUGOU, "delivery": ZONE_INDUSTRIELLE, "kind": "delivery"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["per_km"], 200)
        self.assertEqual(data["base"] + data["distance_fee"] + data["service_fee"], data["total"])
        self.assertGreater(data["distance_km"], 0)

    def test_quote_course(self):
        res = self.client.post(
            reverse("service-quote"),
            {"pickup": DJELIBOUGOU, "delivery": ZONE_INDUSTRIELLE, "kind": "ride"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["kind"], "ride")

    def test_quote_refuse_coordonnees_0_0(self):
        res = self.client.post(
            reverse("service-quote"),
            {"pickup": {"lat": 0, "lng": 0}, "delivery": ZONE_INDUSTRIELLE},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_quote_refuse_hors_zone(self):
        # Paris — hors de la zone de service de Bamako
        res = self.client.post(
            reverse("service-quote"),
            {"pickup": {"lat": 48.85, "lng": 2.35}, "delivery": ZONE_INDUSTRIELLE},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_quote_exige_authentification(self):
        self.client.force_authenticate(None)
        res = self.client.post(
            reverse("service-quote"),
            {"pickup": DJELIBOUGOU, "delivery": ZONE_INDUSTRIELLE},
            format="json",
        )
        self.assertEqual(res.status_code, 401)


@override_settings(CACHES=LOCMEM_CACHE)
class ZonesApiTests(APITestCase):
    def setUp(self):
        self.user = make_client_user("+22370000002")
        self.client.force_authenticate(self.user)

    def test_liste_des_quartiers(self):
        res = self.client.get(reverse("service-zones"))
        self.assertEqual(res.status_code, 200)
        zones = res.json()
        names = [z["name"] for z in zones]
        self.assertIn("Djélibougou", names)
        self.assertIn("Zone Industrielle", names)
        # Chaque zone expose son centre {lat, lng}
        z = zones[0]
        self.assertIn("lat", z["center"])
        self.assertIn("lng", z["center"])


@override_settings(CACHES=LOCMEM_CACHE)
class ServiceRequestValidationTests(APITestCase):
    """La création d'une livraison refuse les coordonnées invalides."""

    def setUp(self):
        self.user = make_client_user("+22370000003")
        self.client.force_authenticate(self.user)

    def _payload(self, pickup, delivery):
        return {
            "pickup_address": "Djélibougou",
            "pickup_location": pickup,
            "delivery_address": "Zone Industrielle",
            "delivery_location": delivery,
            "delivery_contact_name": "Aminata",
            "delivery_contact_phone": "+22370000099",
            "package_description": "Documents",
        }

    def test_creation_refusee_avec_0_0(self):
        res = self.client.post(
            "/api/v1/services/",
            self._payload({"lat": 0, "lng": 0}, ZONE_INDUSTRIELLE),
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_creation_ok_calcule_distance_et_prix(self):
        res = self.client.post(
            "/api/v1/services/",
            self._payload(DJELIBOUGOU, ZONE_INDUSTRIELLE),
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertIsNotNone(data["distance_km"])
        self.assertIsNotNone(data["estimated_price"])
        # total = 1000 + distance×200 + 220
        attendu = 1000 + round(float(data["distance_km"]) * 200) + 220
        self.assertAlmostEqual(float(data["estimated_price"]), attendu, delta=1)
