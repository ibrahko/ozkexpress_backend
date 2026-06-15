import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.railway")

django_asgi_app = get_asgi_application()

from apps.tracking.routing import websocket_urlpatterns as tracking_ws
from apps.notifications.routing import websocket_urlpatterns as notifications_ws


class JWTAuthMiddleware:
    """Middleware WebSocket qui authentifie via JWT passé en query param ?token=..."""
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        from urllib.parse import parse_qs
        from django.contrib.auth.models import AnonymousUser
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]
        scope["user"] = await self._get_user(token)
        return await self.inner(scope, receive, send)

    @staticmethod
    async def _get_user(token):
        from channels.db import database_sync_to_async
        from django.contrib.auth.models import AnonymousUser

        if not token:
            return AnonymousUser()

        @database_sync_to_async
        def get_user():
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from apps.accounts.models import User
                decoded = AccessToken(token)
                return User.objects.get(id=decoded["user_id"])
            except Exception:
                return AnonymousUser()

        return await get_user()


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(tracking_ws + notifications_ws)
        )
    ),
})
