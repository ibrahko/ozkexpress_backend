from rest_framework import serializers
from django.utils import timezone
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
