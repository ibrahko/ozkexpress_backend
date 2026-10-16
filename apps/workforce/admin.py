from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from .models import WorkerDocument


@admin.register(WorkerDocument)
class WorkerDocumentAdmin(ModelAdmin):
    list_display = ["owner", "doc_type", "file_link", "verified_badge", "created_at", "verified_by"]
    list_filter = ["is_verified", "doc_type", "content_type"]
    list_select_related = ["content_type", "verified_by"]
    readonly_fields = ["owner", "file_link", "verified_at", "verified_by", "created_at"]
    fields = [
        "owner", "doc_type", "file", "file_link", "is_verified",
        "rejection_reason", "verified_at", "verified_by", "created_at",
    ]
    actions = ["verify_documents", "reject_documents"]

    def has_add_permission(self, request):
        # Les documents sont ajoutés depuis la fiche du coursier ou du chauffeur
        return False

    @display(description="Travailleur")
    def owner(self, obj):
        model = obj.content_type.model_class()
        worker = model.objects.select_related("user").filter(pk=obj.object_id).first() if model else None
        if not worker:
            return "—"
        return f"{worker.user.get_full_name() or worker.user.phone} ({model._meta.verbose_name})"

    @display(description="Fichier")
    def file_link(self, obj):
        if not obj.file:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Ouvrir</a>', obj.file.url)

    @display(description="Vérification", label={"ok": "success", "rejected": "danger", "todo": "warning"})
    def verified_badge(self, obj):
        if obj.is_verified:
            return "ok", "Vérifié"
        if obj.rejection_reason:
            return "rejected", "Refusé"
        return "todo", "À vérifier"

    @action(description="Marquer comme vérifiés")
    def verify_documents(self, request, queryset):
        n = queryset.update(
            is_verified=True, verified_at=timezone.now(), verified_by=request.user, rejection_reason="",
        )
        self.message_user(request, f"{n} document(s) vérifié(s).")

    @action(description="Refuser (à refaire par le travailleur)")
    def reject_documents(self, request, queryset):
        n = queryset.update(
            is_verified=False, verified_at=timezone.now(), verified_by=request.user,
            rejection_reason="Document refusé : illisible, expiré ou non conforme.",
        )
        self.message_user(request, f"{n} document(s) refusé(s). Précisez le motif dans chaque fiche si besoin.")

    def save_model(self, request, obj, form, change):
        # Cocher « vérifié » à la main enregistre aussi qui l'a fait et quand
        if "is_verified" in form.changed_data and obj.is_verified:
            obj.verified_at, obj.verified_by = timezone.now(), request.user
        super().save_model(request, obj, form, change)
