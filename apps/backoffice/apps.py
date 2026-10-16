from django.apps import AppConfig


class BackofficeConfig(AppConfig):
    """Back-office OzkExpress : tableau de bord et utilitaires de l'admin (django-unfold)."""
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backoffice"
    verbose_name = "Back-office"
