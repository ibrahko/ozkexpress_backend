from rest_framework import generics, viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from core.throttles import PaymentInitiateThrottle
from .models import Transaction, Wallet, WithdrawalRequest, PaymentType
from .serializers import (
    TransactionSerializer, InitiatePaymentSerializer,
    WalletSerializer, WithdrawalRequestSerializer,
)
from .services import PaymentService, WebhookError, WebhookVerifier, generate_reference
import logging

logger = logging.getLogger(__name__)


class InitiatePaymentView(generics.GenericAPIView):
    """POST /api/v1/payments/initiate/ — Initier un paiement."""
    serializer_class = InitiatePaymentSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [PaymentInitiateThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Résoudre l'objet lié et le montant
        transaction_kwargs = {
            "client": request.user,
            "provider": data["provider"],
            "reference": generate_reference(),
            "phone_number": data.get("phone_number", ""),
            "currency": "XOF",
        }

        if sid := data.get("service_request_id"):
            from apps.services.models import ServiceRequest
            req = ServiceRequest.objects.get(id=sid, client=request.user)
            transaction_kwargs.update({
                "payment_type": PaymentType.SERVICE_DELIVERY,
                "amount": req.final_price or req.estimated_price or 0,
                "service_request": req,
            })
        elif rid := data.get("ride_request_id"):
            from apps.services.models import RideRequest
            req = RideRequest.objects.get(id=rid, client=request.user)
            transaction_kwargs.update({
                "payment_type": PaymentType.RIDE,
                "amount": req.final_price or req.estimated_price or 0,
                "ride_request": req,
            })
        elif rental_id := data.get("rental_id"):
            from apps.fleet.models import VehicleRental
            req = VehicleRental.objects.get(id=rental_id, client=request.user)
            transaction_kwargs.update({
                "payment_type": PaymentType.RENTAL,
                "amount": req.total_price or 0,
                "rental": req,
            })

        transaction = Transaction.objects.create(**transaction_kwargs)

        try:
            result = PaymentService.initiate_payment(transaction)
            return Response({
                "transaction": TransactionSerializer(transaction).data,
                "payment_data": result,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /api/v1/payments/transactions/ — Historique des transactions."""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Transaction.objects.filter(client=self.request.user)


class PaymentWebhookView(generics.GenericAPIView):
    """
    POST /api/v1/payments/webhook/{provider}/
    Endpoint appelé par les providers (Orange Money, Wave, Stripe) pour confirmer
    le paiement. Le message est authentifié par WebhookVerifier avant tout effet.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, provider):
        # Corps brut (avant tout parsing) : c'est lui qui est signé par le provider
        raw_body = request.body
        try:
            confirmed = WebhookVerifier.verify(provider, request.headers, raw_body)
        except WebhookError as e:
            logger.warning("Webhook %s refusé : %s", provider, e)
            return Response({"detail": str(e)}, status=e.status_code)

        if confirmed is None:
            return Response({"detail": "Ignoré."})

        transaction, provider_tx_id, payload = confirmed
        if not PaymentService.complete_from_webhook(transaction, provider_tx_id, payload):
            return Response({"detail": "Déjà traité."})
        logger.info("Webhook %s : transaction %s payée.", provider, transaction.reference)
        return Response({"detail": "OK"})


class WalletView(generics.RetrieveAPIView):
    """GET /api/v1/payments/wallet/ — Solde du portefeuille."""
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet


class WithdrawalViewSet(viewsets.ModelViewSet):
    """CRUD des demandes de retrait."""
    serializer_class = WithdrawalRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(wallet__user=self.request.user)
