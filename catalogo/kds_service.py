"""Servicio de cocina KDS: estaciones de preparación, estados y semáforo SLA (PRB-57).

Alcance P-10 (PLAN-PRODUCCION-POS.md §5.1, §8.4, ADR-01):
- KDS web en tiempo real para pantallas de cocina y tablet de barra marina.
- Estaciones canónicas: BARRA_FRIA (Cevichería), COCINA_CALIENTE, BEBIDAS, POSTRES.
- Semáforo SLA de preparación:
    - NORMAL (Verde): < 10 minutos
    - ALERTA (Ámbar): 10 a 20 minutos
    - CRITICO (Rojo): > 20 minutos
- Avance transaccional de comanda: PENDIENTE -> COCINANDO -> LISTO -> SERVIDO.
- Auditoría inmutable de eventos en la tabla compartida 'evento_pedido'.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import EventoPedido, Pedido, Producto

ESTACIONES_INFO = {
    Producto.ESTACION_BARRA_FRIA: {
        "codigo": Producto.ESTACION_BARRA_FRIA,
        "titulo": "Barra Fría (Cevichería)",
        "descripcion": "Ceviches, tiraditos, causas, choros a la chalaca y leche de tigre.",
        "badge_class": "badge-barra-fria",
    },
    Producto.ESTACION_COCINA_CALIENTE: {
        "codigo": Producto.ESTACION_COCINA_CALIENTE,
        "titulo": "Cocina Caliente",
        "descripcion": "Jaleas mixtas, arroces marinos, parihuelas, sudados y platos calientes.",
        "badge_class": "badge-cocina-caliente",
    },
    Producto.ESTACION_BEBIDAS: {
        "codigo": Producto.ESTACION_BEBIDAS,
        "titulo": "Bebidas",
        "descripcion": "Chicha morada casera, limonadas frozen y bebidas preparadas.",
        "badge_class": "badge-bebidas",
    },
    Producto.ESTACION_POSTRES: {
        "codigo": Producto.ESTACION_POSTRES,
        "titulo": "Postres",
        "descripcion": "Suspiros a la limeña, picarones tradicionales y dulces marinos.",
        "badge_class": "badge-postres",
    },
}

TRANSICIONES_COCINA = {
    Pedido.ESTADO_PENDIENTE: [
        Pedido.ESTADO_COCINANDO,
        Pedido.ESTADO_LISTO,
        Pedido.ESTADO_ANULADO,
    ],
    Pedido.ESTADO_COCINANDO: [
        Pedido.ESTADO_LISTO,
        Pedido.ESTADO_ANULADO,
    ],
    Pedido.ESTADO_LISTO: [
        Pedido.ESTADO_SERVIDO,
        Pedido.ESTADO_ANULADO,
    ],
}


def avanzar_estado_comanda(pedido_id, nuevo_estado, usuario_id=None, motivo=""):
    """Avanza de forma atómica el estado de una comanda registrando auditoría en evento_pedido."""
    nuevo_estado = (nuevo_estado or "").strip().upper()

    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        estado_actual = pedido.estado

        permitidos = TRANSICIONES_COCINA.get(estado_actual, [])
        if nuevo_estado not in permitidos:
            raise ValidationError(
                f"Transición no permitida: de '{estado_actual}' a '{nuevo_estado}'."
            )

        pedido.estado = nuevo_estado
        pedido.version = (pedido.version or 1) + 1
        campos_update = ["estado", "version"]
        if nuevo_estado == Pedido.ESTADO_ANULADO and motivo:
            pedido.motivo_anulacion = motivo[:255]
            campos_update.append("motivo_anulacion")
        pedido.save(update_fields=campos_update)

        EventoPedido.objects.create(
            pedido=pedido,
            estado_anterior=estado_actual,
            estado_nuevo=nuevo_estado,
            usuario_id=usuario_id,
            motivo=(motivo or f"Avance en KDS a {nuevo_estado}")[:255],
        )

    return pedido


def obtener_comandas_kds(estacion=None, estado_filtro="activos"):
    """Obtiene y decora las comandas del KDS según estación y estado."""
    qs = Pedido.objects.select_related("mesa").prefetch_related(
        "detalles__producto__categoria"
    )

    hoy = timezone.localdate()
    qs = qs.filter(fecha_creacion__date=hoy)

    estado_filtro = (estado_filtro or "activos").lower()
    if estado_filtro == "pendientes":
        qs = qs.filter(estado=Pedido.ESTADO_PENDIENTE)
    elif estado_filtro == "cocinando":
        qs = qs.filter(estado=Pedido.ESTADO_COCINANDO)
    elif estado_filtro == "listos":
        qs = qs.filter(estado=Pedido.ESTADO_LISTO)
    elif estado_filtro == "historico":
        qs = qs.filter(
            estado__in=[
                Pedido.ESTADO_SERVIDO,
                Pedido.ESTADO_COBRADO,
                Pedido.ESTADO_ANULADO,
            ],
        )
    else:  # "activos" por defecto
        qs = qs.filter(
            estado__in=[
                Pedido.ESTADO_PENDIENTE,
                Pedido.ESTADO_COCINANDO,
                Pedido.ESTADO_LISTO,
            ]
        )

    # En preparación se ordenan FIFO (las comandas más antiguas primero)
    if estado_filtro == "historico":
        qs = qs.order_by("-fecha_creacion")
    else:
        qs = qs.order_by("fecha_creacion")

    estacion_codigo = (estacion or "").strip().upper()
    if estacion_codigo and estacion_codigo not in ESTACIONES_INFO:
        estacion_codigo = ""

    comandas = []
    for ped in qs:
        todos_detalles = list(ped.detalles.all())
        if estacion_codigo:
            detalles_filtrados = [
                d for d in todos_detalles if d.producto.estacion == estacion_codigo
            ]
            if not detalles_filtrados:
                continue
        else:
            detalles_filtrados = todos_detalles

        minutos = ped.tiempo_transcurrido_minutos
        nivel_sla = ped.nivel_sla

        if nivel_sla == Pedido.SLA_CRITICO:
            sla_class = "sla-critico"
            sla_label = "Crítico (> 20m)"
        elif nivel_sla == Pedido.SLA_ALERTA:
            sla_class = "sla-alerta"
            sla_label = "Alerta (10–20m)"
        else:
            sla_class = "sla-normal"
            sla_label = "En tiempo (< 10m)"

        # Determinar siguiente acción KDS sugerida
        proxima_accion = None
        if ped.estado == Pedido.ESTADO_PENDIENTE:
            proxima_accion = {
                "target_estado": Pedido.ESTADO_COCINANDO,
                "label": "Iniciar Preparación",
                "btn_class": "btn-kds-iniciar",
            }
        elif ped.estado == Pedido.ESTADO_COCINANDO:
            proxima_accion = {
                "target_estado": Pedido.ESTADO_LISTO,
                "label": "Marcar como Listo",
                "btn_class": "btn-kds-listo",
            }
        elif ped.estado == Pedido.ESTADO_LISTO:
            proxima_accion = {
                "target_estado": Pedido.ESTADO_SERVIDO,
                "label": "Despachar a Mesa",
                "btn_class": "btn-kds-servir",
            }

        comandas.append(
            {
                "pedido": ped,
                "detalles": detalles_filtrados,
                "total_items": sum(d.cantidad for d in detalles_filtrados),
                "minutos": minutos,
                "tiempo_formateado": ped.tiempo_transcurrido_formateado,
                "nivel_sla": nivel_sla,
                "sla_class": sla_class,
                "sla_label": sla_label,
                "origen": ped.origen_display,
                "proxima_accion": proxima_accion,
            }
        )

    return comandas


def resumen_kpis_kds():
    """Calcula las métricas operativas del KDS para el turno en vivo."""
    hoy = timezone.localdate()
    qs_hoy = Pedido.objects.filter(fecha_creacion__date=hoy)

    pendientes = qs_hoy.filter(estado=Pedido.ESTADO_PENDIENTE).count()
    cocinando = qs_hoy.filter(estado=Pedido.ESTADO_COCINANDO).count()
    listos = qs_hoy.filter(estado=Pedido.ESTADO_LISTO).count()

    # Contar órdenes activas que superan SLA (>= 10 min)
    activos = qs_hoy.filter(
        estado__in=[Pedido.ESTADO_PENDIENTE, Pedido.ESTADO_COCINANDO]
    )
    alertas_sla = 0
    tiempos = []
    for p in activos:
        m = p.tiempo_transcurrido_minutos
        tiempos.append(m)
        if m >= Pedido.SLA_MINUTOS_VERDE:
            alertas_sla += 1

    promedio_espera = round(sum(tiempos) / len(tiempos), 1) if tiempos else 0.0

    return {
        "pendientes": pendientes,
        "cocinando": cocinando,
        "listos": listos,
        "total_activos": pendientes + cocinando,
        "alertas_sla": alertas_sla,
        "promedio_espera_minutos": promedio_espera,
        "total_hoy": qs_hoy.count(),
    }


def serializar_comandas_json(comandas):
    """Serializa la lista de comandas KDS para el polling AJAX en tiempo real."""
    resultado = []
    for c in comandas:
        p = c["pedido"]
        items_payload = []
        for d in c["detalles"]:
            items_payload.append(
                {
                    "id": d.id,
                    "cantidad": d.cantidad,
                    "nombre": d.producto.nombre,
                    "estacion": d.estacion,
                    "estacion_display": d.estacion_display,
                    "notas": d.notas or "",
                }
            )

        resultado.append(
            {
                "id": p.id,
                "mesa": p.mesa.numero if p.mesa else None,
                "origen": c["origen"],
                "mozo_id": p.mozo_id,
                "estado": p.estado,
                "estado_display": p.get_estado_display(),
                "total": str(p.total),
                "tiempo": c["tiempo_formateado"],
                "minutos": c["minutos"],
                "nivel_sla": c["nivel_sla"],
                "sla_class": c["sla_class"],
                "sla_label": c["sla_label"],
                "total_items": c["total_items"],
                "items": items_payload,
                "proxima_accion": c["proxima_accion"],
            }
        )
    return resultado
