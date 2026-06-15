from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.permissions import IsCourier, IsAdminUser
from .models import Courier, CourierEarning


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


router = DefaultRouter()
router.register("couriers", CourierViewSet, basename="courier")
urlpatterns = [path("", include(router.urls))]
