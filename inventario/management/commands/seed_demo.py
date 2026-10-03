"""Carga un catalogo de ejemplo idempotente para la demostracion local."""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from inventario.models import Category, Supply


# --- Datos semilla: vuelven repetible la demostracion sin crear cuentas secretas. ---
class Command(BaseCommand):
    help = "Crea categorias e insumos de ejemplo sin duplicarlos."

    def handle(self, *args, **options):
        examples = [
            ("Medicamentos", "Paracetamol 500 mg", "Paracetamol · caja x 100 tabletas", "MED-26041", 12800, 84, 240),
            ("Medicamentos", "Amoxicilina 500 mg", "Amoxicilina · caja x 21 capsulas", "MED-25918", 24600, 12, 140),
            ("Medicamentos", "Solucion salina 0,9%", "Cloruro de sodio · bolsa 500 ml x 20", "SOL-26107", 38200, 46, 80),
            ("Material quirurgico", "Guantes de nitrilo", "Sin polvo · caja x 100 unidades", "QX-26052", 17900, 132, 900),
            ("Material quirurgico", "Jeringa esteril 10 ml", "Luer lock · caja x 50 unidades", "QX-26031", 22400, 8, 600),
            ("Equipamiento", "Oximetro de pulso", "Sensor portatil · uso clinico", "EQ-26009", 185000, 5, 1200),
        ]
        for category_name, name, ingredient, lot, price, stock, expiry_days in examples:
            category, _ = Category.objects.get_or_create(
                slug=slugify(category_name), defaults={"name": category_name}
            )
            Supply.objects.update_or_create(
                name=name,
                lot=lot,
                defaults={
                    "active_ingredient": ingredient,
                    "category": category,
                    "expiry_date": date.today() + timedelta(days=expiry_days),
                    "unit_price": price,
                    "stock": stock,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"Catalogo de ejemplo listo: {len(examples)} insumos."))