"""Rutas de la interfaz, el administrador, la autenticacion y la API."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView

from inventario.serializers import RoleTokenObtainPairView

urlpatterns = [
    path("", TemplateView.as_view(template_name="inventario/portal.html"), name="portal"),
    path("admin/", admin.site.urls),
    path("api/", include("inventario.urls")),
    path("api/token/", RoleTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]