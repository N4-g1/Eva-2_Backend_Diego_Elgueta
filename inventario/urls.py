"""URLs de inventario y operaciones B2B."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventario.views import (
    CartItemCollectionView,
    CartItemDetailView,
    CategoryViewSet,
    ConfirmOrderView,
    MyOrdersView,
    RegisterView,
    SupplyViewSet,
    UpdateOrderStatusView,
    WarehouseOrderListView,
)

router = DefaultRouter()
router.register("insumos", SupplyViewSet, basename="insumo")
router.register("categorias", CategoryViewSet, basename="categoria")

urlpatterns = [
    path("auth/registro/", RegisterView.as_view(), name="registro"),
    path("carro-insumos/", CartItemCollectionView.as_view(), name="carro-insumos"),
    path("carro-insumos/<int:pk>/", CartItemDetailView.as_view(), name="carro-insumo-detalle"),
    path("solicitudes/confirmar/", ConfirmOrderView.as_view(), name="confirmar-solicitud"),
    path("solicitudes/", WarehouseOrderListView.as_view(), name="solicitudes-bodega"),
    path("mis-solicitudes/", MyOrdersView.as_view(), name="mis-solicitudes"),
    path("solicitudes/<uuid:pk>/estado/", UpdateOrderStatusView.as_view(), name="actualizar-estado-solicitud"),
    path("", include(router.urls)),
]