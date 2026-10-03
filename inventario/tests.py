"""Pruebas de permisos, persistencia del carro y ciclo transaccional."""
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import AccessToken

from django.contrib.auth import get_user_model
from inventario.models import CartItem, Category, Order, Supply

User = get_user_model()


class SupplyAndOrderApiTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Medicamentos", slug="medicamentos")
        self.supply = Supply.objects.create(
            name="Paracetamol 500 mg",
            active_ingredient="Paracetamol",
            category=self.category,
            lot="MED-TEST-01",
            expiry_date="2028-12-31",
            unit_price="12500.00",
            stock=10,
        )
        self.clinic = User.objects.create_user(username="clinica", password="ClaveClinica-2026")
        self.manager = User.objects.create_superuser(
            username="bodega", email="bodega@example.test", password="ClaveBodega-2026"
        )

    def test_catalog_is_public_filtered_and_writes_are_restricted(self):
        response = self.client.get("/api/insumos/?category=medicamentos&min_price=10000&available=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["id"], self.supply.pk)

        self.client.force_authenticate(user=self.clinic)
        forbidden = self.client.post("/api/insumos/", {}, format="json")
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_jwt_access_token_contains_server_assigned_role(self):
        response = self.client.post("/api/token/", {
            "username": self.manager.username,
            "password": "ClaveBodega-2026",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "gestor_bodega")
        token = AccessToken(response.data["access"])
        self.assertEqual(token["role"], "gestor_bodega")

    def test_cart_survives_new_login_and_does_not_reserve_stock(self):
        self.client.force_authenticate(user=self.clinic)
        response = self.client.post("/api/carro-insumos/", {
            "product_id": self.supply.pk,
            "quantity": 3,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.supply.__class__.objects.get(pk=self.supply.pk).stock, 10)

        other_device = APIClient()
        login = other_device.post("/api/token/", {
            "username": self.clinic.username,
            "password": "ClaveClinica-2026",
        }, format="json")
        other_device.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        persisted = other_device.get("/api/carro-insumos/")
        self.assertEqual(persisted.status_code, status.HTTP_200_OK)
        self.assertEqual(persisted.data[0]["quantity"], 3)

    def test_paid_order_deducts_stock_and_cancel_restores_once(self):
        self.client.force_authenticate(user=self.clinic)
        self.client.post("/api/carro-insumos/", {"product_id": self.supply.pk, "quantity": 3}, format="json")
        response = self.client.post("/api/solicitudes/confirmar/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Order.Status.PAID)
        self.assertEqual(Supply.objects.get(pk=self.supply.pk).stock, 7)
        self.assertFalse(CartItem.objects.filter(cart__user=self.clinic).exists())

        self.client.force_authenticate(user=self.manager)
        path = f"/api/solicitudes/{response.data['id']}/estado/"
        cancelled = self.client.patch(path, {"status": Order.Status.CANCELLED}, format="json")
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(Supply.objects.get(pk=self.supply.pk).stock, 10)

        repeat = self.client.patch(path, {"status": Order.Status.CANCELLED}, format="json")
        self.assertEqual(repeat.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Supply.objects.get(pk=self.supply.pk).stock, 10)

    def test_insufficient_stock_rolls_back_order_and_keeps_cart(self):
        self.client.force_authenticate(user=self.clinic)
        self.client.post("/api/carro-insumos/", {"product_id": self.supply.pk, "quantity": 11}, format="json")
        response = self.client.post("/api/solicitudes/confirmar/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Supply.objects.get(pk=self.supply.pk).stock, 10)
        self.assertTrue(CartItem.objects.filter(cart__user=self.clinic, quantity=11).exists())

    def test_manager_cannot_retire_supply_in_an_active_order(self):
        self.client.force_authenticate(user=self.clinic)
        self.client.post("/api/carro-insumos/", {"product_id": self.supply.pk, "quantity": 1}, format="json")
        order = self.client.post("/api/solicitudes/confirmar/", {}, format="json")
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f"/api/insumos/{self.supply.pk}/")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Supply.objects.get(pk=self.supply.pk).is_active)
        self.assertEqual(order.status_code, status.HTTP_201_CREATED)