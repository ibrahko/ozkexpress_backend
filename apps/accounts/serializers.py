from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import random
from .models import User, OTPCode, UserAddress
from .enums import UserType


class PhoneSerializer(serializers.Serializer):
    """Demande d'envoi d'OTP."""
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        # Normaliser le format (garder seulement chiffres et +)
        cleaned = "".join(c for c in value if c.isdigit() or c == "+")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Numéro de téléphone invalide.")
        return cleaned


class OTPVerifySerializer(serializers.Serializer):
    """Vérification du code OTP."""
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6, min_length=4)
    user_type = serializers.ChoiceField(
        choices=UserType.choices, default=UserType.CLIENT
    )

    def validate(self, data):
        phone = data["phone"]
        code = data["code"]

        otp = (
            OTPCode.objects.filter(phone=phone, code=code, is_used=False)
            .order_by("-created_at")
            .first()
        )

        if not otp or not otp.is_valid():
            raise serializers.ValidationError(
                {"code": "Code OTP invalide ou expiré."}
            )

        data["otp"] = otp
        return data


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "first_name", "last_name", "full_name",
            "avatar", "user_type", "status", "is_phone_verified",
            "preferred_language", "created_at",
        ]
        read_only_fields = ["id", "phone", "user_type", "status", "is_phone_verified", "created_at"]


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "avatar", "preferred_language", "push_token"]

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = ["id", "label", "address", "latitude", "longitude", "is_default", "created_at"]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class TokenResponseSerializer(serializers.Serializer):
    """Réponse après authentification réussie."""
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()
    is_new_user = serializers.BooleanField()


# ── Authentification par mot de passe ─────────────────────────────────────────

class PasswordLoginSerializer(serializers.Serializer):
    """
    Connexion coursier / chauffeur : téléphone + mot de passe.
    Le mot de passe par défaut est le numéro de téléphone lui-même.
    """
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        cleaned = "".join(c for c in value if c.isdigit() or c == "+")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Numéro de téléphone invalide.")
        return cleaned

    def validate(self, data):
        from django.contrib.auth import authenticate
        user = authenticate(username=data["phone"], password=data["password"])
        if not user:
            raise serializers.ValidationError(
                {"detail": "Téléphone ou mot de passe incorrect."}
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Ce compte est désactivé."}
            )
        data["user"] = user
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Changement de mot de passe (courant + nouveau)."""
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Les mots de passe ne correspondent pas."}
            )
        return data

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value


# ── Inscription coursier ───────────────────────────────────────────────────────

class CourierVehicleSerializer(serializers.Serializer):
    """Informations véhicule d'un coursier lors de l'inscription."""
    vehicle_type     = serializers.ChoiceField(choices=[
        ("moto", "Moto-taxi"),
        ("tricycle", "Tricycle (Katakatani)"),
        ("car", "Voiture"),
        ("van", "Van / Fourgonnette"),
    ])
    vehicle_brand    = serializers.CharField(max_length=100, help_text="Marque (Yamaha, Honda…)")
    vehicle_model    = serializers.CharField(max_length=100, help_text="Modèle (YBR 125…)")
    vehicle_year     = serializers.IntegerField(min_value=1990, max_value=2030, required=False)
    vehicle_color    = serializers.CharField(max_length=50, required=False, default="")
    vehicle_plate    = serializers.CharField(max_length=20, help_text="Numéro de plaque")
    chassis_number   = serializers.CharField(max_length=50, help_text="Numéro de châssis (sachis)")
    license_number   = serializers.CharField(max_length=50, help_text="Numéro du permis de conduire")
    insurance_expiry       = serializers.DateField(required=False, allow_null=True)
    vignette_expiry        = serializers.DateField(required=False, allow_null=True)
    technical_visit_expiry = serializers.DateField(required=False, allow_null=True)

    def validate_vehicle_plate(self, value):
        from apps.couriers.models import Courier
        from apps.drivers.models import Driver
        if Courier.objects.filter(vehicle_plate=value).exists() or \
           Driver.objects.filter(vehicle_plate=value).exists():
            raise serializers.ValidationError("Ce numéro de plaque est déjà enregistré.")
        return value.upper()

    def validate_chassis_number(self, value):
        from apps.couriers.models import Courier
        from apps.drivers.models import Driver
        if Courier.objects.filter(chassis_number=value).exists() or \
           Driver.objects.filter(chassis_number=value).exists():
            raise serializers.ValidationError("Ce numéro de châssis est déjà enregistré.")
        return value.upper()


class CourierRegisterSerializer(serializers.Serializer):
    """
    Inscription complète d'un coursier.
    Crée un User (mot de passe = numéro de téléphone par défaut)
    et un profil Courier avec toutes les infos véhicule.
    """
    # Infos personnelles
    phone      = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100)
    last_name  = serializers.CharField(max_length=100)

    # Véhicule
    vehicle    = CourierVehicleSerializer()

    # Options coursier
    max_package_size      = serializers.ChoiceField(
        choices=[("small","Petit"),("medium","Moyen"),("large","Grand"),("xl","Très grand")],
        default="medium", required=False,
    )
    accepts_fragile   = serializers.BooleanField(default=True, required=False)
    accepts_documents = serializers.BooleanField(default=True, required=False)
    delivery_zone_radius_km = serializers.IntegerField(default=10, min_value=1, required=False)

    def validate_phone(self, value):
        cleaned = "".join(c for c in value if c.isdigit() or c == "+")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Numéro de téléphone invalide.")
        if User.objects.filter(phone=cleaned).exists():
            raise serializers.ValidationError("Ce numéro est déjà associé à un compte.")
        return cleaned

    @transaction.atomic
    def create(self, validated_data):
        vehicle_data = validated_data.pop("vehicle")
        phone = validated_data["phone"]

        # Créer l'utilisateur — mot de passe par défaut = numéro de téléphone
        user = User.objects.create_user(
            phone=phone,
            password=phone,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            user_type=UserType.COURIER,
            is_phone_verified=False,
            status="pending",
        )

        # Créer le profil coursier
        from apps.couriers.models import Courier
        Courier.objects.create(
            user=user,
            **vehicle_data,
            max_package_size=validated_data.get("max_package_size", "medium"),
            accepts_fragile=validated_data.get("accepts_fragile", True),
            accepts_documents=validated_data.get("accepts_documents", True),
            delivery_zone_radius_km=validated_data.get("delivery_zone_radius_km", 10),
        )
        return user


class DriverRegisterSerializer(serializers.Serializer):
    """
    Inscription complète d'un chauffeur.
    Même logique que le coursier, mot de passe = numéro de téléphone par défaut.
    """
    phone      = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100)
    last_name  = serializers.CharField(max_length=100)

    # Véhicule (même champs)
    vehicle    = CourierVehicleSerializer()

    # Options chauffeur
    service_type = serializers.ChoiceField(
        choices=[
            ("chauffeur_only", "Chauffeur seul"),
            ("vehicle_with_driver", "Véhicule + Chauffeur"),
            ("both", "Les deux"),
        ],
        default="both", required=False,
    )
    passenger_capacity = serializers.IntegerField(default=1, min_value=1, required=False)
    owns_vehicle = serializers.BooleanField(default=True, required=False)

    def validate_phone(self, value):
        cleaned = "".join(c for c in value if c.isdigit() or c == "+")
        if len(cleaned) < 8:
            raise serializers.ValidationError("Numéro de téléphone invalide.")
        if User.objects.filter(phone=cleaned).exists():
            raise serializers.ValidationError("Ce numéro est déjà associé à un compte.")
        return cleaned

    @transaction.atomic
    def create(self, validated_data):
        vehicle_data = validated_data.pop("vehicle")
        phone = validated_data["phone"]

        user = User.objects.create_user(
            phone=phone,
            password=phone,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            user_type=UserType.DRIVER,
            is_phone_verified=False,
            status="pending",
        )

        from apps.drivers.models import Driver
        Driver.objects.create(
            user=user,
            **vehicle_data,
            service_type=validated_data.get("service_type", "both"),
            passenger_capacity=validated_data.get("passenger_capacity", 1),
            owns_vehicle=validated_data.get("owns_vehicle", True),
        )
        return user
