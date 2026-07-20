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

        # Toujours logger le code (utile en dev et pour debug prod)
        logger.info(">>> OTP [%s] code=%s <<<", phone, otp.code)

        # Envoyer par SMS si les credentials Twilio sont configurés
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_PHONE_NUMBER:
            sent = cls.send_sms(phone, otp.code)
            if not sent and getattr(settings, "OTP_ALLOW_SMS_FAILURE", False):
                # Mode test : le SMS a échoué (ex. numéro non vérifié en trial Twilio)
                # mais l'OTP est valide et lisible dans les logs → on ne bloque pas.
                logger.warning("SMS non envoyé à %s — accepté (OTP_ALLOW_SMS_FAILURE).", phone)
                return True
            return sent

        # Pas de credentials Twilio : on retourne True (mode dev sans SMS)
        logger.warning("Twilio non configuré — OTP affiché en console uniquement.")
        return True


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

        # P3 : l'app mobile connecte les coursiers/chauffeurs par OTP —
        # on garantit l'existence du profil métier (statut "pending",
        # infos véhicule à compléter ensuite via PATCH /couriers/me/).
        cls._ensure_worker_profile(user)

        return user, created

    @classmethod
    def _ensure_worker_profile(cls, user: User) -> None:
        """
        Crée le profil Courier/Driver s'il manque.
        vehicle_plate / chassis_number / license_number sont uniques et
        obligatoires : on pose des placeholders "TMP-xxxx" que le worker
        remplacera via PATCH /couriers/me/ (ou /drivers/me/).
        """
        suffix = str(user.id).replace("-", "")[:10].upper()
        placeholders = {
            "vehicle_brand": "",
            "vehicle_model": "",
            "vehicle_plate": f"TMP-P{suffix}",
            "chassis_number": f"TMP-C{suffix}",
            "license_number": f"TMP-L{suffix}",
        }
        if user.user_type == "courier":
            from apps.couriers.models import Courier
            Courier.objects.get_or_create(user=user, defaults=placeholders)
        elif user.user_type == "driver":
            from apps.drivers.models import Driver
            Driver.objects.get_or_create(user=user, defaults=placeholders)

    @classmethod
    def get_tokens_for_user(cls, user: User) -> dict:
        """Génère les tokens JWT pour l'utilisateur."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
