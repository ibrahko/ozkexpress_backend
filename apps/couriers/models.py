from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from apps.workforce.models import BaseWorker
from core.models import BaseModel


class PackageSize(models.TextChoices):
    SMALL = "small", "Petit (< 5kg)"
    MEDIUM = "medium", "Moyen (5-20kg)"
    LARGE = "large", "Grand (20-50kg)"
    EXTRA_LARGE = "xl", "Très grand (> 50kg)"


class Courier(BaseWorker):
    """
    Coursier moto-taxi : propriétaire de sa moto, livre des colis.
    """
    # Spécifique coursier
    max_package_size = models.CharField(
        max_length=10,
        choices=PackageSize.choices,
        default=PackageSize.MEDIUM,
    )
    accepts_fragile = models.BooleanField(default=True)
    accepts_documents = models.BooleanField(default=True)
    delivery_zone_radius_km = models.PositiveSmallIntegerField(
        default=10,
        help_text="Rayon max de livraison en km depuis la position actuelle"
    )

    # Zone de service (ville/quartier)
    service_area = models.CharField(max_length=100, blank=True)

    # Documents (GenericRelation pour requêtes inverses)
    documents = GenericRelation("workforce.WorkerDocument")

    class Meta:
        verbose_name = "Coursier"
        verbose_name_plural = "Coursiers"

    @property
    def can_accept_delivery(self):
        return self.is_available and self.status == "online"


class CourierEarning(BaseModel):
    """Enregistrement de gains pour un coursier."""
    courier = models.ForeignKey(
        Courier, on_delete=models.CASCADE, related_name="earnings"
    )
    service_request = models.ForeignKey(
        "services.ServiceRequest",
        on_delete=models.SET_NULL,
        null=True,
        related_name="courier_earning",
    )
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=15.00)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gain coursier"
        verbose_name_plural = "Gains coursiers"
        ordering = ["-earned_at"]

    def save(self, *args, **kwargs):
        self.commission_amount = self.gross_amount * (self.commission_rate / 100)
        self.net_amount = self.gross_amount - self.commission_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.courier} - {self.net_amount} FCFA"
