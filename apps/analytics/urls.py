from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.urls import path
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta


class DashboardStatsView(APIView):
    """GET /api/v1/analytics/dashboard/ — Stats globales pour admin."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.services.models import ServiceRequest, RideRequest
        from apps.payments.models import Transaction, PaymentStatus
        from apps.accounts.models import User

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Revenus
        revenue_today = Transaction.objects.filter(
            status=PaymentStatus.COMPLETED,
            completed_at__date=today,
        ).aggregate(total=Sum("amount"))["total"] or 0

        revenue_month = Transaction.objects.filter(
            status=PaymentStatus.COMPLETED,
            completed_at__date__gte=month_ago,
        ).aggregate(total=Sum("amount"))["total"] or 0

        # Commandes
        deliveries_today = ServiceRequest.objects.filter(created_at__date=today).count()
        rides_today = RideRequest.objects.filter(created_at__date=today).count()

        # Utilisateurs
        new_users_week = User.objects.filter(created_at__date__gte=week_ago).count()

        return Response({
            "revenue": {
                "today": float(revenue_today),
                "month": float(revenue_month),
            },
            "orders": {
                "deliveries_today": deliveries_today,
                "rides_today": rides_today,
            },
            "users": {
                "new_this_week": new_users_week,
                "total": User.objects.count(),
            },
        })


class WorkerStatsView(APIView):
    """GET /api/v1/analytics/worker/ — Stats personnelles d'un travailleur."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        period = request.query_params.get("period", "month")
        days = {"week": 7, "month": 30, "year": 365}.get(period, 30)
        since = timezone.now() - timedelta(days=days)

        if user.user_type == "courier":
            from apps.services.models import ServiceRequest, RequestStatus
            qs = ServiceRequest.objects.filter(
                courier__user=user, created_at__gte=since
            )
            completed = qs.filter(status=RequestStatus.DELIVERED)
            return Response({
                "total_trips": completed.count(),
                "total_distance_km": float(completed.aggregate(d=Sum("distance_km"))["d"] or 0),
                "avg_rating": float(completed.aggregate(r=Avg("client_rating"))["r"] or 0),
                "earnings": float(
                    user.courier_profile.earnings.filter(earned_at__gte=since)
                    .aggregate(t=Sum("net_amount"))["t"] or 0
                ),
            })

        elif user.user_type == "driver":
            from apps.services.models import RideRequest, RideStatus
            qs = RideRequest.objects.filter(
                driver__user=user, created_at__gte=since
            )
            completed = qs.filter(status=RideStatus.COMPLETED)
            return Response({
                "total_trips": completed.count(),
                "total_distance_km": float(completed.aggregate(d=Sum("distance_km"))["d"] or 0),
                "avg_rating": float(completed.aggregate(r=Avg("client_rating"))["r"] or 0),
                "earnings": float(
                    user.driver_profile.earnings.filter(earned_at__gte=since)
                    .aggregate(t=Sum("net_amount"))["t"] or 0
                ),
            })

        return Response({"detail": "Pas de stats disponibles pour ce type d'utilisateur."})


urlpatterns = [
    path("analytics/dashboard/", DashboardStatsView.as_view(), name="analytics-dashboard"),
    path("analytics/worker/", WorkerStatsView.as_view(), name="analytics-worker"),
]
