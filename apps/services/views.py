from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from core.permissions import IsClient, IsCourier, IsDriver
from core.throttles import ServiceCreateThrottle
from .models import ServiceRequest, RideRequest, RequestStatus, RideStatus, CancellationReason
from .serializers import (
    ServiceRequestSerializer, RideRequestSerializer, RatingSerializer
)


class ServiceRequestViewSet(viewsets.ModelViewSet):
    """
    Demandes de livraison de colis.
    - Client : crée, consulte, annule, note
    - Coursier : consulte les demandes en attente, accepte, met à jour le statut
    """
    serializer_class = ServiceRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["created_at"]

    def get_throttles(self):
        if self.action == "create":
            return [ServiceCreateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return ServiceRequest.objects.select_related("client", "courier__user").all()
        if user.user_type == "courier":
            return ServiceRequest.objects.select_related("client").filter(
                courier__user=user
            ) | ServiceRequest.objects.filter(status=RequestStatus.PENDING)
        return ServiceRequest.objects.select_related("courier__user").filter(client=user)

    def get_permissions(self):
        if self.action == "create":
            return [IsClient()]
        return [IsAuthenticated()]

    # ── Actions CLIENT ──────────────────────────────────────────────

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def cancel(self, request, pk=None):
        """POST /api/v1/services/{id}/cancel/"""
        req = self.get_object()
        if req.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if req.status not in (RequestStatus.PENDING, RequestStatus.ACCEPTED):
            return Response(
                {"detail": "Impossible d'annuler une livraison déjà en cours."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        req.cancel(reason=CancellationReason.CLIENT_REQUEST)
        return Response({"detail": "Livraison annulée."})

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def rate(self, request, pk=None):
        """POST /api/v1/services/{id}/rate/"""
        req = self.get_object()
        if req.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != RequestStatus.DELIVERED:
            return Response(
                {"detail": "Vous ne pouvez noter qu'une livraison terminée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req.client_rating = serializer.validated_data["rating"]
        req.client_review = serializer.validated_data.get("review", "")
        req.save(update_fields=["client_rating", "client_review"])
        # Mettre à jour la note du coursier
        if req.courier:
            self._update_worker_rating(req.courier)
        return Response({"detail": "Merci pour votre évaluation."})

    # ── Actions COURSIER ────────────────────────────────────────────

    @action(detail=False, methods=["get"], permission_classes=[IsCourier])
    def available(self, request):
        """GET /api/v1/services/available/ — demandes en attente près du coursier."""
        qs = ServiceRequest.objects.filter(status=RequestStatus.PENDING).select_related("client")
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsCourier])
    def accept(self, request, pk=None):
        """POST /api/v1/services/{id}/accept/"""
        req = self.get_object()
        if req.status != RequestStatus.PENDING:
            return Response(
                {"detail": "Cette demande n'est plus disponible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        courier = request.user.courier_profile
        req.accept(courier)
        return Response(self.get_serializer(req).data)

    @action(detail=True, methods=["post"], permission_classes=[IsCourier])
    def pickup(self, request, pk=None):
        """POST /api/v1/services/{id}/pickup/ — coursier en route vers départ."""
        req = self.get_object()
        req.mark_pickup()
        return Response({"detail": "Statut mis à jour: en route vers le départ."})

    @action(detail=True, methods=["post"], permission_classes=[IsCourier])
    def start(self, request, pk=None):
        """POST /api/v1/services/{id}/start/ — colis récupéré, en livraison."""
        req = self.get_object()
        req.mark_in_progress()
        return Response({"detail": "Livraison en cours."})

    @action(detail=True, methods=["post"], permission_classes=[IsCourier])
    def deliver(self, request, pk=None):
        """POST /api/v1/services/{id}/deliver/ — livraison terminée."""
        req = self.get_object()
        req.mark_delivered()
        return Response({"detail": "Livraison effectuée avec succès."})

    def _update_worker_rating(self, worker):
        from django.db.models import Avg
        avg = ServiceRequest.objects.filter(
            courier=worker, client_rating__isnull=False
        ).aggregate(avg=Avg("client_rating"))["avg"]
        if avg:
            worker.rating = round(avg, 2)
            worker.save(update_fields=["rating"])


class RideRequestViewSet(viewsets.ModelViewSet):
    """
    Demandes de course / transport de personnes.
    - Client : crée, consulte, annule, note
    - Chauffeur : consulte, accepte, démarre, termine
    """
    serializer_class = RideRequestSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status"]
    ordering_fields = ["created_at"]

    def get_throttles(self):
        if self.action == "create":
            return [ServiceCreateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return RideRequest.objects.select_related("client", "driver__user").all()
        if user.user_type == "driver":
            return RideRequest.objects.filter(
                driver__user=user
            ) | RideRequest.objects.filter(status=RideStatus.PENDING)
        return RideRequest.objects.select_related("driver__user").filter(client=user)

    def get_permissions(self):
        if self.action == "create":
            return [IsClient()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], permission_classes=[IsDriver])
    def available(self, request):
        qs = RideRequest.objects.filter(status=RideStatus.PENDING).select_related("client")
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsDriver])
    def accept(self, request, pk=None):
        ride = self.get_object()
        if ride.status != RideStatus.PENDING:
            return Response({"detail": "Course non disponible."}, status=status.HTTP_400_BAD_REQUEST)
        driver = request.user.driver_profile
        ride.accept(driver)
        return Response(self.get_serializer(ride).data)

    @action(detail=True, methods=["post"], permission_classes=[IsDriver])
    def start(self, request, pk=None):
        ride = self.get_object()
        ride.start()
        return Response({"detail": "Course démarrée."})

    @action(detail=True, methods=["post"], permission_classes=[IsDriver])
    def complete(self, request, pk=None):
        ride = self.get_object()
        ride.complete()
        return Response({"detail": "Course terminée."})

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def cancel(self, request, pk=None):
        ride = self.get_object()
        if ride.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if ride.status not in (RideStatus.PENDING, RideStatus.ACCEPTED):
            return Response({"detail": "Impossible d'annuler."}, status=status.HTTP_400_BAD_REQUEST)
        ride.status = RideStatus.CANCELLED
        ride.save(update_fields=["status"])
        if ride.driver:
            ride.driver.set_available()
        return Response({"detail": "Course annulée."})

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def rate(self, request, pk=None):
        ride = self.get_object()
        if ride.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if ride.status != RideStatus.COMPLETED:
            return Response({"detail": "Course non terminée."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ride.client_rating = serializer.validated_data["rating"]
        ride.client_review = serializer.validated_data.get("review", "")
        ride.save(update_fields=["client_rating", "client_review"])
        if ride.driver:
            avg = RideRequest.objects.filter(
                driver=ride.driver, client_rating__isnull=False
            ).aggregate(avg=__import__("django.db.models", fromlist=["Avg"]).Avg("client_rating"))["avg"]
            if avg:
                ride.driver.rating = round(avg, 2)
                ride.driver.save(update_fields=["rating"])
        return Response({"detail": "Merci pour votre évaluation."})
