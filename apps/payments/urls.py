from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InitiatePaymentView, TransactionViewSet,
    PaymentWebhookView, WalletView, WithdrawalViewSet,
)

router = DefaultRouter()
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("withdrawals", WithdrawalViewSet, basename="withdrawal")

urlpatterns = [
    path("payments/initiate/", InitiatePaymentView.as_view(), name="payment-initiate"),
    path("payments/webhook/<str:provider>/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("payments/wallet/", WalletView.as_view(), name="wallet"),
    path("payments/", include(router.urls)),
]
