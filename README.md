# Nexo Salud

Plataforma B2B de abastecimiento médico construida con Django REST Framework y PostgreSQL. La interfaz en `/` consume la misma API documentada en `/api/docs/`; no usa el almacenamiento local del navegador para pedidos ni inventario.

## Requisitos

- Python 3.12 o superior.
- Docker Desktop con Compose, o un servidor PostgreSQL accesible.

## Puesta en marcha en Windows

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose up -d database
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Abre `http://127.0.0.1:8000/`. El superusuario se autentica con el rol `gestor_bodega`; las instituciones crean su cuenta desde **Crear cuenta**. Configura `STUDENT_NAME`, `STUDENT_SECTION` y `STUDENT_YEAR` en `.env` para personalizar el pie de página.

El archivo `.env.example` contiene credenciales de desarrollo para el contenedor local; cámbialas en instalaciones reales. `DJANGO_SECRET_KEY` también debe ser un secreto aleatorio fuera de desarrollo.

## API

- `POST /api/auth/registro/`: crea una cuenta de institución médica; no permite asignar el rol de bodega.
- `POST /api/token/` y `POST /api/token/refresh/`: emiten access/refresh JWT. El token incluye el claim firmado `role`.
- `GET /api/insumos/` y `GET /api/categorias/`: catálogo público; filtros `category`, `min_price`, `max_price`, `available`, `expiry_before` y búsqueda `search`.
- `POST /api/insumos/`, `PUT/PATCH/DELETE /api/insumos/{id}/`: gestión restringida a bodega. El borrado retira el insumo del catálogo sin destruir su historial.
- `GET/POST/DELETE /api/carro-insumos/` y `PATCH/DELETE /api/carro-insumos/{id}/`: carro persistente asociado 1:1 al usuario.
- `POST /api/solicitudes/confirmar/`: valida stock dentro de una transacción, crea la orden PAGADO, descuenta las cajas y vacía el carro.
- `GET /api/mis-solicitudes/`: historial de la institución autenticada.
- `GET /api/solicitudes/` y `PATCH /api/solicitudes/{uuid}/estado/`: gestión de despachos reservada a bodega. Cancelar repone stock de manera atómica.
- `GET /api/docs/`, `/api/schema/` y `/api/redoc/`: documentación Swagger/OpenAPI y esquema descargable.

## Validación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test inventario
```

Las pruebas usan PostgreSQL real porque el proyecto no configura SQLite.