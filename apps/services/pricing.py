"""
Tarification des livraisons et des courses — source de vérité côté serveur.

Formule :
    total = (prise en charge + distance × tarif/km) × majoration + frais de service

Résolution de la distance (du plus précis au moins précis) :
    1. Matrice de distances entre quartiers (ZoneDistance, saisie dans l'admin)
    2. OSRM si OSRM_URL est configuré (distance routière réelle)
    3. Haversine × facteur routier (défaut 1.3)

Majorations (multiplicateur sur prise en charge + distance, jamais sur les frais) :
    - Nuit (21 h – 6 h, heure de Bamako) : PRICING_NIGHT_MULTIPLIER (défaut 1.0 = désactivé)
    - Forte demande / pluie : PRICING_SURGE_MULTIPLIER (défaut 1.0, à piloter via env)

Monitoring : tout prix total > PRICE_ALERT_THRESHOLD (défaut 20 000 F) est loggé
en warning (visible dans Sentry si configuré).

Montants surchargeables via settings :
    DELIVERY_BASE_FARE, DELIVERY_PER_KM, DELIVERY_SERVICE_FEE,
    RIDE_BASE_FARE, RIDE_PER_KM, RIDE_SERVICE_FEE,
    DELIVERY_ROAD_FACTOR, ZONE_SNAP_RADIUS_KM, OSRM_URL,
    PRICING_NIGHT_MULTIPLIER, PRICING_NIGHT_START_HOUR, PRICING_NIGHT_END_HOUR,
    PRICING_SURGE_MULTIPLIER, PRICE_ALERT_THRESHOLD
"""
import logging
import math
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

logger = logging.getLogger(__name__)

# Livraisons (colis)
BASE_FARE = Decimal(str(getattr(settings, "DELIVERY_BASE_FARE", 1000)))
PER_KM = Decimal(str(getattr(settings, "DELIVERY_PER_KM", 200)))
SERVICE_FEE = Decimal(str(getattr(settings, "DELIVERY_SERVICE_FEE", 220)))

# Courses (transport de personnes) — même barème par défaut, ajustable séparément
RIDE_BASE_FARE = Decimal(str(getattr(settings, "RIDE_BASE_FARE", 1000)))
RIDE_PER_KM = Decimal(str(getattr(settings, "RIDE_PER_KM", 200)))
RIDE_SERVICE_FEE = Decimal(str(getattr(settings, "RIDE_SERVICE_FEE", 220)))

MIN_DISTANCE_KM = Decimal("0.5")
# La distance routière réelle est ~30 % plus longue que le vol d'oiseau
ROAD_FACTOR = Decimal(str(getattr(settings, "DELIVERY_ROAD_FACTOR", 1.3)))

# Rayon (km) pour rattacher un point au quartier le plus proche
ZONE_SNAP_RADIUS_KM = float(getattr(settings, "ZONE_SNAP_RADIUS_KM", 1.5))

# OSRM auto-hébergé (ex: "http://osrm.interne:5000") — vide = désactivé
OSRM_URL = getattr(settings, "OSRM_URL", "")

# Majorations
NIGHT_MULTIPLIER = Decimal(str(getattr(settings, "PRICING_NIGHT_MULTIPLIER", 1.0)))
NIGHT_START_HOUR = int(getattr(settings, "PRICING_NIGHT_START_HOUR", 21))
NIGHT_END_HOUR = int(getattr(settings, "PRICING_NIGHT_END_HOUR", 6))
SURGE_MULTIPLIER = Decimal(str(getattr(settings, "PRICING_SURGE_MULTIPLIER", 1.0)))

# Seuil d'alerte prix aberrant
PRICE_ALERT_THRESHOLD = Decimal(str(getattr(settings, "PRICE_ALERT_THRESHOLD", 20000)))


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


def snap_to_zone(point):
    """
    Quartier actif le plus proche du point (x = lng, y = lat), ou None
    si aucun n'est à moins de ZONE_SNAP_RADIUS_KM.
    """
    from .models import Zone

    best, best_km = None, ZONE_SNAP_RADIUS_KM
    for zone in Zone.objects.filter(is_active=True):
        km = haversine_km(point.y, point.x, zone.center.y, zone.center.x)
        if km <= best_km:
            best, best_km = zone, km
    return best


def _matrix_distance_km(pickup_point, delivery_point):
    """Distance de la matrice quartier→quartier si les deux points s'y rattachent."""
    try:
        from .models import ZoneDistance

        z1 = snap_to_zone(pickup_point)
        z2 = snap_to_zone(delivery_point)
        if not z1 or not z2 or z1.pk == z2.pk:
            return None
        entry = (
            ZoneDistance.objects.filter(zone_from=z1, zone_to=z2).first()
            or ZoneDistance.objects.filter(zone_from=z2, zone_to=z1).first()
        )
        return Decimal(str(entry.road_km)) if entry else None
    except Exception:  # DB indisponible (tests unitaires purs…) → fallback
        return None


def _osrm_distance_km(pickup_point, delivery_point):
    """Distance routière via OSRM (si configuré). Fail-soft : None en cas d'erreur."""
    if not OSRM_URL:
        return None
    try:
        import requests

        url = (
            f"{OSRM_URL.rstrip('/')}/route/v1/driving/"
            f"{pickup_point.x},{pickup_point.y};{delivery_point.x},{delivery_point.y}"
            f"?overview=false"
        )
        res = requests.get(url, timeout=2)
        res.raise_for_status()
        data = res.json()
        meters = data["routes"][0]["distance"]
        return Decimal(str(meters / 1000.0))
    except Exception as exc:  # réseau, format, timeout… → fallback haversine
        logger.warning("OSRM indisponible (%s), fallback haversine", exc)
        return None


def compute_distance_km(pickup_point, delivery_point) -> Decimal:
    """
    Distance routière estimée en km entre deux Points GIS (x = lng, y = lat).
    Matrice quartiers → OSRM → haversine × facteur routier. Min 0,5 km.
    """
    km = _matrix_distance_km(pickup_point, delivery_point)
    if km is None:
        km = _osrm_distance_km(pickup_point, delivery_point)
    if km is None:
        km = Decimal(str(
            haversine_km(pickup_point.y, pickup_point.x, delivery_point.y, delivery_point.x)
        )) * ROAD_FACTOR
    km = max(km, MIN_DISTANCE_KM)
    return Decimal(km).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def current_multiplier(when=None) -> Decimal:
    """
    Multiplicateur en vigueur : nuit × forte demande.
    `when` : datetime aware (défaut : maintenant, heure locale du serveur).
    """
    from django.utils import timezone

    when = when or timezone.localtime()
    hour = when.hour
    is_night = hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR
    multiplier = SURGE_MULTIPLIER * (NIGHT_MULTIPLIER if is_night else Decimal("1.0"))
    return multiplier.quantize(Decimal("0.01"))


def _compute_price(distance_km, base, per_km, fee, multiplier=None) -> Decimal:
    d = Decimal(str(distance_km))
    m = multiplier if multiplier is not None else current_multiplier()
    total = (base + d * per_km) * m + fee
    total = total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if total > PRICE_ALERT_THRESHOLD:
        logger.warning(
            "Prix aberrant détecté : %s FCFA (distance=%s km, multiplicateur=%s)",
            total, d, m,
        )
    return total


def compute_delivery_price(distance_km, multiplier=None) -> Decimal:
    """Prix total d'une livraison, arrondi au franc."""
    return _compute_price(distance_km, BASE_FARE, PER_KM, SERVICE_FEE, multiplier)


def compute_ride_price(distance_km, multiplier=None) -> Decimal:
    """Prix total d'une course, arrondi au franc."""
    return _compute_price(distance_km, RIDE_BASE_FARE, RIDE_PER_KM, RIDE_SERVICE_FEE, multiplier)


def quote(pickup_point, delivery_point, kind: str = "delivery") -> dict:
    """
    Devis détaillé pour l'app mobile (endpoint /quote/).
    kind : "delivery" ou "ride".
    """
    distance = compute_distance_km(pickup_point, delivery_point)
    multiplier = current_multiplier()
    if kind == "ride":
        base, per_km, fee = RIDE_BASE_FARE, RIDE_PER_KM, RIDE_SERVICE_FEE
        total = compute_ride_price(distance, multiplier)
    else:
        base, per_km, fee = BASE_FARE, PER_KM, SERVICE_FEE
        total = compute_delivery_price(distance, multiplier)
    distance_fee = (distance * per_km).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    surcharge = total - (base + distance_fee + fee)
    return {
        "kind": kind,
        "distance_km": float(distance),
        "base": int(base),
        "per_km": int(per_km),
        "distance_fee": int(distance_fee),
        "service_fee": int(fee),
        "multiplier": float(multiplier),
        "surcharge": int(surcharge),
        "total": int(total),
    }
