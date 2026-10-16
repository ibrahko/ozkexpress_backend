from django.db import models
from django.contrib.gis.db import models as gis_models
from core.exceptions import BusinessLogicError
from core.models import BaseModel


class RequestStatus(models.TextChoices):
    PENDING = "pending", "En attente de coursier"
    ACCEPTED = "accepted", "Acceptée"
    PICKUP = "pickup", "En route vers le départ"
    IN_PROGRESS = "in_progress", "En cours"
    DELIVERED = "delivered", "Livrée"
    CANCELLED = "cancelled", "Annulée"
    FAILED = "failed", "Échouée"


class CancellationReason(models.TextChoices):
    CLIENT_REQUEST = "client_request", "Annulation client"
    COURIER_UNAVAILABLE = "courier_unavailable", "Coursier indisponible"
    ADDRESS_ISSUE = "address_issue", "Problème d'adresse"
    PAYMENT_FAILED = "payment_failed", "Paiement échoué"
    OTHER = "other", "Autre"


class AssignmentType(models.TextChoices):
    """Mode d'attribution de la demande (aligné sur l'app mobile)."""
    BROADCAST = "broadcast", "Diffusion aux coursiers proches"
    DIRECT = "direct", "Coursier choisi par le client"


class PaymentMethod(models.TextChoices):
    """Moyens de paiement proposés par l'app mobile (écran C3)."""
    CASH = "cash", "Espèces"
    ORANGE_MONEY = "orange_money", "Orange Money"
    MTN_MOMO = "mtn_momo", "MTN MoMo"
    WAVE = "wave", "Wave"
    STRIPE = "stripe", "Carte bancaire"


class InvalidTransition(BusinessLogicError):
    """Changement de statut interdit (ou déjà effectué par quelqu'un d'autre)."""
    status_code = 409
    default_code = "invalid_transition"


# Machines à états : statut courant → statuts atteignables
DELIVERY_TRANSITIONS = {
    RequestStatus.PENDING: {RequestStatus.ACCEPTED, RequestStatus.CANCELLED},
    RequestStatus.ACCEPTED: {RequestStatus.PICKUP, RequestStatus.CANCELLED},
    RequestStatus.PICKUP: {RequestStatus.IN_PROGRESS, RequestStatus.CANCELLED},
    RequestStatus.IN_PROGRESS: {RequestStatus.DELIVERED, RequestStatus.FAILED},
}


def _transition(instance, transitions, new_status, **fields):
    """
    Passe `instance` à `new_status` si la machine à états l'autorise.
    L'UPDATE est conditionné au statut lu (compare-and-set) : si une autre
    requête a modifié la commande entre-temps (deux coursiers qui acceptent
    en même temps, double appui sur « Livré »…), aucune ligne n'est mise à
    jour et InvalidTransition est levée — pas de verrou ni de double gain.
    """
    from django.utils import timezone

    current = instance.status
    if new_status not in transitions.get(current, set()):
        raise InvalidTransition(
            f"Transition impossible : {current} → {new_status}."
        )
    fields["updated_at"] = timezone.now()
    updated = type(instance).objects.filter(pk=instance.pk, status=current).update(
        status=new_status, **fields
    )
    if not updated:
        raise InvalidTransition("Cette commande a été modifiée entre-temps.")
    instance.status = new_status
    for name, value in fields.items():
        setattr(instance, name, value)


class ServiceRequest(BaseModel):
    """
    Demande de livraison de colis par un client à un coursier.
    """
    client = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="service_requests",
        limit_choices_to={"user_type": "client"},
    )
    courier = models.ForeignKey(
        "couriers.Courier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_requests",
    )

    # Départ
    pickup_address = models.TextField()
    pickup_location = gis_models.PointField(srid=4326)
    pickup_contact_name = models.CharField(max_length=100, blank=True)
    pickup_contact_phone = models.CharField(max_length=20, blank=True)
    pickup_instructions = models.TextField(blank=True)

    # Arrivée
    delivery_address = models.TextField()
    delivery_location = gis_models.PointField(srid=4326)
    delivery_contact_name = models.CharField(max_length=100, blank=True)
    delivery_contact_phone = models.CharField(max_length=20, blank=True)
    delivery_instructions = models.TextField(blank=True)

    # Colis
    package_description = models.TextField(blank=True)
    package_size = models.CharField(max_length=10, default="small")
    is_fragile = models.BooleanField(default=False)
    estimated_weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Tarification
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    tip_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Pourboire du client (100 % reversé au coursier)",
    )

    # Quartiers rattachés (statistiques : trajets les plus demandés)
    pickup_zone = models.ForeignKey(
        "services.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pickups_services",
    )
    delivery_zone = models.ForeignKey(
        "services.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deliveries_services",
    )

    # Attribution & paiement (envoyés par l'app mobile)
    assignment_type = models.CharField(
        max_length=10, choices=AssignmentType.choices, default=AssignmentType.BROADCAST
    )
    broadcast_radius_km = models.PositiveSmallIntegerField(default=5)
    preferred_courier = models.ForeignKey(
        "couriers.Courier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preferred_requests",
        help_text="Renseigné uniquement en attribution directe",
    )
    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )

    # Statut
    status = models.CharField(
        max_length=20, choices=RequestStatus.choices, default=RequestStatus.PENDING, db_index=True
    )
    cancellation_reason = models.CharField(
        max_length=30, choices=CancellationReason.choices, blank=True
    )
    cancellation_note = models.TextField(blank=True)

    # Timing
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Évaluation
    client_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    client_review = models.TextField(blank=True)

    class Meta:
        verbose_name = "Demande de livraison"
        verbose_name_plural = "Demandes de livraison"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["client", "status"]),
            models.Index(fields=["courier", "status"]),
        ]

    def __str__(self):
        return f"Livraison #{str(self.id)[:8]} - {self.get_status_display()}"

    def accept(self, courier):
        """Atomique : si deux coursiers acceptent en même temps, un seul gagne."""
        from django.utils import timezone
        _transition(
            self, DELIVERY_TRANSITIONS, RequestStatus.ACCEPTED,
            courier=courier, accepted_at=timezone.now(),
        )
        courier.set_busy()

    def mark_pickup(self):
        _transition(self, DELIVERY_TRANSITIONS, RequestStatus.PICKUP)

    def mark_in_progress(self):
        from django.utils import timezone
        _transition(
            self, DELIVERY_TRANSITIONS, RequestStatus.IN_PROGRESS,
            picked_up_at=timezone.now(),
        )

    def mark_delivered(self):
        from django.db import transaction
        from django.utils import timezone
        # P4 : figer le prix final (à défaut, le prix estimé)
        final_price = self.final_price if self.final_price is not None else self.estimated_price
        with transaction.atomic():
            _transition(
                self, DELIVERY_TRANSITIONS, RequestStatus.DELIVERED,
                delivered_at=timezone.now(), final_price=final_price,
            )
            if self.courier:
                self.courier.set_available()
                self.courier.total_trips = models.F("total_trips") + 1
                self.courier.save(update_fields=["total_trips"])
                self._create_courier_earning()

    def _create_courier_earning(self):
        """
        P4 : gain du coursier = prix − commission entreprise.
        Commission = frais de service (400 F) de jour ; la nuit, la majoration
        est en plus répartie 85 % coursier / 15 % entreprise (split_night_surcharge).
        Le portefeuille du coursier est mis à jour dans la foulée (voir Wallet.apply_earning).
        """
        from decimal import Decimal
        from apps.couriers.models import CourierEarning
        from apps.payments.models import Wallet
        from .pricing import split_night_surcharge

        if self.final_price is None or self.courier is None:
            return
        if CourierEarning.objects.filter(service_request=self).exists():
            return  # idempotent

        gross = Decimal(self.final_price)
        commission, _net = split_night_surcharge(gross, self.distance_km, kind="delivery")
        commission = min(commission, gross)
        rate = (commission / gross * Decimal("100")).quantize(Decimal("0.01")) if gross else Decimal("0.00")
        CourierEarning.objects.create(
            courier=self.courier,
            service_request=self,
            gross_amount=gross,
            commission_rate=rate,
            commission_amount=commission,
            net_amount=gross - commission,
        )
        Wallet.apply_earning(
            self.courier.user,
            net=gross - commission,
            commission=commission,
            paid_in_cash=self.payment_method == PaymentMethod.CASH,
        )

    def cancel(self, reason: str = CancellationReason.OTHER, note: str = ""):
        from django.utils import timezone
        _transition(
            self, DELIVERY_TRANSITIONS, RequestStatus.CANCELLED,
            cancellation_reason=reason, cancellation_note=note, cancelled_at=timezone.now(),
        )
        if self.courier:
            self.courier.set_available()


class RideStatus(models.TextChoices):
    PENDING = "pending", "En attente de chauffeur"
    ACCEPTED = "accepted", "Acceptée"
    DRIVER_ARRIVING = "driver_arriving", "Chauffeur en route"
    IN_PROGRESS = "in_progress", "Course en cours"
    COMPLETED = "completed", "Terminée"
    CANCELLED = "cancelled", "Annulée"


RIDE_TRANSITIONS = {
    RideStatus.PENDING: {RideStatus.ACCEPTED, RideStatus.CANCELLED},
    RideStatus.ACCEPTED: {RideStatus.DRIVER_ARRIVING, RideStatus.IN_PROGRESS, RideStatus.CANCELLED},
    RideStatus.DRIVER_ARRIVING: {RideStatus.IN_PROGRESS, RideStatus.CANCELLED},
    RideStatus.IN_PROGRESS: {RideStatus.COMPLETED},
}


class RideRequest(BaseModel):
    """
    Demande de course / transport de personnes par un chauffeur.
    Couvre deux cas :
      - client avec son véhicule qui veut un chauffeur
      - client qui loue un véhicule de la flotte avec chauffeur
    """
    client = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="ride_requests",
        limit_choices_to={"user_type": "client"},
    )
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ride_requests",
    )
    # Si location de véhicule de la flotte
    fleet_rental = models.ForeignKey(
        "fleet.VehicleRental",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ride_requests",
    )

    # Départ et destination
    pickup_address = models.TextField()
    pickup_location = gis_models.PointField(srid=4326)
    dropoff_address = models.TextField()
    dropoff_location = gis_models.PointField(srid=4326)

    # Infos course
    passenger_count = models.PositiveSmallIntegerField(default=1)
    client_has_own_vehicle = models.BooleanField(
        default=False,
        help_text="True si le client a son propre véhicule et cherche un chauffeur"
    )
    special_instructions = models.TextField(blank=True)

    # Tarification
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    tip_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Pourboire du client (100 % reversé au chauffeur)",
    )

    # Quartiers rattachés (statistiques)
    pickup_zone = models.ForeignKey(
        "services.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pickups_rides",
    )
    dropoff_zone = models.ForeignKey(
        "services.Zone", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dropoffs_rides",
    )

    # Statut
    status = models.CharField(
        max_length=20, choices=RideStatus.choices, default=RideStatus.PENDING, db_index=True
    )

    # Timing
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Évaluation
    client_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    client_review = models.TextField(blank=True)

    class Meta:
        verbose_name = "Demande de course"
        verbose_name_plural = "Demandes de course"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["client", "status"]),
            models.Index(fields=["driver", "status"]),
        ]

    def __str__(self):
        return f"Course #{str(self.id)[:8]} - {self.get_status_display()}"

    def accept(self, driver):
        """Atomique : si deux chauffeurs acceptent en même temps, un seul gagne."""
        from django.utils import timezone
        _transition(
            self, RIDE_TRANSITIONS, RideStatus.ACCEPTED,
            driver=driver, accepted_at=timezone.now(),
        )
        driver.set_busy()

    def start(self):
        from django.utils import timezone
        _transition(self, RIDE_TRANSITIONS, RideStatus.IN_PROGRESS, started_at=timezone.now())

    def complete(self):
        from django.db import transaction
        from django.utils import timezone
        # Figer le prix final (à défaut, le prix estimé) — aligné sur les livraisons
        final_price = self.final_price if self.final_price is not None else self.estimated_price
        with transaction.atomic():
            _transition(
                self, RIDE_TRANSITIONS, RideStatus.COMPLETED,
                completed_at=timezone.now(), final_price=final_price,
            )
            if self.driver:
                self.driver.set_available()
                self.driver.total_trips = models.F("total_trips") + 1
                self.driver.save(update_fields=["total_trips"])
                self._create_driver_earning()

    def cancel(self):
        _transition(self, RIDE_TRANSITIONS, RideStatus.CANCELLED)
        if self.driver:
            self.driver.set_available()

    def _create_driver_earning(self):
        """
        Gain du chauffeur = prix − commission entreprise (aligné sur les coursiers).
        Commission = frais de service (400 F) de jour ; la nuit, la majoration
        est en plus répartie 85 % chauffeur / 15 % entreprise (split_night_surcharge).
        """
        from decimal import Decimal
        from apps.drivers.models import DriverEarning
        from apps.payments.models import Wallet
        from .pricing import split_night_surcharge

        if self.final_price is None or self.driver is None:
            return
        if DriverEarning.objects.filter(ride_request=self).exists():
            return  # idempotent

        gross = Decimal(self.final_price)
        commission, _net = split_night_surcharge(gross, self.distance_km, kind="ride")
        commission = min(commission, gross)
        rate = (commission / gross * Decimal("100")).quantize(Decimal("0.01")) if gross else Decimal("0.00")
        DriverEarning.objects.create(
            driver=self.driver,
            ride_request=self,
            gross_amount=gross,
            commission_rate=rate,
            commission_amount=commission,
            net_amount=gross - commission,
        )
        # Les courses n'ont pas encore de moyen de paiement : le client paie le chauffeur en espèces
        Wallet.apply_earning(self.driver.user, net=gross - commission, commission=commission, paid_in_cash=True)


class Zone(BaseModel):
    """
    Quartier de Bamako avec son point central.
    Permet au client de choisir « Djélibougou → Zone Industrielle » sans GPS :
    le centre du quartier sert de coordonnées pour le calcul du prix (200 F/km).
    """
    name = models.CharField(max_length=100, unique=True)
    commune = models.CharField(max_length=50, blank=True)
    center = gis_models.PointField(srid=4326)
    # is_active hérité de BaseModel : quartier désactivable sans suppression

    class Meta:
        verbose_name = "Quartier"
        verbose_name_plural = "Quartiers"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.commune})" if self.commune else self.name


class ZoneDistance(BaseModel):
    """
    Distance routière réelle entre deux quartiers (saisie dans l'admin).
    Prioritaire sur le calcul haversine pour les paires fréquentes.
    La paire est symétrique : une seule entrée suffit (A→B vaut aussi B→A).
    """
    zone_from = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="distances_from")
    zone_to = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="distances_to")
    road_km = models.DecimalField(max_digits=6, decimal_places=2, help_text="Distance routière en km")

    class Meta:
        verbose_name = "Distance entre quartiers"
        verbose_name_plural = "Distances entre quartiers"
        constraints = [
            models.UniqueConstraint(fields=["zone_from", "zone_to"], name="unique_zone_pair"),
        ]

    def __str__(self):
        return f"{self.zone_from.name} → {self.zone_to.name} : {self.road_km} km"


class Message(BaseModel):
    """
    F3 : messagerie client ↔ coursier, liée à une demande de livraison.
    Accès limité au client et au coursier assigné (voir la vue `messages`).
    """
    service_request = models.ForeignKey(
        ServiceRequest, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="sent_messages"
    )
    body = models.TextField(max_length=2000)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ["created_at"]
        # Nom explicite : évite qu'un futur `makemigrations` ne détecte un
        # écart si l'algorithme de nommage auto de Django change de version.
        indexes = [
            models.Index(
                fields=["service_request", "created_at"], name="services_me_service_530197_idx"
            )
        ]

    def __str__(self):
        return f"Message de {self.sender_id} sur #{str(self.service_request_id)[:8]}"
