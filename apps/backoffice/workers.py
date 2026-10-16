"""Base commune des ModelAdmin Coursier et Chauffeur (même modèle BaseWorker)."""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import GenericTabularInline, ModelAdmin
from unfold.decorators import action, display

from apps.workforce.models import WorkerDocument, WorkerStatus
from .utils import STATUS_COLORS, fcfa, run_bulk


class WorkerDocumentInline(GenericTabularInline):
    model = WorkerDocument
    extra = 0
    fields = ["doc_type", "file", "is_verified", "verified_at", "rejection_reason"]
    readonly_fields = ["verified_at"]


class PendingValidationFilter(admin.SimpleListFilter):
    title = "à traiter"
    parameter_name = "todo"

    def lookups(self, request, model_admin):
        return [
            ("pending", "En attente de validation"),
            ("placeholder", "Infos véhicule provisoires (TMP-…)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(status=WorkerStatus.PENDING)
        if self.value() == "placeholder":
            return queryset.filter(vehicle_plate__startswith="TMP-")
        return queryset


class BaseWorkerAdmin(ModelAdmin):
    earnings_changelist = None  # ex. "admin:couriers_courierearning_changelist"
    earnings_filter = None      # ex. "courier__id__exact"

    list_display = [
        "worker_name", "phone", "status_badge", "plate", "vehicle_type",
        "rating", "total_trips", "wallet_balance", "documents_state",
    ]
    list_filter = [PendingValidationFilter, "status", "vehicle_type", "is_available"]
    search_fields = ["user__phone", "user__first_name", "user__last_name", "vehicle_plate", "license_number"]
    list_select_related = ["user", "user__wallet"]
    autocomplete_fields = ["user"]
    readonly_fields = [
        "rating", "total_trips", "total_earnings", "last_known_location_display",
        "last_location_update", "earnings_link", "created_at", "updated_at",
    ]
    inlines = [WorkerDocumentInline]
    actions = ["approve_workers", "suspend_workers"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("documents")

    @display(description="Nom", ordering="user__last_name")
    def worker_name(self, obj):
        return obj.user.get_full_name() or "—"

    @display(description="Téléphone", ordering="user__phone")
    def phone(self, obj):
        return obj.user.phone

    @display(description="Statut", ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Plaque", ordering="vehicle_plate", label={"provisoire": "warning"})
    def plate(self, obj):
        if obj.vehicle_plate.startswith("TMP-"):
            return "provisoire", "Provisoire"
        return obj.vehicle_plate

    @display(description="Solde")
    def wallet_balance(self, obj):
        wallet = getattr(obj.user, "wallet", None)
        return fcfa(wallet.balance) if wallet else "—"

    @display(description="Documents", label={"ok": "success", "todo": "warning", "none": "danger"})
    def documents_state(self, obj):
        docs = list(obj.documents.all())
        if not docs:
            return "none", "Aucun"
        pending = sum(1 for d in docs if not d.is_verified)
        if pending:
            return "todo", f"{pending} à vérifier"
        return "ok", f"{len(docs)} vérifiés"

    @display(description="Dernière position")
    def last_known_location_display(self, obj):
        p = obj.last_known_location
        if not p:
            return "—"
        return format_html(
            '<a href="https://www.google.com/maps?q={},{}" target="_blank" rel="noopener">{}, {}</a>',
            p.y, p.x, round(p.y, 5), round(p.x, 5),
        )

    @display(description="Gains")
    def earnings_link(self, obj):
        url = reverse(self.earnings_changelist) + f"?{self.earnings_filter}={obj.pk}"
        return format_html('<a href="{}">Voir l’historique des gains</a>', url)

    @action(description="Valider les comptes sélectionnés")
    def approve_workers(self, request, queryset):
        run_bulk(self, request, queryset, "approve", "compte(s) validé(s)")

    @action(description="Suspendre les comptes sélectionnés")
    def suspend_workers(self, request, queryset):
        run_bulk(self, request, queryset, "suspend", "compte(s) suspendu(s)")
