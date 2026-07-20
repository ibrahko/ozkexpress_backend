from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceRequestViewSet, RideRequestViewSet, ZoneListView, QuoteView

router = DefaultRouter()
router.register("services", ServiceRequestViewSet, basename="service")
router.register("rides", RideRequestViewSet, basename="ride")

from .receipts import ServiceReceiptView

urlpatterns = [
    # Reçu PDF (H2) — avant le router pour prendre la main sur services/<pk>/
    path("services/<uuid:pk>/receipt/", ServiceReceiptView.as_view(), name="service-receipt"),
    # Quartiers de Bamako + devis (tarification par distance, 200 F/km)
    path("services/zones/", ZoneListView.as_view(), name="service-zones"),
    path("services/quote/", QuoteView.as_view(), name="service-quote"),
    path("", include(router.urls)),
]
