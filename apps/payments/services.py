import uuid
import requests
import logging
from abc import ABC, abstractmethod
from django.conf import settings
from .models import Transaction, PaymentProvider, PaymentStatus

logger = logging.getLogger(__name__)


def generate_reference() -> str:
    return f"ME-{uuid.uuid4().hex[:12].upper()}"


class BasePaymentProvider(ABC):
    @abstractmethod
    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        pass

    @abstractmethod
    def verify(self, transaction_id: str) -> dict:
        pass


class OrangeMoneyProvider(BasePaymentProvider):
    def __init__(self):
        self.api_url = settings.ORANGE_MONEY_API_URL
        self.client_id = settings.ORANGE_MONEY_CLIENT_ID
        self.client_secret = settings.ORANGE_MONEY_CLIENT_SECRET

    def _get_token(self) -> str:
        response = requests.post(
            f"{self.api_url}/oauth/v3/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        token = self._get_token()
        response = requests.post(
            f"{self.api_url}/orange-money-webpay/dev/v1/webpayment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "merchant_key": self.client_id,
                "currency": currency,
                "order_id": reference,
                "amount": amount,
                "return_url": f"{settings.APP_BASE_URL}/payments/callback/orange/",
                "cancel_url": f"{settings.APP_BASE_URL}/payments/cancel/orange/",
                "notif_url": f"{settings.APP_BASE_URL}/api/v1/payments/webhook/orange/",
                "lang": "fr",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def verify(self, transaction_id: str) -> dict:
        token = self._get_token()
        response = requests.get(
            f"{self.api_url}/orange-money-webpay/dev/v1/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


class WaveProvider(BasePaymentProvider):
    def __init__(self):
        self.api_url = settings.WAVE_API_URL
        self.api_key = settings.WAVE_API_KEY

    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        response = requests.post(
            f"{self.api_url}/checkout/sessions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "amount": str(amount),
                "currency": currency,
                "client_reference": reference,
                "success_url": f"{settings.APP_BASE_URL}/payments/callback/wave/",
                "error_url": f"{settings.APP_BASE_URL}/payments/cancel/wave/",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def verify(self, transaction_id: str) -> dict:
        response = requests.get(
            f"{self.api_url}/checkout/sessions/{transaction_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


class StripeProvider(BasePaymentProvider):
    def initiate(self, amount: int, currency: str, phone: str, reference: str) -> dict:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency.lower(),
            metadata={"reference": reference},
        )
        return {"client_secret": intent.client_secret, "payment_intent_id": intent.id}

    def verify(self, transaction_id: str) -> dict:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        intent = stripe.PaymentIntent.retrieve(transaction_id)
        return {"status": intent.status}


class PaymentService:
    _providers = {
        PaymentProvider.ORANGE_MONEY: OrangeMoneyProvider,
        PaymentProvider.WAVE: WaveProvider,
        PaymentProvider.STRIPE: StripeProvider,
    }

    @classmethod
    def get_provider(cls, provider: str) -> BasePaymentProvider:
        provider_class = cls._providers.get(provider)
        if not provider_class:
            raise ValueError(f"Provider inconnu: {provider}")
        return provider_class()

    @classmethod
    def initiate_payment(cls, transaction: Transaction) -> dict:
        if transaction.provider == PaymentProvider.CASH:
            transaction.mark_completed(provider_tx_id="CASH")
            return {"method": "cash", "status": "completed"}

        provider = cls.get_provider(transaction.provider)
        try:
            result = provider.initiate(
                amount=int(transaction.amount),
                currency=transaction.currency,
                phone=transaction.phone_number,
                reference=transaction.reference,
            )
            transaction.status = PaymentStatus.PROCESSING
            transaction.save(update_fields=["status"])
            return result
        except Exception as e:
            logger.error("Erreur paiement %s: %s", transaction.reference, str(e))
            transaction.mark_failed(str(e))
            raise

    @classmethod
    def verify_payment(cls, transaction: Transaction, provider_tx_id: str) -> bool:
        provider = cls.get_provider(transaction.provider)
        try:
            result = provider.verify(provider_tx_id)
            transaction.mark_completed(provider_tx_id=provider_tx_id, response=result)
            return True
        except Exception as e:
            logger.error("Erreur vérification %s: %s", transaction.reference, str(e))
            transaction.mark_failed(str(e))
            return False
