from rest_framework import serializers
from .models import Vehicle, VehicleRental


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id", "vehicle_type", "brand", "model", "year", "color",
            "plate_number", "status", "daily_rate", "hourly_rate",
            "passenger_capacity", "description", "photo", "requires_driver",
        ]
        read_only_fields = ["id", "status"]


class VehicleRentalSerializer(serializers.ModelSerializer):
    vehicle_detail = VehicleSerializer(source="vehicle", read_only=True)
    client_name = serializers.CharField(source="client.get_full_name", read_only=True)
    duration_days = serializers.SerializerMethodField()

    class Meta:
        model = VehicleRental
        fields = [
            "id", "vehicle", "vehicle_detail", "client_name", "driver",
            "status", "with_driver", "start_date", "end_date",
            "pickup_location", "dropoff_location", "total_price",
            "deposit_amount", "client_notes", "duration_days", "created_at",
        ]
        read_only_fields = ["id", "status", "total_price", "created_at"]

    def get_duration_days(self, obj):
        if obj.start_date and obj.end_date:
            delta = obj.end_date - obj.start_date
            return max(1, delta.days)
        return None

    def validate(self, data):
        if data.get("start_date") and data.get("end_date"):
            if data["end_date"] <= data["start_date"]:
                raise serializers.ValidationError(
                    {"end_date": "La date de fin doit être après la date de début."}
                )
        return data

    def create(self, validated_data):
        validated_data["client"] = self.context["request"].user
        rental = super().create(validated_data)
        # Calcul automatique du prix
        if rental.start_date and rental.end_date and rental.vehicle:
            days = max(1, (rental.end_date - rental.start_date).days)
            rental.total_price = days * rental.vehicle.daily_rate
            rental.save(update_fields=["total_price"])
        return rental
