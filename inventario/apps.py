"""Aplicacion de catalogo, carros institucionales e inventario."""
from django.apps import AppConfig


class InventarioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventario"
    verbose_name = "Abastecimiento medico"

    def ready(self):
        import inventario.signals  # noqa: F401