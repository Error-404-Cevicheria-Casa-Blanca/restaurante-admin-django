from django.contrib import admin, messages
from django.db.models import Count
from django.utils.translation import ngettext

from .forms import sincronizar_acceso_panel_django
from .models import Categoria, Producto, Rol, Usuario


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    """Administración de categorías del menú."""

    list_display = ("id", "nombre", "total_productos")
    search_fields = ("nombre",)
    ordering = ("id",)

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(_total_productos=Count("productos"))
        )

    @admin.display(description="Total de platos", ordering="_total_productos")
    def total_productos(self, obj):
        if hasattr(obj, "_total_productos"):
            return obj._total_productos
        return obj.productos.count()


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    """Administración del catálogo de platos, precios y disponibilidad diaria.

    Cumple con el alcance del ticket PE-19:
    - Alta y registro detallado de platos marinos.
    - Edición inline y masiva de precios (list_editable).
    - Activación y desactivación de stock según pesca del día (list_editable y acciones).
    """

    list_display = (
        "id",
        "nombre",
        "categoria",
        "precio",
        "disponible",
    )
    list_editable = (
        "precio",
        "disponible",
    )
    list_filter = (
        "disponible",
        "categoria",
    )
    search_fields = (
        "nombre",
        "descripcion",
    )
    ordering = (
        "categoria",
        "nombre",
    )
    list_per_page = 20

    fieldsets = (
        (
            "Información del Plato",
            {
                "fields": (
                    "nombre",
                    "categoria",
                    "descripcion",
                )
            },
        ),
        (
            "Precios y Stock del Día",
            {
                "fields": (
                    "precio",
                    "disponible",
                ),
                "description": (
                    "Ajuste de precio en soles y activación/desactivación del stock "
                    "según la pesca del día."
                ),
            },
        ),
        (
            "Multimedia",
            {
                "fields": ("imagen_url",),
                "classes": ("collapse",),
            },
        ),
    )

    actions = [
        "marcar_disponible_pesca_dia",
        "marcar_no_disponible_pesca_dia",
    ]

    @admin.action(description="Marcar seleccionados como DISPONIBLES (pesca del día)")
    def marcar_disponible_pesca_dia(self, request, queryset):
        filas_actualizadas = queryset.update(disponible=True)
        self.message_user(
            request,
            ngettext(
                "%d plato marcado como disponible (pesca del día).",
                "%d platos marcados como disponibles (pesca del día).",
                filas_actualizadas,
            )
            % filas_actualizadas,
            messages.SUCCESS,
        )

    @admin.action(description="Marcar seleccionados como NO DISPONIBLES / AGOTADOS")
    def marcar_no_disponible_pesca_dia(self, request, queryset):
        filas_actualizadas = queryset.update(disponible=False)
        self.message_user(
            request,
            ngettext(
                "%d plato marcado como no disponible (agotado).",
                "%d platos marcados como no disponibles (agotados).",
                filas_actualizadas,
            )
            % filas_actualizadas,
            messages.WARNING,
        )


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    """Administración de roles del sistema (PRB-12)."""

    list_display = ("id", "nombre", "total_usuarios")
    search_fields = ("nombre",)
    ordering = ("id",)

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(_total_usuarios=Count("usuarios"))
        )

    @admin.display(description="Total de usuarios", ordering="_total_usuarios")
    def total_usuarios(self, obj):
        if hasattr(obj, "_total_usuarios"):
            return obj._total_usuarios
        return obj.usuarios.count()


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    """Administración de usuarios y roles del sistema POS (PRB-12)."""

    list_display = ("id", "username", "rol", "estado_activo")
    list_filter = ("rol",)
    search_fields = ("username",)
    ordering = ("username",)
    actions = ["desactivar_usuarios", "activar_usuarios"]

    @admin.display(boolean=True, description="Activo")
    def estado_activo(self, obj):
        return obj.activo

    @admin.action(description="Desactivar usuarios seleccionados")
    def desactivar_usuarios(self, request, queryset):
        contador = 0
        for usuario in queryset.select_related("rol"):
            if usuario.activo:
                usuario.desactivar()
                usuario.save(update_fields=["clave_hash"])
                sincronizar_acceso_panel_django(usuario)
                contador += 1
        self.message_user(
            request,
            f"{contador} usuario(s) desactivado(s).",
            messages.WARNING,
        )

    @admin.action(description="Activar usuarios seleccionados")
    def activar_usuarios(self, request, queryset):
        contador = 0
        for usuario in queryset.select_related("rol"):
            if not usuario.activo:
                usuario.activar()
                usuario.save(update_fields=["clave_hash"])
                sincronizar_acceso_panel_django(usuario)
                contador += 1
        self.message_user(
            request,
            f"{contador} usuario(s) activado(s).",
            messages.SUCCESS,
        )

