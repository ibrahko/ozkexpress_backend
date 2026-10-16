from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.backoffice.utils import fcfa
from .models import Vehicle, VehicleRental


@admin.register(Vehicle)
class VehicleAdmin(ModelAdmin):
    list_display = ["plate_number", "brand", "model", "vehicle_type", "status", "rate", "insurance_expiry"]
    list_filter = ["status", "vehicle_type", "requires_driver"]
    search_fields = ["plate_number", "brand", "model", "chassis_number"]

    @display(description="Tarif / jour", ordering="daily_rate")
    def rate(self, obj):
        return fcfa(obj.daily_rate)


@admin.register(VehicleRental)
class VehicleRentalAdmin(ModelAdmin):
    list_display = ["vehicle", "client", "status", "start_date", "end_date", "price", "with_driver"]
    list_filter = ["status", "with_driver", "deposit_returned"]
    search_fields = ["client__phone", "client__last_name", "vehicle__plate_number"]
    list_select_related = ["vehicle", "client"]
    autocomplete_fields = ["client", "vehicle", "driver"]
    date_hierarchy = "start_date"

    @display(description="Prix", ordering="total_price")
    def price(self, obj):
        return fcfa(obj.total_price)
