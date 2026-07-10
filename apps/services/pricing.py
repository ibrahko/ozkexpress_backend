"""
Tarification des livraisons — source de vérité côté serveur.

Alignée sur l'app mobile (MotoExpressApp/src/utils/constants.ts · DELIVERY_PRICING) :
    total = prise en charge (1 000 F) + 200 F/km + frais de service (220 F)

Les montants sont surchargables via settings :
    DELIVERY_BASE_FARE, DELIVERY_PER_KM, DELIVERY_SERVICE_FEE
"""
import math
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

BASE_FARE = Decimal(str(getattr(settings, "DELIVERY_BASE_FARE", 1000)))
PER_KM = Decimal(str(getattr(settings, "DELIVERY_PER_KM", 200)))
SERVICE_FEE = Decimal(str(getattr(settings, "DELIVERY_SERVICE_FEE", 220)))
MIN_DISTANCE_KM = Decimal("0.5")


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance à vol d'oiseau en km entre deux coordonnées."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_distance_km(pickup_point, delivery_point) -> Decimal:
    """Distance en km entre deux Points GIS (x = lng, y = lat), arrondie à 2 décimales."""
    km = haversine_km(pickup_point.y, pickup_point.x, delivery_point.y, delivery_point.x)
    km = max(km, float(MIN_DISTANCE_KM))
    return Decimal(str(km)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_delivery_price(distance_km) -> Decimal:
    """Prix total d'une livraison, arrondi au franc."""
    d = Decimal(str(distance_km))
    total = BASE_FARE + (d * PER_KM) + SERVICE_FEE
    return total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
