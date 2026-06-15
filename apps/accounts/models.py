import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from .enums import UserType, UserStatus


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Le numéro de téléphone est obligatoire")
        extra_fields.setdefault("user_type", UserType.CLIENT)
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("user_type", UserType.ADMIN)
        extra_fields.setdefault("is_phone_verified", True)
        extra_fields.setdefault("status", UserStatus.ACTIVE)
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Utilisateur MotoExpress. L'authentification se fait par téléphone + OTP.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identité
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField(blank=True, null=True, unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    # Rôle et statut
    user_type = models.CharField(
        max_length=20, choices=UserType.choices, default=UserType.CLIENT, db_index=True
    )
    status = models.CharField(
        max_length=20, choices=UserStatus.choices, default=UserStatus.PENDING_VERIFICATION, db_index=True
    )

    # Vérification
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # Django requis
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    # Localisation (facultatif, pour le client)
    preferred_language = models.CharField(max_length=5, default="fr")
    push_token = models.TextField(blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.phone})"

    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.phone

    def get_short_name(self):
        return self.first_name or self.phone

    @property
    def is_courier(self):
        return self.user_type == UserType.COURIER

    @property
    def is_driver(self):
        return self.user_type == UserType.DRIVER

    @property
    def is_client(self):
        return self.user_type == UserType.CLIENT


class OTPCode(models.Model):
    """
    Code OTP à usage unique envoyé par SMS.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="otp_codes", null=True, blank=True
    )
    phone = models.CharField(max_length=20, db_index=True)
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Code OTP"
        verbose_name_plural = "Codes OTP"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone", "is_used", "expires_at"]),
        ]

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

    def consume(self):
        self.is_used = True
        self.save(update_fields=["is_used"])

    def __str__(self):
        return f"OTP {self.phone} - {'utilisé' if self.is_used else 'valide'}"


class UserAddress(models.Model):
    """Adresses sauvegardées d'un client."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50)  # Ex: "Maison", "Bureau"
    address = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Adresse"
        verbose_name_plural = "Adresses"
        ordering = ["-is_default", "-created_at"]

    def save(self, *args, **kwargs):
        # Une seule adresse par défaut par utilisateur
        if self.is_default:
            UserAddress.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.label}"
