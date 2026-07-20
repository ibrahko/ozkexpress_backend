"""
Tests unitaires de la tarification (apps/services/pricing.py).
Aucune base de données requise : `manage.py test apps.services.tests.test_pricing`
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.services import pricing


class FakePoint:
    """Point minimal (x = lng, y = lat) — évite la dépendance GEOS dans ces tests."""
    def __init__(self, lng, lat):
        self.x = lng
        self.y = lat


# Centres des quartiers utilisés dans les tests (cf. migration 0005)
DJELIBOUGOU = FakePoint(-7.9770, 12.6740)
ZONE_INDUSTRIELLE = FakePoint(-7.9720, 12.6350)


class HaversineTests(SimpleTestCase):
    def test_distance_nulle_entre_memes_points(self):
        self.assertEqual(pricing.haversine_km(12.65, -7.98, 12.65, -7.98), 0)

    def test_distance_djelibougou_zone_industrielle(self):
        km = pricing.haversine_km(12.6740, -7.9770, 12.6350, -7.9720)
        # ~4,4 km à vol d'oiseau
        self.assertAlmostEqual(km, 4.37, delta=0.1)


class ComputeDistanceTests(SimpleTestCase):
    def test_distance_minimum_0_5_km(self):
        p = FakePoint(-7.98, 12.65)
        self.assertEqual(pricing.compute_distance_km(p, p), Decimal("0.50"))

    def test_facteur_routier_applique(self):
        brut = pricing.haversine_km(
            DJELIBOUGOU.y, DJELIBOUGOU.x, ZONE_INDUSTRIELLE.y, ZONE_INDUSTRIELLE.x
        )
        d = pricing.compute_distance_km(DJELIBOUGOU, ZONE_INDUSTRIELLE)
        self.assertAlmostEqual(float(d), brut * float(pricing.ROAD_FACTOR), places=1)

    def test_arrondi_2_decimales(self):
        d = pricing.compute_distance_km(DJELIBOUGOU, ZONE_INDUSTRIELLE)
        self.assertEqual(d, d.quantize(Decimal("0.01")))


class DeliveryPriceTests(SimpleTestCase):
    def test_formule_1000_plus_200_par_km_plus_220(self):
        # 5 km → 1000 + 1000 + 220 = 2220
        self.assertEqual(pricing.compute_delivery_price(5), Decimal("2220"))

    def test_distance_minimum(self):
        # 0,5 km → 1000 + 100 + 220 = 1320
        self.assertEqual(pricing.compute_delivery_price(Decimal("0.5")), Decimal("1320"))

    def test_arrondi_au_franc(self):
        # 5,68 km → 1000 + 1136 + 220 = 2356
        self.assertEqual(pricing.compute_delivery_price(Decimal("5.68")), Decimal("2356"))

    def test_prix_djelibougou_zone_industrielle(self):
        d = pricing.compute_distance_km(DJELIBOUGOU, ZONE_INDUSTRIELLE)
        total = pricing.compute_delivery_price(d)
        # Ordre de grandeur attendu : entre 2 000 et 2 700 FCFA
        self.assertGreater(total, Decimal("2000"))
        self.assertLess(total, Decimal("2700"))


class RidePriceTests(SimpleTestCase):
    def test_meme_bareme_par_defaut(self):
        self.assertEqual(pricing.compute_ride_price(5), pricing.compute_delivery_price(5))


class QuoteTests(SimpleTestCase):
    def test_structure_et_coherence(self):
        q = pricing.quote(DJELIBOUGOU, ZONE_INDUSTRIELLE, "delivery")
        self.assertEqual(
            set(q),
            {"kind", "distance_km", "base", "per_km", "distance_fee", "service_fee",
             "multiplier", "surcharge", "total"},
        )
        self.assertEqual(q["kind"], "delivery")
        self.assertEqual(q["per_km"], 200)
        # total = base + distance + frais + majoration éventuelle
        self.assertEqual(
            q["base"] + q["distance_fee"] + q["service_fee"] + q["surcharge"], q["total"]
        )

    def test_multiplicateur_neutre_par_defaut(self):
        # Sans majoration configurée, multiplier = 1 et surcharge = 0
        from decimal import Decimal as D
        from datetime import datetime, timezone as tz
        midi = datetime(2026, 7, 20, 12, 0, tzinfo=tz.utc)
        self.assertEqual(pricing.current_multiplier(midi), D("1.00"))

    def test_quote_ride(self):
        q = pricing.quote(DJELIBOUGOU, ZONE_INDUSTRIELLE, "ride")
        self.assertEqual(q["kind"], "ride")
        self.assertGreater(q["total"], 0)
