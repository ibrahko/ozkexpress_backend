from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class OtpVerifyThrottle(UserRateThrottle):
    """Anti-brute-force sur la vérification OTP."""
    scope = "otp_verify"


class OtpRequestThrottle(AnonRateThrottle):
    """Limite les demandes d'envoi de SMS OTP."""
    scope = "otp_request"


class PaymentInitiateThrottle(UserRateThrottle):
    """Limite les tentatives de paiement successives."""
    scope = "payment_initiate"


class ServiceCreateThrottle(UserRateThrottle):
    """Limite la création de commandes de livraison."""
    scope = "service_create"


class CourierLocationThrottle(UserRateThrottle):
    """Limite les mises à jour de position GPS coursier."""
    scope = "courier_location"
