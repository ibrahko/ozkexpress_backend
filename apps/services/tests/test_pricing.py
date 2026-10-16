"""
Tests unitaires de la tarification (apps/services/pricing.py).
Barème validé juillet 2026 : 400 F (prise en charge) + 200 F/km + 400 F (frais
de service), arrondi au multiple de 25 F. Majoration nuit ×1,3 (21h-6h),
répartie 85 % coursier/chauffeur — 15 % entreprise.

Aucune base de données requise : `manage.py test apps.services.tests.test_pricing`
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.services import pricing

DAY = Decimal("1.0")   # multiplicateur explicite pour des tests déterministes,
NIGHT = Decimal("1.3")  # indépendants de l'heure réelle d'exécution des tests


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


class RoundToStepTests(SimpleTestCase):
    def test_arrondi_au_multiple_de_25(self):
        self.assertEqual(pricing.round_to_step(1212), Decimal("1200"))
        self.assertEqual(pricing.round_to_step(1213), Decimal("1225"))
        self.assertEqual(pricing.round_to_step(900), Decimal("900"))


class DeliveryPriceTests(SimpleTestCase):
    def test_formule_400_plus_200_par_km_plus_400(self):
        # 5 km → (400 + 1000) + 400 = 1800 (déjà multiple de 25)
        self.assertEqual(pricing.compute_delivery_price(5, multiplier=DAY), Decimal("1800"))

    def test_distance_minimum(self):
        # 0,5 km → 400 + 100 + 400 = 900
        self.assertEqual(pricing.compute_delivery_price(Decimal("0.5"), multiplier=DAY), Decimal("900"))

    def test_arrondi_au_multiple_de_25(self):
        # 5,68 km → 400 + 1136 + 400 = 1936 → arrondi 1925
        self.assertEqual(pricing.compute_delivery_price(Decimal("5.68"), multiplier=DAY), Decimal("1925"))

    def test_majoration_nuit(self):
        # 5,68 km, nuit ×1,3 → (400+1136)×1,3 + 400 = 2396,8 → arrondi 2400
        self.assertEqual(pricing.compute_delivery_price(Decimal("5.68"), multiplier=NIGHT), Decimal("2400"))

    def test_prix_djelibougou_zone_industrielle(self):
        d = pricing.compute_distance_km(DJELIBOUGOU, ZONE_INDUSTRIELLE)
        total = pricing.compute_delivery_price(d, multiplier=DAY)
        # Ordre de grandeur attendu : entre 1 500 et 2 200 FCFA
        self.assertGreater(total, Decimal("1500"))
        self.assertLess(total, Decimal("2200"))


class RidePriceTests(SimpleTestCase):
    def test_meme_bareme_que_livraison(self):
        # Formule générique partout : même barème colis/courses
        self.assertEqual(
            pricing.compute_ride_price(5, multiplier=DAY),
            pricing.compute_delivery_price(5, multiplier=DAY),
        )


class NightSurchargeSplitTests(SimpleTestCase):
    def test_pas_de_majoration_le_jour(self):
        # Prix de jour : commission = frais de service (400 F), tout le reste au coursier
        day_price = pricing.compute_delivery_price(Decimal("5.68"), multiplier=DAY)
        commission, net = pricing.split_night_surcharge(day_price, Decimal("5.68"), kind="delivery")
        self.assertEqual(commission, Decimal("400"))
        self.assertEqual(net, day_price - Decimal("400"))

    def test_repartition_85_15_la_nuit(self):
        night_price = pricing.compute_delivery_price(Decimal("5.68"), multiplier=NIGHT)  # 2400
        commission, net = pricing.split_night_surcharge(night_price, Decimal("5.68"), kind="delivery")
        self.assertEqual(commission + net, night_price)
        # La commission entreprise doit rester proche de 400 + 15% de la majoration
        self.assertGreater(commission, Decimal("400"))
        # Le coursier doit toucher la grande majorité de la majoration nuit
        day_price = pricing.compute_delivery_price(Decimal("5.68"), multiplier=DAY)
        surcharge = night_price - day_price
        courier_bonus = net - (day_price - Decimal("400"))
        self.assertAlmostEqual(float(courier_bonus / surcharge), 0.85, delta=0.05)


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
        # total = base + distance + frais + majoration éventuelle (peut inclure l'arrondi)
        self.assertEqual(
            q["base"] + q["distance_fee"] + q["service_fee"] + q["surcharge"], q["total"]
        )

    def test_multiplicateur_de_jour(self):
        from datetime import datetime, timezone as tz
        midi = datetime(2026, 7, 20, 12, 0, tzinfo=tz.utc)
        self.assertEqual(pricing.current_multiplier(midi), Decimal("1.00"))

    def test_multiplicateur_de_nuit(self):
        from datetime import datetime, timezone as tz
        minuit = datetime(2026, 7, 20, 23, 0, tzinfo=tz.utc)
        self.assertEqual(pricing.current_multiplier(minuit), Decimal("1.30"))

    def test_quote_ride(self):
        q = pricing.quote(DJELIBOUGOU, ZONE_INDUSTRIELLE, "ride")
        self.assertEqual(q["kind"], "ride")
        self.assertGreater(q["total"], 0)
