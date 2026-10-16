from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.backoffice.utils import fcfa
from apps.backoffice.workers import BaseWorkerAdmin
from .models import Driver, DriverEarning


@admin.register(Driver)
class DriverAdmin(BaseWorkerAdmin):
    earnings_changelist = "admin:drivers_driverearning_changelist"
    earnings_filter = "driver__id__exact"
    fieldsets = (
        ("Compte", {"fields": ("user", "status", "is_available", "service_type")}),
        ("Véhicule", {"fields": (
            "vehicle_type", "vehicle_category", "vehicle_brand", "vehicle_model", "vehicle_year",
            "vehicle_color", "vehicle_plate", "chassis_number", "license_number",
            "passenger_capacity", "owns_vehicle",
        )}),
        ("Échéances réglementaires", {"fields": ("insurance_expiry", "vignette_expiry", "technical_visit_expiry")}),
        ("Activité", {"fields": (
            "rating", "total_trips", "total_earnings", "earnings_link",
            "last_known_location_display", "last_location_update", "created_at", "updated_at",
        )}),
    )


@admin.register(DriverEarning)
class DriverEarningAdmin(ModelAdmin):
    list_display = ["driver", "ride_request", "gross", "commission", "net", "earned_at"]
    list_filter = ["earned_at"]
    search_fields = ["driver__user__phone", "driver__user__last_name"]
    list_select_related = ["driver__user", "ride_request"]
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

    @display(description="Net chauffeur", ordering="net_amount")
    def net(self, obj):
        return fcfa(obj.net_amount)
