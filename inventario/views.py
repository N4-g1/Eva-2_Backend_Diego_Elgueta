"""Vistas DRF con catalogo publico, RBAC y checkout transaccional."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from inventario.filters import SupplyFilter
from inventario.models import Cart, CartItem, Category, Order, OrderItem, Supply
from inventario.permissions import IsMedicalInstitution, IsWarehouseManager
from inventario.serializers import (
    CartItemSerializer,
    CartItemQuantitySerializer,
    CartItemWriteSerializer,
    CategorySerializer,
    OrderSerializer,
    OrderStatusSerializer,
    RegisterSerializer,
    SupplySerializer,
)


# --- Registro publico: el serializer crea cuentas cliente y mantiene role de solo lectura. ---
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


# --- Categorias: lectura abierta para poblar filtros; escritura solo para bodega. ---
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [AllowAny()]
        return [IsAuthenticated(), IsWarehouseManager()]


# --- Insumos: filtros/busqueda publicos, altas y cambios protegidos por RBAC. ---
class SupplyViewSet(viewsets.ModelViewSet):
    serializer_class = SupplySerializer
    filterset_class = SupplyFilter
    search_fields = ["name", "active_ingredient", "lot"]
    ordering_fields = ["name", "unit_price", "expiry_date", "stock"]
    ordering = ["name", "lot"]

    def get_queryset(self):
        # El catalogo oculta insumos retirados; bodega puede pedirlos para gestion.
        queryset = Supply.objects.select_related("category")
        if not (self.request.user.is_authenticated and (self.request.user.is_staff or self.request.user.groups.filter(name="Gestor de bodega").exists())):
            return queryset.filter(is_active=True)
        if self.request.query_params.get("include_inactive") != "true":
            return queryset.filter(is_active=True)
        return queryset

    def get_permissions(self):
        # Solo consulta es publica; las mutaciones exigen usuario y rol de bodega.
        if self.action in {"list", "retrieve"}:
            return [AllowAny()]
        return [IsAuthenticated(), IsWarehouseManager()]

    def destroy(self, request, *args, **kwargs):
        # Se rechaza retirar productos de ordenes activas para poder reponer stock.
        supply = self.get_object()
        active_orders = OrderItem.objects.filter(supply=supply).exclude(
            order__status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED]
        ).exists()
        if active_orders:
            return Response({"detail": "No se puede retirar: hay una solicitud activa con este insumo."}, status=409)
        # El retiro logico conserva las FK del historial y limpia carros pendientes.
        CartItem.objects.filter(product=supply).delete()
        supply.is_active = False
        supply.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Carro persistente: cada operacion consulta unicamente el carro del usuario autenticado. ---
class CartItemCollectionView(APIView):
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(responses=CartItemSerializer(many=True))
    def get(self, request):
        # Se crea el carro si falta y se incluyen producto/categoria en una consulta.
        cart, _ = Cart.objects.get_or_create(user=request.user)
        items = cart.items.select_related("product", "product__category").all()
        return Response(CartItemSerializer(items, many=True).data)

    @extend_schema(request=CartItemWriteSerializer, responses={201: CartItemSerializer, 200: CartItemSerializer})
    def post(self, request):
        # La transaccion y el bloqueo del carro evitan duplicar el mismo producto.
        # Aqui solo se guarda la cantidad; el stock se valida al confirmar el pago.
        serializer = CartItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            cart, _ = Cart.objects.select_for_update().get_or_create(user=request.user)
            item, created = CartItem.objects.select_for_update().get_or_create(
                cart=cart,
                product=serializer.validated_data["product"],
                defaults={"quantity": serializer.validated_data["quantity"]},
            )
            if not created:
                item.quantity += serializer.validated_data["quantity"]
                item.save(update_fields=["quantity"])
        item = CartItem.objects.select_related("product", "product__category").get(pk=item.pk)
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(operation_id="carro_insumos_vaciar", responses={204: None})
    def delete(self, request):
        # Vaciar el carro elimina sus items, nunca modifica el inventario.
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Item de carro: la FK al usuario impide modificar carros ajenos. ---
class CartItemDetailView(APIView):
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(request=CartItemQuantitySerializer, responses=CartItemSerializer)
    def patch(self, request, pk):
        # Serializer valida cantidad positiva antes de persistir el cambio.
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        serializer = CartItemQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.quantity = serializer.validated_data["quantity"]
        item.save(update_fields=["quantity"])
        return Response(CartItemSerializer(item).data)

    @extend_schema(operation_id="carro_insumo_eliminar", responses={204: None})
    def delete(self, request, pk):
        # El item solo se elimina si pertenece al usuario que hizo la peticion.
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Checkout atomico: el pedido, el descuento y el vaciado se confirman juntos. ---
class ConfirmOrderView(APIView):
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(request=None, responses={201: OrderSerializer})
    def post(self, request):
        # Un rollback conserva carro y stock si cualquier validacion falla.
        with transaction.atomic():
            cart, _ = Cart.objects.select_for_update().get_or_create(user=request.user)
            cart_items = list(cart.items.select_related("product").order_by("product_id"))
            if not cart_items:
                raise ValidationError({"detail": "El carro esta vacio."})

            product_ids = [item.product_id for item in cart_items]
            # Bloquear siempre en orden de PK reduce carreras y riesgo de deadlock.
            locked = {
                product.pk: product
                for product in Supply.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
            }
            for item in cart_items:
                product = locked.get(item.product_id)
                if product is None or not product.is_active:
                    raise ValidationError({"detail": f"{item.product.name} ya no esta disponible."})
                if product.stock < item.quantity:
                    raise ValidationError({
                        "detail": f"Stock insuficiente para {product.name}.",
                        "disponible": product.stock,
                        "solicitado": item.quantity,
                    })

            total = sum((locked[item.product_id].unit_price * item.quantity for item in cart_items), Decimal("0.00"))
            # El detalle guarda precio/lote del momento antes de descontar existencias.
            order = Order.objects.create(user=request.user, status=Order.Status.PAID, total=total)
            OrderItem.objects.bulk_create([
                OrderItem(
                    order=order,
                    supply=locked[item.product_id],
                    product_name=locked[item.product_id].name,
                    lot=locked[item.product_id].lot,
                    quantity=item.quantity,
                    unit_price=locked[item.product_id].unit_price,
                )
                for item in cart_items
            ])
            for item in cart_items:
                product = locked[item.product_id]
                product.stock -= item.quantity
                product.save(update_fields=["stock", "updated_at"])
            cart.items.all().delete()

        order = Order.objects.prefetch_related("items").get(pk=order.pk)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


# --- Historial cliente: nunca expone solicitudes de otras instituciones. ---
class MyOrdersView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


# --- Bandeja bodega: permite preparar despachos de todas las instituciones. ---
class WarehouseOrderListView(generics.ListAPIView):
    """Entrega a bodega la lista operativa de pedidos que debe despachar."""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsWarehouseManager]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.select_related("user").prefetch_related("items")


# --- Estados: transiciones permitidas y reposicion se ejecutan bajo bloqueo atomico. ---
class UpdateOrderStatusView(APIView):
    permission_classes = [IsAuthenticated, IsWarehouseManager]

    transitions = {
        Order.Status.PAID: {Order.Status.PREPARING, Order.Status.CANCELLED},
        Order.Status.PREPARING: {Order.Status.DISPATCHED, Order.Status.CANCELLED},
        Order.Status.DISPATCHED: {Order.Status.DELIVERED, Order.Status.CANCELLED},
    }

    @extend_schema(request=OrderStatusSerializer, responses=OrderSerializer)
    def patch(self, request, pk):
        # El serializer limita estados; la tabla de transiciones impide saltos invalidos.
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_status = serializer.validated_data["status"]

        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
            allowed = self.transitions.get(order.status, set())
            if next_status not in allowed:
                raise ValidationError({"status": f"Transicion no permitida desde {order.status}."})

            if next_status == Order.Status.CANCELLED and not order.stock_restored:
                # Orden e insumos se bloquean mientras se devuelve el stock una sola vez.
                items = list(order.items.all())
                supply_ids = sorted(item.supply_id for item in items)
                locked = {
                    supply.pk: supply
                    for supply in Supply.objects.select_for_update().filter(pk__in=supply_ids).order_by("pk")
                }
                for item in items:
                    supply = locked[item.supply_id]
                    supply.stock += item.quantity
                    supply.save(update_fields=["stock", "updated_at"])
                order.stock_restored = True

            order.status = next_status
            order.save(update_fields=["status", "stock_restored", "updated_at"])

        order = Order.objects.prefetch_related("items").get(pk=order.pk)
        return Response(OrderSerializer(order).data)