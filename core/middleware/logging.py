import logging
import time

logger = logging.getLogger("apps")


class LoggingMiddleware:
    """Log chaque requête avec méthode, path, status et durée."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = round((time.time() - start) * 1000)

        request_id = getattr(request, "request_id", "-")
        user_id = str(request.user.id) if request.user.is_authenticated else "anonymous"

        logger.info(
            "%s %s %s | user=%s | request_id=%s | %dms",
            request.method,
            request.path,
            response.status_code,
            user_id,
            request_id,
            duration_ms,
        )
        return response
