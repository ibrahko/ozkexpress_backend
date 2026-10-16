"""
Tableau de bord d'accueil du back-office (UNFOLD["DASHBOARD_CALLBACK"]).
Bamako est à UTC+0 toute l'année : « aujourd'hui » = date UTC.
"""
import json
import os
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from apps.couriers.models import Courier, CourierEarning
from apps.disputes.models import Dispute, DisputeStatus
from apps.drivers.models import Driver, DriverEarning
from apps.payments.models import Wallet, WithdrawalRequest
from apps.services.models import RequestStatus, RideRequest, RideStatus, ServiceRequest
from apps.workforce.models import WorkerDocument, WorkerStatus
from .utils import STATUS_COLORS, fcfa

STALE_PENDING_MINUTES = 5
CHART_DAYS = 14
BAMAKO = {"lat": 12.6392, "lng": -8.0029}

ACTIVE_DELIVERY = [RequestStatus.ACCEPTED, RequestStatus.PICKUP, RequestStatus.IN_PROGRESS]
ACTIVE_RIDE = [RideStatus.ACCEPTED, RideStatus.DRIVER_ARRIVING, RideStatus.IN_PROGRESS]
ONLINE = [WorkerStatus.ONLINE, WorkerStatus.BUSY]


def environment_callback(request):
    """Badge d'environnement en haut à droite (UNFOLD["ENVIRONMENT"])."""
    if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(("railway", "production")):
        return ["Production", "danger"]
    return ["Développement", "warning"]


# ── Séries quotidiennes ─────────────────────────────────────────────────────

def _daily(qs, date_field, value=None):
    """{date: valeur} sur la fenêtre du graphique (nombre, ou somme de `value`)."""
    agg = Sum(value) if value else Count("id")
    rows = qs.annotate(day=TruncDate(date_field)).values("day").annotate(v=agg)
    return {r["day"]: r["v"] or 0 for r in rows}


def _series(days, *mappings):
    return [sum(m.get(d, 0) for m in mappings) for d in days]


def _sparkline(values, width=120, height=36):
    """Points d'une polyligne SVG (valeurs normalisées dans la boîte)."""
    if not values:
        return ""
    top = max(values) or 1
    step = width / max(len(values) - 1, 1)
    return " ".join(
        f"{round(i * step, 1)},{round(height - 3 - (v / top) * (height - 6), 1)}"
        for i, v in enumerate(values)
    )


def _trend(today, yesterday):
    if not yesterday:
        return None if not today else {"direction": "up", "text": "nouveau"}
    change = round((today - yesterday) / yesterday * 100)
    if change == 0:
        return {"direction": "flat", "text": "= hier"}
    return {"direction": "up" if change > 0 else "down", "text": f"{abs(change)} % vs hier"}


def _kpis(days):
    start = days[0]
    delivered = ServiceRequest.objects.filter(status=RequestStatus.DELIVERED, delivered_at__date__gte=start)
    completed = RideRequest.objects.filter(status=RideStatus.COMPLETED, completed_at__date__gte=start)

    orders = _series(
        days,
        _daily(ServiceRequest.objects.filter(created_at__date__gte=start), "created_at"),
        _daily(RideRequest.objects.filter(created_at__date__gte=start), "created_at"),
    )
    revenue = _series(
        days,
        _daily(delivered, "delivered_at", "final_price"),
        _daily(completed, "completed_at", "final_price"),
    )
    commissions = _series(
        days,
        _daily(CourierEarning.objects.filter(earned_at__date__gte=start), "earned_at", "commission_amount"),
        _daily(DriverEarning.objects.filter(earned_at__date__gte=start), "earned_at", "commission_amount"),
    )
    in_progress = (
        ServiceRequest.objects.filter(status__in=ACTIVE_DELIVERY).count()
        + RideRequest.objects.filter(status__in=ACTIVE_RIDE).count()
    )
    waiting = ServiceRequest.objects.filter(status=RequestStatus.PENDING).count()
    online = Courier.objects.filter(status__in=ONLINE).count() + Driver.objects.filter(status__in=ONLINE).count()
    busy = Courier.objects.filter(status=WorkerStatus.BUSY).count() + Driver.objects.filter(status=WorkerStatus.BUSY).count()

    return [
        {
            "label": "Commandes du jour", "icon": "package_2", "value": orders[-1],
            "trend": _trend(orders[-1], orders[-2]), "spark": _sparkline(orders),
        },
        {
            "label": "Chiffre d'affaires", "icon": "payments", "value": fcfa(revenue[-1]),
            "trend": _trend(revenue[-1], revenue[-2]), "spark": _sparkline(revenue),
            "sub": f"{fcfa(commissions[-1])} de commissions",
        },
        {
            "label": "En cours", "icon": "route", "value": in_progress,
            "sub": f"{waiting} en attente de coursier" if waiting else "aucune commande en attente",
            "alert": waiting > 0,
        },
        {
            "label": "Travailleurs en ligne", "icon": "two_wheeler", "value": online,
            "sub": f"dont {busy} en course" if online else "personne n'est en ligne",
        },
    ]


def _todo():
    """Ce qui attend une action de l'équipe, avec un lien direct vers la liste filtrée."""
    stale = timezone.now() - timedelta(minutes=STALE_PENDING_MINUTES)
    pending_withdrawals = WithdrawalRequest.objects.filter(status=WithdrawalRequest.WithdrawalStatus.PENDING)
    debts = Wallet.objects.filter(balance__lt=0)
    amount = lambda qs, f: qs.aggregate(t=Sum(f))["t"] or 0  # noqa: E731
    items = [
        {
            "label": f"Livraisons sans coursier depuis +{STALE_PENDING_MINUTES} min", "icon": "timer",
            "level": "danger",
            "count": ServiceRequest.objects.filter(status=RequestStatus.PENDING, created_at__lt=stale).count(),
            "url": reverse("admin:services_servicerequest_changelist") + "?status__exact=pending",
        },
        {
            "label": "Litiges ouverts", "icon": "gavel", "level": "danger",
            "count": Dispute.objects.filter(status__in=[DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]).count(),
            "url": reverse("admin:disputes_dispute_changelist") + "?status__exact=open",
        },
        {
            "label": "Retraits à traiter", "icon": "account_balance", "level": "warning",
            "count": pending_withdrawals.count(), "detail": fcfa(amount(pending_withdrawals, "amount")),
            "url": reverse("admin:payments_withdrawalrequest_changelist") + "?status__exact=pending",
        },
        {
            "label": "Coursiers à valider", "icon": "how_to_reg", "level": "warning",
            "count": Courier.objects.filter(status=WorkerStatus.PENDING).count(),
            "url": reverse("admin:couriers_courier_changelist") + "?todo=pending",
        },
        {
            "label": "Chauffeurs à valider", "icon": "how_to_reg", "level": "warning",
            "count": Driver.objects.filter(status=WorkerStatus.PENDING).count(),
            "url": reverse("admin:drivers_driver_changelist") + "?todo=pending",
        },
        {
            "label": "Documents à vérifier", "icon": "badge", "level": "warning",
            "count": WorkerDocument.objects.filter(is_verified=False, rejection_reason="").count(),
            "url": reverse("admin:workforce_workerdocument_changelist") + "?is_verified__exact=0",
        },
        {
            "label": "Commissions espèces dues", "icon": "savings", "level": "info",
            "count": debts.count(), "detail": fcfa(-amount(debts, "balance")),
            "url": reverse("admin:payments_wallet_changelist") + "?o=3",
        },
    ]
    # Les urgences d'abord, puis ce qui est vide
    items.sort(key=lambda i: (i["count"] == 0, ["danger", "warning", "info"].index(i["level"])))
    return items


def _chart(days):
    start = days[0]
    qs = ServiceRequest.objects.filter(created_at__date__gte=start)
    delivered = _daily(qs.filter(status=RequestStatus.DELIVERED), "created_at")
    cancelled = _daily(qs.filter(status__in=[RequestStatus.CANCELLED, RequestStatus.FAILED]), "created_at")
    total = _daily(qs, "created_at")
    other = {d: total.get(d, 0) - delivered.get(d, 0) - cancelled.get(d, 0) for d in days}
    return json.dumps({
        "labels": [d.strftime("%d/%m") for d in days],
        "datasets": [
            {"label": "Livrées", "data": _series(days, delivered),
             "backgroundColor": "var(--ozk-chart-done)", "borderRadius": 6, "maxBarThickness": 22},
            {"label": "En cours", "data": _series(days, other),
             "backgroundColor": "var(--ozk-chart-open)", "borderRadius": 6, "maxBarThickness": 22},
            {"label": "Annulées", "data": _series(days, cancelled),
             "backgroundColor": "var(--ozk-chart-cancel)", "borderRadius": 6, "maxBarThickness": 22},
        ],
    })


def _live_map():
    """Coursiers/chauffeurs en ligne et commandes en attente, pour la carte Leaflet."""
    recent = timezone.now() - timedelta(minutes=30)
    workers = []
    for model, kind in ((Courier, "Coursier"), (Driver, "Chauffeur")):
        for w in model.objects.filter(
            status__in=ONLINE, last_known_location__isnull=False, last_location_update__gte=recent,
        ).select_related("user")[:200]:
            workers.append({
                "lat": w.last_known_location.y, "lng": w.last_known_location.x,
                "name": w.user.get_full_name(), "kind": kind, "busy": w.status == WorkerStatus.BUSY,
            })
    orders = [
        {
            "lat": o.pickup_location.y, "lng": o.pickup_location.x,
            "label": f"#{str(o.pk)[:8]} · {o.pickup_address[:40]}",
            "url": reverse("admin:services_servicerequest_change", args=[o.pk]),
        }
        for o in ServiceRequest.objects.filter(status=RequestStatus.PENDING).order_by("-created_at")[:100]
    ]
    return json.dumps({"center": BAMAKO, "workers": workers, "orders": orders})


def _top_couriers(days):
    week_start = days[-7]
    rows = (
        CourierEarning.objects.filter(earned_at__date__gte=week_start)
        .values("courier", "courier__user__first_name", "courier__user__last_name",
                "courier__user__phone", "courier__rating")
        .annotate(deliveries=Count("id"), net=Sum("net_amount"))
        .order_by("-deliveries", "-net")[:5]
    )
    top = []
    for r in rows:
        name = f'{r["courier__user__first_name"]} {r["courier__user__last_name"]}'.strip() or r["courier__user__phone"]
        initials = "".join(p[0] for p in name.split()[:2]).upper() if name[0].isalpha() else "#"
        top.append({
            "name": name, "initials": initials, "deliveries": r["deliveries"], "net": fcfa(r["net"]),
            "rating": r["courier__rating"],
            "url": reverse("admin:couriers_courier_change", args=[r["courier"]]),
        })
    return top


def _latest_orders():
    orders = ServiceRequest.objects.select_related("client", "courier__user", "pickup_zone", "delivery_zone")
    return [
        {
            "ref": f"#{str(o.pk)[:8]}",
            "url": reverse("admin:services_servicerequest_change", args=[o.pk]),
            "when": timezone.localtime(o.created_at),
            "client": o.client.get_full_name(),
            "courier": o.courier.user.get_full_name() if o.courier else None,
            "route": (
                f'{o.pickup_zone.name if o.pickup_zone else o.pickup_address[:24]}'
                f' → {o.delivery_zone.name if o.delivery_zone else o.delivery_address[:24]}'
            ),
            "status": o.get_status_display(),
            "status_variant": STATUS_COLORS.get(o.status, "info"),
            "price": fcfa(o.final_price if o.final_price is not None else o.estimated_price),
        }
        for o in orders.order_by("-created_at")[:8]
    ]


def dashboard_callback(request, context):
    now = timezone.localtime()
    today = now.date()
    days = [today - timedelta(days=CHART_DAYS - 1 - i) for i in range(CHART_DAYS)]
    todo = _todo()
    context.update({
        "title": "Tableau de bord",
        "greeting": "Bonsoir" if now.hour >= 18 else "Bonjour",
        "first_name": request.user.first_name or "",
        "today": now,
        "kpis": _kpis(days),
        "todo": todo,
        "todo_open": sum(1 for i in todo if i["count"]),
        "chart_data": _chart(days),
        "chart_title": f"Livraisons · {CHART_DAYS} derniers jours",
        "map_data": _live_map(),
        "top_couriers": _top_couriers(days),
        "latest_orders": _latest_orders(),
        "orders_url": reverse("admin:services_servicerequest_changelist"),
        "couriers_url": reverse("admin:couriers_courier_changelist"),
    })
    return context
