from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from apps.workforce.models import BaseWorker
from core.models import BaseModel


class VehicleCategory(models.TextChoices):
    MOTO = "moto", "Moto-taxi"
    TRICYCLE = "tricycle", "Tricycle"
    CAR = "car", "Voiture"
    MINIBUS = "minibus", "Minibus"
    VAN = "van", "Van/Fourgonnette"


class DriverServiceType(models.TextChoices):
    CHAUFFEUR_ONLY = "chauffeur_only", "Chauffeur seul (client avec véhicule)"
    VEHICLE_WITH_DRIVER = "vehicle_with_driver", "Véhicule + Chauffeur (location avec chauffeur)"
    BOTH = "both", "Les deux"


class Driver(BaseWorker):
    """
    Chauffeur : transporte des personnes.
    Deux cas d'usage :
      1. Le client loue un véhicule de la flotte → le chauffeur accompagne
      2. Le client a son propre véhicule et a besoin d'un chauffeur
    """
    # Type de service proposé
    service_type = models.CharField(
        max_length=30,
        choices=DriverServiceType.choices,
        default=DriverServiceType.BOTH,
    )

    # Catégorie de véhicule que le chauffeur peut conduire
    vehicle_category = models.CharField(
        max_length=20,
        choices=VehicleCategory.choices,
        default=VehicleCategory.MOTO,
    )

    # Capacité passagers (si le chauffeur utilise son propre véhicule)
    passenger_capacity = models.PositiveSmallIntegerField(default=1)

    # Le véhicule appartient-il au chauffeur ou à la flotte ?
    owns_vehicle = models.BooleanField(
        default=False,
        help_text="True si le chauffeur possède son propre véhicule"
    )

    # Documents (GenericRelation pour requêtes inverses)
    documents = GenericRelation("workforce.WorkerDocument")

    class Meta:
        verbose_name = "Chauffeur"
        verbose_name_plural = "Chauffeurs"

    @property
    def can_drive_fleet_vehicle(self):
        """Le chauffeur peut-il conduire un véhicule de la flotte ?"""
        return self.service_type in (
            DriverServiceType.VEHICLE_WITH_DRIVER,
            DriverServiceType.BOTH,
        )

    @property
    def can_drive_client_vehicle(self):
        """Le chauffeur peut-il conduire le véhicule du client ?"""
        return self.service_type in (
            DriverServiceType.CHAUFFEUR_ONLY,
            DriverServiceType.BOTH,
        )


class DriverEarning(BaseModel):
    """Enregistrement de gains pour un chauffeur."""
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="earnings"
    )
    ride_request = models.ForeignKey(
        "services.RideRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_earning",
    )
    rental = models.ForeignKey(
        "fleet.VehicleRental",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_earning",
    )
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=20.00)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gain chauffeur"
        verbose_name_plural = "Gains chauffeurs"
        ordering = ["-earned_at"]

    def save(self, *args, **kwargs):
        self.commission_amount = self.gross_amount * (self.commission_rate / 100)
        self.net_amount = self.gross_amount - self.commission_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.driver} - {self.net_amount} FCFA"
