"""Petits utilitaires partagés par les ModelAdmin du back-office."""
from decimal import Decimal

from django.contrib import messages


def fcfa(amount) -> str:
    """1925.00 → « 1 925 F » (espace insécable entre les milliers)."""
    if amount is None:
        return "—"
    value = int(Decimal(amount).quantize(Decimal("1")))
    return f"{value:,}".replace(",", "\u00a0") + "\u00a0F"


# Couleurs des badges de statut (variantes de label Unfold)
STATUS_COLORS = {
    # Commandes / courses
    "pending": "warning",
    "accepted": "info",
    "pickup": "info",
    "driver_arriving": "info",
    "in_progress": "info",
    "delivered": "success",
    "completed": "success",
    "cancelled": "danger",
    "failed": "danger",
    # Travailleurs
    "active": "success",
    "online": "success",
    "offline": "info",
    "busy": "info",
    "suspended": "danger",
    # Paiements / retraits
    "processing": "info",
    "refunded": "warning",
    "approved": "info",
    "paid": "success",
    "rejected": "danger",
    # Litiges
    "open": "danger",
    "under_review": "warning",
    "resolved": "success",
    "closed": "info",
}


def run_bulk(modeladmin, request, queryset, method_name, success_label, **kwargs):
    """
    Applique `obj.<method_name>(**kwargs)` à chaque élément sélectionné.
    Les erreurs métier (transition interdite, solde insuffisant…) sont
    affichées par élément sans interrompre le reste du lot.
    """
    done, errors = 0, []
    for obj in queryset:
        try:
            getattr(obj, method_name)(**kwargs)
            done += 1
        except Exception as exc:  # erreur métier lisible pour l'opérateur
            detail = getattr(exc, "detail", None) or str(exc)
            errors.append(f"{obj} : {detail}")
    if done:
        modeladmin.message_user(request, f"{done} {success_label}.", messages.SUCCESS)
    for error in errors:
        modeladmin.message_user(request, error, messages.ERROR)
