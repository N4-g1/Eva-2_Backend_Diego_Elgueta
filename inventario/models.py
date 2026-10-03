"""Modelos relacionales del catalogo y el ciclo de abastecimiento."""
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


# --- Categorias: el slug se usa en filtros publicos sin exponer IDs internos. ---
class Category(models.Model):
    name = models.CharField("nombre", max_length=80, unique=True)
    slug = models.SlugField("identificador", max_length=90, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return self.name


# --- Insumos: cada lote conserva vencimiento y stock; nombre+lote es unico. ---
class Supply(models.Model):
    name = models.CharField("nombre comercial", max_length=140)
    active_ingredient = models.CharField("principio activo o detalle", max_length=180)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="supplies")
    lot = models.CharField("lote", max_length=60, db_index=True)
    expiry_date = models.DateField("fecha de vencimiento")
    unit_price = models.DecimalField("precio por caja", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    stock = models.PositiveIntegerField("cajas disponibles")
    is_active = models.BooleanField("visible en catalogo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "lot"]
        # No se puede confundir un lote nuevo con otro ya registrado para el insumo.
        constraints = [models.UniqueConstraint(fields=["name", "lot"], name="unique_supply_name_lot")]
        verbose_name = "insumo"
        verbose_name_plural = "insumos"

    def __str__(self):
        return f"{self.name} · {self.lot}"


# --- Carro: OneToOne mantiene un carro persistente por cuenta institucional. ---
class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="medical_cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carro de {self.user}"


# --- Items de carro: se guarda cantidad, pero no se reserva stock al agregar. ---
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Supply, on_delete=models.PROTECT, related_name="cart_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        # La restriccion evita duplicados; la vista suma cantidades al mismo item.
        constraints = [models.UniqueConstraint(fields=["cart", "product"], name="unique_product_per_cart")]
        ordering = ["id"]


# --- Orden: UUID identifica cada solicitud y CHOICES limita sus estados validos. ---
class Order(models.Model):
    class Status(models.TextChoices):
        PAID = "PAGADO", "Pagado"
        PREPARING = "EN_PREPARACION", "En preparacion"
        DISPATCHED = "EN_DESPACHO", "En despacho"
        DELIVERED = "ENTREGADO", "Entregado"
        CANCELLED = "CANCELADO", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="medical_orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PAID, db_index=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    # La marca evita reponer existencias mas de una vez ante una cancelacion.
    stock_restored = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Solicitud {self.id} · {self.get_status_display()}"


# --- Detalle de orden: copia nombre, lote y precio para preservar el historial. ---
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    supply = models.ForeignKey(Supply, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=140)
    lot = models.CharField(max_length=60)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["id"]