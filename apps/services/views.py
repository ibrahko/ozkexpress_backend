from rest_framework import viewsets, status, filters, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from core.permissions import IsClient, IsCourier, IsDriver
from core.throttles import ServiceCreateThrottle
from .models import (
    ServiceRequest, RideRequest, RequestStatus, RideStatus,
    CancellationReason, AssignmentType, Message, Zone,
)
from .serializers import (
    ServiceRequestSerializer, RideRequestSerializer, RatingSerializer, MessageSerializer,
    ZoneSerializer, QuoteRequestSerializer, TipSerializer,
)


class ZoneListView(generics.ListAPIView):
    """
    GET /api/v1/services/zones/ — quartiers de Bamako (sélecteur de l'app mobile).
    """
    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # liste courte, chargée en une fois et cachée par l'app

    def get_queryset(self):
        return Zone.objects.filter(is_active=True).order_by("name")


class QuoteView(APIView):
    """
    POST /api/v1/services/quote/ — devis avant confirmation (source de vérité).
    Body : {"pickup": {lat, lng}, "delivery": {lat, lng}, "kind": "delivery"|"ride"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .pricing import quote

        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(quote(data["pickup"], data["delivery"], data["kind"]))

# Escalade automatique de la diffusion (P5) :
# après 60 s sans acceptation → rayon élargi à 10 km min,
# après 180 s → visible par tous les coursiers en ligne.
ESCALATION_WIDEN_S = 60
ESCALATION_WIDEN_KM = 10
ESCALATION_OPEN_S = 180


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

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def tip(self, request, pk=None):
        """POST /api/v1/services/{id}/tip/ — pourboire (100 % pour le coursier)."""
        from django.db.models import F
        from apps.couriers.models import CourierEarning

        req = self.get_object()
        if req.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != RequestStatus.DELIVERED:
            return Response(
                {"detail": "Le pourboire n'est possible qu'après la livraison."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        delta = amount - req.tip_amount
        req.tip_amount = amount
        req.save(update_fields=["tip_amount", "updated_at"])
        # Répercuter sur le gain du coursier (sans commission sur le pourboire)
        CourierEarning.objects.filter(service_request=req).update(
            gross_amount=F("gross_amount") + delta,
            net_amount=F("net_amount") + delta,
        )
        return Response({"detail": "Pourboire enregistré. Merci !", "tip_amount": amount})

    # ── Actions COURSIER ────────────────────────────────────────────

    @action(detail=False, methods=["get"], permission_classes=[IsCourier])
    def available(self, request):
        """
        GET /api/v1/services/available/ — demandes en attente pour CE coursier.
        - broadcast : point de récupération dans le rayon de diffusion
          (si la position du coursier est connue, sinon toutes les diffusions)
        - direct : uniquement les demandes qui lui sont destinées
        """
        from django.db.models import Q

        courier = getattr(request.user, "courier_profile", None)
        if courier is None:
            return Response(
                {"detail": "Profil coursier introuvable. Contactez le support."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = (
            ServiceRequest.objects.filter(status=RequestStatus.PENDING)
            .select_related("client")
            .filter(Q(assignment_type=AssignmentType.BROADCAST) | Q(preferred_courier=courier))
        )

        # Rayon de diffusion : filtrage par distance au point de récupération,
        # avec escalade automatique selon l'ancienneté de la demande (P5).
        results = list(qs)
        if courier.last_known_location:
            from django.utils import timezone
            from django.contrib.gis.db.models.functions import Distance

            now = timezone.now()
            annotated = qs.annotate(
                pickup_distance=Distance("pickup_location", courier.last_known_location)
            )

            def effective_radius_km(r):
                """Rayon effectif : élargi avec le temps d'attente. None = illimité."""
                age_s = (now - r.created_at).total_seconds()
                if age_s >= ESCALATION_OPEN_S:
                    return None
                base = float(r.broadcast_radius_km or 5)
                if age_s >= ESCALATION_WIDEN_S:
                    return max(base, ESCALATION_WIDEN_KM)
                return base

            results = []
            for r in annotated:
                if r.preferred_courier_id == courier.id:  # direct : toujours visible
                    results.append(r)
                    continue
                radius = effective_radius_km(r)
                if radius is None or r.pickup_distance is None or r.pickup_distance.km <= radius:
                    results.append(r)

        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data)

    # ── F3 : Messagerie client ↔ coursier ──────────────────────────

    @action(detail=True, methods=["get", "post"], permission_classes=[IsAuthenticated])
    def messages(self, request, pk=None):
        """
        GET  /api/v1/services/{id}/messages/  — fil de discussion
        POST /api/v1/services/{id}/messages/  — envoyer { "body": "..." }
        Accès : client de la demande, coursier assigné, staff.
        """
        req = self.get_object()
        user = request.user
        is_client = req.client_id == user.id
        is_courier = req.courier is not None and req.courier.user_id == user.id
        if not (is_client or is_courier or user.is_staff):
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        if request.method == "POST":
            body = str(request.data.get("body", "")).strip()
            if not body:
                return Response({"detail": "Message vide."}, status=status.HTTP_400_BAD_REQUEST)
            msg = Message.objects.create(service_request=req, sender=user, body=body[:2000])
            return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

        from django.utils import timezone
        thread = req.messages.select_related("sender").order_by("created_at")
        # Les messages reçus sont marqués lus à l'ouverture du fil
        thread.filter(read_at__isnull=True).exclude(sender=user).update(read_at=timezone.now())
        return Response(MessageSerializer(thread, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsCourier])
    def accept(self, request, pk=None):
        """POST /api/v1/services/{id}/accept/"""
        req = self.get_object()
        if req.status != RequestStatus.PENDING:
            return Response(
                {"detail": "Cette demande n'est plus disponible."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        courier = getattr(request.user, "courier_profile", None)
        if courier is None:
            return Response(
                {"detail": "Profil coursier introuvable. Contactez le support."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Attribution directe : réservée au coursier choisi
        if req.preferred_courier_id and req.preferred_courier_id != courier.id:
            return Response(
                {"detail": "Cette demande est réservée à un autre coursier."},
                status=status.HTTP_403_FORBIDDEN,
            )
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
        driver = getattr(request.user, "driver_profile", None)
        if driver is None:
            return Response(
                {"detail": "Profil chauffeur introuvable. Contactez le support."},
                status=status.HTTP_403_FORBIDDEN,
            )
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

    @action(detail=True, methods=["post"], permission_classes=[IsClient])
    def tip(self, request, pk=None):
        """POST /api/v1/rides/{id}/tip/ — pourboire (100 % pour le chauffeur)."""
        from django.db.models import F
        from apps.drivers.models import DriverEarning

        ride = self.get_object()
        if ride.client != request.user:
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if ride.status != RideStatus.COMPLETED:
            return Response(
                {"detail": "Le pourboire n'est possible qu'après la course."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = TipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        delta = amount - ride.tip_amount
        ride.tip_amount = amount
        ride.save(update_fields=["tip_amount", "updated_at"])
        # Répercuter sur le gain du chauffeur (sans commission sur le pourboire)
        DriverEarning.objects.filter(ride_request=ride).update(
            gross_amount=F("gross_amount") + delta,
            net_amount=F("net_amount") + delta,
        )
        return Response({"detail": "Pourboire enregistré. Merci !", "tip_amount": amount})
