from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RequestOTPView,
    VerifyOTPView,
    RefreshTokenView,
    LogoutView,
    MeView,
    UserAddressViewSet,
    PasswordLoginView,
    ChangePasswordView,
    CourierRegisterView,
    DriverRegisterView,
)

router = DefaultRouter()
router.register("addresses", UserAddressViewSet, basename="address")

urlpatterns = [
    # ── Auth OTP (clients) ──────────────────────────────────
    path("auth/otp/request/", RequestOTPView.as_view(), name="otp-request"),
    path("auth/otp/verify/", VerifyOTPView.as_view(), name="otp-verify"),

    # ── Auth mot de passe (coursiers & chauffeurs) ──────────
    path("auth/login/", PasswordLoginView.as_view(), name="password-login"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),

    # ── Inscription coursier & chauffeur ────────────────────
    path("auth/register/courier/", CourierRegisterView.as_view(), name="register-courier"),
    path("auth/register/driver/", DriverRegisterView.as_view(), name="register-driver"),

    # ── Tokens ──────────────────────────────────────────────
    path("auth/token/refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),

    # ── Profil ──────────────────────────────────────────────
    path("auth/me/", MeView.as_view(), name="me"),

    # ── Adresses ────────────────────────────────────────────
    path("", include(router.urls)),
]
