from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Handler global d'exceptions DRF.
    Retourne toujours une réponse JSON structurée.
    """
    # Convertir les exceptions Django standard en DRF
    if isinstance(exc, Http404):
        from rest_framework.exceptions import NotFound
        exc = NotFound()
    elif isinstance(exc, PermissionDenied):
        from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
        exc = DRFPermissionDenied()

    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "success": False,
            "error": {
                "code": getattr(exc, "default_code", "error"),
                "message": str(exc.detail) if hasattr(exc, "detail") else str(exc),
                "status_code": response.status_code,
            }
        }

        # Détails de validation (erreurs par champ)
        if hasattr(exc, "detail") and isinstance(exc.detail, dict):
            error_data["error"]["fields"] = exc.detail

        response.data = error_data

    return response


class BusinessLogicError(APIException):
    """Exception pour les erreurs métier (pas des erreurs serveur)."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_error"

    def __init__(self, detail, code=None):
        self.detail = detail
        if code:
            self.default_code = code


class ServiceUnavailableError(APIException):
    """Exception pour les services tiers indisponibles."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "service_unavailable"
