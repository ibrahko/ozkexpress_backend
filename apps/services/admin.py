from django import forms
from django.contrib import admin
from django.contrib.gis.geos import Point
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.backoffice.utils import STATUS_COLORS, fcfa, run_bulk
from .models import (
    CancellationReason, Message, RideRequest, ServiceRequest, Zone, ZoneDistance,
)


def map_link(point, label=None):
    if not point:
        return "—"
    return format_html(
        '<a href="https://www.google.com/maps?q={},{}" target="_blank" rel="noopener">{}</a>',
        point.y, point.x, label or "Voir sur la carte",
    )


class OrderAdminMixin:
    """Commun aux livraisons et aux courses : lecture seule, annulation contrôlée."""

    list_per_page = 50
    date_hierarchy = "created_at"
    actions = ["cancel_orders"]

    def has_add_permission(self, request):
        # Les commandes naissent dans l'app mobile, jamais au back-office
        return False

    def has_delete_permission(self, request, obj=None):
        # On annule, on ne supprime pas : l'historique sert aux litiges et à la compta
        return False

    @display(description="Réf.", ordering="created_at")
    def short_id(self, obj):
        return f"#{str(obj.pk)[:8]}"

    @display(description="Client", ordering="client__last_name")
    def client_display(self, obj):
        return obj.client.get_full_name() or obj.client.phone

    @display(description="Statut", ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Prix", ordering="estimated_price")
    def price(self, obj):
        return fcfa(obj.final_price if obj.final_price is not None else obj.estimated_price)


class MessageInline(TabularInline):
    model = Message
    extra = 0
    fields = ["created_at", "sender", "body", "read_at"]
    readonly_fields = fields
    can_delete = False
    verbose_name_plural = "Messagerie client ↔ coursier"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ServiceRequest)
class ServiceRequestAdmin(OrderAdminMixin, ModelAdmin):
    list_display = [
        "short_id", "created_at", "client_display", "courier", "route",
        "status_badge", "payment_method", "price",
    ]
    list_filter = ["status", "payment_method", "assignment_type", "is_fragile", "package_size"]
    search_fields = [
        "id", "client__phone", "client__last_name", "courier__user__phone",
        "pickup_address", "delivery_address", "pickup_contact_phone", "delivery_contact_phone",
    ]
    list_select_related = ["client", "courier__user"]
    inlines = [MessageInline]
    readonly_fields = [
        "client", "courier", "preferred_courier", "pickup_map", "delivery_map",
        "estimated_price", "final_price", "distance_km", "tip_amount",
        "pickup_zone", "delivery_zone", "assignment_type", "broadcast_radius_km",
        "payment_method", "status", "cancellation_reason", "cancellation_note",
        "accepted_at", "picked_up_at", "delivered_at", "cancelled_at",
        "client_rating", "client_review", "created_at", "updated_at",
    ]
    fieldsets = (
        ("Commande", {"fields": (
            "status", "client", "courier", "assignment_type", "preferred_courier", "broadcast_radius_km",
        )}),
        ("Départ", {"fields": (
            "pickup_address", "pickup_map", "pickup_zone", "pickup_contact_name",
            "pickup_contact_phone", "pickup_instructions",
        )}),
        ("Arrivée", {"fields": (
            "delivery_address", "delivery_map", "delivery_zone", "delivery_contact_name",
            "delivery_contact_phone", "delivery_instructions",
        )}),
        ("Colis", {"fields": ("package_description", "package_size", "is_fragile", "estimated_weight_kg")}),
        ("Prix & paiement", {"fields": (
            "distance_km", "estimated_price", "final_price", "tip_amount", "payment_method",
        )}),
        ("Chronologie", {"fields": (
            "created_at", "accepted_at", "picked_up_at", "delivered_at", "cancelled_at",
            "cancellation_reason", "cancellation_note", "updated_at",
        )}),
        ("Évaluation", {"fields": ("client_rating", "client_review")}),
    )

    @display(description="Trajet")
    def route(self, obj):
        z_from = obj.pickup_zone.name if obj.pickup_zone else obj.pickup_address[:30]
        z_to = obj.delivery_zone.name if obj.delivery_zone else obj.delivery_address[:30]
        return f"{z_from} → {z_to}"

    @display(description="Position de départ")
    def pickup_map(self, obj):
        return map_link(obj.pickup_location)

    @display(description="Position d'arrivée")
    def delivery_map(self, obj):
        return map_link(obj.delivery_location)

    @action(description="Annuler les commandes sélectionnées (support)")
    def cancel_orders(self, request, queryset):
        run_bulk(
            self, request, queryset, "cancel", "commande(s) annulée(s)",
            reason=CancellationReason.OTHER, note=f"Annulée par le support ({request.user.phone})",
        )


@admin.register(RideRequest)
class RideRequestAdmin(OrderAdminMixin, ModelAdmin):
    list_display = ["short_id", "created_at", "client_display", "driver", "route", "status_badge", "price"]
    list_filter = ["status", "client_has_own_vehicle"]
    search_fields = ["id", "client__phone", "client__last_name", "driver__user__phone", "pickup_address", "dropoff_address"]
    list_select_related = ["client", "driver__user"]
    readonly_fields = [
        "client", "driver", "fleet_rental", "pickup_map", "dropoff_map",
        "estimated_price", "final_price", "distance_km", "duration_minutes", "tip_amount",
        "pickup_zone", "dropoff_zone", "status", "accepted_at", "started_at",
        "completed_at", "cancelled_at", "client_rating", "client_review", "created_at", "updated_at",
    ]
    fieldsets = (
        ("Course", {"fields": ("status", "client", "driver", "fleet_rental", "client_has_own_vehicle", "passenger_count")}),
        ("Trajet", {"fields": (
            "pickup_address", "pickup_map", "pickup_zone", "dropoff_address", "dropoff_map",
            "dropoff_zone", "special_instructions",
        )}),
        ("Prix", {"fields": ("distance_km", "duration_minutes", "estimated_price", "final_price", "tip_amount")}),
        ("Chronologie", {"fields": ("created_at", "accepted_at", "started_at", "completed_at", "cancelled_at", "updated_at")}),
        ("Évaluation", {"fields": ("client_rating", "client_review")}),
    )

    @display(description="Trajet")
    def route(self, obj):
        z_from = obj.pickup_zone.name if obj.pickup_zone else obj.pickup_address[:30]
        z_to = obj.dropoff_zone.name if obj.dropoff_zone else obj.dropoff_address[:30]
        return f"{z_from} → {z_to}"

    @display(description="Position de départ")
    def pickup_map(self, obj):
        return map_link(obj.pickup_location)

    @display(description="Position d'arrivée")
    def dropoff_map(self, obj):
        return map_link(obj.dropoff_location)

    @action(description="Annuler les courses sélectionnées (support)")
    def cancel_orders(self, request, queryset):
        run_bulk(self, request, queryset, "cancel", "course(s) annulée(s)")


# ── Tarifs : quartiers et matrice de distances ──────────────────────────────

class ZoneForm(forms.ModelForm):
    """Saisie du centre d'un quartier en latitude / longitude (copiées depuis Google Maps)."""
    latitude = forms.FloatField(min_value=-90, max_value=90, help_text="Ex. 12.6392 (Bamako)")
    longitude = forms.FloatField(min_value=-180, max_value=180, help_text="Ex. -8.0029 (Bamako)")

    class Meta:
        model = Zone
        fields = ["name", "commune", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.center:
            self.fields["latitude"].initial = self.instance.center.y
            self.fields["longitude"].initial = self.instance.center.x

    def save(self, commit=True):
        self.instance.center = Point(
            self.cleaned_data["longitude"], self.cleaned_data["latitude"], srid=4326
        )
        return super().save(commit)


@admin.register(Zone)
class ZoneAdmin(ModelAdmin):
    form = ZoneForm
    list_display = ["name", "commune", "center_link", "is_active"]
    list_filter = ["commune", "is_active"]
    search_fields = ["name", "commune"]
    fields = ["name", "commune", "latitude", "longitude", "is_active"]

    @display(description="Centre")
    def center_link(self, obj):
        return map_link(obj.center, f"{obj.center.y:.4f}, {obj.center.x:.4f}" if obj.center else None)


@admin.register(ZoneDistance)
class ZoneDistanceAdmin(ModelAdmin):
    list_display = ["zone_from", "zone_to", "road_km", "is_active"]
    list_filter = ["is_active", "zone_from__commune"]
    search_fields = ["zone_from__name", "zone_to__name"]
    autocomplete_fields = ["zone_from", "zone_to"]
    list_select_related = ["zone_from", "zone_to"]
