from django.db import models
from django.contrib.gis.db import models as gis_models
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
        from django.utils import timezone
        self.courier = courier
        self.status = RequestStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=["courier", "status", "accepted_at", "updated_at"])
        courier.set_busy()

    def mark_pickup(self):
        self.status = RequestStatus.PICKUP
        self.save(update_fields=["status", "updated_at"])

    def mark_in_progress(self):
        from django.utils import timezone
        self.status = RequestStatus.IN_PROGRESS
        self.picked_up_at = timezone.now()
        self.save(update_fields=["status", "picked_up_at", "updated_at"])

    def mark_delivered(self):
        from django.utils import timezone
        self.status = RequestStatus.DELIVERED
        self.delivered_at = timezone.now()
        # P4 : figer le prix final (à défaut, le prix estimé)
        if self.final_price is None and self.estimated_price is not None:
            self.final_price = self.estimated_price
        self.save(update_fields=["status", "delivered_at", "final_price", "updated_at"])
        if self.courier:
            self.courier.set_available()
            self.courier.total_trips = models.F("total_trips") + 1
            self.courier.save(update_fields=["total_trips"])
            self._create_courier_earning()

    def _create_courier_earning(self):
        """P4 : gain du coursier = prix − frais de service (aligné sur l'app mobile)."""
        from decimal import Decimal
        from apps.couriers.models import CourierEarning
        from .pricing import SERVICE_FEE

        if self.final_price is None or self.courier is None:
            return
        if CourierEarning.objects.filter(service_request=self).exists():
            return  # idempotent

        gross = Decimal(self.final_price)
        commission = min(SERVICE_FEE, gross)
        rate = (commission / gross * Decimal("100")).quantize(Decimal("0.01")) if gross else Decimal("0.00")
        CourierEarning.objects.create(
            courier=self.courier,
            service_request=self,
            gross_amount=gross,
            commission_rate=rate,
            commission_amount=commission,
            net_amount=gross - commission,
        )

    def cancel(self, reason: str = CancellationReason.OTHER, note: str = ""):
        from django.utils import timezone
        self.status = RequestStatus.CANCELLED
        self.cancellation_reason = reason
        self.cancellation_note = note
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancellation_reason", "cancellation_note", "cancelled_at", "updated_at"])
        if self.courier:
            self.courier.set_available()


class RideStatus(models.TextChoices):
    PENDING = "pending", "En attente de chauffeur"
    ACCEPTED = "accepted", "Acceptée"
    DRIVER_ARRIVING = "driver_arriving", "Chauffeur en route"
    IN_PROGRESS = "in_progress", "Course en cours"
    COMPLETED = "completed", "Terminée"
    CANCELLED = "cancelled", "Annulée"


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
        from django.utils import timezone
        self.driver = driver
        self.status = RideStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=["driver", "status", "accepted_at", "updated_at"])
        driver.set_busy()

    def start(self):
        from django.utils import timezone
        self.status = RideStatus.IN_PROGRESS
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at", "updated_at"])

    def complete(self):
        from django.utils import timezone
        self.status = RideStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])
        if self.driver:
            self.driver.set_available()
            self.driver.total_trips = models.F("total_trips") + 1
            self.driver.save(update_fields=["total_trips"])


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
        indexes = [models.Index(fields=["service_request", "created_at"])]

    def __str__(self):
        return f"Message de {self.sender_id} sur #{str(self.service_request_id)[:8]}"
