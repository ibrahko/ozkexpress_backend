from django.contrib import admin
from django.utils import timezone
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.backoffice.utils import STATUS_COLORS, fcfa
from .models import Dispute, DisputeMessage, DisputeStatus


class DisputeMessageInline(TabularInline):
    model = DisputeMessage
    extra = 1
    fields = ["created_at", "sender", "content", "attachment"]
    readonly_fields = ["created_at"]
    autocomplete_fields = ["sender"]


@admin.register(Dispute)
class DisputeAdmin(ModelAdmin):
    list_display = ["short_id", "created_at", "opened_by", "reason", "status_badge", "assigned_to", "refund"]
    list_filter = ["status", "reason", "assigned_to"]
    search_fields = ["id", "opened_by__phone", "opened_by__last_name", "description"]
    list_select_related = ["opened_by", "assigned_to"]
    autocomplete_fields = ["opened_by", "assigned_to", "service_request", "ride_request"]
    readonly_fields = ["created_at", "resolved_at"]
    inlines = [DisputeMessageInline]
    actions = ["take_ownership", "mark_resolved"]
    fieldsets = (
        ("Litige", {"fields": ("status", "reason", "opened_by", "assigned_to", "description")}),
        ("Commande concernée", {"fields": ("service_request", "ride_request")}),
        ("Résolution", {"fields": ("resolution", "refund_amount", "resolved_at", "created_at")}),
    )

    @display(description="Réf.")
    def short_id(self, obj):
        return f"#{str(obj.pk)[:8]}"

    @display(description="Statut", ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Remboursement")
    def refund(self, obj):
        return fcfa(obj.refund_amount) if obj.refund_amount else "—"

    @action(description="M'attribuer ces litiges")
    def take_ownership(self, request, queryset):
        n = queryset.filter(status=DisputeStatus.OPEN).update(
            assigned_to=request.user, status=DisputeStatus.UNDER_REVIEW,
        )
        self.message_user(request, f"{n} litige(s) pris en charge.")

    @action(description="Marquer comme résolus")
    def mark_resolved(self, request, queryset):
        n = queryset.exclude(status__in=[DisputeStatus.RESOLVED, DisputeStatus.CLOSED]).update(
            status=DisputeStatus.RESOLVED, resolved_at=timezone.now(),
        )
        self.message_user(request, f"{n} litige(s) résolu(s). Pensez à renseigner la résolution.")

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data and obj.status == DisputeStatus.RESOLVED and not obj.resolved_at:
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)
