from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import BaseModel


class LocationHistory(BaseModel):
    """
    Historique des positions GPS d'un travailleur.
    Enregistré toutes les N secondes pendant une course active.
    """
    worker_user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="location_history"
    )
    location = gis_models.PointField(srid=4326)
    speed_kmh = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    heading = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    accuracy_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Lien optionnel vers la course/livraison en cours
    service_request = models.ForeignKey(
        "services.ServiceRequest", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="location_history"
    )
    ride_request = models.ForeignKey(
        "services.RideRequest", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="location_history"
    )

    class Meta:
        verbose_name = "Historique de position"
        verbose_name_plural = "Historiques de position"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["worker_user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.worker_user.get_full_name()} @ {self.created_at}"
