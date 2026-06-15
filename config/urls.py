from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({"status": "ok", "service": "MotoExpress API"})


API_V1 = "api/v1/"

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Health
    path("health/", health_check, name="health-check"),

    # API v1
    path(API_V1, include("apps.accounts.urls")),
    path(API_V1, include("apps.couriers.urls")),
    path(API_V1, include("apps.drivers.urls")),
    path(API_V1, include("apps.fleet.urls")),
    path(API_V1, include("apps.services.urls")),
    path(API_V1, include("apps.payments.urls")),
    path(API_V1, include("apps.tracking.urls")),
    path(API_V1, include("apps.disputes.urls")),
    path(API_V1, include("apps.notifications.urls")),
    path(API_V1, include("apps.analytics.urls")),
]

# Swagger / Redoc uniquement si drf-spectacular est disponible
try:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerUIView, SpectacularRedocView
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerUIView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]
except ImportError:
    pass

if settings.DEBUG:
    try:
        import debug_toolbar
        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
