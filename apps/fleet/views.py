from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from core.permissions import IsClient
from .models import Vehicle, VehicleRental, VehicleStatus, RentalStatus
from .serializers import VehicleSerializer, VehicleRentalSerializer


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    """Liste et détail des véhicules disponibles à la location."""
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["vehicle_type", "status", "requires_driver"]
    search_fields = ["brand", "model", "plate_number"]
    ordering_fields = ["daily_rate", "year"]

    def get_queryset(self):
        return Vehicle.objects.filter(is_active=True)

    @action(detail=False, methods=["get"])
    def available(self, request):
        """GET /api/v1/fleet/vehicles/available/ — véhicules disponibles uniquement."""
        qs = self.get_queryset().filter(status=VehicleStatus.AVAILABLE)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class VehicleRentalViewSet(viewsets.ModelViewSet):
    """CRUD des locations de véhicules."""
    serializer_class = VehicleRentalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["start_date", "created_at"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return VehicleRental.objects.select_related("vehicle", "client", "driver").all()
        return VehicleRental.objects.select_related("vehicle").filter(client=user)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rental = self.get_object()
        if rental.status not in (RentalStatus.PENDING, RentalStatus.CONFIRMED):
            return Response(
                {"detail": "Impossible d'annuler une location déjà active ou terminée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rental.cancel()
        return Response({"detail": "Location annulée."})
