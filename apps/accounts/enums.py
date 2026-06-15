from django.db import models


class UserType(models.TextChoices):
    CLIENT = "client", "Client"
    COURIER = "courier", "Coursier"
    DRIVER = "driver", "Chauffeur"
    ADMIN = "admin", "Administrateur"


class UserStatus(models.TextChoices):
    ACTIVE = "active", "Actif"
    INACTIVE = "inactive", "Inactif"
    SUSPENDED = "suspended", "Suspendu"
    PENDING_VERIFICATION = "pending", "En attente de vérification"
