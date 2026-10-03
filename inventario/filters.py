"""Filtros de catalogo por categoria, precio, stock y vencimiento."""
from django_filters import rest_framework as filters

from inventario.models import Supply


class SupplyFilter(filters.FilterSet):
    category = filters.CharFilter(field_name="category__slug")
    min_price = filters.NumberFilter(field_name="unit_price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="unit_price", lookup_expr="lte")
    available = filters.BooleanFilter(method="filter_available")
    expiry_before = filters.DateFilter(field_name="expiry_date", lookup_expr="lte")

    class Meta:
        model = Supply
        fields = ["category", "min_price", "max_price", "available", "expiry_before"]

    def filter_available(self, queryset, name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)