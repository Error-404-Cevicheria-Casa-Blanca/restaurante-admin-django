"""Rutas del módulo web de gestión de catálogo, precios y pesca del día (PRB-19)."""

from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.dashboard_catalogo, name="dashboard"),
    path("operativo/kpis/", views.kpis_operativos_api, name="kpis_operativos"),
    path("login/", views.panel_login, name="login"),
    path("logout/", views.panel_logout, name="logout"),
    path("platos/", views.lista_platos, name="platos_list"),
    path("platos/nuevo/", views.crear_plato, name="plato_create"),
    path("platos/<int:pk>/editar/", views.editar_plato, name="plato_edit"),
    path("platos/<int:pk>/eliminar/", views.eliminar_plato, name="plato_delete"),
    path(
        "platos/<int:pk>/toggle-disponibilidad/",
        views.toggle_disponibilidad_plato,
        name="plato_toggle",
    ),
    path(
        "platos/<int:pk>/actualizar-precio/",
        views.actualizar_precio_plato,
        name="plato_update_price",
    ),
    path(
        "platos/accion-masiva/",
        views.accion_masiva_platos,
        name="platos_bulk_action",
    ),
    path("pesca-del-dia/", views.pesca_del_dia, name="pesca_dia"),
    path(
        "pesca-del-dia/categoria/<int:pk>/estado/",
        views.cambiar_estado_categoria,
        name="categoria_toggle_all",
    ),
    path("categorias/", views.gestion_categorias, name="categorias"),
    path(
        "categorias/<int:pk>/editar/",
        views.editar_categoria,
        name="categoria_edit",
    ),
    path(
        "categorias/<int:pk>/eliminar/",
        views.eliminar_categoria,
        name="categoria_delete",
    ),
    path(
        "cargar-carta-ejemplo/",
        views.cargar_carta_ejemplo_view,
        name="seed_demo",
    ),
    # Cierre de caja y arqueo por turno (PRB-60)
    path("caja/", views.caja_arqueo, name="caja"),
    path("caja/abrir/", views.abrir_caja, name="caja_abrir"),
    path("caja/cerrar/", views.cerrar_caja, name="caja_cerrar"),
    # Reportes básicos de ventas y medios de pago (PRB-61)
    path("reportes/", views.reportes_ventas, name="reportes"),
    # Inventario reducido: stock del día, descuento y reversión (PRB-59)
    path("stock-del-dia/", views.stock_del_dia, name="stock_dia"),
    path(
        "platos/<int:pk>/fijar-stock/",
        views.fijar_stock_plato,
        name="plato_fijar_stock",
    ),
    path(
        "platos/<int:pk>/ajustar-stock/",
        views.ajustar_stock_plato,
        name="plato_ajustar_stock",
    ),
    path(
        "stock-del-dia/carga-masiva/",
        views.carga_masiva_stock,
        name="stock_carga_masiva",
    ),
    # Personal operativo, roles, PIN BCrypt y datos reales (PRB-52 / PRB-12)
    path("personal/", views.personal_operativo, name="personal"),
    path("personal/nuevo/", views.crear_usuario_operativo, name="personal_create"),
    path(
        "personal/<int:pk>/credenciales/",
        views.actualizar_credenciales_operativas,
        name="personal_update_credentials",
    ),
    path(
        "personal/<int:pk>/desbloquear/",
        views.desbloquear_usuario_operativo,
        name="personal_unlock",
    ),
    path(
        "personal/sincronizar-produccion/",
        views.sincronizar_seeds_produccion_view,
        name="personal_sync_seeds",
    ),
    # KDS de cocina en tiempo real: estaciones y semáforo SLA (PRB-57 · P-10)
    path("cocina/", views.kds_cocina, name="kds_cocina"),
    path(
        "cocina/pedidos/<int:pk>/avanzar/",
        views.kds_avanzar_pedido,
        name="kds_avanzar_pedido",
    ),
    path(
        "cocina/items/<int:detalle_id>/avanzar/",
        views.kds_avanzar_item,
        name="kds_avanzar_item",
    ),
    path(
        "cocina/api/comandas/",
        views.kds_api_comandas,
        name="kds_api_comandas",
    ),
]
