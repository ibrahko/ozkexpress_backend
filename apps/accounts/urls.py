from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RequestOTPView,
    VerifyOTPView,
    RefreshTokenView,
    LogoutView,
    MeView,
    UserAddressViewSet,
)

router = DefaultRouter()
router.register("addresses", UserAddressViewSet, basename="address")

urlpatterns = [
    # Auth OTP
    path("auth/otp/request/", RequestOTPView.as_view(), name="otp-request"),
    path("auth/otp/verify/", VerifyOTPView.as_view(), name="otp-verify"),
    path("auth/token/refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),

    # Profil
    path("auth/me/", MeView.as_view(), name="me"),

    # Adresses
    path("", include(router.urls)),
]
