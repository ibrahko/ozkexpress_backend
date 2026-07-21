"""
Tests des transitions de statut et des gains (livraisons et courses).
Nécessite la base de test PostGIS :
`manage.py test apps.services.tests.test_status_transitions`
"""
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase

from apps.accounts.models import User
from apps.couriers.models import Courier, CourierEarning
from apps.drivers.models import Driver, DriverEarning
from apps.services.models import (
    ServiceRequest, RideRequest, RequestStatus, RideStatus, CancellationReason,
)

PICKUP = Point(-7.9770, 12.6740, srid=4326)      # Djélibougou
DROPOFF = Point(-7.9720, 12.6350, srid=4326)     # Zone Industrielle


def make_courier(phone="+22371000001", plate="AB-1234-MD"):
    user = User.objects.create_user(phone=phone, user_type="courier")
    return Courier.objects.create(
        user=user,
        vehicle_brand="Yamaha",
        vehicle_model="YBR 125",
        vehicle_plate=plate,
        chassis_number=f"CH-{plate}",
    )


def make_driver(phone="+22372000001", plate="CD-5678-MD"):
    user = User.objects.create_user(phone=phone, user_type="driver")
    return Driver.objects.create(
        user=user,
        vehicle_brand="Honda",
        vehicle_model="CB 150",
        vehicle_plate=plate,
        chassis_number=f"CH-{plate}",
    )


def make_delivery(client, **kwargs):
    defaults = dict(
        client=client,
        pickup_address="Djélibougou",
        pickup_location=PICKUP,
        delivery_address="Zone Industrielle",
        delivery_location=DROPOFF,
        estimated_price=Decimal("2356"),
        distance_km=Decimal("5.68"),
    )
    defaults.update(kwargs)
    return ServiceRequest.objects.create(**defaults)


class DeliveryTransitionTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000010", user_type="client")
        self.courier = make_courier()
        self.request = make_delivery(self.client_user)

    def test_cycle_complet(self):
        self.request.accept(self.courier)
        self.assertEqual(self.request.status, RequestStatus.ACCEPTED)
        self.assertIsNotNone(self.request.accepted_at)

        self.request.mark_pickup()
        self.assertEqual(self.request.status, RequestStatus.PICKUP)

        self.request.mark_in_progress()
        self.assertEqual(self.request.status, RequestStatus.IN_PROGRESS)
        self.assertIsNotNone(self.request.picked_up_at)

        self.request.mark_delivered()
        self.assertEqual(self.request.status, RequestStatus.DELIVERED)
        self.assertIsNotNone(self.request.delivered_at)
        # Le prix final est figé sur le prix estimé
        self.assertEqual(self.request.final_price, Decimal("2356"))

    def test_gain_coursier_cree_et_idempotent(self):
        self.request.accept(self.courier)
        self.request.mark_delivered()

        earnings = CourierEarning.objects.filter(service_request=self.request)
        self.assertEqual(earnings.count(), 1)
        e = earnings.first()
        # Commission ≈ frais de service (220), net ≈ brut − commission.
        # Tolérance : save() recalcule la commission depuis le taux arrondi à 2 décimales.
        self.assertAlmostEqual(float(e.commission_amount), 220, delta=0.5)
        self.assertAlmostEqual(float(e.net_amount), 2136, delta=0.5)

        # Rejouer la livraison ne crée pas de doublon
        self.request._create_courier_earning()
        self.assertEqual(CourierEarning.objects.filter(service_request=self.request).count(), 1)

    def test_annulation_libere_le_coursier(self):
        self.request.accept(self.courier)
        self.request.cancel(reason=CancellationReason.CLIENT_REQUEST, note="Changement de plan")
        self.assertEqual(self.request.status, RequestStatus.CANCELLED)
        self.assertEqual(self.request.cancellation_reason, CancellationReason.CLIENT_REQUEST)
        self.assertIsNotNone(self.request.cancelled_at)
        self.courier.refresh_from_db()
        self.assertNotEqual(self.courier.status, "busy")


class RideTransitionTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000020", user_type="client")
        self.driver = make_driver()
        self.ride = RideRequest.objects.create(
            client=self.client_user,
            pickup_address="Djélibougou",
            pickup_location=PICKUP,
            dropoff_address="Zone Industrielle",
            dropoff_location=DROPOFF,
            estimated_price=Decimal("2356"),
            distance_km=Decimal("5.68"),
        )

    def test_cycle_complet_fige_le_prix(self):
        self.ride.accept(self.driver)
        self.assertEqual(self.ride.status, RideStatus.ACCEPTED)

        self.ride.start()
        self.assertEqual(self.ride.status, RideStatus.IN_PROGRESS)

        self.ride.complete()
        self.assertEqual(self.ride.status, RideStatus.COMPLETED)
        self.assertEqual(self.ride.final_price, Decimal("2356"))

    def test_gain_chauffeur_cree_et_idempotent(self):
        self.ride.accept(self.driver)
        self.ride.complete()

        earnings = DriverEarning.objects.filter(ride_request=self.ride)
        self.assertEqual(earnings.count(), 1)
        e = earnings.first()
        self.assertEqual(e.gross_amount, Decimal("2356"))
        # net = brut − commission (DriverEarning.save recalcule via le taux)
        self.assertAlmostEqual(float(e.net_amount), 2136, delta=1)

        self.ride._create_driver_earning()
        self.assertEqual(DriverEarning.objects.filter(ride_request=self.ride).count(), 1)
