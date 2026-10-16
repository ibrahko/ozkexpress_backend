from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from apps.backoffice.utils import STATUS_COLORS, fcfa, run_bulk
from .models import Transaction, Wallet, WithdrawalRequest


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    """Journal des paiements clients : consultation uniquement (seuls les webhooks le modifient)."""
    list_display = ["reference", "created_at", "client", "provider", "payment_type", "status_badge", "amount_display"]
    list_filter = ["status", "provider", "payment_type"]
    search_fields = ["reference", "provider_transaction_id", "client__phone", "phone_number"]
    list_select_related = ["client"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in Transaction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Statut", ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Montant", ordering="amount")
    def amount_display(self, obj):
        return fcfa(obj.amount)


class WithdrawalInline(TabularInline):
    model = WithdrawalRequest
    extra = 0
    fields = ["created_at", "amount", "provider", "phone_number", "status", "processed_at"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wallet)
class WalletAdmin(ModelAdmin):
    """
    Portefeuilles des coursiers et chauffeurs. Les montants ne se modifient
    jamais à la main : ils évoluent avec les livraisons et les retraits.
    """
    list_display = ["user", "user_type", "balance_display", "earned", "withdrawn", "updated_at"]
    list_filter = ["user__user_type"]
    search_fields = ["user__phone", "user__first_name", "user__last_name"]
    list_select_related = ["user"]
    readonly_fields = ["user", "balance", "total_earned", "total_withdrawn", "currency", "created_at", "updated_at"]
    inlines = [WithdrawalInline]
    ordering = ["balance"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Rôle", ordering="user__user_type")
    def user_type(self, obj):
        return obj.user.get_user_type_display()

    @display(description="Solde", ordering="balance", label={"debt": "danger", "ok": "success", "zero": "info"})
    def balance_display(self, obj):
        # Solde négatif = commissions dues sur des courses payées en espèces
        key = "debt" if obj.balance < 0 else ("ok" if obj.balance > 0 else "zero")
        return key, fcfa(obj.balance)

    @display(description="Total gagné", ordering="total_earned")
    def earned(self, obj):
        return fcfa(obj.total_earned)

    @display(description="Total retiré", ordering="total_withdrawn")
    def withdrawn(self, obj):
        return fcfa(obj.total_withdrawn)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(ModelAdmin):
    list_display = ["created_at", "worker", "amount_display", "balance", "provider", "phone_number", "status_badge", "processed_at"]
    list_filter = ["status", "provider"]
    search_fields = ["wallet__user__phone", "wallet__user__last_name", "phone_number"]
    list_select_related = ["wallet__user"]
    readonly_fields = ["wallet", "amount", "provider", "phone_number", "status", "processed_at", "created_at"]
    fields = ["wallet", "amount", "provider", "phone_number", "status", "admin_note", "processed_at", "created_at"]
    actions = ["approve", "reject", "mark_paid"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="Travailleur", ordering="wallet__user__last_name")
    def worker(self, obj):
        user = obj.wallet.user
        return f"{user.get_full_name() or user.phone} ({user.get_user_type_display()})"

    @display(description="Montant", ordering="amount")
    def amount_display(self, obj):
        return fcfa(obj.amount)

    @display(description="Solde actuel")
    def balance(self, obj):
        return fcfa(obj.wallet.balance)

    @display(description="Statut", ordering="status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @action(description="1. Approuver (débite le portefeuille)")
    def approve(self, request, queryset):
        run_bulk(self, request, queryset, "approve", "retrait(s) approuvé(s)",
                 note=f"Approuvé par {request.user.phone}")

    @action(description="2. Marquer comme payés (argent envoyé)")
    def mark_paid(self, request, queryset):
        run_bulk(self, request, queryset, "mark_paid", "retrait(s) marqué(s) payé(s)",
                 note=f"Payé par {request.user.phone}")

    @action(description="Refuser")
    def reject(self, request, queryset):
        run_bulk(self, request, queryset, "reject", "retrait(s) refusé(s)",
                 note=f"Refusé par {request.user.phone}")
