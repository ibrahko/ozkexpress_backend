"""
Tableau de bord d'accueil du back-office (UNFOLD["DASHBOARD_CALLBACK"]).
Bamako est à UTC+0 toute l'année : « aujourd'hui » = date UTC.
"""
import json
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.couriers.models import Courier, CourierEarning
from apps.disputes.models import Dispute, DisputeStatus
from apps.drivers.models import Driver, DriverEarning
from apps.payments.models import Wallet, WithdrawalRequest
from apps.services.models import RequestStatus, RideRequest, RideStatus, ServiceRequest
from apps.workforce.models import WorkerDocument, WorkerStatus
from .utils import fcfa

STALE_PENDING_MINUTES = 5
CHART_DAYS = 14


def _sum(qs, field):
    return qs.aggregate(total=Sum(field))["total"] or 0


def _kpis(today):
    deliveries = ServiceRequest.objects.filter(created_at__date=today)
    rides = RideRequest.objects.filter(created_at__date=today)
    revenue = _sum(
        ServiceRequest.objects.filter(delivered_at__date=today, status=RequestStatus.DELIVERED), "final_price"
    ) + _sum(RideRequest.objects.filter(completed_at__date=today, status=RideStatus.COMPLETED), "final_price")
    commissions = _sum(CourierEarning.objects.filter(earned_at__date=today), "commission_amount") + _sum(
        DriverEarning.objects.filter(earned_at__date=today), "commission_amount"
    )
    online = (
        Courier.objects.filter(status__in=[WorkerStatus.ONLINE, WorkerStatus.BUSY]).count()
        + Driver.objects.filter(status__in=[WorkerStatus.ONLINE, WorkerStatus.BUSY]).count()
    )
    in_progress = ServiceRequest.objects.filter(
        status__in=[RequestStatus.ACCEPTED, RequestStatus.PICKUP, RequestStatus.IN_PROGRESS]
    ).count() + RideRequest.objects.filter(
        status__in=[RideStatus.ACCEPTED, RideStatus.DRIVER_ARRIVING, RideStatus.IN_PROGRESS]
    ).count()
    return [
        {"title": "Commandes du jour", "value": deliveries.count() + rides.count(),
         "footer": f"{deliveries.count()} livraisons · {rides.count()} courses", "icon": "package_2"},
        {"title": "Chiffre d'affaires du jour", "value": fcfa(revenue),
         "footer": f"dont {fcfa(commissions)} de commissions", "icon": "payments"},
        {"title": "En cours maintenant", "value": in_progress,
         "footer": "livraisons et courses actives", "icon": "route"},
        {"title": "Travailleurs en ligne", "value": online,
         "footer": "coursiers et chauffeurs", "icon": "two_wheeler"},
    ]


def _todo():
    """Ce qui attend une action de l'équipe, avec un lien direct vers la liste filtrée."""
    stale = timezone.now() - timedelta(minutes=STALE_PENDING_MINUTES)
    pending_withdrawals = WithdrawalRequest.objects.filter(status=WithdrawalRequest.WithdrawalStatus.PENDING)
    debts = Wallet.objects.filter(balance__lt=0)
    items = [
        {
            "label": "Coursiers à valider",
            "count": Courier.objects.filter(status=WorkerStatus.PENDING).count(),
            "url": reverse("admin:couriers_courier_changelist") + "?todo=pending",
        },
        {
            "label": "Chauffeurs à valider",
            "count": Driver.objects.filter(status=WorkerStatus.PENDING).count(),
            "url": reverse("admin:drivers_driver_changelist") + "?todo=pending",
        },
        {
            "label": "Documents à vérifier",
            "count": WorkerDocument.objects.filter(is_verified=False, rejection_reason="").count(),
            "url": reverse("admin:workforce_workerdocument_changelist") + "?is_verified__exact=0",
        },
        {
            "label": "Retraits à traiter",
            "count": pending_withdrawals.count(),
            "detail": fcfa(_sum(pending_withdrawals, "amount")),
            "url": reverse("admin:payments_withdrawalrequest_changelist") + "?status__exact=pending",
        },
        {
            "label": "Litiges ouverts",
            "count": Dispute.objects.filter(status__in=[DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]).count(),
            "url": reverse("admin:disputes_dispute_changelist") + "?status__exact=open",
        },
        {
            "label": f"Livraisons sans coursier depuis plus de {STALE_PENDING_MINUTES} min",
            "count": ServiceRequest.objects.filter(status=RequestStatus.PENDING, created_at__lt=stale).count(),
            "url": reverse("admin:services_servicerequest_changelist") + "?status__exact=pending",
        },
        {
            "label": "Commissions espèces dues",
            "count": debts.count(),
            "detail": fcfa(-_sum(debts, "balance")),
            "url": reverse("admin:payments_wallet_changelist"),
        },
    ]
    return items


def _chart(today):
    start = today - timedelta(days=CHART_DAYS - 1)
    rows = (
        ServiceRequest.objects.filter(created_at__date__gte=start)
        .values("created_at__date")
        .annotate(
            delivered=Count("id", filter=Q(status=RequestStatus.DELIVERED)),
            cancelled=Count("id", filter=Q(status__in=[RequestStatus.CANCELLED, RequestStatus.FAILED])),
            other=Count("id", filter=~Q(status__in=[
                RequestStatus.DELIVERED, RequestStatus.CANCELLED, RequestStatus.FAILED,
            ])),
        )
    )
    by_day = {r["created_at__date"]: r for r in rows}
    days = [start + timedelta(days=i) for i in range(CHART_DAYS)]

    def series(key):
        return [by_day.get(d, {}).get(key, 0) for d in days]

    return json.dumps({
        "labels": [d.strftime("%d/%m") for d in days],
        "datasets": [
            {"label": "Livrées", "data": series("delivered"), "backgroundColor": "var(--color-primary-600)"},
            {"label": "En cours / en attente", "data": series("other"), "backgroundColor": "var(--color-primary-300)"},
            {"label": "Annulées", "data": series("cancelled"), "backgroundColor": "var(--color-base-300)"},
        ],
    })


def _latest_orders():
    orders = ServiceRequest.objects.select_related("client", "courier__user").order_by("-created_at")[:8]
    return {
        "headers": ["Commande", "Client", "Coursier", "Statut", "Prix"],
        "rows": [
            [
                f"#{str(o.pk)[:8]} · {timezone.localtime(o.created_at):%d/%m %H:%M}",
                o.client.get_full_name() or o.client.phone,
                (o.courier.user.get_full_name() or o.courier.user.phone) if o.courier else "—",
                o.get_status_display(),
                fcfa(o.final_price if o.final_price is not None else o.estimated_price),
            ]
            for o in orders
        ],
    }


def dashboard_callback(request, context):
    today = timezone.localdate()
    context.update({
        "kpis": _kpis(today),
        "todo": _todo(),
        "chart_data": _chart(today),
        "chart_title": f"Livraisons des {CHART_DAYS} derniers jours",
        "latest_orders": _latest_orders(),
        "orders_url": reverse("admin:services_servicerequest_changelist"),
    })
    return context
