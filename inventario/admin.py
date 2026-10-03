"""Administracion Django para catalogo, carros y trazabilidad de pedidos."""
from django.contrib import admin

from inventario.models import Cart, CartItem, Category, Order, OrderItem, Supply


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "lot", "expiry_date", "stock", "unit_price", "is_active"]
    list_filter = ["category", "is_active", "expiry_date"]
    search_fields = ["name", "active_ingredient", "lot"]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "updated_at"]
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["supply", "product_name", "lot", "quantity", "unit_price"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "total", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["id", "user__username", "user__email"]
    inlines = [OrderItemInline]
    readonly_fields = ["id", "user", "total", "stock_restored", "created_at", "updated_at"]