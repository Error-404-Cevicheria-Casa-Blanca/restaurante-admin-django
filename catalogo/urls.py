"""Rutas del módulo web de gestión de catálogo, precios y pesca del día (PRB-19)."""

from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.dashboard_catalogo, name="dashboard"),
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
]
