from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import ServiceRequest, RideRequest, RequestStatus, RideStatus, Message


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
    # P2 : infos coursier attendues par l'app mobile (suivi carte, appel, profil)
    courier_rating = serializers.SerializerMethodField()
    courier_phone = serializers.SerializerMethodField()
    courier_vehicle = serializers.SerializerMethodField()
    courier_location = serializers.SerializerMethodField()

    class Meta:
        model = ServiceRequest
        fields = [
            "id", "client_name", "courier", "courier_name",
            "courier_rating", "courier_phone", "courier_vehicle", "courier_location",
            "pickup_address", "pickup_location", "pickup_contact_name", "pickup_contact_phone", "pickup_instructions",
            "delivery_address", "delivery_location", "delivery_contact_name", "delivery_contact_phone", "delivery_instructions",
            "package_description", "package_size", "is_fragile", "estimated_weight_kg",
            "estimated_price", "final_price", "distance_km",
            "assignment_type", "broadcast_radius_km", "preferred_courier", "payment_method",
            "status", "status_display",
            "accepted_at", "picked_up_at", "delivered_at", "cancelled_at",
            "client_rating", "client_review", "created_at",
        ]
        read_only_fields = [
            "id", "status", "courier",
            # P1 : le tarif et la distance sont calculés côté serveur
            "estimated_price", "final_price", "distance_km",
            "accepted_at", "picked_up_at", "delivered_at", "cancelled_at", "created_at",
        ]

    def get_courier_name(self, obj):
        if obj.courier:
            return obj.courier.user.get_full_name()
        return None

    def get_courier_rating(self, obj):
        if obj.courier and obj.courier.rating is not None:
            return float(obj.courier.rating)
        return None

    def get_courier_phone(self, obj):
        return obj.courier.user.phone if obj.courier else None

    def get_courier_vehicle(self, obj):
        if not obj.courier:
            return None
        c = obj.courier
        parts = [
            c.vehicle_brand or None,
            c.vehicle_model or None,
            f"Plaque {c.vehicle_plate}" if c.vehicle_plate and not c.vehicle_plate.startswith("TMP-") else None,
            c.vehicle_color or None,
        ]
        label = " · ".join(p for p in parts if p)
        return label or None

    def get_courier_location(self, obj):
        loc = obj.courier.last_known_location if obj.courier else None
        if loc:
            return {"lat": loc.y, "lng": loc.x}
        return None

    def validate(self, data):
        # En attribution directe, le coursier choisi est obligatoire
        if data.get("assignment_type") == "direct" and not data.get("preferred_courier"):
            raise serializers.ValidationError(
                {"preferred_courier": "Requis en attribution directe."}
            )
        return data

    def create(self, validated_data):
        from .pricing import compute_distance_km, compute_delivery_price

        validated_data["client"] = self.context["request"].user
        # P1 : distance et tarif calculés côté serveur (source de vérité)
        pickup = validated_data.get("pickup_location")
        delivery = validated_data.get("delivery_location")
        if pickup and delivery:
            distance = compute_distance_km(pickup, delivery)
            validated_data["distance_km"] = distance
            validated_data["estimated_price"] = compute_delivery_price(distance)
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
    # P2 : infos chauffeur attendues par l'app mobile
    driver_rating = serializers.SerializerMethodField()
    driver_phone = serializers.SerializerMethodField()
    driver_vehicle = serializers.SerializerMethodField()
    driver_location = serializers.SerializerMethodField()

    class Meta:
        model = RideRequest
        fields = [
            "id", "client_name", "driver", "driver_name", "fleet_rental",
            "driver_rating", "driver_phone", "driver_vehicle", "driver_location",
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

    def get_driver_rating(self, obj):
        if obj.driver and obj.driver.rating is not None:
            return float(obj.driver.rating)
        return None

    def get_driver_phone(self, obj):
        return obj.driver.user.phone if obj.driver else None

    def get_driver_vehicle(self, obj):
        if not obj.driver:
            return None
        d = obj.driver
        parts = [
            d.vehicle_brand or None,
            d.vehicle_model or None,
            f"Plaque {d.vehicle_plate}" if d.vehicle_plate and not d.vehicle_plate.startswith("TMP-") else None,
            d.vehicle_color or None,
        ]
        label = " · ".join(p for p in parts if p)
        return label or None

    def get_driver_location(self, obj):
        loc = obj.driver.last_known_location if obj.driver else None
        if loc:
            return {"lat": loc.y, "lng": loc.x}
        return None

    def create(self, validated_data):
        validated_data["client"] = self.context["request"].user
        return super().create(validated_data)


class RatingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    review = serializers.CharField(required=False, allow_blank=True)


class MessageSerializer(serializers.ModelSerializer):
    """F3 : message du chat client ↔ coursier."""
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "sender_name", "body", "read_at", "created_at"]
        read_only_fields = ["id", "sender", "sender_name", "read_at", "created_at"]
