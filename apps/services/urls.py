from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, RideRequestViewSet

router = DefaultRouter()
router.register("services", ServiceRequestViewSet, basename="service")
router.register("rides", RideRequestViewSet, basename="ride")

urlpatterns = [
    path("", include(router.urls)),
]
