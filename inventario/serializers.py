"""Serializadores para auth JWT, catalogo, carros y ordenes."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from inventario.models import CartItem, Category, Order, OrderItem, Supply
from inventario.permissions import user_role

User = get_user_model()


# --- Registro: las cuentas publicas siempre nacen como institucion medica. ---
class RegisterSerializer(serializers.ModelSerializer):
    # Password nunca se devuelve y role es calculado por el servidor, no por el POST.
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "password", "role"]
        read_only_fields = ["id", "role"]

    def validate_email(self, value):
        # Evita correos duplicados aunque cambie el uso de mayusculas/minusculas.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return value

    def get_role(self, user) -> str:
        return user_role(user)

    def create(self, validated_data):
        # create_user aplica el hash seguro de Django y la senal crea el carro 1:1.
        return User.objects.create_user(**validated_data)


# --- El rol se firma dentro del access y refresh token, no desde el cliente. ---
class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # SimpleJWT incluye estos claims firmados tanto en access como en refresh.
        token = super().get_token(user)
        token["role"] = user_role(user)
        token["username"] = user.get_username()
        return token

    def validate(self, attrs):
        # La respuesta de login facilita a la interfaz mostrar el rol autenticado.
        data = super().validate(attrs)
        data["role"] = user_role(self.user)
        data["username"] = self.user.get_username()
        return data


class RoleTokenObtainPairView(TokenObtainPairView):
    serializer_class = RoleTokenObtainPairSerializer


# --- Categoria: expone el slug estable usado como parametro de filtro. ---
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


# --- Insumo: agrega nombre/slug legibles sin reemplazar la FK de escritura. ---
class SupplySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)

    class Meta:
        model = Supply
        fields = [
            "id", "name", "active_ingredient", "category", "category_name", "category_slug",
            "lot", "expiry_date", "unit_price", "stock", "is_active",
        ]
        read_only_fields = ["id"]


# --- Entrada de carro: acepta ID y cantidad positiva, no reserva stock. ---
class CartItemWriteSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(source="product", queryset=Supply.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, default=1)


# --- Edicion del carro: limita la entrada al nuevo entero positivo. ---
class CartItemQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


# --- Salida de carro: incluye el detalle actual del producto y las cajas pedidas. ---
class CartItemSerializer(serializers.ModelSerializer):
    product = SupplySerializer(read_only=True)

    class Meta:
        model = CartItem
        fields = ["id", "product", "quantity"]


# --- Detalle de orden: devuelve la fotografia de precio y lote al confirmar. ---
class OrderItemSerializer(serializers.ModelSerializer):
    supply_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["supply_id", "product_name", "lot", "quantity", "unit_price"]


# --- Orden: presenta estado, total e items historicos en una sola respuesta. ---
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Order
        fields = ["id", "username", "status", "total", "created_at", "items"]


# --- Cambio de estado: solo admite las opciones definidas en Order.Status. ---
class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)