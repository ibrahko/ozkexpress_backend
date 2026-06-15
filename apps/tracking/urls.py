from django.urls import path
from .views import LocationUpdateView, NearbyWorkersView

urlpatterns = [
    path("tracking/location/", LocationUpdateView.as_view(), name="location-update"),
    path("tracking/nearby/", NearbyWorkersView.as_view(), name="nearby-workers"),
]
