from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.backoffice.utils import fcfa
from apps.backoffice.workers import BaseWorkerAdmin
from .models import Courier, CourierEarning


@admin.register(Courier)
class CourierAdmin(BaseWorkerAdmin):
    earnings_changelist = "admin:couriers_courierearning_changelist"
    earnings_filter = "courier__id__exact"
    fieldsets = (
        ("Compte", {"fields": ("user", "status", "is_available", "service_area")}),
        ("Véhicule", {"fields": (
            "vehicle_type", "vehicle_brand", "vehicle_model", "vehicle_year", "vehicle_color",
            "vehicle_plate", "chassis_number", "license_number",
        )}),
        ("Échéances réglementaires", {"fields": ("insurance_expiry", "vignette_expiry", "technical_visit_expiry")}),
        ("Colis acceptés", {"fields": (
            "max_package_size", "accepts_fragile", "accepts_documents", "delivery_zone_radius_km",
        )}),
        ("Activité", {"fields": (
            "rating", "total_trips", "total_earnings", "earnings_link",
            "last_known_location_display", "last_location_update", "created_at", "updated_at",
        )}),
    )


@admin.register(CourierEarning)
class CourierEarningAdmin(ModelAdmin):
    list_display = ["courier", "service_request", "gross", "commission", "net", "earned_at"]
    list_filter = ["earned_at"]
    search_fields = ["courier__user__phone", "courier__user__last_name"]
    list_select_related = ["courier__user", "service_request"]
    date_hierarchy = "earned_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description="Brut", ordering="gross_amount")
    def gross(self, obj):
        return fcfa(obj.gross_amount)

    @display(description="Commission", ordering="commission_amount")
    def commission(self, obj):
        return fcfa(obj.commission_amount)

    @display(description="Net coursier", ordering="net_amount")
    def net(self, obj):
        return fcfa(obj.net_amount)
