"""Pruebas del esqueleto PE-6 y del módulo de catálogo de platos PE-19."""

import os
import subprocess
import sys
from decimal import Decimal
from unittest.mock import MagicMock

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from catalogo.admin import CategoriaAdmin, ProductoAdmin
from catalogo.kds_service import (
    avanzar_estado_comanda,
    obtener_comandas_kds,
    resumen_kpis_kds,
)
from catalogo.models import (
    Categoria,
    DetallePedido,
    EventoPedido,
    Mesa,
    MovimientoStock,
    Pago,
    Pedido,
    Producto,
    Rol,
    SesionCaja,
    Usuario,
)
from catalogo.produccion_seeds import HASH_DEBIL_DEMO, auditar_datos_produccion
from catalogo.stock_service import (
    StockInsuficienteError,
    ajustar_stock_producto,
    descontar_stock_pedido,
    fijar_stock_diario,
    revertir_stock_item,
    revertir_stock_pedido,
    sincronizar_stock_con_pedidos,
)

RUTA_PROYECTO = str(settings.BASE_DIR)

# Variables que definen la conexión a PostgreSQL (las mismas de config.settings).
POSTGRES_VARS = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")

_DB_COMPLETAS = {
    "DB_NAME": "panel_pruebas",
    "DB_USER": "panel_pruebas",
    "DB_PASSWORD": "falsa-clave",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
}

_CLAVE_PRUEBAS = "clave-solo-pruebas-subproceso-NO-USAR-en-produccion"


def _ejecutar_en_subproceso(codigo, entorno_extra):
    """Ejecuta código Python en un proceso limpio, sin variables heredadas."""
    entorno = dict(os.environ)
    for nombre in ("DJANGO_SECRET_KEY", "DJANGO_DEBUG", *POSTGRES_VARS):
        entorno.pop(nombre, None)
    entorno.update(entorno_extra)
    return subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        cwd=RUTA_PROYECTO,
        env=entorno,
        check=False,
    )


def _importar_settings_en_subproceso(entorno_extra):
    """Importa config.settings en un proceso limpio, sin variables heredadas."""
    return _ejecutar_en_subproceso("import config.settings", entorno_extra)


def _motor_bd_en_subproceso(entorno_extra):
    """Devuelve el ENGINE de la BD leído en un proceso limpio, o el error."""
    codigo = "import config.settings as s; print(s.DATABASES['default']['ENGINE'])"
    return _ejecutar_en_subproceso(codigo, entorno_extra)


class ConfiguracionTests(SimpleTestCase):
    """Pruebas de configuración por entorno (PE-6). No tocan la base de datos."""

    def test_settings_carga_sin_error(self):
        self.assertIn("catalogo", settings.INSTALLED_APPS)
        self.assertIn("inventario", settings.INSTALLED_APPS)
        self.assertEqual(settings.LANGUAGE_CODE, "es-pe")
        self.assertEqual(settings.TIME_ZONE, "America/Lima")
        self.assertIs(settings.USE_TZ, True)

    def test_debug_es_falso_por_defecto(self):
        resultado = _ejecutar_en_subproceso(
            "import config.settings as s; print(s.DEBUG)",
            {"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS},
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "False")

    def test_basada_en_sqlite_sin_variables_de_entorno(self):
        resultado = _motor_bd_en_subproceso({"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS})
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "django.db.backends.sqlite3")

    def test_clave_secreta_obligatoria_sin_debug(self):
        resultado = _importar_settings_en_subproceso({})
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", resultado.stderr + resultado.stdout)

    def test_clave_de_desarrollo_solo_con_django_debug(self):
        resultado = _importar_settings_en_subproceso({"DJANGO_DEBUG": "1"})
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_sin_variables_db_usa_sqlite_en_subproceso(self):
        resultado = _motor_bd_en_subproceso({"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS})
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "django.db.backends.sqlite3")

    def test_con_las_cinco_variables_db_usa_postgresql(self):
        entorno = {"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS, **_DB_COMPLETAS}
        resultado = _motor_bd_en_subproceso(entorno)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), "django.db.backends.postgresql")

    def test_con_variables_db_parciales_falla_indicando_faltantes(self):
        parciales = {
            nombre: _DB_COMPLETAS[nombre]
            for nombre in ("DB_NAME", "DB_USER", "DB_PASSWORD")
        }
        entorno = {"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS, **parciales}
        resultado = _motor_bd_en_subproceso(entorno)
        self.assertNotEqual(resultado.returncode, 0)
        salida = resultado.stderr + resultado.stdout
        self.assertIn("ImproperlyConfigured", salida)
        self.assertIn("DB_HOST", salida)
        self.assertIn("DB_PORT", salida)


# =============================================================================
# Pruebas del módulo de catálogo, precios y stock del día (PE-19)
# =============================================================================


def _crear_tablas_unmanaged_si_no_existen():
    """Crea categoria y producto con el esquema real del modelo, en cualquier motor.

    `managed=False` impide que `migrate` las cree, pero el editor de esquema
    sí puede crearlas (SQLite y PostgreSQL) sin DDL específico de un motor.
    Debe llamarse ANTES de super().setUpClass(): en SQLite el schema_editor
    no puede desactivar las FK dentro del atomic que abre TestCase.
    """
    existentes = set(connection.introspection.table_names())
    with connection.schema_editor() as editor:
        if Categoria._meta.db_table not in existentes:
            editor.create_model(Categoria)
        if Producto._meta.db_table not in existentes:
            editor.create_model(Producto)
        if Mesa._meta.db_table not in existentes:
            editor.create_model(Mesa)
        if Pedido._meta.db_table not in existentes:
            editor.create_model(Pedido)
        if SesionCaja._meta.db_table not in existentes:
            editor.create_model(SesionCaja)
        if Pago._meta.db_table not in existentes:
            editor.create_model(Pago)
        if DetallePedido._meta.db_table not in existentes:
            editor.create_model(DetallePedido)
        if MovimientoStock._meta.db_table not in existentes:
            editor.create_model(MovimientoStock)
        if Rol._meta.db_table not in existentes:
            editor.create_model(Rol)
        if Usuario._meta.db_table not in existentes:
            editor.create_model(Usuario)
        if EventoPedido._meta.db_table not in existentes:
            editor.create_model(EventoPedido)


class CatalogoModelTests(TestCase):
    """Pruebas unitarias para los modelos Categoria y Producto (PE-19)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Platos Marinos")

    def test_creacion_categoria_y_str(self):
        """Verifica la persistencia y representación en texto de Categoria."""
        self.assertEqual(str(self.categoria), "Platos Marinos")
        self.assertEqual(self.categoria.nombre, "Platos Marinos")

    def test_alta_plato_marino(self):
        """Alcance PE-19: Alta de plato marino con información completa."""
        plato = Producto.objects.create(
            nombre="Ceviche Mixto Especial",
            descripcion=(
                "Pescado fresco del día, langostinos, calamar y pulpo con camote y choclo."
            ),
            precio=Decimal("52.50"),
            disponible=True,
            categoria=self.categoria,
            imagen_url="https://ejemplo.com/ceviche-mixto.jpg",
        )
        self.assertIsNotNone(plato.id)
        self.assertEqual(plato.nombre, "Ceviche Mixto Especial")
        self.assertEqual(plato.precio, Decimal("52.50"))
        self.assertTrue(plato.disponible)
        self.assertEqual(plato.categoria, self.categoria)
        self.assertEqual(str(plato), "Ceviche Mixto Especial (S/ 52.50)")

    def test_validacion_precio_debe_ser_positivo(self):
        """Alcance PE-19: El precio debe ser estrictamente mayor a 0 (MinValueValidator)."""
        plato_cero = Producto(
            nombre="Plato Inválido Cero",
            precio=Decimal("0.00"),
            categoria=self.categoria,
        )
        with self.assertRaises(ValidationError):
            plato_cero.full_clean()

        plato_negativo = Producto(
            nombre="Plato Inválido Negativo",
            precio=Decimal("-15.00"),
            categoria=self.categoria,
        )
        with self.assertRaises(ValidationError):
            plato_negativo.full_clean()

    def test_actualizacion_de_precios(self):
        """Alcance PE-19: Actualización individual o por lote del precio del plato."""
        plato = Producto.objects.create(
            nombre="Tiradito Nikkei",
            precio=Decimal("45.00"),
            categoria=self.categoria,
        )
        plato.precio = Decimal("49.00")
        plato.save()

        plato_actualizado = Producto.objects.get(id=plato.id)
        self.assertEqual(plato_actualizado.precio, Decimal("49.00"))

    def test_control_stock_pesca_del_dia(self):
        """Alcance PE-19: Activación y desactivación de disponibilidad según pesca del día."""
        plato = Producto.objects.create(
            nombre="Corvina a la Plancha",
            precio=Decimal("58.00"),
            disponible=True,
            categoria=self.categoria,
        )
        self.assertTrue(plato.disponible)

        # Se agota la pesca del día: desactivar plato
        plato.disponible = False
        plato.save()

        plato_recargado = Producto.objects.get(id=plato.id)
        self.assertFalse(plato_recargado.disponible)

        # Llega nueva captura del día: reactivar plato
        plato_recargado.disponible = True
        plato_recargado.save()

        self.assertTrue(Producto.objects.get(id=plato.id).disponible)

    def test_relacion_categoria_productos(self):
        """Verifica la relación inversa entre categoría y productos."""
        p1 = Producto.objects.create(
            nombre="Arroz con Mariscos",
            precio=Decimal("48.00"),
            categoria=self.categoria,
        )
        p2 = Producto.objects.create(
            nombre="Chaufa de Mariscos",
            precio=Decimal("46.00"),
            categoria=self.categoria,
        )
        productos_categoria = list(self.categoria.productos.all())
        self.assertIn(p1, productos_categoria)
        self.assertIn(p2, productos_categoria)
        self.assertEqual(self.categoria.productos.count(), 2)


class CatalogoAdminTests(TestCase):
    """Pruebas unitarias para las acciones y vistas de Django Admin (PE-19)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        self.site = AdminSite()
        self.categoria_admin = CategoriaAdmin(Categoria, self.site)
        self.producto_admin = ProductoAdmin(Producto, self.site)
        self.categoria = Categoria.objects.create(nombre="Marinos Admin")
        self.plato1 = Producto.objects.create(
            nombre="Parihuela Especial",
            precio=Decimal("55.00"),
            disponible=True,
            categoria=self.categoria,
        )
        self.plato2 = Producto.objects.create(
            nombre="Sudado de Pescado",
            precio=Decimal("50.00"),
            disponible=True,
            categoria=self.categoria,
        )

    def test_admin_categoria_total_productos(self):
        """Verifica el cálculo de total de platos por categoría en admin."""
        self.assertEqual(
            self.categoria_admin.total_productos(self.categoria),
            2,
        )

    def test_accion_admin_marcar_no_disponible_pesca_dia(self):
        """Acción masiva: marcar platos como agotados/no disponibles."""
        request = MagicMock()
        qs = Producto.objects.filter(id__in=[self.plato1.id, self.plato2.id])

        self.producto_admin.marcar_no_disponible_pesca_dia(request, qs)

        self.plato1.refresh_from_db()
        self.plato2.refresh_from_db()
        self.assertFalse(self.plato1.disponible)
        self.assertFalse(self.plato2.disponible)

    def test_accion_admin_marcar_disponible_pesca_dia(self):
        """Acción masiva: reactivar platos con stock disponible por pesca del día."""
        self.plato1.disponible = False
        self.plato1.save()
        self.plato2.disponible = False
        self.plato2.save()

        request = MagicMock()
        qs = Producto.objects.filter(id__in=[self.plato1.id, self.plato2.id])

        self.producto_admin.marcar_disponible_pesca_dia(request, qs)

        self.plato1.refresh_from_db()
        self.plato2.refresh_from_db()
        self.assertTrue(self.plato1.disponible)
        self.assertTrue(self.plato2.disponible)


class CatalogoWebPanelTests(TestCase):
    """Pruebas integrales de la interfaz web moderna de catálogo (PRB-19)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="admin_carta",
            password="ClaveSegura!2026",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="invitado",
            password="ClaveSegura!2026",
            is_staff=False,
        )
        self.cat_entradas = Categoria.objects.create(nombre="Entradas")
        self.cat_fondos = Categoria.objects.create(nombre="Platos de Fondo")
        self.plato_disp = Producto.objects.create(
            nombre="Ceviche Clásico",
            precio=Decimal("48.00"),
            disponible=True,
            categoria=self.cat_entradas,
        )
        self.plato_agot = Producto.objects.create(
            nombre="Jalea Real",
            precio=Decimal("58.00"),
            disponible=False,
            categoria=self.cat_fondos,
        )

    def test_acceso_protegido_redirige_a_login(self):
        """Usuarios anónimos o sin is_staff son redirigidos al login del panel."""
        resp_anon = self.client.get("/")
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/login/", resp_anon["Location"])

        self.client.force_login(self.normal_user)
        resp_no_staff = self.client.get("/platos/")
        self.assertEqual(resp_no_staff.status_code, 302)
        self.assertIn("/login/", resp_no_staff["Location"])

    def test_dashboard_calcula_kpis_reales_prb19(self):
        """El dashboard muestra conteos, disponibilidad y precios reales de carta."""
        self.client.force_login(self.staff_user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_platos"], 2)
        self.assertEqual(resp.context["platos_disponibles"], 1)
        self.assertEqual(resp.context["platos_agotados"], 1)
        self.assertEqual(resp.context["pct_disponibles"], 50.0)
        self.assertEqual(resp.context["precio_promedio"], Decimal("53.00"))
        self.assertContains(resp, "Ceviche Clásico")

    def test_alta_y_edicion_plato_desde_panel_web(self):
        """Permite dar de alta un nuevo plato marino y rechaza precios inválidos."""
        self.client.force_login(self.staff_user)
        resp_invalido = self.client.post(
            "/platos/nuevo/",
            {
                "nombre": "Plato Precio Cero",
                "categoria": self.cat_entradas.id,
                "precio": "0.00",
                "disponible": "on",
            },
        )
        self.assertEqual(resp_invalido.status_code, 200)
        self.assertFalse(Producto.objects.filter(nombre="Plato Precio Cero").exists())

        resp_ok = self.client.post(
            "/platos/nuevo/",
            {
                "nombre": "Tiradito al Ají Amarillo",
                "categoria": self.cat_entradas.id,
                "descripcion": "Láminas de pescado del día.",
                "precio": "46.50",
                "disponible": "on",
            },
        )
        self.assertEqual(resp_ok.status_code, 302)
        creado = Producto.objects.get(nombre="Tiradito al Ají Amarillo")
        self.assertEqual(creado.precio, Decimal("46.50"))
        self.assertTrue(creado.disponible)

    def test_actualizacion_rapida_precio_y_toggle_pesca_dia_json(self):
        """Soporta cambio rápido de precio y switch JSON de pesca del día."""
        self.client.force_login(self.staff_user)
        resp_precio = self.client.post(
            f"/platos/{self.plato_disp.id}/actualizar-precio/",
            {"precio": "51.90"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_precio.status_code, 200)
        self.plato_disp.refresh_from_db()
        self.assertEqual(self.plato_disp.precio, Decimal("51.90"))

        resp_toggle = self.client.post(
            f"/platos/{self.plato_disp.id}/toggle-disponibilidad/",
            {},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_toggle.status_code, 200)
        datos = resp_toggle.json()
        self.assertTrue(datos["ok"])
        self.assertFalse(datos["disponible"])
        self.plato_disp.refresh_from_db()
        self.assertFalse(self.plato_disp.disponible)

    def test_precio_no_finito_devuelve_400(self):
        """NaN e Infinity se rechazan con 400, no con 500."""
        self.client.force_login(self.staff_user)
        for valor in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(valor=valor):
                resp = self.client.post(
                    f"/platos/{self.plato_disp.id}/actualizar-precio/",
                    {"precio": valor},
                    HTTP_ACCEPT="application/json",
                )
                self.assertEqual(resp.status_code, 400)
                self.assertFalse(resp.json()["ok"])
        self.plato_disp.refresh_from_db()
        self.assertEqual(self.plato_disp.precio, Decimal("48.00"))

    def test_acciones_lote_y_proteccion_borrado_categoria(self):
        """Ejecuta acciones por lote e impide borrar categorías con platos."""
        self.client.force_login(self.staff_user)
        self.client.post(
            "/platos/accion-masiva/",
            {
                "accion": "marcar_disponible",
                "plato_ids": [str(self.plato_agot.id)],
            },
        )
        self.plato_agot.refresh_from_db()
        self.assertTrue(self.plato_agot.disponible)

        self.client.post(f"/categorias/{self.cat_entradas.id}/eliminar/")
        self.assertTrue(Categoria.objects.filter(pk=self.cat_entradas.id).exists())

        cat_vacia = Categoria.objects.create(nombre="Bebidas Temporales")
        self.client.post(f"/categorias/{cat_vacia.id}/eliminar/")
        self.assertFalse(Categoria.objects.filter(pk=cat_vacia.id).exists())


class DashboardOperativoTests(TestCase):
    """Pruebas unitarias e integración del Dashboard Operativo del día (PRB-45).

    Verifica:
    - Mesas ocupadas vs libres.
    - Ventas del día (suma de comandas en estado COBRADO de hoy).
    - Platos agotados.
    - Pedidos pendientes en cocina.
    - Endpoint JSON de sondeo simple (/operativo/kpis/).
    - Rendereo HTML de los componentes operativos y mapa de salón.
    """

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="administrador_operativo",
            password="adminpassword123",
            is_staff=True,
        )
        self.categoria = Categoria.objects.create(
            nombre="Ceviches Operativos",
        )
        self.plato_disp = Producto.objects.create(
            nombre="Ceviche Clásico Operativo",
            precio=Decimal("45.00"),
            disponible=True,
            categoria=self.categoria,
        )
        self.plato_agot = Producto.objects.create(
            nombre="Pargo al Horno (Agotado)",
            precio=Decimal("65.00"),
            disponible=False,
            categoria=self.categoria,
        )

        # Crear mesas
        self.m1 = Mesa.objects.create(
            numero=1,
            capacidad=4,
            ubicacion="Salón Principal",
            estado=Mesa.ESTADO_LIBRE,
        )
        self.m2 = Mesa.objects.create(
            numero=2,
            capacidad=2,
            ubicacion="Terraza",
            estado=Mesa.ESTADO_OCUPADA,
        )
        self.m3 = Mesa.objects.create(
            numero=3,
            capacidad=6,
            ubicacion="Zona VIP",
            estado=Mesa.ESTADO_ATENDIENDO,
        )
        self.m4 = Mesa.objects.create(
            numero=4,
            capacidad=4,
            ubicacion="Salón Principal",
            estado=Mesa.ESTADO_PIDE_CUENTA,
        )

        # Crear pedidos
        # 1 cobrado hoy
        self.p_cobrado = Pedido.objects.create(
            mesa=self.m4,
            mozo_id=101,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("120.50"),
        )
        # 1 pendiente
        self.p_pendiente = Pedido.objects.create(
            mesa=self.m2,
            mozo_id=102,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("85.00"),
        )
        # 1 cocinando
        self.p_cocinando = Pedido.objects.create(
            mesa=self.m3,
            mozo_id=101,
            estado=Pedido.ESTADO_COCINANDO,
            total=Decimal("150.00"),
        )

    def test_dashboard_html_contiene_seccion_operativa(self):
        """GET / renderiza indicadores operativos, mesas y pedidos activos."""
        self.client.force_login(self.staff_user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Operaciones del Día · Salón y Cocina")
        self.assertContains(resp, "Mesas ocupadas")
        self.assertContains(resp, "Ventas del día")
        self.assertContains(resp, "Platos agotados")
        self.assertContains(resp, "Pedidos pendientes")
        self.assertContains(resp, "Salón y Estado de Mesas")
        self.assertContains(resp, "Comandas en Curso")
        self.assertContains(resp, "Mesa 1")
        self.assertContains(resp, "Mesa 2")
        self.assertTrue(
            "120,50" in resp.content.decode("utf-8")
            or "120.50" in resp.content.decode("utf-8")
        )

    def test_endpoint_kpis_operativos_json(self):
        """GET /operativo/kpis/ devuelve métricas calculadas en JSON."""
        self.client.force_login(self.staff_user)
        resp = self.client.get("/operativo/kpis/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["total_mesas"], 4)
        # m2 (OCUPADA) y m3 (ATENDIENDO) suman 2
        self.assertEqual(data["mesas_ocupadas"], 2)
        self.assertEqual(data["mesas_libres"], 1)
        self.assertEqual(data["mesas_pide_cuenta"], 1)
        self.assertEqual(data["ventas_dia"], "120.50")
        self.assertEqual(data["platos_agotados"], 1)
        # p_pendiente + p_cocinando = 2
        self.assertEqual(data["pedidos_pendientes"], 2)
        self.assertEqual(len(data["mesas"]), 4)

    def test_kpis_operativos_requiere_autenticacion(self):
        """El endpoint operativo rechaza accesos anónimos redirigiendo al login."""
        resp = self.client.get("/operativo/kpis/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)


class EsquemaV2ModelTests(TestCase):
    """Pruebas unitarias de modelos y tablas introducidos en el esquema v2 (PRB-51)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        self.mesa = Mesa.objects.create(
            numero=10,
            capacidad=4,
            ubicacion="Segundo piso",
            estado=Mesa.ESTADO_LIBRE,
        )

    def test_sesion_caja_creacion_defaults_y_str(self):
        """Verifica la persistencia, valores por defecto y representación de SesionCaja."""
        sesion = SesionCaja.objects.create(
            cajero_id=5,
            monto_inicial=Decimal("150.00"),
            monto_esperado=Decimal("150.00"),
        )
        self.assertIsNotNone(sesion.id)
        self.assertEqual(sesion.estado, SesionCaja.ESTADO_ABIERTA)
        self.assertEqual(sesion.monto_ventas_efectivo, Decimal("0.00"))
        self.assertEqual(sesion.monto_ventas_digital, Decimal("0.00"))
        self.assertIn(f"Caja #{sesion.id}", str(sesion))

    def test_pedido_soporta_anulado_version_idempotencia_y_para_llevar(self):
        """Verifica soporte para ANULADO, client_request_id, version y pedidos sin mesa."""
        pedido_llevar = Pedido.objects.create(
            mesa=None,
            mozo_id=1,
            estado=Pedido.ESTADO_ANULADO,
            total=Decimal("45.00"),
            client_request_id="uuid-idempotencia-12345",
            version=1,
        )
        self.assertIsNone(pedido_llevar.mesa)
        self.assertEqual(pedido_llevar.estado, Pedido.ESTADO_ANULADO)
        self.assertEqual(pedido_llevar.version, 1)
        self.assertEqual(pedido_llevar.client_request_id, "uuid-idempotencia-12345")
        self.assertIn("Para llevar", str(pedido_llevar))

    def test_pago_con_mesa_y_sin_mesa_str_seguro(self):
        """Verifica registro de pago multimoneda, relación con sesion_caja y __str__ seguro."""
        sesion = SesionCaja.objects.create(cajero_id=5, monto_inicial=Decimal("100.00"))
        pedido = Pedido.objects.create(
            mesa=self.mesa, mozo_id=1, total=Decimal("80.00")
        )

        pago_salon = Pago.objects.create(
            pedido=pedido,
            mesa=self.mesa,
            sesion_caja=sesion,
            metodo=Pago.METODO_YAPE,
            monto=Decimal("80.00"),
            client_request_id="req-pago-salon-001",
        )
        self.assertEqual(pago_salon.metodo, Pago.METODO_YAPE)
        self.assertEqual(pago_salon.sesion_caja, sesion)
        self.assertIn("Mesa 10", str(pago_salon))

        pago_llevar = Pago.objects.create(
            pedido=pedido,
            mesa=None,
            sesion_caja=sesion,
            metodo=Pago.METODO_EFECTIVO,
            monto=Decimal("50.00"),
            client_request_id="req-pago-llevar-002",
        )
        self.assertIn("Para llevar", str(pago_llevar))


class CajaArqueoTests(TestCase):
    """Pruebas integrales de apertura, control de turno único y Cierre Z (PRB-60)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="cajero_principal",
            password="ClaveCaja!2026",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="mozo_sin_panel",
            password="ClaveCaja!2026",
            is_staff=False,
        )
        self.mesa1 = Mesa.objects.create(
            numero=1,
            capacidad=4,
            ubicacion="Primer piso",
            estado=Mesa.ESTADO_OCUPADA,
        )

    def test_caja_requiere_staff_autenticado(self):
        """Las rutas de caja redirigen al login para anónimos o usuarios sin is_staff."""
        for ruta in ("/caja/", "/caja/abrir/", "/caja/cerrar/"):
            resp = self.client.get(ruta)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login/", resp["Location"])

        self.client.force_login(self.normal_user)
        resp_no_staff = self.client.get("/caja/")
        self.assertEqual(resp_no_staff.status_code, 302)
        self.assertIn("/login/", resp_no_staff["Location"])

    def test_apertura_caja_y_bloqueo_doble_apertura(self):
        """PRB-60: Permite abrir turno y bloquea estrictamente una segunda caja abierta."""
        self.client.force_login(self.staff_user)

        resp_abrir = self.client.post(
            "/caja/abrir/",
            {
                "monto_inicial": "150.00",
                "observaciones": "Fondo inicial verificado",
            },
        )
        self.assertEqual(resp_abrir.status_code, 302)
        self.assertEqual(
            SesionCaja.objects.filter(estado=SesionCaja.ESTADO_ABIERTA).count(),
            1,
        )
        sesion = SesionCaja.objects.get(estado=SesionCaja.ESTADO_ABIERTA)
        self.assertEqual(sesion.monto_inicial, Decimal("150.00"))
        self.assertEqual(sesion.monto_esperado, Decimal("150.00"))

        # Intentar abrir una segunda sesión mientras la primera sigue ABIERTA
        resp_segunda = self.client.post(
            "/caja/abrir/",
            {"monto_inicial": "200.00", "observaciones": "Intento duplicado"},
            follow=True,
        )
        self.assertEqual(resp_segunda.status_code, 200)
        self.assertEqual(
            SesionCaja.objects.filter(estado=SesionCaja.ESTADO_ABIERTA).count(),
            1,
        )
        self.assertContains(resp_segunda, "Solo puede existir una caja ABIERTA")

    def test_cierre_z_cuadrado_con_pagos_multimedios_y_para_llevar(self):
        """PRB-60: Calcula monto esperado exacto y ejecuta Cierre Z cuadrado (dif = 0)."""
        self.client.force_login(self.staff_user)
        self.client.post("/caja/abrir/", {"monto_inicial": "100.00"})
        sesion = SesionCaja.objects.get(estado=SesionCaja.ESTADO_ABIERTA)

        ped_salon = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=2,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("125.00"),
        )
        ped_llevar = Pedido.objects.create(
            mesa=None,
            mozo_id=2,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("125.00"),
        )

        Pago.objects.create(
            pedido=ped_salon,
            mesa=self.mesa1,
            sesion_caja=sesion,
            metodo=Pago.METODO_EFECTIVO,
            monto=Decimal("80.00"),
            propina=Decimal("5.00"),
            client_request_id="req-efec-001",
        )
        Pago.objects.create(
            pedido=ped_salon,
            mesa=self.mesa1,
            sesion_caja=sesion,
            metodo=Pago.METODO_YAPE,
            monto=Decimal("45.00"),
            referencia="YP-991",
            client_request_id="req-yape-002",
        )
        Pago.objects.create(
            pedido=ped_llevar,
            mesa=None,
            sesion_caja=sesion,
            metodo=Pago.METODO_PLIN,
            monto=Decimal("30.00"),
            referencia="PL-442",
            client_request_id="req-plin-003",
        )
        Pago.objects.create(
            pedido=ped_llevar,
            mesa=None,
            sesion_caja=sesion,
            metodo=Pago.METODO_TARJETA,
            monto=Decimal("95.00"),
            propina=Decimal("10.00"),
            referencia="POS-778",
            client_request_id="req-tarj-004",
        )

        resp_vista = self.client.get("/caja/")
        self.assertEqual(resp_vista.status_code, 200)
        resumen = resp_vista.context["resumen_actual"]
        self.assertEqual(resumen["efectivo"], Decimal("80.00"))
        self.assertEqual(resumen["ventas_digital"], Decimal("170.00"))
        self.assertEqual(resumen["total_ventas"], Decimal("250.00"))
        self.assertEqual(resumen["total_propinas"], Decimal("15.00"))
        self.assertEqual(resumen["monto_esperado"], Decimal("180.00"))
        self.assertContains(resp_vista, "Para llevar")

        resp_cierre = self.client.post(
            "/caja/cerrar/",
            {"monto_real": "180.00", "observaciones": ""},
        )
        self.assertEqual(resp_cierre.status_code, 302)

        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, SesionCaja.ESTADO_CERRADA)
        self.assertIsNotNone(sesion.fecha_cierre)
        self.assertEqual(sesion.monto_ventas_efectivo, Decimal("80.00"))
        self.assertEqual(sesion.monto_ventas_digital, Decimal("170.00"))
        self.assertEqual(sesion.monto_esperado, Decimal("180.00"))
        self.assertEqual(sesion.monto_real, Decimal("180.00"))
        self.assertEqual(sesion.diferencia, Decimal("0.00"))

    def test_cierre_z_con_descuadre_exige_justificacion_y_registra_diferencia(self):
        """PRB-60: Bloquea descuadres sin explicar y registra faltantes/sobrantes justificados."""
        self.client.force_login(self.staff_user)
        self.client.post("/caja/abrir/", {"monto_inicial": "100.00"})
        sesion = SesionCaja.objects.get(estado=SesionCaja.ESTADO_ABIERTA)

        ped = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=2,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("50.00"),
        )
        Pago.objects.create(
            pedido=ped,
            mesa=self.mesa1,
            sesion_caja=sesion,
            metodo=Pago.METODO_EFECTIVO,
            monto=Decimal("50.00"),
            client_request_id="req-descuadre-001",
        )

        # Esperado = 150.00; contado = 142.50 sin observación -> debe rechazarse
        resp_sin_obs = self.client.post(
            "/caja/cerrar/",
            {"monto_real": "142.50", "observaciones": ""},
        )
        self.assertEqual(resp_sin_obs.status_code, 200)
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, SesionCaja.ESTADO_ABIERTA)
        self.assertContains(resp_sin_obs, "faltante")

        # Ahora con justificación del descuadre -> se cierra con diferencia = -7.50
        resp_con_obs = self.client.post(
            "/caja/cerrar/",
            {
                "monto_real": "142.50",
                "observaciones": "Faltante por error de vuelto en mesa 1",
            },
        )
        self.assertEqual(resp_con_obs.status_code, 302)
        sesion.refresh_from_db()
        self.assertEqual(sesion.estado, SesionCaja.ESTADO_CERRADA)
        self.assertEqual(sesion.diferencia, Decimal("-7.50"))
        self.assertIn("error de vuelto", sesion.observaciones)

        # Abrir nuevo turno tras cerrar el anterior y cerrar con sobrante (+5.00)
        self.client.post("/caja/abrir/", {"monto_inicial": "50.00"})
        sesion2 = SesionCaja.objects.get(estado=SesionCaja.ESTADO_ABIERTA)
        self.client.post(
            "/caja/cerrar/",
            {
                "monto_real": "55.00",
                "observaciones": "Sobrante por propina en efectivo dejada en caja",
            },
        )
        sesion2.refresh_from_db()
        self.assertEqual(sesion2.estado, SesionCaja.ESTADO_CERRADA)
        self.assertEqual(sesion2.diferencia, Decimal("5.00"))


class ReportesVentasTests(TestCase):
    """Pruebas integrales de reportes diarios de ventas y medios de pago (PRB-61)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="admin_reportes",
            password="ClaveRep!2026",
            is_staff=True,
        )
        self.mesa = Mesa.objects.create(
            numero=5,
            capacidad=6,
            ubicacion="Segundo piso",
            estado=Mesa.ESTADO_LIBRE,
        )

    def test_reportes_requiere_staff_autenticado(self):
        """GET /reportes/ redirige al login cuando no hay sesión administrativa."""
        resp = self.client.get("/reportes/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_reporte_ventas_ticket_promedio_y_desglose_medios_pago(self):
        """PRB-61: Calcula ventas totales, ticket promedio con pago dividido y desglose exacto."""
        self.client.force_login(self.staff_user)
        sesion = SesionCaja.objects.create(
            cajero_id=1,
            monto_inicial=Decimal("100.00"),
            monto_esperado=Decimal("100.00"),
            estado=SesionCaja.ESTADO_ABIERTA,
        )

        # Pedido 1: S/ 75.00 pagado dividido (S/ 40 Efectivo + S/ 35 Yape)
        p1 = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=2,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("75.00"),
        )
        Pago.objects.create(
            pedido=p1,
            mesa=self.mesa,
            sesion_caja=sesion,
            metodo=Pago.METODO_EFECTIVO,
            monto=Decimal("40.00"),
            client_request_id="rep-p1-efec",
        )
        Pago.objects.create(
            pedido=p1,
            mesa=self.mesa,
            sesion_caja=sesion,
            metodo=Pago.METODO_YAPE,
            monto=Decimal("35.00"),
            referencia="YAPE-101",
            client_request_id="rep-p1-yape",
        )

        # Pedido 2: S/ 60.00 pagado con Plin
        p2 = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=2,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("60.00"),
        )
        Pago.objects.create(
            pedido=p2,
            mesa=self.mesa,
            sesion_caja=sesion,
            metodo=Pago.METODO_PLIN,
            monto=Decimal("60.00"),
            referencia="PLIN-202",
            client_request_id="rep-p2-plin",
        )

        # Pedido 3 (Para llevar): S/ 105.00 pagado con Tarjeta + S/ 10 propina
        p3 = Pedido.objects.create(
            mesa=None,
            mozo_id=3,
            estado=Pedido.ESTADO_COBRADO,
            total=Decimal("105.00"),
        )
        Pago.objects.create(
            pedido=p3,
            mesa=None,
            sesion_caja=sesion,
            metodo=Pago.METODO_TARJETA,
            monto=Decimal("105.00"),
            propina=Decimal("10.00"),
            referencia="VISA-303",
            client_request_id="rep-p3-tarj",
        )

        resp = self.client.get("/reportes/")
        self.assertEqual(resp.status_code, 200)
        # Ventas totales: 40 + 35 + 60 + 105 = 240.00
        self.assertEqual(resp.context["ventas_dia"], Decimal("240.00"))
        # 3 pedidos únicos (el cobro dividido cuenta como 1 pedido, no 2)
        self.assertEqual(resp.context["pedidos_cobrados"], 3)
        # Ticket promedio: 240.00 / 3 = 80.00
        self.assertEqual(resp.context["ticket_promedio"], Decimal("80.00"))
        self.assertEqual(resp.context["total_efectivo"], Decimal("40.00"))
        self.assertEqual(resp.context["total_digital"], Decimal("200.00"))
        self.assertEqual(resp.context["total_propinas"], Decimal("10.00"))

        por_codigo = {m["codigo"]: m["monto"] for m in resp.context["desglose_medios"]}
        self.assertEqual(por_codigo["EFECTIVO"], Decimal("40.00"))
        self.assertEqual(por_codigo["YAPE"], Decimal("35.00"))
        self.assertEqual(por_codigo["PLIN"], Decimal("60.00"))
        self.assertEqual(por_codigo["TARJETA"], Decimal("105.00"))

        self.assertContains(resp, "Conciliación con Caja")
        self.assertContains(resp, "Efectivo")
        self.assertContains(resp, "Yape")
        self.assertContains(resp, "Plin")
        self.assertContains(resp, "Tarjeta")

    def test_reporte_filtro_fecha_vacia_y_fecha_invalida(self):
        """PRB-61: Soporta consulta histórica sin datos y tolera fechas malformadas."""
        self.client.force_login(self.staff_user)

        resp_vacia = self.client.get("/reportes/?fecha=2025-01-15")
        self.assertEqual(resp_vacia.status_code, 200)
        self.assertEqual(resp_vacia.context["ventas_dia"], Decimal("0.00"))
        self.assertEqual(resp_vacia.context["pedidos_cobrados"], 0)
        self.assertEqual(resp_vacia.context["ticket_promedio"], Decimal("0.00"))

        resp_invalida = self.client.get("/reportes/?fecha=fecha-invalida")
        self.assertEqual(resp_invalida.status_code, 200)
        self.assertTrue(resp_invalida.context["es_hoy"])


# =============================================================================
# Pruebas de Inventario Reducido: Stock del Día, Descuento y Reversión (PRB-59)
# =============================================================================


class StockDelDiaTests(TestCase):
    """Pruebas unitarias e integrales de stock diario, descuento y reversión (PRB-59)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="chef_stock",
            password="PasswordSegura123!",
            is_staff=True,
        )
        self.cat_ceviches = Categoria.objects.create(nombre="Ceviches Stock")
        self.cat_bebidas = Categoria.objects.create(nombre="Bebidas Stock")

        self.ceviche = Producto.objects.create(
            nombre="Ceviche de Conchas Negras",
            precio=Decimal("56.00"),
            disponible=True,
            stock_disponible=5,
            stock_minimo=2,
            categoria=self.cat_ceviches,
        )
        self.tiradito = Producto.objects.create(
            nombre="Tiradito al Ají Amarillo",
            precio=Decimal("49.00"),
            disponible=True,
            stock_disponible=3,
            stock_minimo=1,
            categoria=self.cat_ceviches,
        )
        self.chicha = Producto.objects.create(
            nombre="Chicha Morada 1L",
            precio=Decimal("16.00"),
            disponible=True,
            stock_disponible=None,
            stock_minimo=0,
            categoria=self.cat_bebidas,
        )
        self.mesa = Mesa.objects.create(
            numero=12,
            capacidad=4,
            ubicacion="Segundo piso",
            estado=Mesa.ESTADO_OCUPADA,
        )

    def test_fijar_stock_diario_y_propiedades_alerta(self):
        """PRB-59: Fijar cupo actualiza disponible, alerta de bajo stock y kardex."""
        plato, mov = fijar_stock_diario(
            self.ceviche.id,
            stock_disponible=2,
            stock_minimo=2,
            motivo="Ingreso matutino de conchas",
            registrado_por="chef_stock",
        )
        self.assertEqual(plato.stock_disponible, 2)
        self.assertTrue(plato.disponible)
        self.assertTrue(plato.controla_stock)
        self.assertTrue(plato.stock_bajo)
        self.assertEqual(mov.tipo, MovimientoStock.TIPO_CARGA_DIARIA)

        plato_cero, _ = fijar_stock_diario(self.ceviche.id, stock_disponible=0)
        self.assertEqual(plato_cero.stock_disponible, 0)
        self.assertFalse(plato_cero.disponible)

        plato_libre, _ = fijar_stock_diario(self.ceviche.id, stock_disponible=None)
        self.assertIsNone(plato_libre.stock_disponible)
        self.assertTrue(plato_libre.disponible)
        self.assertFalse(plato_libre.controla_stock)

    def test_descuento_transaccional_idempotente_y_agotamiento_en_cero(self):
        """PRB-59: Descuenta cupo exacto, ignora ilimitados, agota en 0 y es idempotente."""
        pedido = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("296.00"),
        )
        items = [
            {"producto_id": self.ceviche.id, "cantidad": 5},
            {"producto_id": self.chicha.id, "cantidad": 1},
        ]
        movs_1 = descontar_stock_pedido(pedido.id, items=items)
        self.assertEqual(len(movs_1), 1)

        self.ceviche.refresh_from_db()
        self.chicha.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 0)
        self.assertFalse(self.ceviche.disponible)
        self.assertIsNone(self.chicha.stock_disponible)
        self.assertTrue(self.chicha.disponible)

        # Reintento idempotente con el mismo pedido_id no vuelve a descontar
        movs_2 = descontar_stock_pedido(pedido.id, items=items)
        self.assertEqual([m.id for m in movs_1], [m.id for m in movs_2])

    def test_descuento_stock_insuficiente_hace_rollback_total(self):
        """PRB-59: Si un ítem supera el cupo disponible, ningún plato se descuenta."""
        pedido = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("300.00"),
        )
        items = [
            {"producto_id": self.ceviche.id, "cantidad": 2},
            {"producto_id": self.tiradito.id, "cantidad": 4},  # Solo hay 3 disponibles
        ]
        with self.assertRaises(StockInsuficienteError) as ctx:
            descontar_stock_pedido(pedido.id, items=items)

        self.assertEqual(ctx.exception.codigo, "STOCK_INSUFICIENTE")
        self.assertEqual(len(ctx.exception.detalles), 1)
        self.assertEqual(ctx.exception.detalles[0]["producto_id"], self.tiradito.id)

        self.ceviche.refresh_from_db()
        self.tiradito.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 5)
        self.assertEqual(self.tiradito.stock_disponible, 3)
        self.assertEqual(MovimientoStock.objects.filter(pedido=pedido).count(), 0)

    def test_reversion_stock_pedido_anulado_reactiva_plato_agotado_e_idempotencia(self):
        """PRB-59: Revertir pedido restaura cupo, reactiva plato desde 0 y es idempotente."""
        pedido = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("147.00"),
        )
        descontar_stock_pedido(
            pedido.id,
            items=[{"producto_id": self.tiradito.id, "cantidad": 3}],
        )
        self.tiradito.refresh_from_db()
        self.assertEqual(self.tiradito.stock_disponible, 0)
        self.assertFalse(self.tiradito.disponible)

        pedido.estado = Pedido.ESTADO_ANULADO
        pedido.save(update_fields=["estado"])

        revs_1 = revertir_stock_pedido(pedido.id, motivo="Cliente se retiró")
        self.assertEqual(len(revs_1), 1)
        self.tiradito.refresh_from_db()
        self.assertEqual(self.tiradito.stock_disponible, 3)
        self.assertTrue(self.tiradito.disponible)

        # Segunda llamada es no-op idempotente (no infla el stock a 6)
        revs_2 = revertir_stock_pedido(pedido.id, motivo="Reintento duplicado")
        self.assertEqual(revs_2, [])
        self.tiradito.refresh_from_db()
        self.assertEqual(self.tiradito.stock_disponible, 3)

    def test_reversion_parcial_por_item_individual(self):
        """PRB-59: Revertir un ítem individual restaura solo la cantidad anulada."""
        pedido = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=1,
            estado=Pedido.ESTADO_COCINANDO,
            total=Decimal("224.00"),
        )
        descontar_stock_pedido(
            pedido.id,
            items=[{"producto_id": self.ceviche.id, "cantidad": 4}],
        )
        self.ceviche.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 1)

        mov = revertir_stock_item(pedido.id, self.ceviche.id, cantidad=2)
        self.assertIsNotNone(mov)
        self.ceviche.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 3)

    def test_sincronizacion_automatica_pedidos_pos_y_anulaciones(self):
        """PRB-59: Concilia automáticamente DetallePedido y ANULADO escritos desde Java."""
        fijar_stock_diario(self.ceviche.id, stock_disponible=4, stock_minimo=1)

        pedido = Pedido.objects.create(
            mesa=self.mesa,
            mozo_id=2,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("224.00"),
        )
        DetallePedido.objects.create(
            pedido=pedido,
            producto=self.ceviche,
            precio_unitario=Decimal("56.00"),
            cantidad=4,
            subtotal=Decimal("224.00"),
        )

        res_1 = sincronizar_stock_con_pedidos()
        self.assertEqual(res_1["descuentos"], 1)
        self.ceviche.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 0)
        self.assertFalse(self.ceviche.disponible)

        # Ejecutar de nuevo sin cambios es idempotente
        res_2 = sincronizar_stock_con_pedidos()
        self.assertEqual(res_2["descuentos"], 0)
        self.assertEqual(res_2["reversiones"], 0)

        # Java anula el pedido -> el sincronizador restaura las 4 porciones y reactiva
        pedido.estado = Pedido.ESTADO_ANULADO
        pedido.save(update_fields=["estado"])
        res_3 = sincronizar_stock_con_pedidos()
        self.assertEqual(res_3["reversiones"], 1)
        self.ceviche.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 4)
        self.assertTrue(self.ceviche.disponible)

    def test_panel_web_stock_dia_fijar_ajustar_y_carga_masiva(self):
        """PRB-59: Flujo web completo en /stock-del-dia/, ajustes +/- y carga masiva."""
        self.client.force_login(self.staff_user)

        resp_get = self.client.get("/stock-del-dia/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, "Stock del Día")
        self.assertEqual(resp_get.context["kpis_stock"]["con_cupo"], 2)

        # Fijar cupo individual por JSON/AJAX
        resp_json = self.client.post(
            f"/platos/{self.ceviche.id}/fijar-stock/",
            {"stock_disponible": "12", "stock_minimo": "3"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_json.status_code, 200)
        self.assertEqual(resp_json.json()["stock_disponible"], 12)

        # Ajuste relativo (-2 porciones)
        resp_aj = self.client.post(
            f"/platos/{self.ceviche.id}/ajustar-stock/",
            {"delta": "-2", "motivo": "Degustación"},
        )
        self.assertEqual(resp_aj.status_code, 302)
        self.ceviche.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 10)

        # Carga masiva sobre categoría Ceviches
        resp_masiva = self.client.post(
            "/stock-del-dia/carga-masiva/",
            {
                "accion": "fijar_cupo",
                "categoria_id": str(self.cat_ceviches.id),
                "cupo": "20",
                "stock_minimo": "4",
            },
        )
        self.assertEqual(resp_masiva.status_code, 302)
        self.ceviche.refresh_from_db()
        self.tiradito.refresh_from_db()
        self.assertEqual(self.ceviche.stock_disponible, 20)
        self.assertEqual(self.tiradito.stock_disponible, 20)

    def test_toggle_disponibilidad_bloquea_activar_plato_con_stock_cero(self):
        """PRB-59: Impide reactivar manualmente un plato cuyo cupo diario está en 0."""
        self.client.force_login(self.staff_user)
        fijar_stock_diario(self.tiradito.id, stock_disponible=0)

        resp_json = self.client.post(
            f"/platos/{self.tiradito.id}/toggle-disponibilidad/",
            {"disponible": "true"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_json.status_code, 409)
        self.tiradito.refresh_from_db()
        self.assertFalse(self.tiradito.disponible)
        self.assertEqual(self.tiradito.stock_disponible, 0)

    def test_ajustar_stock_producto_impide_quedar_en_negativo(self):
        """PRB-59: El ajuste directo suma/resta porciones y rechaza saldos negativos."""
        plato, mov = ajustar_stock_producto(
            self.tiradito.id, delta=2, motivo="Nuevo ingreso"
        )
        self.assertEqual(plato.stock_disponible, 5)
        self.assertEqual(mov.tipo, MovimientoStock.TIPO_AJUSTE)

        with self.assertRaises(ValidationError):
            ajustar_stock_producto(self.tiradito.id, delta=-10)


class DatosRealesProduccionTests(TestCase):
    """Pruebas integrales de seeds reales, usuarios/PIN BCrypt y panel /personal/ (PRB-52)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="gerente_prod",
            password="ClaveSegura!2026",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="externo",
            password="ClaveSegura!2026",
            is_staff=False,
        )

    def test_modelos_rol_y_usuario_son_unmanaged_y_validan_bcrypt_d8(self):
        """PRB-52 / D7 / D8: Rol y Usuario tienen managed=False y hashes BCrypt cost 10."""
        self.assertFalse(Rol._meta.managed)
        self.assertFalse(Usuario._meta.managed)

        rol_mozo = Rol.objects.create(nombre="MOZO")
        mozo = Usuario(username="mozo_turno", rol=rol_mozo)

        with self.assertRaises(ValidationError):
            mozo.set_password_bcrypt("password123")
        with self.assertRaises(ValidationError):
            mozo.set_password_bcrypt("corta")
        with self.assertRaises(ValidationError):
            mozo.set_pin_bcrypt("12ab")

        mozo.set_password_bcrypt("MarinaSegura#2026")
        mozo.set_pin_bcrypt("4815")
        mozo.save()

        self.assertTrue(mozo.clave_hash.startswith("$2b$10$"))
        self.assertTrue(mozo.pin_hash.startswith("$2b$10$"))
        self.assertTrue(mozo.tiene_pin)
        self.assertTrue(mozo.check_password_bcrypt("MarinaSegura#2026"))
        self.assertFalse(mozo.check_password_bcrypt("incorrecta"))
        self.assertTrue(mozo.check_pin_bcrypt("4815"))
        self.assertFalse(mozo.check_pin_bcrypt("0000"))

    def test_comando_seed_produccion_idempotente_y_fotos_verificadas(self):
        """PRB-52: seed_produccion puebla carta (15), mesas (13), roles (4) y PINs sin duplicar."""
        # Simular residuos previos de seed.sql (admin_test con password123 y plato demo)
        r_admin = Rol.objects.create(nombre="ADMIN")
        r_mozo = Rol.objects.create(nombre="MOZO")
        Usuario.objects.create(
            username="admin_test",
            clave_hash=HASH_DEBIL_DEMO,
            rol=r_admin,
        )
        Usuario.objects.create(
            username="mozo_01",
            clave_hash=HASH_DEBIL_DEMO,
            pin_hash=None,
            rol=r_mozo,
        )
        cat_vieja = Categoria.objects.create(nombre="Entradas")
        Producto.objects.create(
            nombre="Ceviche Clásico",
            precio=Decimal("48.00"),
            disponible=True,
            categoria=cat_vieja,
        )

        # Ejecutar 2 veces seguidas para verificar idempotencia total
        call_command("seed_produccion")
        call_command("seed_produccion")
        call_command("seed_produccion", "--solo-auditar")

        auditoria = auditar_datos_produccion()
        self.assertTrue(auditoria["ok"], auditoria["errores"])
        self.assertEqual(auditoria["roles_total"], 4)
        self.assertEqual(auditoria["platos_oficiales"], 15)
        self.assertEqual(auditoria["mesas_total"], 13)
        self.assertFalse(Usuario.objects.filter(username="admin_test").exists())
        self.assertFalse(Usuario.objects.filter(clave_hash=HASH_DEBIL_DEMO).exists())
        self.assertFalse(Categoria.objects.filter(nombre="Entradas").exists())

        mozo1 = Usuario.objects.get(username="mozo_01")
        self.assertTrue(mozo1.tiene_pin)
        self.assertTrue(mozo1.check_pin_bcrypt("3011"))

    def test_personal_requiere_staff_autenticado(self):
        """PRB-52: /personal/ exige autenticación con permisos de staff."""
        resp_anon = self.client.get("/personal/")
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/login/", resp_anon["Location"])

        self.client.force_login(self.normal_user)
        resp_no_staff = self.client.get("/personal/")
        self.assertEqual(resp_no_staff.status_code, 302)

    def test_panel_personal_alta_rotacion_pin_y_desbloqueo(self):
        """PRB-52 / PRB-12: Permite crear usuario POS, rotar PIN/clave y desbloquear cuenta."""
        self.client.force_login(self.staff_user)

        resp_get = self.client.get("/personal/")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(Rol.objects.count(), 4)

        rol_cajero = Rol.objects.get(nombre="CAJERO")
        resp_crear = self.client.post(
            "/personal/nuevo/",
            {
                "username": "cajero_noche",
                "rol": str(rol_cajero.id),
                "password": "TurnoNoche!2026",
                "pin": "7788",
            },
        )
        self.assertEqual(resp_crear.status_code, 302)
        cajero = Usuario.objects.get(username="cajero_noche")
        self.assertTrue(cajero.check_password_bcrypt("TurnoNoche!2026"))
        self.assertTrue(cajero.check_pin_bcrypt("7788"))

        # Simular bloqueo por intentos fallidos en el POS y desbloquear desde Django
        cajero.intentos_fallidos = 5
        cajero.bloqueado_hasta = timezone.now() + timezone.timedelta(minutes=15)
        cajero.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
        self.assertTrue(cajero.esta_bloqueado)

        resp_unlock = self.client.post(f"/personal/{cajero.id}/desbloquear/")
        self.assertEqual(resp_unlock.status_code, 302)
        cajero.refresh_from_db()
        self.assertFalse(cajero.esta_bloqueado)
        self.assertEqual(cajero.intentos_fallidos, 0)

        # Rotar PIN a 9922 desde el formulario inline
        resp_upd = self.client.post(
            f"/personal/{cajero.id}/credenciales/",
            {
                "rol_id": str(rol_cajero.id),
                "nueva_clave": "",
                "nuevo_pin": "9922",
            },
        )
        self.assertEqual(resp_upd.status_code, 302)
        cajero.refresh_from_db()
        self.assertTrue(cajero.check_pin_bcrypt("9922"))

        # Sincronizar seeds reales desde botón web
        resp_sync = self.client.post("/personal/sincronizar-produccion/")
        self.assertEqual(resp_sync.status_code, 302)
        self.assertTrue(auditar_datos_produccion()["ok"])


class KDSCocinaTests(TestCase):
    """Pruebas integrales del KDS web de cocina, estaciones y semáforo SLA (PRB-57)."""

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.cocinero = User.objects.create_user(
            username="jefe_cocina",
            password="ClaveCocina!2026",
            is_staff=True,
        )
        self.mozo = User.objects.create_user(
            username="mozo_salon",
            password="ClaveMozo!2026",
            is_staff=False,
        )

        # Categorías
        self.cat_entradas = Categoria.objects.create(nombre="Entradas Marinas")
        self.cat_ceviches = Categoria.objects.create(nombre="Ceviches y Tiraditos")
        self.cat_fondos = Categoria.objects.create(nombre="Platos de Fondo")
        self.cat_bebidas = Categoria.objects.create(nombre="Bebidas")
        self.cat_postres = Categoria.objects.create(nombre="Postres")

        # Platos por estación
        self.ceviche = Producto.objects.create(
            nombre="Ceviche Clásico Casa Blanca",
            precio=Decimal("48.00"),
            disponible=True,
            categoria=self.cat_ceviches,
        )
        self.leche_tigre = Producto.objects.create(
            nombre="Leche de Tigre Clásica",
            precio=Decimal("25.00"),
            disponible=True,
            categoria=self.cat_entradas,
        )
        self.jalea = Producto.objects.create(
            nombre="Jalea Mixta Real",
            precio=Decimal("58.00"),
            disponible=True,
            categoria=self.cat_fondos,
        )
        self.chicha = Producto.objects.create(
            nombre="Chicha Morada de la Casa (1 L)",
            precio=Decimal("16.00"),
            disponible=True,
            categoria=self.cat_bebidas,
        )
        self.suspiro = Producto.objects.create(
            nombre="Suspiro a la Limeña",
            precio=Decimal("14.00"),
            disponible=True,
            categoria=self.cat_postres,
        )

        # Mesa
        self.mesa1 = Mesa.objects.create(
            numero=1,
            capacidad=4,
            ubicacion="Primer piso - Salón",
            estado=Mesa.ESTADO_OCUPADA,
        )

    def test_derivacion_de_estaciones_de_cocina_y_items(self):
        """PRB-57: Valida asignación canónica a BARRA_FRIA, COCINA_CALIENTE, BEBIDAS y POSTRES."""
        self.assertEqual(self.ceviche.estacion, Producto.ESTACION_BARRA_FRIA)
        self.assertEqual(self.leche_tigre.estacion, Producto.ESTACION_BARRA_FRIA)
        self.assertEqual(self.jalea.estacion, Producto.ESTACION_COCINA_CALIENTE)
        self.assertEqual(self.chicha.estacion, Producto.ESTACION_BEBIDAS)
        self.assertEqual(self.suspiro.estacion, Producto.ESTACION_POSTRES)

        # En DetallePedido
        pedido = Pedido.objects.create(
            mesa=self.mesa1, mozo_id=1, total=Decimal("48.00")
        )
        det = DetallePedido.objects.create(
            pedido=pedido,
            producto=self.ceviche,
            cantidad=1,
            precio_unitario=Decimal("48.00"),
            subtotal=Decimal("48.00"),
        )
        self.assertEqual(det.estacion, Producto.ESTACION_BARRA_FRIA)
        self.assertIn("Barra Fría", det.estacion_display)

    def test_cronometro_sla_y_semaforo_de_tiempos(self):
        """PRB-57: Semáforo SLA clasifica en NORMAL (<10m), ALERTA (10..20m) y CRITICO (>20m)."""
        ahora = timezone.now()

        # Comanda reciente (4 minutos): NORMAL (Verde)
        p_normal = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            total=Decimal("48.00"),
        )
        Pedido.objects.filter(pk=p_normal.pk).update(
            fecha_creacion=ahora - timezone.timedelta(minutes=4, seconds=15)
        )
        p_normal.refresh_from_db()
        self.assertEqual(p_normal.tiempo_transcurrido_minutos, 4)
        self.assertEqual(p_normal.nivel_sla, Pedido.SLA_NORMAL)

        # Comanda con demora moderada (14 minutos): ALERTA (Ámbar)
        p_alerta = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            total=Decimal("58.00"),
        )
        Pedido.objects.filter(pk=p_alerta.pk).update(
            fecha_creacion=ahora - timezone.timedelta(minutes=14, seconds=30)
        )
        p_alerta.refresh_from_db()
        self.assertEqual(p_alerta.tiempo_transcurrido_minutos, 14)
        self.assertEqual(p_alerta.nivel_sla, Pedido.SLA_ALERTA)

        # Comanda crítica (25 minutos): CRITICO (Rojo)
        p_critico = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            total=Decimal("70.00"),
        )
        Pedido.objects.filter(pk=p_critico.pk).update(
            fecha_creacion=ahora - timezone.timedelta(minutes=25, seconds=5)
        )
        p_critico.refresh_from_db()
        self.assertEqual(p_critico.tiempo_transcurrido_minutos, 25)
        self.assertEqual(p_critico.nivel_sla, Pedido.SLA_CRITICO)

    def test_avanzar_estado_comanda_y_auditoria_evento_pedido(self):
        """PRB-57: Transiciones PENDIENTE -> COCINANDO -> LISTO -> SERVIDO con EventoPedido."""
        pedido = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=2,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("106.00"),
        )

        # 1. PENDIENTE -> COCINANDO
        p1 = avanzar_estado_comanda(pedido.id, Pedido.ESTADO_COCINANDO, usuario_id=10)
        self.assertEqual(p1.estado, Pedido.ESTADO_COCINANDO)
        self.assertEqual(p1.version, 2)
        ev1 = EventoPedido.objects.filter(pedido=pedido).first()
        self.assertIsNotNone(ev1)
        self.assertEqual(ev1.estado_anterior, Pedido.ESTADO_PENDIENTE)
        self.assertEqual(ev1.estado_nuevo, Pedido.ESTADO_COCINANDO)
        self.assertEqual(ev1.usuario_id, 10)

        # 2. COCINANDO -> LISTO
        p2 = avanzar_estado_comanda(pedido.id, Pedido.ESTADO_LISTO, usuario_id=10)
        self.assertEqual(p2.estado, Pedido.ESTADO_LISTO)
        self.assertEqual(EventoPedido.objects.filter(pedido=pedido).count(), 2)

        # 3. LISTO -> SERVIDO
        p3 = avanzar_estado_comanda(pedido.id, Pedido.ESTADO_SERVIDO, usuario_id=2)
        self.assertEqual(p3.estado, Pedido.ESTADO_SERVIDO)
        self.assertEqual(EventoPedido.objects.filter(pedido=pedido).count(), 3)

        # 4. Transición inválida desde SERVIDO debe lanzar ValidationError
        with self.assertRaises(ValidationError):
            avanzar_estado_comanda(pedido.id, Pedido.ESTADO_COCINANDO)

    def test_filtrado_por_estaciones_y_estados_en_kds(self):
        """PRB-57: La cocina filtra comandas e ítems según la estación de trabajo."""
        # Pedido 1: solo ceviche (BARRA_FRIA)
        p1 = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("48.00"),
        )
        DetallePedido.objects.create(
            pedido=p1,
            producto=self.ceviche,
            cantidad=1,
            precio_unitario=Decimal("48.00"),
            subtotal=Decimal("48.00"),
        )

        # Pedido 2: mixto (jalea en COCINA_CALIENTE + chicha en BEBIDAS)
        p2 = Pedido.objects.create(
            mesa=None, mozo_id=1, estado=Pedido.ESTADO_COCINANDO, total=Decimal("74.00")
        )
        DetallePedido.objects.create(
            pedido=p2,
            producto=self.jalea,
            cantidad=1,
            precio_unitario=Decimal("58.00"),
            subtotal=Decimal("58.00"),
        )
        DetallePedido.objects.create(
            pedido=p2,
            producto=self.chicha,
            cantidad=1,
            precio_unitario=Decimal("16.00"),
            subtotal=Decimal("16.00"),
        )

        # Consulta todas las estaciones
        todas = obtener_comandas_kds(estacion=None, estado_filtro="activos")
        self.assertEqual(len(todas), 2)

        # Consulta solo Barra Fría: solo debe venir p1
        barra_fria = obtener_comandas_kds(
            estacion=Producto.ESTACION_BARRA_FRIA, estado_filtro="activos"
        )
        self.assertEqual(len(barra_fria), 1)
        self.assertEqual(barra_fria[0]["pedido"].id, p1.id)

        # Consulta solo Cocina Caliente: solo debe venir p2 y solo con el ítem de jalea
        cocina_cal = obtener_comandas_kds(
            estacion=Producto.ESTACION_COCINA_CALIENTE, estado_filtro="activos"
        )
        self.assertEqual(len(cocina_cal), 1)
        self.assertEqual(cocina_cal[0]["pedido"].id, p2.id)
        self.assertEqual(len(cocina_cal[0]["detalles"]), 1)
        self.assertEqual(
            cocina_cal[0]["detalles"][0].producto.nombre, "Jalea Mixta Real"
        )

        # Filtro de estado: pendientes vs cocinando
        pendientes = obtener_comandas_kds(estacion=None, estado_filtro="pendientes")
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["pedido"].id, p1.id)

        cocinando = obtener_comandas_kds(estacion=None, estado_filtro="cocinando")
        self.assertEqual(len(cocinando), 1)
        self.assertEqual(cocinando[0]["pedido"].id, p2.id)

    def test_kpis_kds_y_promedio_espera(self):
        """PRB-57: resumen_kpis_kds calcula pendientes, cocinando, listos y alertas."""
        Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("20.00"),
        )
        Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_COCINANDO,
            total=Decimal("30.00"),
        )
        Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_LISTO,
            total=Decimal("40.00"),
        )

        kpis = resumen_kpis_kds()
        self.assertEqual(kpis["pendientes"], 1)
        self.assertEqual(kpis["cocinando"], 1)
        self.assertEqual(kpis["listos"], 1)
        self.assertEqual(kpis["total_activos"], 2)

    def test_kds_seguridad_staff_y_render_pantalla(self):
        """PRB-57: /cocina/ exige usuario staff autenticado y renderiza comanda completa."""
        # Anónimo redirige al login
        resp_anon = self.client.get("/cocina/")
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/login/", resp_anon["Location"])

        # No staff redirige
        self.client.force_login(self.mozo)
        resp_no_staff = self.client.get("/cocina/")
        self.assertEqual(resp_no_staff.status_code, 302)

        # Staff entra OK
        self.client.force_login(self.cocinero)
        ped = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("48.00"),
        )
        DetallePedido.objects.create(
            pedido=ped,
            producto=self.ceviche,
            cantidad=2,
            notas="Sin culantro",
            precio_unitario=Decimal("48.00"),
            subtotal=Decimal("96.00"),
        )

        resp_ok = self.client.get("/cocina/")
        self.assertEqual(resp_ok.status_code, 200)
        self.assertContains(resp_ok, "KDS Cocina")
        self.assertContains(resp_ok, "Ceviche Clásico Casa Blanca")
        self.assertContains(resp_ok, "Sin culantro")
        self.assertContains(resp_ok, "Mesa 1")

    def test_kds_avanzar_pedido_html_y_ajax(self):
        """PRB-57: POST a avanzar soporta redirección HTML y respuesta AJAX."""
        self.client.force_login(self.cocinero)
        ped = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=1,
            estado=Pedido.ESTADO_PENDIENTE,
            total=Decimal("50.00"),
        )

        # 1. POST HTML estándar -> redirige a /cocina/
        resp_html = self.client.post(
            f"/cocina/pedidos/{ped.id}/avanzar/",
            {"nuevo_estado": Pedido.ESTADO_COCINANDO},
        )
        self.assertEqual(resp_html.status_code, 302)
        self.assertIn("/cocina/", resp_html["Location"])
        ped.refresh_from_db()
        self.assertEqual(ped.estado, Pedido.ESTADO_COCINANDO)

        # 2. POST AJAX con header XMLHttpRequest -> JSON {ok: true, nuevo_estado: "LISTO"}
        resp_ajax = self.client.post(
            f"/cocina/pedidos/{ped.id}/avanzar/",
            {"nuevo_estado": Pedido.ESTADO_LISTO},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp_ajax.status_code, 200)
        datos = resp_ajax.json()
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["nuevo_estado"], Pedido.ESTADO_LISTO)
        ped.refresh_from_db()
        self.assertEqual(ped.estado, Pedido.ESTADO_LISTO)

    def test_kds_api_comandas_polling_json(self):
        """PRB-57: GET /cocina/api/comandas/ devuelve JSON estructurado con comandas y KPIs."""
        self.client.force_login(self.cocinero)
        ped = Pedido.objects.create(
            mesa=self.mesa1,
            mozo_id=3,
            estado=Pedido.ESTADO_COCINANDO,
            total=Decimal("48.00"),
        )
        DetallePedido.objects.create(
            pedido=ped,
            producto=self.ceviche,
            cantidad=1,
            notas="Ají limo picado",
            precio_unitario=Decimal("48.00"),
            subtotal=Decimal("48.00"),
        )

        resp = self.client.get("/cocina/api/comandas/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("kpis", data)
        self.assertIn("comandas", data)
        self.assertEqual(len(data["comandas"]), 1)
        c0 = data["comandas"][0]
        self.assertEqual(c0["id"], ped.id)
        self.assertEqual(c0["estado"], Pedido.ESTADO_COCINANDO)
        self.assertEqual(c0["items"][0]["nombre"], "Ceviche Clásico Casa Blanca")
        self.assertEqual(c0["items"][0]["notas"], "Ají limo picado")
        self.assertEqual(c0["items"][0]["estacion"], Producto.ESTACION_BARRA_FRIA)
