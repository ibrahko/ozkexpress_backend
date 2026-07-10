"""
Reçu PDF d'une livraison (écran H2 du mobile).

GET /api/v1/services/{id}/receipt/
Auth : header Authorization OU ?token=<access JWT> (pour ouverture directe
dans le navigateur depuis l'app mobile via Linking.openURL).
"""
import io
from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ServiceRequest, RequestStatus


def _user_from_request(request):
    """Utilisateur authentifié par header DRF ou par ?token= (JWT access)."""
    if request.user and request.user.is_authenticated:
        return request.user
    token = request.query_params.get("token")
    if not token:
        return None
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        from apps.accounts.models import User
        decoded = AccessToken(token)
        return User.objects.get(id=decoded["user_id"])
    except Exception:
        return None


class ServiceReceiptView(APIView):
    permission_classes = [AllowAny]  # contrôle manuel (header ou ?token=)

    def get(self, request, pk):
        user = _user_from_request(request)
        if user is None:
            return Response({"detail": "Authentification requise."}, status=status.HTTP_401_UNAUTHORIZED)

        req = get_object_or_404(ServiceRequest, pk=pk)
        is_client = req.client_id == user.id
        is_courier = req.courier is not None and req.courier.user_id == user.id
        if not (is_client or is_courier or user.is_staff):
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)
        if req.status != RequestStatus.DELIVERED:
            return Response(
                {"detail": "Le reçu n'est disponible qu'après la livraison."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from reportlab.lib.pagesizes import A5
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
        except ImportError:
            return Response(
                {"detail": "Génération PDF indisponible (installer reportlab)."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        from .pricing import BASE_FARE, PER_KM, SERVICE_FEE

        ref = f"#{str(req.id)[:8].upper()}"
        total = req.final_price or req.estimated_price or Decimal("0")
        distance = req.distance_km
        distance_fee = (Decimal(str(distance)) * PER_KM).quantize(Decimal("1")) if distance else None

        buf = io.BytesIO()
        w, h = A5
        p = canvas.Canvas(buf, pagesize=A5)

        # En-tête
        p.setFillColorRGB(1, 0.42, 0)  # orange MotoExpress
        p.rect(0, h - 30 * mm, w, 30 * mm, fill=1, stroke=0)
        p.setFillColorRGB(1, 1, 1)
        p.setFont("Helvetica-Bold", 18)
        p.drawString(15 * mm, h - 15 * mm, "MotoExpress")
        p.setFont("Helvetica", 10)
        p.drawString(15 * mm, h - 22 * mm, f"Reçu de livraison {ref}")

        y = h - 42 * mm
        p.setFillColorRGB(0.07, 0.09, 0.15)

        def line(label, value, bold=False):
            nonlocal y
            p.setFont("Helvetica", 9)
            p.drawString(15 * mm, y, label)
            p.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
            p.drawRightString(w - 15 * mm, y, str(value))
            y -= 7 * mm

        date_str = req.delivered_at.strftime("%d/%m/%Y %H:%M") if req.delivered_at else "—"
        line("Date de livraison", date_str)
        line("Récupération", (req.pickup_address or "")[:55])
        line("Livraison", (req.delivery_address or "")[:55])
        line("Remis à", req.delivery_contact_name or "—")
        if req.courier:
            line("Coursier", req.courier.user.get_full_name())
        y -= 3 * mm
        p.line(15 * mm, y, w - 15 * mm, y)
        y -= 8 * mm

        line("Prise en charge", f"{BASE_FARE:,.0f} FCFA".replace(",", " "))
        if distance_fee is not None:
            line(f"Distance ({distance} km)", f"{distance_fee:,.0f} FCFA".replace(",", " "))
        line("Frais de service", f"{SERVICE_FEE:,.0f} FCFA".replace(",", " "))
        y -= 2 * mm
        p.line(15 * mm, y, w - 15 * mm, y)
        y -= 8 * mm
        p.setFont("Helvetica-Bold", 12)
        p.drawString(15 * mm, y, f"Total ({req.get_payment_method_display()})")
        p.drawRightString(w - 15 * mm, y, f"{total:,.0f} FCFA".replace(",", " "))

        p.setFont("Helvetica", 7)
        p.setFillColorRGB(0.5, 0.5, 0.5)
        p.drawCentredString(w / 2, 12 * mm, "Merci d'avoir choisi MotoExpress — Vite. Fiable. Partout.")

        p.showPage()
        p.save()
        buf.seek(0)

        response = HttpResponse(buf.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="recu-{ref[1:]}.pdf"'
        return response
