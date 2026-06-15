from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.permissions import IsDriver
from .models import Driver, DriverEarning


class DriverSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    avatar = serializers.ImageField(source="user.avatar", read_only=True)

    class Meta:
        model = Driver
        fields = [
            "id", "user_name", "phone", "avatar",
            "status", "service_type", "vehicle_category",
            "vehicle_plate", "vehicle_model", "vehicle_year", "vehicle_color",
            "license_number", "passenger_capacity", "owns_vehicle",
            "rating", "total_trips", "is_available", "last_location_update",
        ]
        read_only_fields = ["id", "rating", "total_trips", "last_location_update"]


class DriverEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverEarning
        fields = ["id", "gross_amount", "commission_rate", "commission_amount", "net_amount", "earned_at"]
        read_only_fields = fields


class DriverViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return DriverSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Driver.objects.select_related("user").all()
        return Driver.objects.filter(user=user)

    @action(detail=False, methods=["get", "patch"], permission_classes=[IsDriver])
    def me(self, request):
        driver = request.user.driver_profile
        if request.method == "PATCH":
            serializer = DriverSerializer(driver, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(DriverSerializer(driver).data)

    @action(detail=False, methods=["post"], permission_classes=[IsDriver])
    def go_online(self, request):
        request.user.driver_profile.go_online()
        return Response({"detail": "Vous êtes maintenant en ligne."})

    @action(detail=False, methods=["post"], permission_classes=[IsDriver])
    def go_offline(self, request):
        request.user.driver_profile.go_offline()
        return Response({"detail": "Vous êtes maintenant hors ligne."})

    @action(detail=False, methods=["get"], permission_classes=[IsDriver])
    def earnings(self, request):
        earnings = DriverEarning.objects.filter(driver__user=request.user)
        serializer = DriverEarningSerializer(earnings, many=True)
        total = sum(e.net_amount for e in earnings)
        return Response({"results": serializer.data, "total_net": total})


router = DefaultRouter()
router.register("drivers", DriverViewSet, basename="driver")
urlpatterns = [path("", include(router.urls))]
