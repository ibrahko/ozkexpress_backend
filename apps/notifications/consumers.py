import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket pour les notifications temps réel."""

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or isinstance(self.user, AnonymousUser):
            await self.close(code=4001)
            return
        self.group_name = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("type") == "mark_read":
            notif_id = data.get("notification_id")
            if notif_id:
                await self.mark_notification_read(notif_id)

    async def notification_message(self, event):
        await self.send(json.dumps({
            "type": "notification",
            "id": event["id"],
            "notification_type": event["notification_type"],
            "title": event["title"],
            "body": event["body"],
            "data": event.get("data", {}),
        }))

    @database_sync_to_async
    def mark_notification_read(self, notif_id):
        from .models import Notification
        try:
            notif = Notification.objects.get(id=notif_id, recipient=self.user)
            notif.mark_read()
        except Notification.DoesNotExist:
            pass
