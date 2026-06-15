from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import ServiceRequest, RideRequest, RequestStatus, RideStatus


class PointField(serializers.Field):
    """Sérialise/désérialise un Point GIS en {lat, lng}."""
    def to_representation(self, value):
        if value:
            return {"lat": value.y, "lng": value.x}
        return None

    def to_internal_value(self, data):
        try:
            return Point(float(data["lng"]), float(data["lat"]), srid=4326)
        except (KeyError, TypeError, ValueError):
            raise serializers.ValidationError("Format attendu: {lat: ..., lng: ...}")


class ServiceRequestSerializer(serializers.ModelSerializer):
    pickup_location = PointField()
    delivery_location = PointField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    client_name = serializers.CharField(source="client.get_full_name", read_only=True)
    courier_name = serializers.SerializerMethodField()
    courier_location = serializers.SerializerMethodField()
    courier_rating = serializers.SerializerMethodField()
    # Nouveaux champs (défensifs — fonctionnent avant et après migration)
    assignment_type = serializers.SerializerMethodField()
    broadcast_radius_km = serializers.SerializerMethodField()
    is_escalated = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "id", "client_name", "courier", "courier_name", "courier_location", "courier_rating",
            "assignment_type", "broadcast_radius_km", "is_escalated",
            "pickup_address", "pickup_location", "pickup_contact_name", "pickup_contact_phone", "pickup_instructions",
            "delivery_address", "delivery_location", "delivery_contact_name", "delivery_contact_phone", "delivery_instructions",
            "package_description", "package_size", "is_fragile", "estimated_weight_kg",
            "estimated_price", "final_price", "distance_km",
            "status", "status_display",
            "accepted_at", "picked_up_at", "delivered_at", "cancelled_at",
            "client_rating", "client_review", "created_at",
        ]
        read_only_fields = [
            "id", "status", "courier", "estimated_price", "final_price",
            "accepted_at", "picked_up_at", "delivered_at", "cancelled_at", "created_at",
        ]

    def get_courier_name(self, obj):
        if obj.courier:
            return obj.courier.user.get_full_name()
        return None

    def get_courier_location(self, obj):
        if obj.courier and obj.courier.last_known_location:
            loc = obj.courier.last_known_location
            return {"lat": loc.y, "lng": loc.x}
        return None

    def get_courier_rating(self, obj):
        if obj.courier:
            return float(obj.courier.rating)
        return None

    def get_assignment_type(self, obj):
        return getattr(obj, 'assignment_type', 'broadcast')

    def get_broadcast_radius_km(self, obj):
        return getattr(obj, 'broadcast_radius_km', 5)

    def get_is_escalated(self, obj):
        return getattr(obj, 'escalated_at', None) is not None

    def create(self, validated_data):
        validated_data["client"] = self.context["request"].user
        return super().create(validated_data)


class ServiceRequestStatusSerializer(serializers.ModelSerializer):
    """Serializer léger pour les mises à jour de statut."""
    class Meta:
        model = ServiceRequest
        fields = ["id", "status", "cancellation_reason", "cancellation_note"]
        read_only_fields = ["id", "status"]


class RideRequestSerializer(serializers.ModelSerializer):
    pickup_location = PointField()
    dropoff_location = PointField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    client_name = serializers.CharField(source="client.get_full_name", read_only=True)
    driver_name = serializers.SerializerMethodField()
    driver_location = serializers.SerializerMethodField()
    driver_rating = serializers.SerializerMethodField()

    class Meta:
        model = RideRequest
        fields = [
            "id", "client_name", "driver", "driver_name", "driver_location", "driver_rating", "fleet_rental",
            "pickup_address", "pickup_location",
            "dropoff_address", "dropoff_location",
            "passenger_count", "client_has_own_vehicle", "special_instructions",
            "estimated_price", "final_price", "distance_km", "duration_minutes",
            "status", "status_display",
            "accepted_at", "started_at", "completed_at", "cancelled_at",
            "client_rating", "client_review", "created_at",
        ]
        read_only_fields = [
            "id", "status", "driver", "estimated_price", "final_price",
            "accepted_at", "started_at", "completed_at", "cancelled_at", "created_at",
        ]

    def get_driver_name(self, obj):
        if obj.driver:
            return obj.driver.user.get_full_name()
        return None

    def get_driver_location(self, obj):
        if obj.driver and obj.driver.last_known_location:
            loc = obj.driver.last_known_location
            return {"lat": loc.y, "lng": loc.x}
        return None

    def get_driver_rating(self, obj):
        if obj.driver:
            return float(obj.driver.rating)
        return None

    def create(self, validated_data):
        validated_data["client"] = self.context["request"].user
        return super().create(validated_data)


class RatingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    review = serializers.CharField(required=False, allow_blank=True)
