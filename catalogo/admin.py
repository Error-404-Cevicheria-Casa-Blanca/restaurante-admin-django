from django.contrib import admin, messages
from django.db.models import Count
from django.utils.translation import ngettext

from .models import Categoria, MovimientoStock, Pago, Producto, Rol, SesionCaja, Usuario


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
        "stock_disponible",
        "stock_minimo",
        "disponible",
    )
    list_editable = (
        "precio",
        "stock_disponible",
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
                    "stock_disponible",
                    "stock_minimo",
                    "disponible",
                ),
                "description": (
                    "Ajuste de precio en soles, cupo diario de porciones y "
                    "activación/desactivación del stock según la pesca del día."
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


@admin.register(SesionCaja)
class SesionCajaAdmin(admin.ModelAdmin):
    """Consulta administrativa de turnos de caja y cierres Z (PRB-60)."""

    list_display = (
        "id",
        "estado",
        "cajero_id",
        "fecha_apertura",
        "fecha_cierre",
        "monto_inicial",
        "monto_ventas_efectivo",
        "monto_ventas_digital",
        "monto_esperado",
        "monto_real",
        "diferencia",
    )
    list_filter = ("estado",)
    ordering = ("-fecha_apertura",)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    """Consulta administrativa de cobros por medio de pago (PRB-61)."""

    list_display = (
        "id",
        "pedido",
        "mesa",
        "sesion_caja",
        "metodo",
        "monto",
        "propina",
        "referencia",
        "fecha_pago",
    )
    list_filter = ("metodo",)
    search_fields = ("referencia", "client_request_id")
    ordering = ("-fecha_pago",)


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    """Consulta administrativa del kardex de stock del día (PRB-59)."""

    list_display = (
        "id",
        "fecha",
        "producto",
        "tipo",
        "cantidad",
        "stock_anterior",
        "stock_resultante",
        "pedido",
        "registrado_por",
        "motivo",
    )
    list_filter = ("tipo",)
    search_fields = ("producto__nombre", "motivo", "registrado_por")
    ordering = ("-fecha", "-id")


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    """Consulta de roles operativos del POS (PRB-52)."""

    list_display = ("id", "nombre")
    ordering = ("id",)


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    """Consulta administrativa de personal operativo y estado de PIN (PRB-52)."""

    list_display = (
        "id",
        "username",
        "rol",
        "tiene_pin",
        "intentos_fallidos",
        "bloqueado_hasta",
    )
    list_filter = ("rol",)
    search_fields = ("username",)
    ordering = ("rol_id", "username")
