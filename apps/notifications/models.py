from django.db import models
from core.models import BaseModel


class NotificationType(models.TextChoices):
    SERVICE_ACCEPTED = "service_accepted", "Livraison acceptée"
    SERVICE_PICKUP = "service_pickup", "Coursier en route"
    SERVICE_IN_PROGRESS = "service_in_progress", "Livraison en cours"
    SERVICE_DELIVERED = "service_delivered", "Livraison effectuée"
    SERVICE_CANCELLED = "service_cancelled", "Livraison annulée"
    RIDE_ACCEPTED = "ride_accepted", "Course acceptée"
    RIDE_DRIVER_ARRIVING = "ride_driver_arriving", "Chauffeur en route"
    RIDE_STARTED = "ride_started", "Course démarrée"
    RIDE_COMPLETED = "ride_completed", "Course terminée"
    PAYMENT_SUCCESS = "payment_success", "Paiement réussi"
    PAYMENT_FAILED = "payment_failed", "Paiement échoué"
    NEW_REQUEST_NEARBY = "new_request_nearby", "Nouvelle demande à proximité"
    DISPUTE_UPDATE = "dispute_update", "Mise à jour litige"
    SYSTEM = "system", "Notification système"


class Notification(BaseModel):
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    data = models.JSONField(null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_push = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"])]

    def mark_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"{self.title} → {self.recipient.get_full_name()}"
