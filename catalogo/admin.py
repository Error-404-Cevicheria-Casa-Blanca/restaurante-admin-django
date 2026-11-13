from django.contrib import admin, messages
from django.db.models import Count
from django.utils.translation import ngettext

from .models import (
    Categoria,
    EventoPedido,
    ImpresionCola,
    MovimientoStock,
    Pago,
    Producto,
    Rol,
    SesionCaja,
    SesionMozo,
    Terminal,
    Turno,
    Usuario,
)


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


@admin.register(EventoPedido)
class EventoPedidoAdmin(admin.ModelAdmin):
    """Consulta de auditoría inmutable de eventos de cocina y comanda (PRB-57)."""

    list_display = (
        "id",
        "fecha",
        "pedido",
        "estado_anterior",
        "estado_nuevo",
        "usuario_id",
        "motivo",
    )
    list_filter = ("estado_nuevo", "estado_anterior")
    search_fields = ("pedido__id", "motivo")
    ordering = ("-fecha", "-id")


@admin.register(ImpresionCola)
class ImpresionColaAdmin(admin.ModelAdmin):
    """Monitoreo y administración de la cola de impresión térmica de 80 mm (PRB-58)."""

    list_display = (
        "id",
        "fecha_creacion",
        "tipo",
        "estacion",
        "pedido",
        "estado",
        "intentos",
        "fecha_impresion",
    )
    list_filter = ("estado", "tipo", "estacion")
    search_fields = ("pedido__id", "payload", "error")
    ordering = ("-fecha_creacion", "-id")
    actions = ["reintentar_trabajos_seleccionados"]

    @admin.action(description="Reintentar trabajos de impresión seleccionados")
    def reintentar_trabajos_seleccionados(self, request, queryset):
        from .impresion_service import reintentar_trabajo

        reintentados = 0
        for trabajo in queryset:
            exito, _ = reintentar_trabajo(trabajo.id)
            if exito:
                reintentados += 1
        self.message_user(
            request,
            f"Se reintentaron {reintentados} trabajos de impresión.",
            messages.SUCCESS,
        )


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    """Administración y consulta de turnos de salón (PRB-84)."""

    list_display = ("id", "nombre", "hora_inicio", "hora_fin", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)
    ordering = ("hora_inicio", "id")


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    """Administración y consulta de terminales físicas POS (PRB-84)."""

    list_display = ("id", "codigo", "nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("codigo", "nombre")
    ordering = ("codigo",)


@admin.register(SesionMozo)
class SesionMozoAdmin(admin.ModelAdmin):
    """Consulta de auditoría de sesiones de mozos por terminal y turno (PRB-84)."""

    list_display = (
        "id",
        "usuario",
        "terminal",
        "turno",
        "inicio",
        "fin",
        "esta_activa",
    )
    list_filter = ("turno", "terminal")
    search_fields = ("usuario__username", "terminal__codigo", "turno__nombre")
    ordering = ("-inicio", "-id")
