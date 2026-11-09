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
from django.db import connection
from django.test import SimpleTestCase, TestCase

from catalogo.admin import CategoriaAdmin, ProductoAdmin, RolAdmin, UsuarioAdmin
from catalogo.models import Categoria, Mesa, Pedido, Producto, Rol, Usuario

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
        if Rol._meta.db_table not in existentes:
            editor.create_model(Rol)
        if Usuario._meta.db_table not in existentes:
            editor.create_model(Usuario)


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


class UsuariosRolesCRUDTests(TestCase):
    """Pruebas unitarias e integración del CRUD de usuarios y roles (PRB-12).

    Verifica el criterio de aceptación de PRB-12:
    - Listado, alta, edición y desactivación de usuarios.
    - Asignación y cambio de rol (ADMIN, MOZO, CAJERO, COCINERO).
    - Validación de usuario único y datos obligatorios.
    - Protección de acceso al panel y sincronización de permisos según rol.
    """

    @classmethod
    def setUpClass(cls):
        _crear_tablas_unmanaged_si_no_existen()
        super().setUpClass()

    def setUp(self):
        User = get_user_model()
        self.admin_panel = User.objects.create_user(
            username="admin_prb12",
            password="AdminPassword!123",
            is_staff=True,
        )
        self.usuario_sin_permiso = User.objects.create_user(
            username="mozo_sin_panel",
            password="MozoPassword!123",
            is_staff=False,
        )
        self.rol_admin, _ = Rol.objects.get_or_create(nombre=Rol.ROL_ADMIN)
        self.rol_mozo, _ = Rol.objects.get_or_create(nombre=Rol.ROL_MOZO)
        self.rol_cajero, _ = Rol.objects.get_or_create(nombre=Rol.ROL_CAJERO)
        self.rol_cocinero, _ = Rol.objects.get_or_create(nombre=Rol.ROL_COCINERO)

    def test_proteccion_acceso_panel_usuarios(self):
        """Usuarios anónimos o sin rol ADMIN son redirigidos al login."""
        for ruta in ("/usuarios/", "/usuarios/nuevo/"):
            resp_anon = self.client.get(ruta)
            self.assertEqual(resp_anon.status_code, 302)
            self.assertIn("/login/", resp_anon["Location"])

        self.client.force_login(self.usuario_sin_permiso)
        resp_mozo = self.client.get("/usuarios/")
        self.assertEqual(resp_mozo.status_code, 302)
        self.assertIn("/login/", resp_mozo["Location"])

    def test_alta_usuario_y_sincronizacion_acceso_panel_por_rol(self):
        """Crear un usuario ADMIN habilita acceso al panel; MOZO queda como operativo."""
        self.client.force_login(self.admin_panel)

        # 1. Crear usuario con rol ADMIN
        resp_admin = self.client.post(
            "/usuarios/nuevo/",
            {
                "username": "nuevo_admin",
                "rol": self.rol_admin.id,
                "password": "ClaveAdmin2026!",
                "activo": "on",
            },
        )
        self.assertEqual(resp_admin.status_code, 302)
        u_admin = Usuario.objects.get(username="nuevo_admin")
        self.assertEqual(u_admin.rol.nombre, "ADMIN")
        self.assertTrue(u_admin.activo)

        User = get_user_model()
        auth_admin = User.objects.get(username="nuevo_admin")
        self.assertTrue(auth_admin.is_staff)
        self.assertTrue(auth_admin.is_active)
        self.assertTrue(auth_admin.check_password("ClaveAdmin2026!"))

        # 2. Crear usuario con rol MOZO
        resp_mozo = self.client.post(
            "/usuarios/nuevo/",
            {
                "username": "mozo_salon_01",
                "rol": self.rol_mozo.id,
                "password": "ClaveMozo2026!",
                "activo": "on",
            },
        )
        self.assertEqual(resp_mozo.status_code, 302)
        u_mozo = Usuario.objects.get(username="mozo_salon_01")
        self.assertEqual(u_mozo.rol.nombre, "MOZO")
        self.assertTrue(u_mozo.activo)

        auth_mozo = User.objects.get(username="mozo_salon_01")
        self.assertFalse(auth_mozo.is_staff)
        self.assertTrue(auth_mozo.is_active)

    def test_validacion_unicidad_y_campos_obligatorios(self):
        """Rechaza usernames duplicados, con espacios, vacíos o contraseñas cortas."""
        self.client.force_login(self.admin_panel)
        Usuario.objects.create(
            username="cajero_existente",
            clave_hash="hash_inicial",
            rol=self.rol_cajero,
        )

        # Username duplicado (case-insensitive)
        resp_dup = self.client.post(
            "/usuarios/nuevo/",
            {
                "username": "CAJERO_EXISTENTE",
                "rol": self.rol_cajero.id,
                "password": "ClaveSegura123",
                "activo": "on",
            },
        )
        self.assertEqual(resp_dup.status_code, 200)
        self.assertContains(resp_dup, "Ya existe un usuario con ese nombre de usuario.")
        self.assertEqual(
            Usuario.objects.filter(username__iexact="cajero_existente").count(),
            1,
        )

        # Username vacío y contraseña corta
        resp_inv = self.client.post(
            "/usuarios/nuevo/",
            {
                "username": "   ",
                "rol": self.rol_mozo.id,
                "password": "123",
                "activo": "on",
            },
        )
        self.assertEqual(resp_inv.status_code, 200)
        self.assertContains(resp_inv, "El nombre de usuario es obligatorio.")
        self.assertContains(
            resp_inv,
            "La contraseña debe tener al menos 6 caracteres.",
        )

    def test_edicion_cambio_rol_y_desactivacion_usuario(self):
        """Editar rol y desactivar usuario refleja cambios en BD y acceso al panel."""
        self.client.force_login(self.admin_panel)
        self.client.post(
            "/usuarios/nuevo/",
            {
                "username": "supervisor_turno",
                "rol": self.rol_admin.id,
                "password": "PasswordInicial123",
                "activo": "on",
            },
        )
        u = Usuario.objects.get(username="supervisor_turno")
        User = get_user_model()
        self.assertTrue(User.objects.get(username="supervisor_turno").is_staff)

        # Cambiar rol de ADMIN a COCINERO mediante endpoint rápido
        resp_rol = self.client.post(
            f"/usuarios/{u.id}/cambiar-rol/",
            {"rol": str(self.rol_cocinero.id)},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_rol.status_code, 200)
        self.assertEqual(resp_rol.json()["rol"], "COCINERO")
        u.refresh_from_db()
        self.assertEqual(u.rol.nombre, "COCINERO")
        self.assertFalse(User.objects.get(username="supervisor_turno").is_staff)

        # Editar usuario por formulario (cambiar username y volver a ADMIN)
        resp_edit = self.client.post(
            f"/usuarios/{u.id}/editar/",
            {
                "username": "jefe_cocina",
                "rol": self.rol_admin.id,
                "password": "",
                "activo": "on",
            },
        )
        self.assertEqual(resp_edit.status_code, 302)
        u.refresh_from_db()
        self.assertEqual(u.username, "jefe_cocina")
        self.assertEqual(u.rol.nombre, "ADMIN")
        self.assertTrue(User.objects.get(username="jefe_cocina").is_staff)

        # Desactivar usuario mediante toggle
        resp_toggle = self.client.post(
            f"/usuarios/{u.id}/toggle-estado/",
            {},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_toggle.status_code, 200)
        self.assertFalse(resp_toggle.json()["activo"])
        u.refresh_from_db()
        self.assertFalse(u.activo)
        auth_u = User.objects.get(username="jefe_cocina")
        self.assertFalse(auth_u.is_active)
        self.assertFalse(auth_u.is_staff)

        # Reactivar usuario mediante toggle
        resp_react = self.client.post(
            f"/usuarios/{u.id}/toggle-estado/",
            {},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp_react.status_code, 200)
        self.assertTrue(resp_react.json()["activo"])
        u.refresh_from_db()
        self.assertTrue(u.activo)
        auth_u.refresh_from_db()
        self.assertTrue(auth_u.is_active)
        self.assertTrue(auth_u.is_staff)

    def test_listado_filtros_y_acciones_admin_usuarios(self):
        """Verifica listado con filtros por rol/estado y acciones de UsuarioAdmin."""
        self.client.force_login(self.admin_panel)
        u1 = Usuario.objects.create(
            username="mozo_a",
            clave_hash="hash_a",
            rol=self.rol_mozo,
        )
        u2 = Usuario.objects.create(
            username="cajero_b",
            clave_hash="!INACTIVO!hash_b",
            rol=self.rol_cajero,
        )

        resp_list = self.client.get("/usuarios/?rol=MOZO&estado=activos")
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, "mozo_a")
        self.assertNotContains(resp_list, "cajero_b")

        resp_inact = self.client.get("/usuarios/?estado=inactivos")
        self.assertEqual(resp_inact.status_code, 200)
        self.assertContains(resp_inact, "cajero_b")
        self.assertNotContains(resp_inact, "mozo_a")

        # Acciones en Django Admin
        site = AdminSite()
        rol_admin = RolAdmin(Rol, site)
        usuario_admin = UsuarioAdmin(Usuario, site)
        self.assertEqual(rol_admin.total_usuarios(self.rol_mozo), 1)

        req = MagicMock()
        usuario_admin.desactivar_usuarios(req, Usuario.objects.filter(pk=u1.id))
        u1.refresh_from_db()
        self.assertFalse(u1.activo)

        usuario_admin.activar_usuarios(req, Usuario.objects.filter(pk=u2.id))
        u2.refresh_from_db()
        self.assertTrue(u2.activo)

