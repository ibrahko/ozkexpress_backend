from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers
# from core.throttles import CourierLocationThrottle  # désactivé pour test
CourierLocationThrottle = None
from .models import LocationHistory


class LocationUpdateSerializer(drf_serializers.Serializer):
    lat = drf_serializers.FloatField()
    lng = drf_serializers.FloatField()
    speed_kmh = drf_serializers.FloatField(required=False)
    heading = drf_serializers.FloatField(required=False)
    request_id = drf_serializers.UUIDField(required=False)


class LocationUpdateView(generics.GenericAPIView):
    """
    POST /api/v1/tracking/location/
    Fallback REST pour la mise à jour GPS (si WebSocket indisponible).
    """
    serializer_class = LocationUpdateSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from django.contrib.gis.geos import Point
        user = request.user
        lat = data["lat"]
        lng = data["lng"]

        # Mettre à jour la position du profil
        if user.user_type == "courier":
            try:
                user.courier_profile.update_location(lat, lng)
            except Exception:
                pass
        elif user.user_type == "driver":
            try:
                user.driver_profile.update_location(lat, lng)
            except Exception:
                pass

        # Enregistrer l'historique
        LocationHistory.objects.create(
            worker_user=user,
            location=Point(lng, lat, srid=4326),
            speed_kmh=data.get("speed_kmh"),
            heading=data.get("heading"),
        )

        return Response({"detail": "Position mise à jour."})


class WorkerLocationSerializer(drf_serializers.Serializer):
    id = drf_serializers.UUIDField()
    name = drf_serializers.CharField()
    lat = drf_serializers.FloatField()
    lng = drf_serializers.FloatField()
    last_update = drf_serializers.DateTimeField()


class NearbyWorkersView(generics.GenericAPIView):
    """
    GET /api/v1/tracking/nearby/?lat=12.36&lng=-1.53&type=courier
    Retourne les travailleurs disponibles près d'une position.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        lat = float(request.query_params.get("lat", 0))
        lng = float(request.query_params.get("lng", 0))
        worker_type = request.query_params.get("type", "courier")
        radius_km = float(request.query_params.get("radius", 5))

        from django.contrib.gis.geos import Point
        from django.contrib.gis.measure import D

        point = Point(lng, lat, srid=4326)
        workers = []

        if worker_type == "courier":
            from apps.couriers.models import Courier
            qs = Courier.objects.filter(
                is_available=True,
                last_known_location__distance_lte=(point, D(km=radius_km)),
            ).select_related("user")
            for c in qs:
                if c.last_known_location:
                    workers.append({
                        "id": str(c.user.id),
                        "name": c.user.get_full_name(),
                        "lat": c.last_known_location.y,
                        "lng": c.last_known_location.x,
                        "last_update": c.last_location_update,
                        "rating": float(c.rating),
                    })
        elif worker_type == "driver":
            from apps.drivers.models import Driver
            qs = Driver.objects.filter(
                is_available=True,
                last_known_location__distance_lte=(point, D(km=radius_km)),
            ).select_related("user")
            for d in qs:
                if d.last_known_location:
                    workers.append({
                        "id": str(d.user.id),
                        "name": d.user.get_full_name(),
                        "lat": d.last_known_location.y,
                        "lng": d.last_known_location.x,
                        "last_update": d.last_location_update,
                        "rating": float(d.rating),
                    })

        return Response({"workers": workers, "count": len(workers)})
