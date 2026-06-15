from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """L'objet doit appartenir à l'utilisateur connecté."""
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsClient(BasePermission):
    """L'utilisateur doit avoir le rôle client."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "client"


class IsCourier(BasePermission):
    """L'utilisateur doit avoir le rôle coursier."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "courier"


class IsDriver(BasePermission):
    """L'utilisateur doit avoir le rôle chauffeur."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == "driver"


class IsCourierOrDriver(BasePermission):
    """L'utilisateur doit être coursier ou chauffeur."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.user_type in ("courier", "driver")
        )


class IsAdminUser(BasePermission):
    """L'utilisateur doit être staff Django."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff
