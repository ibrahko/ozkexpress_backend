import time


class TimingMiddleware:
    """Ajoute le header X-Response-Time à chaque réponse."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = round((time.time() - start) * 1000)
        response["X-Response-Time"] = f"{duration_ms}ms"
        return response
