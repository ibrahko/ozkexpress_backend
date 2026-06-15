from rest_framework import serializers
from .models import Transaction, Wallet, WithdrawalRequest, PaymentProvider


class TransactionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    provider_display = serializers.CharField(source="get_provider_display", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "reference", "provider", "provider_display", "payment_type",
            "status", "status_display", "amount", "currency",
            "phone_number", "initiated_at", "completed_at",
        ]
        read_only_fields = fields


class InitiatePaymentSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=PaymentProvider.choices)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    service_request_id = serializers.UUIDField(required=False)
    ride_request_id = serializers.UUIDField(required=False)
    rental_id = serializers.UUIDField(required=False)

    def validate(self, data):
        count = sum([
            bool(data.get("service_request_id")),
            bool(data.get("ride_request_id")),
            bool(data.get("rental_id")),
        ])
        if count != 1:
            raise serializers.ValidationError(
                "Exactly one of service_request_id, ride_request_id, rental_id is required."
            )
        if data["provider"] in (PaymentProvider.ORANGE_MONEY, PaymentProvider.WAVE):
            if not data.get("phone_number"):
                raise serializers.ValidationError(
                    {"phone_number": "Numéro requis pour Mobile Money."}
                )
        return data


class WalletSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "user_name", "balance", "total_earned", "total_withdrawn", "currency"]
        read_only_fields = fields


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = ["id", "amount", "provider", "phone_number", "status", "status_display", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def validate_amount(self, value):
        user = self.context["request"].user
        try:
            wallet = user.wallet
        except Exception:
            raise serializers.ValidationError("Portefeuille introuvable.")
        if value > wallet.balance:
            raise serializers.ValidationError(
                f"Solde insuffisant. Disponible: {wallet.balance}"
            )
        return value

    def create(self, validated_data):
        validated_data["wallet"] = self.context["request"].user.wallet
        return super().create(validated_data)
