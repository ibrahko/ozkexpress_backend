from django.db import models
from core.models import BaseModel


class PaymentProvider(models.TextChoices):
    STRIPE = "stripe", "Stripe (Carte bancaire)"
    ORANGE_MONEY = "orange_money", "Orange Money"
    WAVE = "wave", "Wave"
    CASH = "cash", "Espèces"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    PROCESSING = "processing", "En cours"
    COMPLETED = "completed", "Complété"
    FAILED = "failed", "Échoué"
    REFUNDED = "refunded", "Remboursé"
    CANCELLED = "cancelled", "Annulé"


class PaymentType(models.TextChoices):
    SERVICE_DELIVERY = "service_delivery", "Livraison de colis"
    RIDE = "ride", "Course / Transport"
    RENTAL = "rental", "Location de véhicule"
    DEPOSIT = "deposit", "Caution"


class Transaction(BaseModel):
    """Enregistrement de chaque transaction financière."""
    client = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="transactions"
    )
    provider = models.CharField(max_length=20, choices=PaymentProvider.choices, db_index=True)
    payment_type = models.CharField(max_length=30, choices=PaymentType.choices)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default="XOF")

    # Référence interne
    reference = models.CharField(max_length=100, unique=True, db_index=True)

    # Référence externe (retournée par le provider)
    provider_transaction_id = models.CharField(max_length=200, blank=True)
    provider_response = models.JSONField(null=True, blank=True)

    # Lien vers la commande
    service_request = models.OneToOneField(
        "services.ServiceRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transaction"
    )
    ride_request = models.OneToOneField(
        "services.RideRequest", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transaction"
    )
    rental = models.OneToOneField(
        "fleet.VehicleRental", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="transaction"
    )

    # Timing
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    # Numéro de téléphone utilisé pour Mobile Money
    phone_number = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "status"]),
            models.Index(fields=["provider", "status"]),
        ]

    def __str__(self):
        return f"{self.reference} - {self.amount} {self.currency} ({self.get_status_display()})"

    def mark_completed(self, provider_tx_id: str = "", response: dict = None):
        from django.utils import timezone
        self.status = PaymentStatus.COMPLETED
        self.provider_transaction_id = provider_tx_id
        self.provider_response = response or {}
        self.completed_at = timezone.now()
        self.save(update_fields=[
            "status", "provider_transaction_id", "provider_response", "completed_at"
        ])

    def mark_failed(self, reason: str = ""):
        from django.utils import timezone
        self.status = PaymentStatus.FAILED
        self.failure_reason = reason
        self.failed_at = timezone.now()
        self.save(update_fields=["status", "failure_reason", "failed_at"])


class Wallet(BaseModel):
    """Portefeuille interne de chaque travailleur (coursier ou chauffeur)."""
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=5, default="XOF")

    class Meta:
        verbose_name = "Portefeuille"

    def __str__(self):
        return f"Wallet {self.user.get_full_name()} — {self.balance} {self.currency}"

    def credit(self, amount):
        self.balance += amount
        self.total_earned += amount
        self.save(update_fields=["balance", "total_earned", "updated_at"])

    def debit(self, amount):
        if amount > self.balance:
            raise ValueError("Solde insuffisant.")
        self.balance -= amount
        self.total_withdrawn += amount
        self.save(update_fields=["balance", "total_withdrawn", "updated_at"])


class WithdrawalRequest(BaseModel):
    """Demande de retrait de gains par un travailleur."""

    class WithdrawalStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Rejetée"
        PAID = "paid", "Payée"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=20, choices=PaymentProvider.choices)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20, choices=WithdrawalStatus.choices, default=WithdrawalStatus.PENDING
    )
    admin_note = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Demande de retrait"
        verbose_name_plural = "Demandes de retrait"
        ordering = ["-created_at"]
