import logging
from .models import Notification, NotificationType

logger = logging.getLogger(__name__)


class NotificationService:
    @classmethod
    def send(cls, recipient, notification_type: str, title: str, body: str, data: dict = None) -> Notification:
        """Crée la notification en DB et envoie un push si possible."""
        notif = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data or {},
        )
        # Envoyer push Firebase si le token est disponible
        if recipient.push_token:
            cls._send_push(recipient.push_token, title, body, data or {})
            notif.sent_push = True
            notif.save(update_fields=["sent_push"])

        # Envoyer via WebSocket si connecté
        cls._send_ws(recipient, notif)
        return notif

    @classmethod
    def _send_push(cls, token: str, title: str, body: str, data: dict):
        try:
            import firebase_admin.messaging as messaging
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in data.items()},
                token=token,
            )
            messaging.send(message)
            logger.info("Push envoyé: %s", title)
        except Exception as e:
            logger.error("Erreur push Firebase: %s", str(e))

    @classmethod
    def _send_ws(cls, recipient, notif: Notification):
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{recipient.id}",
                {
                    "type": "notification.message",
                    "id": str(notif.id),
                    "notification_type": notif.notification_type,
                    "title": notif.title,
                    "body": notif.body,
                    "data": notif.data,
                }
            )
        except Exception as e:
            logger.warning("WS notification non envoyée: %s", str(e))

    # ── Helpers métier ───────────────────────────────────────────────

    @classmethod
    def service_accepted(cls, service_request):
        cls.send(
            service_request.client,
            NotificationType.SERVICE_ACCEPTED,
            "Coursier trouvé !",
            f"{service_request.courier.user.get_full_name()} a accepté votre demande.",
            {"request_id": str(service_request.id)},
        )

    @classmethod
    def service_delivered(cls, service_request):
        cls.send(
            service_request.client,
            NotificationType.SERVICE_DELIVERED,
            "Livraison effectuée ✓",
            "Votre colis a été livré avec succès.",
            {"request_id": str(service_request.id)},
        )

    @classmethod
    def ride_accepted(cls, ride_request):
        cls.send(
            ride_request.client,
            NotificationType.RIDE_ACCEPTED,
            "Chauffeur trouvé !",
            f"{ride_request.driver.user.get_full_name()} est en route.",
            {"ride_id": str(ride_request.id)},
        )

    @classmethod
    def payment_success(cls, transaction):
        cls.send(
            transaction.client,
            NotificationType.PAYMENT_SUCCESS,
            "Paiement confirmé ✓",
            f"Paiement de {transaction.amount} {transaction.currency} reçu.",
            {"transaction_id": str(transaction.id)},
        )

    @classmethod
    def new_request_nearby(cls, worker_user, request_id: str, request_type: str = "service"):
        cls.send(
            worker_user,
            NotificationType.NEW_REQUEST_NEARBY,
            "Nouvelle demande à proximité",
            "Un client a besoin de vous.",
            {"request_id": request_id, "type": request_type},
        )
