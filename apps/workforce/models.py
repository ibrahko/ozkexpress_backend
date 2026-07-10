from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import BaseModel


class WorkerStatus(models.TextChoices):
    PENDING = "pending", "En attente de validation"
    ACTIVE = "active", "Actif"
    SUSPENDED = "suspended", "Suspendu"
    ONLINE = "online", "En ligne"
    OFFLINE = "offline", "Hors ligne"
    BUSY = "busy", "En course"


class VehicleType(models.TextChoices):
    MOTO = "moto", "Moto-taxi"
    TRICYCLE = "tricycle", "Tricycle (Katakatani)"
    CAR = "car", "Voiture"
    VAN = "van", "Van / Fourgonnette"


class DocumentType(models.TextChoices):
    NATIONAL_ID = "national_id", "Carte d'identité nationale"
    DRIVER_LICENSE = "driver_license", "Permis de conduire"
    VEHICLE_REGISTRATION = "vehicle_registration", "Carte grise"
    INSURANCE = "insurance", "Assurance véhicule"
    VIGNETTE = "vignette", "Vignette"
    TECHNICAL_VISIT = "technical_visit", "Visite technique"
    PHOTO = "photo", "Photo d'identité"


class BaseWorker(BaseModel):
    """
    Modèle abstrait commun aux coursiers et chauffeurs.
    Contient: profil, véhicule complet, GPS, notation, documents.
    """
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="%(class)s_profile",
    )
    status = models.CharField(
        max_length=20,
        choices=WorkerStatus.choices,
        default=WorkerStatus.PENDING,
        db_index=True,
    )

    # ── Véhicule ──────────────────────────────────────────────
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.MOTO,
        db_index=True,
    )
    vehicle_brand = models.CharField(max_length=100, help_text="Marque (ex: Yamaha, Honda, Bajaj)")
    vehicle_model = models.CharField(max_length=100, help_text="Modèle (ex: YBR 125, CB 150)")
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_color = models.CharField(max_length=50, blank=True)
    vehicle_plate = models.CharField(
        max_length=20, unique=True,
        help_text="Numéro de plaque d'immatriculation"
    )
    chassis_number = models.CharField(
        max_length=50, unique=True,
        help_text="Numéro de châssis (numéro sachis)"
    )

    # ── Documents réglementaires ───────────────────────────────
    insurance_expiry = models.DateField(
        null=True, blank=True,
        help_text="Date d'expiration de l'assurance"
    )
    vignette_expiry = models.DateField(
        null=True, blank=True,
        help_text="Date d'expiration de la vignette"
    )
    technical_visit_expiry = models.DateField(
        null=True, blank=True,
        help_text="Date d'expiration de la visite technique"
    )

    # ── Permis de conduire ────────────────────────────────────
    license_number = models.CharField(max_length=50, unique=True)

    # GPS temps réel
    last_known_location = gis_models.PointField(null=True, blank=True, srid=4326)
    last_location_update = models.DateTimeField(null=True, blank=True)

    # Statistiques
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00)
    total_trips = models.PositiveIntegerField(default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Disponibilité
    is_available = models.BooleanField(default=False, db_index=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["status", "is_available"]),
        ]

    def go_online(self):
        self.status = WorkerStatus.ONLINE
        self.is_available = True
        self.save(update_fields=["status", "is_available", "updated_at"])

    def go_offline(self):
        self.status = WorkerStatus.OFFLINE
        self.is_available = False
        self.save(update_fields=["status", "is_available", "updated_at"])

    def set_busy(self):
        self.status = WorkerStatus.BUSY
        self.is_available = False
        self.save(update_fields=["status", "is_available", "updated_at"])

    def set_available(self):
        self.status = WorkerStatus.ONLINE
        self.is_available = True
        self.save(update_fields=["status", "is_available", "updated_at"])

    def update_location(self, latitude: float, longitude: float):
        from django.utils import timezone
        from django.contrib.gis.geos import Point
        self.last_known_location = Point(longitude, latitude, srid=4326)
        self.last_location_update = timezone.now()
        self.save(update_fields=["last_known_location", "last_location_update", "updated_at"])

    def __str__(self):
        return f"{self.__class__.__name__} - {self.user.get_full_name()}"


class WorkerDocument(BaseModel):
    """
    Document uploadé par un travailleur (permis, CNI, carte grise...).
    Partagé entre Courier et Driver via content_type / object_id (GenericFK).
    """
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType

    content_type = models.ForeignKey(
        "contenttypes.ContentType", on_delete=models.CASCADE
    )
    object_id = models.UUIDField()
    # content_object défini dans chaque sous-classe via GenericRelation

    doc_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file = models.FileField(upload_to="worker_documents/")
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_documents",
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Document travailleur"
        verbose_name_plural = "Documents travailleurs"

    def verify(self, admin_user):
        from django.utils import timezone
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = admin_user
        self.save(update_fields=["is_verified", "verified_at", "verified_by"])

    def reject(self, reason: str):
        self.is_verified = False
        self.rejection_reason = reason
        self.save(update_fields=["is_verified", "rejection_reason"])

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.object_id}"
