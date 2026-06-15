from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Dispute, DisputeMessage, DisputeStatus


class DisputeMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source="sender.get_full_name", read_only=True)

    class Meta:
        model = DisputeMessage
        fields = ["id", "sender_name", "content", "attachment", "created_at"]
        read_only_fields = ["id", "created_at"]


class DisputeSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    messages = DisputeMessageSerializer(many=True, read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.get_full_name", read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "opened_by_name", "reason", "reason_display",
            "status", "status_display", "description", "resolution",
            "refund_amount", "service_request", "ride_request",
            "resolved_at", "created_at", "messages",
        ]
        read_only_fields = ["id", "status", "resolution", "refund_amount", "resolved_at", "created_at"]

    def create(self, validated_data):
        validated_data["opened_by"] = self.context["request"].user
        return super().create(validated_data)
