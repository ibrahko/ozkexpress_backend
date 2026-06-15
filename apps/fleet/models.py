from django.db import models
from core.models import BaseModel


class VehicleType(models.TextChoices):
    MOTO = "moto", "Moto"
    TRICYCLE = "tricycle", "Tricycle"
    CAR = "car", "Voiture"
    MINIBUS = "minibus", "Minibus"
    VAN = "van", "Van"


class VehicleStatus(models.TextChoices):
    AVAILABLE = "available", "Disponible"
    RENTED = "rented", "En location"
    MAINTENANCE = "maintenance", "En maintenance"
    INACTIVE = "inactive", "Inactif"


class RentalStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    CONFIRMED = "confirmed", "Confirmée"
    ACTIVE = "active", "En cours"
    COMPLETED = "completed", "Terminée"
    CANCELLED = "cancelled", "Annulée"


class Vehicle(BaseModel):
    """Véhicule appartenant à la flotte MotoExpress."""
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, db_index=True)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()
    color = models.CharField(max_length=50)
    plate_number = models.CharField(max_length=20, unique=True)
    chassis_number = models.CharField(max_length=50, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=VehicleStatus.choices, default=VehicleStatus.AVAILABLE, db_index=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    passenger_capacity = models.PositiveSmallIntegerField(default=1)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="fleet/vehicles/", null=True, blank=True)
    requires_driver = models.BooleanField(default=False)
    mileage_km = models.PositiveIntegerField(default=0)
    last_maintenance_date = models.DateField(null=True, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    registration_expiry = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"
        ordering = ["vehicle_type", "brand"]

    def __str__(self):
        return f"{self.brand} {self.model} ({self.plate_number})"

    def mark_rented(self):
        self.status = VehicleStatus.RENTED
        self.save(update_fields=["status", "updated_at"])

    def mark_available(self):
        self.status = VehicleStatus.AVAILABLE
        self.save(update_fields=["status", "updated_at"])


class VehicleRental(BaseModel):
    """Location d'un véhicule de la flotte par un client."""
    client = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="rentals")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="rentals")
    driver = models.ForeignKey(
        "drivers.Driver", on_delete=models.SET_NULL, null=True, blank=True, related_name="rentals",
        help_text="Optionnel: chauffeur assigné pour conduire le véhicule loué"
    )
    status = models.CharField(max_length=20, choices=RentalStatus.choices, default=RentalStatus.PENDING, db_index=True)
    with_driver = models.BooleanField(default=False)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    actual_end_date = models.DateTimeField(null=True, blank=True)
    pickup_location = models.TextField(blank=True)
    dropoff_location = models.TextField(blank=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_returned = models.BooleanField(default=False)
    client_notes = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Location de véhicule"
        verbose_name_plural = "Locations de véhicules"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "start_date"])]

    def __str__(self):
        return f"Location {self.vehicle} par {self.client.get_full_name()}"

    def confirm(self):
        self.status = RentalStatus.CONFIRMED
        self.vehicle.mark_rented()
        self.save(update_fields=["status", "updated_at"])

    def start(self):
        self.status = RentalStatus.ACTIVE
        self.save(update_fields=["status", "updated_at"])

    def complete(self):
        from django.utils import timezone
        self.status = RentalStatus.COMPLETED
        self.actual_end_date = timezone.now()
        self.vehicle.mark_available()
        self.save(update_fields=["status", "actual_end_date", "updated_at"])

    def cancel(self):
        self.status = RentalStatus.CANCELLED
        if self.vehicle.status == VehicleStatus.RENTED:
            self.vehicle.mark_available()
        self.save(update_fields=["status", "updated_at"])
