from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.permissions import IsCourier, IsAdminUser
from .models import Courier, CourierEarning, FavoriteCourier


class CourierSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    avatar = serializers.ImageField(source="user.avatar", read_only=True)

    class Meta:
        model = Courier
        fields = [
            "id", "user_name", "phone", "avatar",
            "status", "vehicle_plate", "vehicle_model", "vehicle_year", "vehicle_color",
            "license_number", "max_package_size", "accepts_fragile", "accepts_documents",
            "delivery_zone_radius_km", "service_area",
            "rating", "total_trips", "is_available", "last_location_update",
        ]
        read_only_fields = ["id", "rating", "total_trips", "last_location_update"]


class CourierEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourierEarning
        fields = ["id", "gross_amount", "commission_rate", "commission_amount", "net_amount", "earned_at"]
        read_only_fields = fields


class CourierViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return CourierSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Courier.objects.select_related("user").all()
        return Courier.objects.filter(user=user)

    @action(detail=False, methods=["get", "patch"], permission_classes=[IsCourier])
    def me(self, request):
        courier = request.user.courier_profile
        if request.method == "PATCH":
            serializer = CourierSerializer(courier, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(CourierSerializer(courier).data)

    @action(detail=False, methods=["post"], permission_classes=[IsCourier])
    def go_online(self, request):
        request.user.courier_profile.go_online()
        return Response({"detail": "Vous êtes maintenant en ligne."})

    @action(detail=False, methods=["post"], permission_classes=[IsCourier])
    def go_offline(self, request):
        request.user.courier_profile.go_offline()
        return Response({"detail": "Vous êtes maintenant hors ligne."})

    @action(detail=False, methods=["get"], permission_classes=[IsCourier])
    def earnings(self, request):
        earnings = CourierEarning.objects.filter(courier__user=request.user)
        serializer = CourierEarningSerializer(earnings, many=True)
        total = sum(e.net_amount for e in earnings)
        return Response({"results": serializer.data, "total_net": total})


# ── E4 : Coursiers favoris (API consommée par l'app mobile) ─────────────

class FavoriteCourierSerializer(serializers.ModelSerializer):
    """Forme alignée sur le type FavoriteCourier du mobile (src/utils/favorites.ts)."""
    courier_id = serializers.UUIDField(source="courier.id", read_only=True)
    name = serializers.CharField(source="courier.user.get_full_name", read_only=True)
    phone = serializers.CharField(source="courier.user.phone", read_only=True)
    rating = serializers.FloatField(source="courier.rating", read_only=True)
    vehicle = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteCourier
        fields = ["id", "courier_id", "name", "phone", "rating", "vehicle", "created_at"]
        read_only_fields = fields

    def get_vehicle(self, obj):
        c = obj.courier
        parts = [
            c.vehicle_brand or None,
            c.vehicle_model or None,
            f"Plaque {c.vehicle_plate}" if c.vehicle_plate and not c.vehicle_plate.startswith("TMP-") else None,
        ]
        label = " · ".join(p for p in parts if p)
        return label or None


class FavoriteCourierViewSet(viewsets.GenericViewSet):
    """
    GET  /api/v1/favorites/couriers/          — liste des favoris du client
    POST /api/v1/favorites/couriers/add/      — { "courier_id": "<uuid>" }
    POST /api/v1/favorites/couriers/remove/   — { "courier_id": "<uuid>" }
    """
    permission_classes = [IsAuthenticated]
    serializer_class = FavoriteCourierSerializer

    def get_queryset(self):
        return FavoriteCourier.objects.filter(
            client=self.request.user
        ).select_related("courier__user")

    def list(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add(self, request):
        courier = Courier.objects.filter(id=request.data.get("courier_id")).first()
        if courier is None:
            return Response({"detail": "Coursier introuvable."}, status=status.HTTP_404_NOT_FOUND)
        fav, _ = FavoriteCourier.objects.get_or_create(client=request.user, courier=courier)
        return Response(self.get_serializer(fav).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def remove(self, request):
        FavoriteCourier.objects.filter(
            client=request.user, courier_id=request.data.get("courier_id")
        ).delete()
        return Response({"detail": "Retiré des favoris."})


router = DefaultRouter()
router.register("couriers", CourierViewSet, basename="courier")
router.register("favorites/couriers", FavoriteCourierViewSet, basename="favorite-courier")
urlpatterns = [path("", include(router.urls))]
