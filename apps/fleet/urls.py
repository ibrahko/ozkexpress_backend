from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VehicleViewSet, VehicleRentalViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("rentals", VehicleRentalViewSet, basename="rental")

urlpatterns = [
    path("fleet/", include(router.urls)),
]
