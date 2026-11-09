"""Servicio de impresión térmica ESC/POS de 80 mm para comandas y pre-cuentas (PRB-58).

Alcance P-11 (PLAN-PRODUCCION-POS.md §5.2, §8.4, ADR-02):
- Impresión centralizada en backend con cola transaccional en 'impresion_cola'.
- Ancho útil estándar: 80 mm = 48 columnas (Fuente A, 12x24 dots, Epson TM-T20III).
- Formatos oficiales:
    * Comanda de cocina / barra por estación (platos, notas, mesa, mozo, hora, corte).
    * Pre-cuenta de mesa (cabecera fiscal no-valida, detalle, IGV incluido, totales, corte).
- Envío por socket TCP RAW (puerto 9100) con timeout, reintentos (max 3) y modo simulador.
- Auditoría, reintentos y reimpresión de comandas y cuentas.
"""

import os
import socket
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ImpresionCola, Pedido

# =============================================================================
# CONSTANTES Y CONFIGURACIÓN ESC/POS (EPSON TM-T20III / 80 MM)
# =============================================================================

ANCHO_80MM = 48  # Ancho útil estándar en caracteres para Fuente A (80 mm / 72 mm print)
MAX_INTENTOS_IMPRESION = 3

# Modos de operación: "NETWORK" (socket TCP real), "DUMMY" (buffer memoria), "FAIL_SIMULATED"
PRINTER_MODE_DEFAULT = getattr(
    settings, "PRINTER_MODE", os.getenv("PRINTER_MODE", "DUMMY")
)
PRINTER_HOST_DEFAULT = getattr(
    settings, "PRINTER_HOST", os.getenv("PRINTER_HOST", "192.168.1.200")
)
PRINTER_PORT_DEFAULT = int(
    getattr(settings, "PRINTER_PORT", os.getenv("PRINTER_PORT", "9100"))
)
PRINTER_TIMEOUT_DEFAULT = int(
    getattr(settings, "PRINTER_TIMEOUT", os.getenv("PRINTER_TIMEOUT", "3"))
)

# Comandos ESC/POS estándar (bytes)
ESC = b"\x1b"
GS = b"\x1d"

CMD_INIT = ESC + b"@"  # Reset / inicializar impresora
CMD_ALIGN_LEFT = ESC + b"a\x00"  # Alinear a la izquierda
CMD_ALIGN_CENTER = ESC + b"a\x01"  # Alinear al centro
CMD_ALIGN_RIGHT = ESC + b"a\x02"  # Alinear a la derecha
CMD_BOLD_ON = ESC + b"E\x01"  # Negrita activada
CMD_BOLD_OFF = ESC + b"E\x00"  # Negrita desactivada
CMD_DOUBLE_ON = GS + b"!\x11"  # Doble ancho y alto
CMD_NORMAL_SIZE = GS + b"!\x00"  # Tamaño normal de fuente
CMD_FEED_CUT = GS + b"V\x42\x00"  # Avance y corte de papel (Autocutter)

# Buffer en memoria para pruebas y modo simulado
BUFFER_IMPRESIONES_SIMULADAS = []


def limpiar_buffer_simulado():
    """Limpia el buffer de trabajos enviados en modo DUMMY."""
    BUFFER_IMPRESIONES_SIMULADAS.clear()


def obtener_buffer_simulado():
    """Retorna una copia de los trabajos enviados en modo DUMMY."""
    return list(BUFFER_IMPRESIONES_SIMULADAS)


# =============================================================================
# UTILITARIOS DE FORMATEO A 48 COLUMNAS
# =============================================================================


def linea_separador(char="-", ancho=ANCHO_80MM):
    """Genera una línea divisoria de exactamente 'ancho' caracteres."""
    return (char * ancho)[:ancho]


def centrar(texto, ancho=ANCHO_80MM):
    """Centra el texto en un bloque de 'ancho' caracteres."""
    texto_str = str(texto or "").strip()
    if len(texto_str) >= ancho:
        return texto_str[:ancho]
    return texto_str.center(ancho)


def formatear_fecha(dt):
    """Convierte un datetime (naive o aware) al horario local en formato dd/mm/yyyy hh:mm:ss."""
    if not dt:
        dt = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt).strftime("%d/%m/%Y %H:%M:%S")


def alinear_dos_columnas(izq, der, ancho=ANCHO_80MM):
    """Alinea el texto izquierdo a la izquierda y el derecho al margen derecho."""
    izq_str = str(izq or "").strip()
    der_str = str(der or "").strip()
    espacio_libre = ancho - len(der_str)
    if espacio_libre <= len(izq_str):
        # Truncar izquierda si no alcanza
        izq_str = izq_str[: max(0, espacio_libre - 1)]
    return f"{izq_str:<{espacio_libre}}{der_str}"


def formatear_linea_item(cant, descripcion, precio_unit, subtotal, ancho=ANCHO_80MM):
    """Formatea una fila de ítem de consumo en 48 columnas:

    CANT(4) + DESCRIPCION(24) + P.UNIT(9) + SUBTOTAL(11) = 48
    """
    cant_str = f"{cant:<4}"[:4]
    unit_str = f"{Decimal(precio_unit):.2f}".rjust(9)[:9]
    sub_str = f"{Decimal(subtotal):.2f}".rjust(11)[:11]

    ancho_desc = ancho - (4 + 9 + 11)  # 24 columnas
    desc_str = str(descripcion or "").strip()

    lineas = []
    if len(desc_str) <= ancho_desc:
        lineas.append(f"{cant_str}{desc_str:<{ancho_desc}}{unit_str}{sub_str}")
    else:
        primera = desc_str[:ancho_desc]
        lineas.append(f"{cant_str}{primera:<{ancho_desc}}{unit_str}{sub_str}")
        resto = desc_str[ancho_desc:].strip()
        while resto:
            parte = resto[:ancho_desc]
            lineas.append(f"{' ':4}{parte:<{ancho_desc}}")
            resto = resto[ancho_desc:].strip()

    return "\n".join(lineas)


# =============================================================================
# GENERADORES DE FORMATOS TÉRMICOS (TEXTO Y ESC/POS)
# =============================================================================


def generar_texto_comanda(pedido, estacion=None):
    """Genera el texto plano formateado a 48 columnas para comanda de cocina/barra."""
    lineas = [
        linea_separador("="),
        centrar("*** COMANDA DE COCINA ***"),
    ]

    estacion_codigo = (estacion or "").strip().upper()
    if estacion_codigo:
        lineas.append(centrar(f"ESTACION: {estacion_codigo}"))
    else:
        lineas.append(centrar("ESTACION: GENERAL / TODAS"))

    lineas.extend(
        [
            linea_separador("="),
            f"Comanda #:  #{pedido.id}",
            f"Mesa:       {pedido.origen_display}",
            f"Mozo:       Mozo #{pedido.mozo_id or 1}",
            f"Fecha/Hora: {formatear_fecha(pedido.fecha_creacion)}",
            linea_separador("-"),
            f"{'CANT':<5}{'DESCRIPCION Y NOTAS'}",
            linea_separador("-"),
        ]
    )

    detalles = list(pedido.detalles.all())
    if estacion_codigo:
        detalles = [d for d in detalles if d.producto.estacion == estacion_codigo]

    total_platos = 0
    if not detalles:
        lineas.append("  (No hay platos registrados para esta estación)")
    else:
        for d in detalles:
            total_platos += d.cantidad
            prod_nombre = d.producto.nombre.upper()
            lineas.append(f"{d.cantidad:<5}{prod_nombre}")
            if d.notas:
                notas_clean = d.notas.strip()
                lineas.append(f"     * NOTA: {notas_clean}")

    lineas.extend(
        [
            linea_separador("-"),
            alinear_dos_columnas("TOTAL ITEMS EN COMANDA:", str(total_platos)),
            linea_separador("="),
            centrar("Cevichería Restaurante Casa Blanca"),
            linea_separador("="),
        ]
    )

    return "\n".join(lineas)


def generar_escpos_comanda(pedido, estacion=None):
    """Genera la secuencia binaria de bytes ESC/POS lista para la impresora de 80 mm."""
    texto = generar_texto_comanda(pedido, estacion=estacion)
    # Codificar con CP850 o latin-1 para preservar caracteres hispanos
    payload_bytes = bytearray()
    payload_bytes.extend(CMD_INIT)
    payload_bytes.extend(CMD_ALIGN_LEFT)
    payload_bytes.extend(texto.encode("cp850", errors="replace"))
    payload_bytes.extend(b"\n\n\n")
    payload_bytes.extend(CMD_FEED_CUT)
    return bytes(payload_bytes)


def generar_texto_precuenta(pedido):
    """Genera el texto plano formateado a 48 columnas para la pre-cuenta de mesa."""
    fecha_str = formatear_fecha(pedido.fecha_creacion)
    subtotal_total = Decimal(str(pedido.total or "0.00"))

    # Cálculo informativo de IGV (18% incluido según norma D13)
    base_imponible = (subtotal_total / Decimal("1.18")).quantize(Decimal("0.01"))
    igv_calculado = (subtotal_total - base_imponible).quantize(Decimal("0.01"))

    lineas = [
        linea_separador("="),
        centrar("CEVICHERIA LA CASA BLANCA"),
        centrar("El autentico sabor del mar norteno"),
        centrar("RUC: 20601234567"),
        centrar("Jr. Dos de Mayo 456 - Cajamarca"),
        centrar("Tel: (076) 364521"),
        linea_separador("="),
        centrar("PRE-CUENTA DE CONSUMO"),
        centrar("CONTROL INTERNO - NO FISCAL"),
        linea_separador("-"),
        f"Pedido #:   #{pedido.id}",
        f"Mesa:       {pedido.origen_display}",
        f"Mozo:       Mozo #{pedido.mozo_id or 1}",
        f"Fecha/Hora: {fecha_str}",
        linea_separador("-"),
        f"{'CANT':<4}{'DESCRIPCION':<24}{'P.UNIT':>9}{'SUBTOTAL':>11}",
        linea_separador("-"),
    ]

    detalles = list(pedido.detalles.all())
    if not detalles:
        lineas.append(centrar("(Sin ítems registrados)"))
    else:
        for d in detalles:
            lineas.append(
                formatear_linea_item(
                    cant=d.cantidad,
                    descripcion=d.producto.nombre,
                    precio_unit=d.precio_unitario,
                    subtotal=d.subtotal,
                )
            )

    lineas.extend(
        [
            linea_separador("-"),
            alinear_dos_columnas("OP. GRAVADA (Base):", f"S/ {base_imponible:.2f}"),
            alinear_dos_columnas("I.G.V. (18% incluido):", f"S/ {igv_calculado:.2f}"),
            linea_separador("="),
            alinear_dos_columnas("TOTAL A PAGAR:", f"S/ {subtotal_total:.2f}"),
            linea_separador("="),
            centrar("DOCUMENTO NO VALIDO COMO"),
            centrar("COMPROBANTE FISCAL"),
            centrar("Solicite su Boleta o Factura en Caja"),
            linea_separador("-"),
            centrar("¡Muchas gracias por su preferencia!"),
            centrar("La Casa Blanca le espera pronto"),
            linea_separador("="),
        ]
    )

    return "\n".join(lineas)


def generar_escpos_precuenta(pedido):
    """Genera la secuencia binaria ESC/POS para la pre-cuenta con corte de papel."""
    texto = generar_texto_precuenta(pedido)
    payload_bytes = bytearray()
    payload_bytes.extend(CMD_INIT)
    payload_bytes.extend(CMD_ALIGN_LEFT)
    payload_bytes.extend(texto.encode("cp850", errors="replace"))
    payload_bytes.extend(b"\n\n\n")
    payload_bytes.extend(CMD_FEED_CUT)
    return bytes(payload_bytes)


# =============================================================================
# CLIENTE TCP Y DESPACHO DE IMPRESIÓN
# =============================================================================


def enviar_bytes_a_impresora(
    payload_bytes,
    host=None,
    port=None,
    timeout=None,
    modo=None,
):
    """Envía los bytes a la impresora térmica sobre socket TCP RAW (puerto 9100).

    Retorna una tupla (exito: bool, mensaje: str).
    """
    modo_operacion = modo or PRINTER_MODE_DEFAULT
    host_destino = host or PRINTER_HOST_DEFAULT
    puerto_destino = port or PRINTER_PORT_DEFAULT
    timeout_segundos = timeout or PRINTER_TIMEOUT_DEFAULT

    if modo_operacion == "DUMMY":
        # Simulación en memoria para desarrollo y pruebas
        BUFFER_IMPRESIONES_SIMULADAS.append(
            {
                "timestamp": timezone.now(),
                "host": host_destino,
                "port": puerto_destino,
                "bytes_len": len(payload_bytes),
                "payload_bytes": payload_bytes,
            }
        )
        return True, f"Impresión simulada exitosa ({len(payload_bytes)} bytes en DUMMY)"

    if modo_operacion == "FAIL_SIMULATED":
        return (
            False,
            "Fallo simulado de conexión: ConnectionRefusedError a impresora térmica",
        )

    # Modo NETWORK: socket TCP real
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_segundos)
        sock.connect((host_destino, puerto_destino))
        sock.sendall(payload_bytes)
        return (
            True,
            f"Impresión enviada correctamente a {host_destino}:{puerto_destino}",
        )
    except (socket.timeout, socket.error, OSError) as exc:
        return (
            False,
            f"Error de red hacia impresora ({host_destino}:{puerto_destino}): {exc}",
        )
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


# =============================================================================
# GESTIÓN DE COLA TRANSACCIONAL (ImpresionCola / ADR-02)
# =============================================================================


def encolar_comanda(pedido, estacion=None, despachar_inmediato=True, modo=None):
    """Encola un trabajo de impresión de comanda en 'impresion_cola'."""
    estacion_codigo = (estacion or "").strip().upper() or "COCINA_GENERAL"
    texto_comanda = generar_texto_comanda(pedido, estacion=estacion_codigo)

    trabajo = ImpresionCola.objects.create(
        pedido=pedido,
        tipo=ImpresionCola.TIPO_COMANDA,
        estacion=estacion_codigo,
        payload=texto_comanda,
        estado=ImpresionCola.ESTADO_PENDIENTE,
        intentos=0,
    )

    if despachar_inmediato:
        despachar_trabajo(trabajo.id, modo=modo)
        trabajo.refresh_from_db()

    return trabajo


def encolar_precuenta(pedido, despachar_inmediato=True, modo=None):
    """Encola un trabajo de impresión de pre-cuenta en 'impresion_cola'."""
    texto_precuenta = generar_texto_precuenta(pedido)

    trabajo = ImpresionCola.objects.create(
        pedido=pedido,
        tipo=ImpresionCola.TIPO_PRECUENTA,
        estacion="CAJA",
        payload=texto_precuenta,
        estado=ImpresionCola.ESTADO_PENDIENTE,
        intentos=0,
    )

    if despachar_inmediato:
        despachar_trabajo(trabajo.id, modo=modo)
        trabajo.refresh_from_db()

    return trabajo


def despachar_trabajo(trabajo_id, modo=None):
    """Despacha un trabajo de impresión pendiente con control atómico de reintentos."""
    with transaction.atomic():
        try:
            trabajo = ImpresionCola.objects.select_for_update().get(id=trabajo_id)
        except ImpresionCola.DoesNotExist:
            return False, f"Trabajo #{trabajo_id} no existe"

        # Generar bytes ESC/POS
        if trabajo.pedido:
            if trabajo.tipo == ImpresionCola.TIPO_PRECUENTA:
                payload_bytes = generar_escpos_precuenta(trabajo.pedido)
            else:
                payload_bytes = generar_escpos_comanda(
                    trabajo.pedido, estacion=trabajo.estacion
                )
        else:
            # Si no hay pedido directo, codificar el payload de texto plano almacenado
            payload_bytes = (
                CMD_INIT
                + CMD_ALIGN_LEFT
                + trabajo.payload.encode("cp850", errors="replace")
                + b"\n\n\n"
                + CMD_FEED_CUT
            )

        trabajo.intentos += 1
        exito, mensaje = enviar_bytes_a_impresora(payload_bytes, modo=modo)

        if exito:
            trabajo.estado = ImpresionCola.ESTADO_IMPRESO
            trabajo.fecha_impresion = timezone.now()
            trabajo.error = None
        else:
            trabajo.error = mensaje
            if trabajo.intentos >= MAX_INTENTOS_IMPRESION:
                trabajo.estado = ImpresionCola.ESTADO_FALLIDO

        trabajo.save()
        return exito, mensaje


def despachar_cola_pendientes(limite=10, modo=None):
    """Despacha en orden FIFO los trabajos que se encuentren en estado PENDIENTE."""
    pendientes = list(
        ImpresionCola.objects.filter(estado=ImpresionCola.ESTADO_PENDIENTE)
        .order_by("fecha_creacion")[:limite]
        .values_list("id", flat=True)
    )

    resultados = []
    for t_id in pendientes:
        exito, msg = despachar_trabajo(t_id, modo=modo)
        resultados.append({"id": t_id, "exito": exito, "mensaje": msg})
    return resultados


def reintentar_trabajo(trabajo_id, modo=None):
    """Reinicia un trabajo (incluso si estaba FALLIDO) y lo despacha de inmediato."""
    with transaction.atomic():
        try:
            trabajo = ImpresionCola.objects.select_for_update().get(id=trabajo_id)
        except ImpresionCola.DoesNotExist:
            return False, f"Trabajo #{trabajo_id} no existe"

        trabajo.estado = ImpresionCola.ESTADO_PENDIENTE
        trabajo.intentos = 0
        trabajo.error = None
        trabajo.save()

    return despachar_trabajo(trabajo_id, modo=modo)


def reimprimir_pedido(
    pedido_id, tipo=ImpresionCola.TIPO_COMANDA, estacion=None, modo=None
):
    """Crea un nuevo trabajo en cola para reimprimir una comanda o pre-cuenta existente."""
    try:
        pedido = Pedido.objects.get(id=pedido_id)
    except Pedido.DoesNotExist:
        return None

    if tipo == ImpresionCola.TIPO_PRECUENTA:
        return encolar_precuenta(pedido, despachar_inmediato=True, modo=modo)
    return encolar_comanda(
        pedido, estacion=estacion, despachar_inmediato=True, modo=modo
    )
