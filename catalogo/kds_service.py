"""Servicio de cocina KDS: estaciones de preparación, estados y semáforo SLA (PRB-57, PRB-86).

Alcance P-10 (PLAN-PRODUCCION-POS.md §5.1, §8.4, ADR-01):
- KDS web en tiempo real para pantallas de cocina y tablet de barra marina.
- Estaciones canónicas: BARRA_FRIA (Cevichería), COCINA_CALIENTE, BEBIDAS, POSTRES.
- Semáforo SLA de preparación:
    - NORMAL (Verde): < 10 minutos
    - ALERTA (Ámbar): 10 a 20 minutos
    - CRITICO (Rojo): > 20 minutos
- Avance transaccional de comanda y por ítem individual (PRB-86):
  Comanda: PENDIENTE -> COCINANDO -> LISTO -> SERVIDO.
  Ítem: PENDIENTE -> EN_PREPARACION -> LISTO -> SERVIDO (CONTRATO-API-V2 / EstadoItem).
- Aislamiento por estación: marcar 'Listo' en barra fría no marca platos de cocina caliente.
- Auditoría inmutable de eventos en la tabla compartida 'evento_pedido'.
"""

import logging
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import DetallePedido, EventoPedido, Pedido, Producto, Usuario

logger = logging.getLogger(__name__)

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

TRANSICIONES_ITEM = {
    DetallePedido.ESTADO_ITEM_PENDIENTE: [
        DetallePedido.ESTADO_ITEM_EN_PREPARACION,
        DetallePedido.ESTADO_ITEM_LISTO,
    ],
    DetallePedido.ESTADO_ITEM_EN_PREPARACION: [
        DetallePedido.ESTADO_ITEM_LISTO,
    ],
    DetallePedido.ESTADO_ITEM_LISTO: [
        DetallePedido.ESTADO_ITEM_SERVIDO,
    ],
    DetallePedido.ESTADO_ITEM_SERVIDO: [],
}

MAPA_PEDIDO_A_ESTADO_ITEM = {
    Pedido.ESTADO_PENDIENTE: DetallePedido.ESTADO_ITEM_PENDIENTE,
    Pedido.ESTADO_COCINANDO: DetallePedido.ESTADO_ITEM_EN_PREPARACION,
    Pedido.ESTADO_LISTO: DetallePedido.ESTADO_ITEM_LISTO,
    Pedido.ESTADO_SERVIDO: DetallePedido.ESTADO_ITEM_SERVIDO,
}


def _validar_fk_usuario_id(usuario_id):
    """Garantiza que usuario_id sea válido para evitar ForeignKeyViolation en PostgreSQL."""
    if not usuario_id:
        return None
    try:
        from django.db import connection

        # En SQLite (pruebas locales), respetar el ID asignado directamente
        if connection.vendor == "sqlite":
            return usuario_id
        if Usuario.objects.filter(pk=usuario_id).exists():
            return usuario_id
    except Exception:
        pass
    return None


def recalcular_estado_pedido(pedido):
    """Recalcula el estado general del Pedido en función de sus ítems (PRB-86)."""
    detalles = list(pedido.detalles.all())
    if not detalles:
        return pedido.estado

    estados_activos = set(d.estado_item for d in detalles)
    if all(e == DetallePedido.ESTADO_ITEM_SERVIDO for e in estados_activos):
        nuevo_estado = Pedido.ESTADO_SERVIDO
    elif all(
        e in (DetallePedido.ESTADO_ITEM_LISTO, DetallePedido.ESTADO_ITEM_SERVIDO)
        for e in estados_activos
    ):
        nuevo_estado = Pedido.ESTADO_LISTO
    elif any(
        e
        in (
            DetallePedido.ESTADO_ITEM_EN_PREPARACION,
            DetallePedido.ESTADO_ITEM_LISTO,
            DetallePedido.ESTADO_ITEM_SERVIDO,
        )
        for e in estados_activos
    ):
        nuevo_estado = Pedido.ESTADO_COCINANDO
    else:
        nuevo_estado = Pedido.ESTADO_PENDIENTE

    if pedido.estado != nuevo_estado:
        pedido.estado = nuevo_estado
        pedido.version = (pedido.version or 1) + 1
        pedido.save(update_fields=["estado", "version"])

    return pedido.estado


def avanzar_estado_item(detalle_id, nuevo_estado, usuario_id=None, motivo=""):
    """Avanza atómicamente el estado de un plato/ítem individual de la comanda (PRB-57, PRB-86)."""
    nuevo_estado = (nuevo_estado or "").strip().upper()

    with transaction.atomic():
        detalle = (
            DetallePedido.objects.select_for_update()
            .select_related("pedido", "producto")
            .get(pk=detalle_id)
        )
        pedido = detalle.pedido
        estado_ant = detalle.estado_item or DetallePedido.ESTADO_ITEM_PENDIENTE

        permitidos = TRANSICIONES_ITEM.get(estado_ant, [])
        if nuevo_estado not in permitidos and nuevo_estado != estado_ant:
            raise ValidationError(
                f"Transición de ítem no permitida: de '{estado_ant}' a '{nuevo_estado}'."
            )

        detalle.estado_item = nuevo_estado
        detalle.save(update_fields=["estado_item"])

        usuario_valido_id = _validar_fk_usuario_id(usuario_id)

        EventoPedido.objects.create(
            pedido=pedido,
            estado_anterior=estado_ant,
            estado_nuevo=nuevo_estado,
            usuario_id=usuario_valido_id,
            motivo=(
                motivo
                or f"Avance ítem #{detalle.id} ({detalle.producto.nombre}) a {nuevo_estado}"
            )[:255],
        )

        recalcular_estado_pedido(pedido)

        # Descuento de stock automático al pasar a EN_PREPARACION o LISTO
        if nuevo_estado in (
            DetallePedido.ESTADO_ITEM_EN_PREPARACION,
            DetallePedido.ESTADO_ITEM_LISTO,
        ):
            try:
                from .stock_service import descontar_stock_pedido

                descontar_stock_pedido(
                    pedido_id=pedido.id,
                    motivo=(
                        f"Avance KDS ítem #{detalle.id} "
                        f"({detalle.producto.nombre}) a {nuevo_estado}"
                    ),
                    registrado_por=(
                        f"kds_usuario_{usuario_valido_id}"
                        if usuario_valido_id
                        else "kds"
                    ),
                    estricto=False,
                )
            except Exception as exc:
                logger.warning(
                    "Error al descontar stock para pedido %s en KDS (ítem %s): %s",
                    pedido.id,
                    detalle.id,
                    exc,
                )

    return detalle


def avanzar_estado_comanda(
    pedido_id, nuevo_estado, estacion=None, usuario_id=None, motivo=""
):
    """Avanza de forma atómica el estado de una comanda o de una estación específica (PRB-57).

    Si se especifica `estacion`, solo avanza los ítems pertenecientes a esa estación,
    evitando que marcar 'Listo' en una barra (ej. Bebidas) marque toda la comanda como lista.
    """
    nuevo_estado = (nuevo_estado or "").strip().upper()
    if nuevo_estado == "EN_PREPARACION":
        nuevo_estado = Pedido.ESTADO_COCINANDO

    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        estado_actual = pedido.estado
        usuario_valido_id = _validar_fk_usuario_id(usuario_id)

        estado_item_destino = MAPA_PEDIDO_A_ESTADO_ITEM.get(nuevo_estado)

        # Si se especifica estación, avanzar solo los ítems de esa estación
        if estacion:
            estacion_cod = estacion.strip().upper()
            detalles_qs = pedido.detalles.select_for_update().select_related(
                "producto"
            )
            afectados = 0
            for d in detalles_qs:
                if (d.estacion_item or d.producto.estacion) == estacion_cod:
                    if estado_item_destino:
                        d.estado_item = estado_item_destino
                        d.save(update_fields=["estado_item"])
                        afectados += 1

            if afectados > 0:
                EventoPedido.objects.create(
                    pedido=pedido,
                    estado_anterior=estado_actual,
                    estado_nuevo=f"{nuevo_estado} [{estacion_cod}]",
                    usuario_id=usuario_valido_id,
                    motivo=(
                        motivo or f"Avance estación {estacion_cod} a {nuevo_estado}"
                    )[:255],
                )

            recalcular_estado_pedido(pedido)

        else:
            # Avance global de comanda
            permitidos = TRANSICIONES_COCINA.get(estado_actual, [])
            if nuevo_estado not in permitidos and nuevo_estado != estado_actual:
                raise ValidationError(
                    f"Transición no permitida: de '{estado_actual}' a '{nuevo_estado}'."
                )

            if estado_item_destino:
                for d in pedido.detalles.select_for_update():
                    d.estado_item = estado_item_destino
                    d.save(update_fields=["estado_item"])

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
                usuario_id=usuario_valido_id,
                motivo=(motivo or f"Avance en KDS a {nuevo_estado}")[:255],
            )

        # Descuento de stock automático al pasar a COCINANDO o LISTO
        if nuevo_estado in (Pedido.ESTADO_COCINANDO, Pedido.ESTADO_LISTO):
            try:
                from .stock_service import descontar_stock_pedido

                descontar_stock_pedido(
                    pedido_id=pedido.id,
                    motivo=(motivo or f"Avance en KDS a {nuevo_estado}")[:255],
                    registrado_por=(
                        f"kds_usuario_{usuario_valido_id}"
                        if usuario_valido_id
                        else "kds"
                    ),
                    estricto=False,
                )
            except Exception as exc:
                logger.warning(
                    "Error al descontar stock para comanda %s en KDS: %s",
                    pedido.id,
                    exc,
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
                d
                for d in todos_detalles
                if (d.estacion_item or d.producto.estacion) == estacion_codigo
            ]
            if not detalles_filtrados:
                continue
        else:
            detalles_filtrados = todos_detalles

        # Decorar cada ítem con su siguiente acción individual
        for d in detalles_filtrados:
            st = d.estado_item or DetallePedido.ESTADO_ITEM_PENDIENTE
            prox_item = None
            if st == DetallePedido.ESTADO_ITEM_PENDIENTE:
                prox_item = {
                    "target_estado": DetallePedido.ESTADO_ITEM_EN_PREPARACION,
                    "label": "Preparar",
                    "btn_class": "btn-item-iniciar",
                }
            elif st == DetallePedido.ESTADO_ITEM_EN_PREPARACION:
                prox_item = {
                    "target_estado": DetallePedido.ESTADO_ITEM_LISTO,
                    "label": "Listo",
                    "btn_class": "btn-item-listo",
                }
            elif st == DetallePedido.ESTADO_ITEM_LISTO:
                prox_item = {
                    "target_estado": DetallePedido.ESTADO_ITEM_SERVIDO,
                    "label": "Servir",
                    "btn_class": "btn-item-servir",
                }
            d.proxima_accion = prox_item

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

        # Determinar siguiente acción sugerida (a nivel de estación o comanda)
        proxima_accion = None
        if estacion_codigo:
            estados_estacion = set(
                d.estado_item or DetallePedido.ESTADO_ITEM_PENDIENTE
                for d in detalles_filtrados
            )
            if DetallePedido.ESTADO_ITEM_PENDIENTE in estados_estacion:
                proxima_accion = {
                    "target_estado": Pedido.ESTADO_COCINANDO,
                    "label": "Iniciar Estación",
                    "btn_class": "btn-kds-iniciar",
                }
            elif DetallePedido.ESTADO_ITEM_EN_PREPARACION in estados_estacion:
                proxima_accion = {
                    "target_estado": Pedido.ESTADO_LISTO,
                    "label": "Marcar Estación Lista",
                    "btn_class": "btn-kds-listo",
                }
            elif all(
                e == DetallePedido.ESTADO_ITEM_LISTO for e in estados_estacion
            ):
                proxima_accion = {
                    "target_estado": Pedido.ESTADO_SERVIDO,
                    "label": "Despachar Estación",
                    "btn_class": "btn-kds-servir",
                }
        else:
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
                    "estado_item": d.estado_item,
                    "estado_display": d.get_estado_item_display(),
                    "notas": d.notas or "",
                    "proxima_accion": getattr(d, "proxima_accion", None),
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
