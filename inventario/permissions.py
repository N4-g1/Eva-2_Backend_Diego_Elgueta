"""Permisos RBAC compartidos por las vistas de inventario y compra."""
from rest_framework.permissions import BasePermission


def user_role(user):
    if user.is_authenticated and (user.is_staff or user.groups.filter(name="Gestor de bodega").exists()):
        return "gestor_bodega"
    return "institucion_medica"


class IsWarehouseManager(BasePermission):
    """Autoriza solo a personal de bodega o administradores de Django."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and user_role(request.user) == "gestor_bodega"


class IsMedicalInstitution(BasePermission):
    """Restringe compras y carros a cuentas institucionales autenticadas."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and user_role(request.user) == "institucion_medica"