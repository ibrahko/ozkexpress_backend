import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class TrackingConsumer(AsyncWebsocketConsumer):
    """
    WebSocket pour le tracking GPS en temps réel.

    Flux coursier/chauffeur → serveur → client:
      1. Travailleur se connecte sur /ws/tracking/
      2. Il envoie ses coordonnées GPS périodiquement
      3. Le serveur broadcast sa position à tous les clients
         qui suivent cette course (groupe "tracking_{request_id}")

    Flux client → serveur:
      1. Client se connecte sur /ws/tracking/{request_id}/
      2. Il reçoit les mises à jour de position en temps réel
    """

    async def connect(self):
        self.user = self.scope.get("user")

        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return

        self.user_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()
        logger.info("WS tracking connecté: %s", self.user.phone)

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        # Si c'était un travailleur, le marquer hors ligne
        if self.user and not isinstance(self.user, AnonymousUser):
            await self.set_worker_offline(self.user)
        logger.info("WS tracking déconnecté: code=%s", close_code)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"error": "JSON invalide"}))
            return

        msg_type = data.get("type")

        if msg_type == "location.update":
            await self.handle_location_update(data)
        elif msg_type == "subscribe.tracking":
            await self.handle_subscribe(data)
        elif msg_type == "ping":
            await self.send(json.dumps({"type": "pong"}))

    async def handle_location_update(self, data):
        """Traite une mise à jour GPS envoyée par un travailleur."""
        lat = data.get("lat")
        lng = data.get("lng")
        speed = data.get("speed")
        heading = data.get("heading")
        request_id = data.get("request_id")

        if not (lat and lng):
            return

        # Sauvegarder en DB
        await self.save_location(self.user, lat, lng, speed, heading, request_id)

        # Mettre à jour la position du profil travailleur
        await self.update_worker_location(self.user, lat, lng)

        # Broadcaster aux clients qui suivent cette course
        if request_id:
            await self.channel_layer.group_send(
                f"tracking_{request_id}",
                {
                    "type": "location.broadcast",
                    "lat": lat,
                    "lng": lng,
                    "speed": speed,
                    "heading": heading,
                    "worker_id": str(self.user.id),
                    "worker_name": self.user.get_full_name(),
                }
            )

    async def handle_subscribe(self, data):
        """Un client s'abonne aux mises à jour d'une course."""
        request_id = data.get("request_id")
        if not request_id:
            return
        group_name = f"tracking_{request_id}"
        await self.channel_layer.group_add(group_name, self.channel_name)
        await self.send(json.dumps({
            "type": "subscribed",
            "request_id": request_id,
            "message": "Abonné au tracking de cette course."
        }))

    async def location_broadcast(self, event):
        """Reçoit un broadcast de position et l'envoie au client WebSocket."""
        await self.send(json.dumps({
            "type": "location.update",
            "lat": event["lat"],
            "lng": event["lng"],
            "speed": event.get("speed"),
            "heading": event.get("heading"),
            "worker_id": event["worker_id"],
            "worker_name": event["worker_name"],
        }))

    @database_sync_to_async
    def save_location(self, user, lat, lng, speed, heading, request_id):
        from django.contrib.gis.geos import Point
        from .models import LocationHistory
        kwargs = {
            "worker_user": user,
            "location": Point(float(lng), float(lat), srid=4326),
            "speed_kmh": speed,
            "heading": heading,
        }
        if request_id:
            from apps.services.models import ServiceRequest, RideRequest
            try:
                kwargs["service_request"] = ServiceRequest.objects.get(id=request_id)
            except ServiceRequest.DoesNotExist:
                try:
                    kwargs["ride_request"] = RideRequest.objects.get(id=request_id)
                except RideRequest.DoesNotExist:
                    pass
        LocationHistory.objects.create(**kwargs)

    @database_sync_to_async
    def update_worker_location(self, user, lat, lng):
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

    @database_sync_to_async
    def set_worker_offline(self, user):
        if user.user_type == "courier":
            try:
                user.courier_profile.go_offline()
            except Exception:
                pass
        elif user.user_type == "driver":
            try:
                user.driver_profile.go_offline()
            except Exception:
                pass
