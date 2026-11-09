"""Script de verificación en vivo de PRB-57 contra PostgreSQL 18.

Verifica (sin ejecutar DDL ni alterar el esquema):
1. Conexión nativa a PostgreSQL 18 (localhost:5432 / casablanca).
2. Existencia previa de columnas PRB-86 en 'detalle_pedido': estado_item, estacion, anulado_motivo.
3. Ciclo de vida por ítem y aislamiento de estaciones (Barra Fría vs Bebidas).
4. Descuento automático de stock en KDS (PRB-59) registrando MovimientoStock con registrado_por.
5. Verificación de que marcar 'Listo' en Barra Fría NO marca la comanda completa como lista.
6. Inserción de eventos inmutables en 'evento_pedido' con FK segura de usuario.
7. Verificación técnica de cabeceras PNG (IHDR), dimensiones y entropía de las 15 fotos reales.
"""

import math
import os
import struct
import sys
from collections import Counter

# Agregar raíz del proyecto a sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configurar Django sin valores sensibles expuestos en código
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "django.db.backends.postgresql")
os.environ.setdefault("DB_NAME", os.getenv("DB_NAME", "casablanca"))
os.environ.setdefault("DB_USER", os.getenv("DB_USER", "postgres"))
os.environ.setdefault("DB_HOST", os.getenv("DB_HOST", "localhost"))
os.environ.setdefault("DB_PORT", os.getenv("DB_PORT", "5432"))

# Validar que los secretos requeridos se suministren por el entorno
if not os.environ.get("DJANGO_SECRET_KEY"):
    sys.exit(
        "ERROR: Debe definir la variable de entorno DJANGO_SECRET_KEY antes de "
        "ejecutar este script.\n"
        "Ejemplo (PowerShell): $env:DJANGO_SECRET_KEY=\"tu-clave-secreta\""
    )

if not os.environ.get("DB_PASSWORD"):
    sys.exit(
        "ERROR: Debe definir la variable de entorno DB_PASSWORD con la contraseña de PostgreSQL.\n"
        "Ejemplo (PowerShell): $env:DB_PASSWORD=\"tu-contraseña-postgres\""
    )

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from catalogo.models import (  # noqa: E402
    DetallePedido, EventoPedido, Mesa, MovimientoStock, Pedido, Producto, Usuario,
)
from catalogo.kds_service import avanzar_estado_item  # noqa: E402


def _analizar_png_real(ruta):
    """Verifica firma PNG, dimensiones IHDR y entropía de Shannon para descartar placeholders."""
    with open(ruta, "rb") as fh:
        datos = fh.read()
    firma_png = b"\x89PNG\r\n\x1a\n"
    assert datos[:8] == firma_png, f"{ruta} no tiene cabecera PNG válida"
    ancho, alto = struct.unpack(">II", datos[16:24])
    conteo = Counter(datos)
    total = len(datos)
    entropia = -sum((c / total) * math.log2(c / total) for c in conteo.values())
    return total, ancho, alto, entropia


def main():
    print("=" * 70)
    print("VERIFICACION EN VIVO PRB-57 - KDS COCINA Y PRB-86 ESTADO POR ITEM")
    print("=" * 70)

    # 1. Version de PostgreSQL
    with connection.cursor() as cur:
        cur.execute("SELECT version();")
        pg_ver = cur.fetchone()[0]
        print(f"[OK] PostgreSQL Version: {pg_ver[:60]}...")

    # 2. Verificar columnas PRB-86 e índice en detalle_pedido (solo lectura, sin ejecutar DDL)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'detalle_pedido'
              AND column_name IN ('estado_item', 'estacion', 'anulado_motivo')
            ORDER BY column_name;
        """)
        cols = cur.fetchall()
        print("[OK] Columnas PRB-86 en detalle_pedido (esquema verificado en modo lectura):")
        for col, dtype, maxlen, nullable, default in cols:
            print(
                f"     - {col} ({dtype}({maxlen}), nullable={nullable}) "
                f"DEFAULT {default}"
            )
        assert len(cols) == 3, (
            f"Se esperaban 3 columnas en detalle_pedido, encontradas {len(cols)}. "
            "Aplique manualmente db/migrations/V4__kds_estado_item.sql antes de verificar."
        )

        cur.execute("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'detalle_pedido' AND indexname = 'idx_detalle_estado_estacion';
        """)
        idx = cur.fetchone()
        assert idx is not None, "Índice idx_detalle_estado_estacion no encontrado"
        print(f"[OK] Índice: {idx[0]} -> {idx[1]}")

    # 3. Obtener mesa, mozo y platos para prueba
    mesa = Mesa.objects.filter(numero=1).first() or Mesa.objects.first()
    mozo = Usuario.objects.filter(rol__nombre="MOZO").first() or Usuario.objects.first()
    ceviche = Producto.objects.filter(nombre__icontains="Ceviche Clásico").first()
    chicha = Producto.objects.filter(nombre__icontains="Chicha Morada").first()

    assert mesa, "No hay mesas en DB"
    assert mozo, "No hay mozo en DB"
    assert ceviche, "No hay ceviche en DB"
    assert chicha, "No hay chicha en DB"

    stock_orig_ceviche = ceviche.stock_disponible
    stock_orig_chicha = chicha.stock_disponible
    if ceviche.stock_disponible is None or ceviche.stock_disponible < 5:
        ceviche.stock_disponible = 20
        ceviche.save(update_fields=["stock_disponible"])

    print(f"[OK] Datos base: Mesa {mesa.numero}, Mozo {mozo.username} (ID {mozo.id})")
    print(f"     Plato 1: {ceviche.nombre} [Estación: {ceviche.estacion}]")
    print(f"     Plato 2: {chicha.nombre} [Estación: {chicha.estacion}]")

    # 4. Crear comanda de prueba
    pedido = Pedido.objects.create(
        mesa=mesa,
        mozo_id=mozo.id,
        estado=Pedido.ESTADO_PENDIENTE,
        total=ceviche.precio + chicha.precio,
    )
    try:
        d1 = DetallePedido.objects.create(
            pedido=pedido,
            producto=ceviche,
            cantidad=1,
            precio_unitario=ceviche.precio,
            subtotal=ceviche.precio,
            estado_item=DetallePedido.ESTADO_ITEM_PENDIENTE,
            estacion_item=ceviche.estacion,
        )
        d2 = DetallePedido.objects.create(
            pedido=pedido,
            producto=chicha,
            cantidad=1,
            precio_unitario=chicha.precio,
            subtotal=chicha.precio,
            estado_item=DetallePedido.ESTADO_ITEM_PENDIENTE,
            estacion_item=chicha.estacion,
        )
        print(f"[OK] Comanda #{pedido.id} creada: estado inicial '{pedido.estado}'")
        print(f"     - Ítem #{d1.id} ({d1.producto.nombre}): {d1.estado_item}")
        print(f"     - Ítem #{d2.id} ({d2.producto.nombre}): {d2.estado_item}")

        # 5. Barra Fría inicia su plato (verifica además descuento de stock D2)
        avanzar_estado_item(
            d1.id,
            DetallePedido.ESTADO_ITEM_COCINANDO,
            usuario_id=mozo.id,
            motivo="Cocinero inicia ceviche",
        )
        d1.refresh_from_db()
        pedido.refresh_from_db()
        movs = list(MovimientoStock.objects.filter(pedido=pedido))
        print(
            f"[OK] Paso 1: Ceviche pasa a '{d1.estado_item}', "
            f"Comanda pasa a '{pedido.estado}'"
        )
        print(
            f"[OK] Descuento de stock KDS (D2): {len(movs)} movimiento(s) en "
            f"'movimiento_stock' (registrado_por='{movs[0].registrado_por if movs else ''}')"
        )
        assert d1.estado_item == DetallePedido.ESTADO_ITEM_COCINANDO
        assert pedido.estado == Pedido.ESTADO_COCINANDO
        assert len(movs) >= 1, "No se registró el descuento de stock en movimiento_stock"

        # 6. Barra Fría termina y marca LISTO su plato
        avanzar_estado_item(
            d1.id,
            DetallePedido.ESTADO_ITEM_LISTO,
            usuario_id=mozo.id,
            motivo="Barra Fría termina ceviche",
        )
        d1.refresh_from_db()
        d2.refresh_from_db()
        pedido.refresh_from_db()
        print("[OK] Paso 2 (Aislamiento de estación):")
        print(f"     - Ceviche (Barra Fría): '{d1.estado_item}'")
        print(f"     - Chicha (Bebidas): '{d2.estado_item}'")
        print(f"     - Comanda general: '{pedido.estado}' (NO está LISTO porque falta Bebidas)")
        assert d1.estado_item == DetallePedido.ESTADO_ITEM_LISTO
        assert d2.estado_item == DetallePedido.ESTADO_ITEM_PENDIENTE
        assert pedido.estado == Pedido.ESTADO_COCINANDO

        # 7. Bebidas marca LISTO su ítem
        avanzar_estado_item(
            d2.id,
            DetallePedido.ESTADO_ITEM_LISTO,
            usuario_id=mozo.id,
            motivo="Bar termina chicha",
        )
        d2.refresh_from_db()
        pedido.refresh_from_db()
        print(
            f"[OK] Paso 3: Chicha pasa a '{d2.estado_item}' -> "
            "Ahora TODOS los platos están listos."
        )
        print(
            f"     - Comanda general: '{pedido.estado}' "
            "(Recalculado automáticamente a LISTO)"
        )
        assert pedido.estado == Pedido.ESTADO_LISTO

        # 8. Mozo despacha a mesa
        avanzar_estado_item(
            d1.id,
            DetallePedido.ESTADO_ITEM_SERVIDO,
            usuario_id=mozo.id,
            motivo="Mozo sirve ceviche",
        )
        avanzar_estado_item(
            d2.id,
            DetallePedido.ESTADO_ITEM_SERVIDO,
            usuario_id=mozo.id,
            motivo="Mozo sirve chicha",
        )
        pedido.refresh_from_db()
        print(f"[OK] Paso 4: Ambos ítems SERVIDO -> Comanda general: '{pedido.estado}'")
        assert pedido.estado == Pedido.ESTADO_SERVIDO

        # 9. Verificar auditoría evento_pedido
        eventos = list(EventoPedido.objects.filter(pedido=pedido).order_by("id"))
        print(
            f"[OK] Auditoría: {len(eventos)} eventos inmutables registrados "
            "en 'evento_pedido':"
        )
        for ev in eventos:
            print(
                f"     - Evento #{ev.id}: {ev.estado_anterior} -> {ev.estado_nuevo} | "
                f"Usuario ID: {ev.usuario_id} | Motivo: {ev.motivo}"
            )
            assert ev.usuario_id == mozo.id
    finally:
        # 10. Limpieza de datos transaccionales de prueba y restauración de stock
        MovimientoStock.objects.filter(pedido=pedido).delete()
        pedido.delete()
        ceviche.stock_disponible = stock_orig_ceviche
        ceviche.save(update_fields=["stock_disponible"])
        chicha.stock_disponible = stock_orig_chicha
        chicha.save(update_fields=["stock_disponible"])
        print("[OK] Limpieza: Comanda de prueba, movimientos y stock restaurados.")

    # 11. Verificar fotos reales (cabecera PNG, resolución IHDR y entropía > 7.5 bits/byte)
    img_dir = os.path.join("catalogo", "static", "catalogo", "img", "platos")
    fotos = sorted(os.listdir(img_dir))
    print(f"[OK] Fotos de platos ({len(fotos)} verificadas en {img_dir}):")
    assert len(fotos) == 15, f"Se esperaban 15 fotos, encontradas {len(fotos)}"
    for f in fotos:
        p = os.path.join(img_dir, f)
        sz, w, h, entropia = _analizar_png_real(p)
        print(
            f"     - {f}: {sz:,} bytes | {w}x{h} px | "
            f"entropía={entropia:.2f} bits/byte (Fotografía PNG verificada)"
        )
        assert sz > 100000, f"Foto {f} demasiado pequeña ({sz} bytes)"
        assert w >= 300 and h >= 300, f"Resolución insuficiente en {f}: {w}x{h}"
        assert entropia > 7.5, f"Baja entropía en {f} ({entropia:.2f}): posible placeholder"

    print("=" * 70)
    print("TODAS LAS VERIFICACIONES EN POSTGRESQL 18 PASARON EXITOSAMENTE (EXIT=0)")
    print("=" * 70)


if __name__ == "__main__":
    main()
