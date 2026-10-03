"""Senales para que toda cuenta tenga un carro persistente desde su creacion."""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from inventario.models import Cart


# --- Alta de usuario: crea el carro 1:1 y evita depender de la sesion web. ---
@receiver(post_save, sender=get_user_model())
def create_user_cart(sender, instance, created, **kwargs):
    # Solo se ejecuta al crear la cuenta; get_or_create mantiene la senal idempotente.
    if created:
        Cart.objects.get_or_create(user=instance)