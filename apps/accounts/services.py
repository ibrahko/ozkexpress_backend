import random
import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import OTPCode, User

logger = logging.getLogger(__name__)


class OTPService:
    OTP_EXPIRY_MINUTES = 10

    @classmethod
    def generate_code(cls) -> str:
        return str(random.randint(100000, 999999))

    @classmethod
    def create_otp(cls, phone: str) -> OTPCode:
        """Invalide les anciens OTPs et en crée un nouveau."""
        # Invalider les OTPs existants non utilisés
        OTPCode.objects.filter(phone=phone, is_used=False).update(is_used=True)

        otp = OTPCode.objects.create(
            phone=phone,
            code=cls.generate_code(),
            expires_at=timezone.now() + timedelta(minutes=cls.OTP_EXPIRY_MINUTES),
        )
        return otp

    @classmethod
    def send_sms(cls, phone: str, code: str) -> bool:
        """
        Envoie le code OTP par SMS via Twilio.
        Retourne True si l'envoi a réussi.
        """
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=f"Votre code MotoExpress : {code}\nValide {cls.OTP_EXPIRY_MINUTES} minutes.",
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone,
            )
            logger.info("SMS OTP envoyé à %s, SID: %s", phone, message.sid)
            return True
        except Exception as e:
            logger.error("Erreur envoi SMS OTP à %s: %s", phone, str(e))
            return False

    @classmethod
    def request_otp(cls, phone: str) -> bool:
        """Génère et envoie un OTP. Retourne le succès de l'envoi SMS."""
        otp = cls.create_otp(phone)

        # Mode dev : log le code si DEBUG ou si Twilio non configuré
        twilio_configured = bool(
            getattr(settings, 'TWILIO_ACCOUNT_SID', '') and
            getattr(settings, 'TWILIO_AUTH_TOKEN', '') and
            getattr(settings, 'TWILIO_PHONE_NUMBER', '')
        )
        if settings.DEBUG or not twilio_configured:
            logger.info(">>> OTP DEV [%s] code=%s <<<", phone, otp.code)
            return True

        return cls.send_sms(phone, otp.code)


class AuthService:
    @classmethod
    def get_or_create_user(cls, phone: str, user_type: str) -> tuple:
        """
        Récupère ou crée l'utilisateur après vérification OTP.
        Retourne (user, is_new_user).
        """
        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                "user_type": user_type,
                "is_phone_verified": True,
                "status": "active",
            }
        )

        if not created:
            # L'utilisateur existait, on marque le téléphone comme vérifié
            if not user.is_phone_verified:
                user.is_phone_verified = True
                user.save(update_fields=["is_phone_verified"])

        # Auto-créer le profil métier si absent
        cls._ensure_worker_profile(user)

        return user, created

    @classmethod
    def _ensure_worker_profile(cls, user) -> None:
        """Crée le profil Courier ou Driver s'il n'existe pas encore."""
        if user.user_type == "courier":
            try:
                user.courier_profile
            except Exception:
                from apps.couriers.models import Courier
                Courier.objects.get_or_create(user=user)
        elif user.user_type == "driver":
            try:
                user.driver_profile
            except Exception:
                from apps.drivers.models import Driver
                Driver.objects.get_or_create(user=user)

    @classmethod
    def get_tokens_for_user(cls, user: User) -> dict:
        """Génère les tokens JWT pour l'utilisateur."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
