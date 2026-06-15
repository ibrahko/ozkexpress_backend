from rest_framework import viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_notification_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "notification_type", "type_display", "title", "body", "data", "is_read", "read_at", "created_at"]
        read_only_fields = fields


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notif = self.get_object()
        notif.mark_read()
        return Response({"detail": "Notification marquée comme lue."})

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        from django.utils import timezone
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"detail": "Toutes les notifications marquées comme lues."})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread_count": count})


router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [path("", include(router.urls))]
