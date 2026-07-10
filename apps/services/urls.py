from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, RideRequestViewSet

router = DefaultRouter()
router.register("services", ServiceRequestViewSet, basename="service")
router.register("rides", RideRequestViewSet, basename="ride")

from .receipts import ServiceReceiptView

urlpatterns = [
    # Reçu PDF (H2) — avant le router pour prendre la main sur services/<pk>/
    path("services/<uuid:pk>/receipt/", ServiceReceiptView.as_view(), name="service-receipt"),
    path("", include(router.urls)),
]
