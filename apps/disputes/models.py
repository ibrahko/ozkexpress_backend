from django.db import models
from core.models import BaseModel


class DisputeReason(models.TextChoices):
    PACKAGE_DAMAGED = "package_damaged", "Colis endommagé"
    PACKAGE_LOST = "package_lost", "Colis perdu"
    WRONG_DELIVERY = "wrong_delivery", "Livraison au mauvais endroit"
    OVERCHARGE = "overcharge", "Surfacturation"
    COURIER_BEHAVIOR = "courier_behavior", "Comportement inapproprié du coursier"
    DRIVER_BEHAVIOR = "driver_behavior", "Comportement inapproprié du chauffeur"
    LATE_DELIVERY = "late_delivery", "Livraison en retard"
    OTHER = "other", "Autre"


class DisputeStatus(models.TextChoices):
    OPEN = "open", "Ouverte"
    UNDER_REVIEW = "under_review", "En cours d'examen"
    RESOLVED = "resolved", "Résolue"
    CLOSED = "closed", "Fermée"
    REJECTED = "rejected", "Rejetée"


class Dispute(BaseModel):
    """Litige ouvert par un client ou un travailleur."""
    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="disputes_opened"
    )
    assigned_to = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="disputes_assigned", limit_choices_to={"is_staff": True}
    )
    reason = models.CharField(max_length=30, choices=DisputeReason.choices)
    status = models.CharField(
        max_length=20, choices=DisputeStatus.choices, default=DisputeStatus.OPEN, db_index=True
    )
    description = models.TextField()
    resolution = models.TextField(blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Lien vers la commande concernée
    service_request = models.ForeignKey(
        "services.ServiceRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="disputes"
    )
    ride_request = models.ForeignKey(
        "services.RideRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="disputes"
    )

    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Litige"
        verbose_name_plural = "Litiges"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Litige #{str(self.id)[:8]} - {self.get_status_display()}"

    def resolve(self, resolution: str, refund_amount=None):
        from django.utils import timezone
        self.status = DisputeStatus.RESOLVED
        self.resolution = resolution
        self.refund_amount = refund_amount
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolution", "refund_amount", "resolved_at"])


class DisputeMessage(BaseModel):
    """Messages échangés dans un litige."""
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey("accounts.User", on_delete=models.CASCADE)
    content = models.TextField()
    attachment = models.FileField(upload_to="disputes/attachments/", null=True, blank=True)

    class Meta:
        verbose_name = "Message de litige"
        verbose_name_plural = "Messages de litige"
        ordering = ["created_at"]

    def __str__(self):
        return f"Message de {self.sender.get_full_name()} sur litige {str(self.dispute.id)[:8]}"
