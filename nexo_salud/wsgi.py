"""Configuracion WSGI para ejecutar Nexo Salud en un servidor web."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexo_salud.settings")
application = get_wsgi_application()