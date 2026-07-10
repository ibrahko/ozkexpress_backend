from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from core.throttles import OtpVerifyThrottle, OtpRequestThrottle
from .models import User, UserAddress
from .serializers import (
    PhoneSerializer,
    OTPVerifySerializer,
    UserSerializer,
    UserUpdateSerializer,
    UserAddressSerializer,
    TokenResponseSerializer,
    PasswordLoginSerializer,
    ChangePasswordSerializer,
    CourierRegisterSerializer,
    DriverRegisterSerializer,
)
from .services import OTPService, AuthService


class RequestOTPView(generics.GenericAPIView):
    """
    POST /api/v1/auth/otp/request/
    Envoie un code OTP par SMS.
    """
    serializer_class = PhoneSerializer
    permission_classes = [AllowAny]
    throttle_classes = [OtpRequestThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        success = OTPService.request_otp(phone)

        if not success:
            return Response(
                {"detail": "Impossible d'envoyer le SMS. Réessayez."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response(
            {"detail": f"Code OTP envoyé au {phone}."},
            status=status.HTTP_200_OK
        )


class VerifyOTPView(generics.GenericAPIView):
    """
    POST /api/v1/auth/otp/verify/
    Vérifie l'OTP et authentifie l'utilisateur (ou le crée s'il est nouveau).
    """
    serializer_class = OTPVerifySerializer
    permission_classes = [AllowAny]
    throttle_classes = [OtpVerifyThrottle]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        user_type = serializer.validated_data["user_type"]
        otp = serializer.validated_data["otp"]

        # Consommer l'OTP
        otp.consume()

        # Récupérer ou créer l'utilisateur
        user, is_new = AuthService.get_or_create_user(phone, user_type)

        # Lier l'OTP à l'utilisateur
        if not otp.user:
            otp.user = user
            otp.save(update_fields=["user"])

        tokens = AuthService.get_tokens_for_user(user)

        return Response({
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": UserSerializer(user).data,
            "is_new_user": is_new,
        }, status=status.HTTP_200_OK)


class RefreshTokenView(generics.GenericAPIView):
    """
    POST /api/v1/auth/token/refresh/
    Renouvelle l'access token via le refresh token.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token requis."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            return Response({"access": str(token.access_token)})
        except TokenError as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(generics.GenericAPIView):
    """
    POST /api/v1/auth/logout/
    Blackliste le refresh token.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token requis."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Déconnexion réussie."}, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"detail": "Token invalide."}, status=status.HTTP_400_BAD_REQUEST)


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/   → profil de l'utilisateur connecté
    PATCH /api/v1/auth/me/  → mise à jour du profil
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UserUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user


class UserAddressViewSet(viewsets.ModelViewSet):
    """
    CRUD des adresses sauvegardées de l'utilisateur connecté.
    GET    /api/v1/addresses/
    POST   /api/v1/addresses/
    PATCH  /api/v1/addresses/{id}/
    DELETE /api/v1/addresses/{id}/
    """
    serializer_class = UserAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def set_default(self, request, pk=None):
        address = self.get_object()
        UserAddress.objects.filter(user=request.user, is_default=True).update(is_default=False)
        address.is_default = True
        address.save(update_fields=["is_default"])
        return Response(self.get_serializer(address).data)


# ── Auth par mot de passe (coursiers & chauffeurs) ────────────────────────────

class PasswordLoginView(generics.GenericAPIView):
    """
    POST /api/v1/auth/login/
    Connexion par téléphone + mot de passe.
    Utilisé par les coursiers et chauffeurs.
    Mot de passe par défaut = numéro de téléphone (à changer après la 1ère connexion).
    """
    serializer_class = PasswordLoginSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        tokens = AuthService.get_tokens_for_user(user)
        return Response({
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": UserSerializer(user).data,
            "password_is_default": user.check_password(user.phone),
        }, status=status.HTTP_200_OK)


class ChangePasswordView(generics.GenericAPIView):
    """
    POST /api/v1/auth/change-password/
    Changement de mot de passe (authentifié requis).
    """
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Mot de passe modifié avec succès."}, status=status.HTTP_200_OK)


# ── Inscription coursier & chauffeur ──────────────────────────────────────────

class CourierRegisterView(generics.GenericAPIView):
    """
    POST /api/v1/auth/register/courier/
    Inscription d'un nouveau coursier avec toutes les infos véhicule.
    Crée un compte User + profil Courier en attente de validation admin.
    Mot de passe initial = numéro de téléphone.
    """
    serializer_class = CourierRegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = AuthService.get_tokens_for_user(user)
        return Response({
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": UserSerializer(user).data,
            "message": (
                "Inscription réussie. Votre dossier est en cours de validation. "
                "Votre mot de passe actuel est votre numéro de téléphone — "
                "pensez à le changer dès votre première connexion."
            ),
        }, status=status.HTTP_201_CREATED)


class DriverRegisterView(generics.GenericAPIView):
    """
    POST /api/v1/auth/register/driver/
    Inscription d'un nouveau chauffeur.
    Même logique que le coursier.
    """
    serializer_class = DriverRegisterSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = AuthService.get_tokens_for_user(user)
        return Response({
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "user": UserSerializer(user).data,
            "message": (
                "Inscription réussie. Votre dossier est en cours de validation. "
                "Votre mot de passe actuel est votre numéro de téléphone — "
                "pensez à le changer dès votre première connexion."
            ),
        }, status=status.HTTP_201_CREATED)
