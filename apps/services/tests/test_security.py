"""
Tests des correctifs de sécurité sur le cycle de vie des commandes :
- machine à états (transitions interdites refusées),
- acceptation atomique (deux coursiers ne peuvent pas prendre la même commande),
- seules les personnes assignées font avancer une commande,
- portefeuille mis à jour à la livraison.
`manage.py test apps.services.tests.test_security`
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.payments.models import Wallet
from apps.services.models import (
    InvalidTransition, PaymentMethod, RequestStatus, RideRequest, RideStatus,
)
from apps.services.tests.test_status_transitions import (
    DROPOFF, PICKUP, make_courier, make_delivery, make_driver,
)


def deliver_fully(request, courier):
    request.accept(courier)
    request.mark_pickup()
    request.mark_in_progress()
    request.mark_delivered()


class DeliveryStateMachineTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000100", user_type="client")
        self.courier = make_courier()
        self.request = make_delivery(self.client_user)

    def test_livrer_une_commande_en_attente_est_refuse(self):
        with self.assertRaises(InvalidTransition):
            self.request.mark_delivered()
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.PENDING)

    def test_sauter_des_etapes_est_refuse(self):
        self.request.accept(self.courier)
        with self.assertRaises(InvalidTransition):
            self.request.mark_delivered()

    def test_livrer_deux_fois_est_refuse(self):
        deliver_fully(self.request, self.courier)
        with self.assertRaises(InvalidTransition):
            self.request.mark_delivered()

    def test_annuler_une_commande_livree_est_refuse(self):
        deliver_fully(self.request, self.courier)
        with self.assertRaises(InvalidTransition):
            self.request.cancel()

    def test_acceptation_concurrente_un_seul_gagnant(self):
        # Deux coursiers ont chargé la même commande « en attente »
        other = make_courier(phone="+22371000002", plate="EF-9012-MD")
        seen_by_first = type(self.request).objects.get(pk=self.request.pk)
        seen_by_second = type(self.request).objects.get(pk=self.request.pk)

        seen_by_first.accept(self.courier)
        with self.assertRaises(InvalidTransition):
            seen_by_second.accept(other)

        self.request.refresh_from_db()
        self.assertEqual(self.request.courier, self.courier)


class RideStateMachineTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000101", user_type="client")
        self.driver = make_driver()
        self.ride = RideRequest.objects.create(
            client=self.client_user,
            pickup_address="Djélibougou", pickup_location=PICKUP,
            dropoff_address="Zone Industrielle", dropoff_location=DROPOFF,
            estimated_price=Decimal("1925"), distance_km=Decimal("5.68"),
        )

    def test_terminer_sans_demarrer_est_refuse(self):
        self.ride.accept(self.driver)
        with self.assertRaises(InvalidTransition):
            self.ride.complete()

    def test_annuler_une_course_en_cours_est_refuse(self):
        self.ride.accept(self.driver)
        self.ride.start()
        with self.assertRaises(InvalidTransition):
            self.ride.cancel()
        self.assertEqual(RideRequest.objects.get(pk=self.ride.pk).status, RideStatus.IN_PROGRESS)


# Throttling DRF sans Redis local
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class AssignedWorkerApiTests(TestCase):
    """Un coursier ne peut faire avancer que les commandes qui lui sont assignées."""

    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000102", user_type="client")
        self.courier = make_courier()
        self.intruder = make_courier(phone="+22371000003", plate="GH-3456-MD")
        self.request = make_delivery(self.client_user)
        self.api = APIClient()

    def post(self, user, action):
        self.api.force_authenticate(user)
        return self.api.post(f"/api/v1/services/{self.request.pk}/{action}/")

    def test_un_autre_coursier_ne_peut_pas_livrer_une_commande_en_attente(self):
        response = self.post(self.intruder.user, "deliver")
        self.assertEqual(response.status_code, 403)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.PENDING)

    def test_un_autre_coursier_ne_peut_pas_toucher_une_commande_acceptee(self):
        self.request.accept(self.courier)
        response = self.post(self.intruder.user, "pickup")
        self.assertIn(response.status_code, (403, 404))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, RequestStatus.ACCEPTED)

    def test_cycle_complet_par_le_coursier_assigne_puis_double_livraison(self):
        self.assertEqual(self.post(self.courier.user, "accept").status_code, 200)
        self.assertEqual(self.post(self.courier.user, "pickup").status_code, 200)
        self.assertEqual(self.post(self.courier.user, "start").status_code, 200)
        self.assertEqual(self.post(self.courier.user, "deliver").status_code, 200)
        # Double appui sur « Livré » : refusé, pas de second gain
        self.assertEqual(self.post(self.courier.user, "deliver").status_code, 409)

    def test_deuxieme_acceptation_refusee(self):
        self.assertEqual(self.post(self.courier.user, "accept").status_code, 200)
        # La commande n'est plus « en attente » : elle disparaît pour les autres coursiers
        self.assertEqual(self.post(self.intruder.user, "accept").status_code, 404)
        self.request.refresh_from_db()
        self.assertEqual(self.request.courier, self.courier)


class WalletOnDeliveryTests(TestCase):
    """Prix de jour 1 925 F → commission 400 F, net 1 525 F (voir test_status_transitions)."""

    def setUp(self):
        self.client_user = User.objects.create_user(phone="+22370000103", user_type="client")
        self.courier = make_courier()

    def wallet(self, user):
        return Wallet.objects.get(user=user)

    def test_paiement_electronique_credite_le_net(self):
        request = make_delivery(self.client_user, payment_method=PaymentMethod.WAVE)
        deliver_fully(request, self.courier)
        wallet = self.wallet(self.courier.user)
        self.assertEqual(wallet.balance, Decimal("1525"))
        self.assertEqual(wallet.total_earned, Decimal("1525"))

    def test_especes_le_coursier_doit_la_commission(self):
        request = make_delivery(self.client_user, payment_method=PaymentMethod.CASH)
        deliver_fully(request, self.courier)
        wallet = self.wallet(self.courier.user)
        self.assertEqual(wallet.balance, Decimal("-400"))
        self.assertEqual(wallet.total_earned, Decimal("1525"))

    def test_deux_livraisons_se_cumulent(self):
        deliver_fully(make_delivery(self.client_user, payment_method=PaymentMethod.WAVE), self.courier)
        deliver_fully(make_delivery(self.client_user, payment_method=PaymentMethod.CASH), self.courier)
        self.assertEqual(self.wallet(self.courier.user).balance, Decimal("1125"))

    def test_course_chauffeur_en_especes(self):
        driver = make_driver()
        ride = RideRequest.objects.create(
            client=self.client_user,
            pickup_address="A", pickup_location=PICKUP,
            dropoff_address="B", dropoff_location=DROPOFF,
            estimated_price=Decimal("1925"), distance_km=Decimal("5.68"),
        )
        ride.accept(driver)
        ride.start()
        ride.complete()
        self.assertEqual(self.wallet(driver.user).balance, Decimal("-400"))

    def test_retrait_refuse_si_solde_insuffisant(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.courier.user)
        wallet.credit(Decimal("1000"))
        with self.assertRaises(ValueError):
            wallet.debit(Decimal("1500"))
        wallet.debit(Decimal("600"))
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("400"))
        self.assertEqual(wallet.total_withdrawn, Decimal("600"))
