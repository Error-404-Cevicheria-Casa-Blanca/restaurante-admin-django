"""Servicio transaccional de stock del día, descuentos y reversiones (PRB-59).

Alcance P-13 (PLAN-PRODUCCION-POS.md §5.1, §8.5, §8.10c):
- Control directo de cupo diario por producto (`stock_disponible`, `stock_minimo`),
  sin recetas, insumos ni merma.
- `stock_disponible IS NULL`: modo libre/ilimitado (disponibilidad gobernada por booleano).
- `stock_disponible >= 0`: cupo finito del día; al llegar a 0 marca automáticamente
  `disponible = False` para bloquear nuevas comandas en Android y Spring Boot.
- Descuento atómico con `select_for_update()` e idempotencia por `pedido_id`.
- Reversión atómica e idempotente ante anulación total de pedido o de ítem individual,
  reactivando `disponible = True` cuando un plato agotado recupera porciones (> 0).
"""

from collections import defaultdict
from datetime import timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from .models import DetallePedido, MovimientoStock, Pedido, Producto


def _normalizar_dt_utc(dt):
    """Normaliza datetimes naive (TIMESTAMP) y aware (TIMESTAMPTZ) a UTC."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


class StockInsuficienteError(ValidationError):
    """Error de dominio cuando uno o más platos carecen de porciones suficientes."""

    codigo = "STOCK_INSUFICIENTE"

    def __init__(self, mensaje, detalles=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or []


def fijar_stock_diario(
    producto_id,
    stock_disponible,
    stock_minimo=None,
    motivo="",
    registrado_por="sistema",
):
    """Configura o reinicia el cupo diario de un plato (`None` = ilimitado)."""
    if stock_disponible is not None and stock_disponible < 0:
        raise ValidationError("El stock disponible no puede ser negativo.")
    if stock_minimo is not None and stock_minimo < 0:
        raise ValidationError("El stock mínimo no puede ser negativo.")

    with transaction.atomic():
        plato = Producto.objects.select_for_update().get(pk=producto_id)
        stock_anterior = plato.stock_disponible
        plato.stock_disponible = stock_disponible

        campos = ["stock_disponible"]
        if stock_minimo is not None:
            plato.stock_minimo = stock_minimo
            campos.append("stock_minimo")

        if stock_disponible is not None:
            nuevo_disp = stock_disponible > 0
            if plato.disponible != nuevo_disp:
                plato.disponible = nuevo_disp
                campos.append("disponible")
        elif stock_anterior == 0 and not plato.disponible:
            plato.disponible = True
            campos.append("disponible")

        plato.save(update_fields=campos)

        texto_motivo = (motivo or "").strip() or (
            "Cambio a stock libre (sin límite diario)"
            if stock_disponible is None
            else f"Carga de cupo del día: {stock_disponible} porciones"
        )
        movimiento = MovimientoStock.objects.create(
            producto=plato,
            pedido=None,
            tipo=MovimientoStock.TIPO_CARGA_DIARIA,
            cantidad=stock_disponible if stock_disponible is not None else 0,
            stock_anterior=stock_anterior,
            stock_resultante=stock_disponible,
            motivo=texto_motivo[:255],
            registrado_por=(registrado_por or "sistema")[:100],
        )
        return plato, movimiento


def ajustar_stock_producto(
    producto_id,
    delta,
    motivo="",
    registrado_por="sistema",
):
    """Aplica un ajuste relativo (+/- porciones) sobre el stock diario del plato."""
    if not isinstance(delta, int) or delta == 0:
        raise ValidationError("El ajuste de stock debe ser un entero distinto de cero.")

    with transaction.atomic():
        plato = Producto.objects.select_for_update().get(pk=producto_id)
        stock_anterior = plato.stock_disponible
        base = stock_anterior if stock_anterior is not None else 0
        nuevo_stock = base + delta

        if nuevo_stock < 0:
            raise ValidationError(
                f"No se puede descontar {abs(delta)} porciones de «{plato.nombre}» "
                f"(stock actual: {base})."
            )

        plato.stock_disponible = nuevo_stock
        plato.disponible = nuevo_stock > 0
        plato.save(update_fields=["stock_disponible", "disponible"])

        signo = f"+{delta}" if delta > 0 else str(delta)
        texto_motivo = (motivo or "").strip() or f"Ajuste manual ({signo} porciones)"
        movimiento = MovimientoStock.objects.create(
            producto=plato,
            pedido=None,
            tipo=MovimientoStock.TIPO_AJUSTE,
            cantidad=abs(delta),
            stock_anterior=stock_anterior,
            stock_resultante=nuevo_stock,
            motivo=texto_motivo[:255],
            registrado_por=(registrado_por or "sistema")[:100],
        )
        return plato, movimiento


def _neto_descontado_por_pedido(pedido_id):
    """Calcula `{producto_id: neto}` ya descontado para un pedido (`SALIDA - REVERSION`)."""
    filas = (
        MovimientoStock.objects.filter(
            pedido_id=pedido_id,
            tipo__in=(
                MovimientoStock.TIPO_SALIDA_VENTA,
                MovimientoStock.TIPO_REVERSION,
            ),
        )
        .values("producto_id", "tipo")
        .annotate(total=Sum("cantidad"))
    )
    netos = defaultdict(int)
    for fila in filas:
        pid = fila["producto_id"]
        cant = fila["total"] or 0
        if fila["tipo"] == MovimientoStock.TIPO_SALIDA_VENTA:
            netos[pid] += cant
        else:
            netos[pid] -= cant
    return {pid: max(0, val) for pid, val in netos.items() if val > 0}


def descontar_stock_pedido(
    pedido_id,
    items=None,
    motivo="",
    registrado_por="pos",
    estricto=True,
):
    """Descuenta de forma atómica e idempotente el stock de los platos de un pedido.

    - Si `items` se proporciona (`[{"producto_id": int, "cantidad": int}]`), opera
      con idempotencia estricta por `pedido_id`.
    - Si `items` es `None`, lee `DetallePedido` y descuenta únicamente el diferencial
      pendiente respecto a movimientos previos (soportando ampliación PRB-82).
    - Con `estricto=True`, si algún plato está agotado o no alcanza su `stock_disponible`,
      lanza `StockInsuficienteError` revirtiendo toda la transacción.
    """
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        if pedido.estado in (Pedido.ESTADO_ANULADO, Pedido.ESTADO_CANCELADO):
            return []

        if items is not None:
            existentes = list(
                MovimientoStock.objects.filter(
                    pedido_id=pedido.id,
                    tipo=MovimientoStock.TIPO_SALIDA_VENTA,
                ).order_by("id")
            )
            if existentes:
                return existentes

            requeridos = defaultdict(int)
            for item in items:
                pid = int(item["producto_id"])
                cant = int(item["cantidad"])
                if cant < 1:
                    raise ValidationError("La cantidad por ítem debe ser al menos 1.")
                requeridos[pid] += cant
            pendientes = dict(requeridos)
        else:
            detalles_qs = (
                DetallePedido.objects.filter(pedido_id=pedido.id)
                .values("producto_id")
                .annotate(total=Sum("cantidad"))
            )
            netos_previos = _neto_descontado_por_pedido(pedido.id)
            pendientes = {}
            for fila in detalles_qs:
                pid = fila["producto_id"]
                dif = (fila["total"] or 0) - netos_previos.get(pid, 0)
                if dif > 0:
                    pendientes[pid] = dif

        if not pendientes:
            return []

        platos_bloqueados = {
            p.id: p
            for p in Producto.objects.select_for_update()
            .filter(id__in=sorted(pendientes.keys()))
            .order_by("id")
        }

        faltantes = []
        for pid in sorted(pendientes.keys()):
            cant = pendientes[pid]
            plato = platos_bloqueados.get(pid)
            if plato is None:
                raise ValidationError(f"Producto #{pid} no existe.")
            if estricto:
                if not plato.disponible:
                    faltantes.append(
                        {
                            "producto_id": plato.id,
                            "nombre": plato.nombre,
                            "solicitado": cant,
                            "disponible": plato.stock_disponible or 0,
                        }
                    )
                elif (
                    plato.stock_disponible is not None and plato.stock_disponible < cant
                ):
                    faltantes.append(
                        {
                            "producto_id": plato.id,
                            "nombre": plato.nombre,
                            "solicitado": cant,
                            "disponible": plato.stock_disponible,
                        }
                    )

        if faltantes:
            resumen = ", ".join(
                f"{f['nombre']} (solicitado: {f['solicitado']}, disponible: {f['disponible']})"
                for f in faltantes
            )
            raise StockInsuficienteError(
                f"Stock insuficiente para procesar el pedido: {resumen}.",
                detalles=faltantes,
            )

        movimientos = []
        texto_motivo = (motivo or "").strip() or f"Consumo por Pedido #{pedido.id}"
        for pid in sorted(pendientes.keys()):
            cant = pendientes[pid]
            plato = platos_bloqueados[pid]
            if plato.stock_disponible is None:
                continue

            stock_anterior = plato.stock_disponible
            nuevo_stock = max(0, stock_anterior - cant)
            plato.stock_disponible = nuevo_stock
            campos = ["stock_disponible"]
            if nuevo_stock == 0 and plato.disponible:
                plato.disponible = False
                campos.append("disponible")
            plato.save(update_fields=campos)

            mov = MovimientoStock.objects.create(
                producto=plato,
                pedido=pedido,
                tipo=MovimientoStock.TIPO_SALIDA_VENTA,
                cantidad=stock_anterior - nuevo_stock,
                stock_anterior=stock_anterior,
                stock_resultante=nuevo_stock,
                motivo=texto_motivo[:255],
                registrado_por=(registrado_por or "pos")[:100],
            )
            movimientos.append(mov)

        return movimientos


def revertir_stock_pedido(
    pedido_id,
    motivo="Anulación de pedido",
    registrado_por="pos",
):
    """Restaura de forma atómica e idempotente las porciones descontadas por un pedido."""
    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        netos = _neto_descontado_por_pedido(pedido.id)
        if not netos:
            return []

        platos_bloqueados = {
            p.id: p
            for p in Producto.objects.select_for_update()
            .filter(id__in=sorted(netos.keys()))
            .order_by("id")
        }

        movimientos = []
        texto_motivo = (
            motivo or ""
        ).strip() or f"Reversión por anulación de Pedido #{pedido.id}"
        for pid in sorted(netos.keys()):
            cant = netos[pid]
            plato = platos_bloqueados.get(pid)
            if plato is None or plato.stock_disponible is None or cant <= 0:
                continue

            stock_anterior = plato.stock_disponible
            nuevo_stock = stock_anterior + cant
            plato.stock_disponible = nuevo_stock
            campos = ["stock_disponible"]
            if stock_anterior == 0 and nuevo_stock > 0 and not plato.disponible:
                plato.disponible = True
                campos.append("disponible")
            plato.save(update_fields=campos)

            mov = MovimientoStock.objects.create(
                producto=plato,
                pedido=pedido,
                tipo=MovimientoStock.TIPO_REVERSION,
                cantidad=cant,
                stock_anterior=stock_anterior,
                stock_resultante=nuevo_stock,
                motivo=texto_motivo[:255],
                registrado_por=(registrado_por or "pos")[:100],
            )
            movimientos.append(mov)

        return movimientos


def revertir_stock_item(
    pedido_id,
    producto_id,
    cantidad,
    motivo="Anulación de ítem de pedido",
    registrado_por="pos",
):
    """Restaura parcialmente el stock cuando se anula un ítem individual de una comanda."""
    if cantidad < 1:
        raise ValidationError("La cantidad a revertir debe ser al menos 1.")

    with transaction.atomic():
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        netos = _neto_descontado_por_pedido(pedido.id)
        disponible_revertir = netos.get(producto_id, 0)
        cant_efectiva = min(int(cantidad), disponible_revertir)
        if cant_efectiva <= 0:
            return None

        plato = Producto.objects.select_for_update().get(pk=producto_id)
        if plato.stock_disponible is None:
            return None

        stock_anterior = plato.stock_disponible
        nuevo_stock = stock_anterior + cant_efectiva
        plato.stock_disponible = nuevo_stock
        campos = ["stock_disponible"]
        if stock_anterior == 0 and nuevo_stock > 0 and not plato.disponible:
            plato.disponible = True
            campos.append("disponible")
        plato.save(update_fields=campos)

        texto_motivo = (
            motivo or ""
        ).strip() or f"Reversión de ítem en Pedido #{pedido.id}"
        return MovimientoStock.objects.create(
            producto=plato,
            pedido=pedido,
            tipo=MovimientoStock.TIPO_REVERSION,
            cantidad=cant_efectiva,
            stock_anterior=stock_anterior,
            stock_resultante=nuevo_stock,
            motivo=texto_motivo[:255],
            registrado_por=(registrado_por or "pos")[:100],
        )


def sincronizar_stock_con_pedidos():
    """Concilia de forma idempotente comandas y anulaciones registradas por el POS Java.

    Solo evalúa platos con cupo numérico (`stock_disponible IS NOT NULL`) y considera
    únicamente comandas posteriores a la última `CARGA_DIARIA` de cada plato, evitando
    descontar pedidos históricos previos a la apertura del stock del día.
    """
    platos_con_cupo = list(
        Producto.objects.filter(stock_disponible__isnull=False).values_list(
            "id", flat=True
        )
    )
    if not platos_con_cupo:
        return {"descuentos": 0, "reversiones": 0}

    ultimas_cargas = dict(
        MovimientoStock.objects.filter(
            producto_id__in=platos_con_cupo,
            tipo=MovimientoStock.TIPO_CARGA_DIARIA,
        )
        .values("producto_id")
        .annotate(ultima_fecha=Max("fecha"))
        .values_list("producto_id", "ultima_fecha")
    )

    # 1. Revertir pedidos que ya tenían descuento registrado y pasaron a ANULADO/CANCELADO
    pedidos_con_mov = list(
        MovimientoStock.objects.filter(
            producto_id__in=platos_con_cupo,
            pedido_id__isnull=False,
            tipo=MovimientoStock.TIPO_SALIDA_VENTA,
        )
        .values_list("pedido_id", flat=True)
        .distinct()
    )

    reversiones_count = 0
    if pedidos_con_mov:
        anulados_ids = list(
            Pedido.objects.filter(
                id__in=pedidos_con_mov,
                estado__in=(Pedido.ESTADO_ANULADO, Pedido.ESTADO_CANCELADO),
            ).values_list("id", flat=True)
        )
        for ped_id in anulados_ids:
            revs = revertir_stock_pedido(
                ped_id,
                motivo=f"Reversión automática por Pedido #{ped_id} ANULADO",
                registrado_por="sincronizador-pos",
            )
            reversiones_count += len(revs)

        # También conciliar ítems individuales eliminados en pedidos aún activos
        activos_con_mov_ids = set(pedidos_con_mov) - set(anulados_ids)
        for ped_id in sorted(activos_con_mov_ids):
            netos = _neto_descontado_por_pedido(ped_id)
            if not netos:
                continue
            actuales = dict(
                DetallePedido.objects.filter(
                    pedido_id=ped_id, producto_id__in=netos.keys()
                )
                .values("producto_id")
                .annotate(total=Sum("cantidad"))
                .values_list("producto_id", "total")
            )
            for pid, neto_previo in netos.items():
                cant_actual = actuales.get(pid, 0) or 0
                if cant_actual < neto_previo:
                    mov = revertir_stock_item(
                        ped_id,
                        pid,
                        neto_previo - cant_actual,
                        motivo=f"Reversión por ítem eliminado en Pedido #{ped_id}",
                        registrado_por="sincronizador-pos",
                    )
                    if mov:
                        reversiones_count += 1

    # 2. Descontar ítems nuevos en pedidos activos posteriores a la carga diaria del plato
    detalles_activos = (
        DetallePedido.objects.filter(producto_id__in=platos_con_cupo)
        .exclude(pedido__estado__in=(Pedido.ESTADO_ANULADO, Pedido.ESTADO_CANCELADO))
        .select_related("pedido")
        .order_by("pedido_id", "id")
    )

    pedidos_candidatos = set()
    for det in detalles_activos:
        fecha_corte = _normalizar_dt_utc(ultimas_cargas.get(det.producto_id))
        fecha_ped = _normalizar_dt_utc(det.pedido.fecha_creacion)
        if fecha_corte is None or (fecha_ped is not None and fecha_ped >= fecha_corte):
            pedidos_candidatos.add(det.pedido_id)

    descuentos_count = 0
    for ped_id in sorted(pedidos_candidatos):
        with transaction.atomic():
            pedido = Pedido.objects.select_for_update().get(pk=ped_id)
            if pedido.estado in (Pedido.ESTADO_ANULADO, Pedido.ESTADO_CANCELADO):
                continue
            netos_previos = _neto_descontado_por_pedido(pedido.id)
            agrupados = (
                DetallePedido.objects.filter(
                    pedido_id=pedido.id,
                    producto_id__in=platos_con_cupo,
                )
                .values("producto_id")
                .annotate(total=Sum("cantidad"))
            )
            fecha_ped = _normalizar_dt_utc(pedido.fecha_creacion)
            for fila in agrupados:
                pid = fila["producto_id"]
                fecha_corte = _normalizar_dt_utc(ultimas_cargas.get(pid))
                if (
                    fecha_corte is not None
                    and fecha_ped is not None
                    and fecha_ped < fecha_corte
                ):
                    continue
                dif = (fila["total"] or 0) - netos_previos.get(pid, 0)
                if dif <= 0:
                    continue
                plato = Producto.objects.select_for_update().get(pk=pid)
                if plato.stock_disponible is None or plato.stock_disponible <= 0:
                    continue
                stock_ant = plato.stock_disponible
                descontado_real = min(stock_ant, dif)
                nuevo_stock = stock_ant - descontado_real
                plato.stock_disponible = nuevo_stock
                campos = ["stock_disponible"]
                if nuevo_stock == 0 and plato.disponible:
                    plato.disponible = False
                    campos.append("disponible")
                plato.save(update_fields=campos)
                MovimientoStock.objects.create(
                    producto=plato,
                    pedido=pedido,
                    tipo=MovimientoStock.TIPO_SALIDA_VENTA,
                    cantidad=descontado_real,
                    stock_anterior=stock_ant,
                    stock_resultante=nuevo_stock,
                    motivo=f"Consumo POS en Pedido #{pedido.id}",
                    registrado_por="sincronizador-pos",
                )
                descuentos_count += 1

    return {"descuentos": descuentos_count, "reversiones": reversiones_count}
