from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Dispute, DisputeMessage
from .serializers import DisputeSerializer, DisputeMessageSerializer


class DisputeViewSet(viewsets.ModelViewSet):
    serializer_class = DisputeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Dispute.objects.select_related("opened_by").prefetch_related("messages").all()
        return Dispute.objects.prefetch_related("messages").filter(opened_by=user)

    @action(detail=True, methods=["post"])
    def message(self, request, pk=None):
        dispute = self.get_object()
        serializer = DisputeMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(dispute=dispute, sender=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
