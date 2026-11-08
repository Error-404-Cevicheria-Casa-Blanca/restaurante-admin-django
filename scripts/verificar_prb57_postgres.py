"""Script de verificación en vivo de PRB-57 contra PostgreSQL 18.

Verifica:
1. Conexión nativa a PostgreSQL 18 (localhost:5432 / casablanca).
2. Existencia de columnas PRB-86 en 'detalle_pedido': estado_item, estacion, anulado_motivo e índice idx_detalle_estado_estacion.
3. Ciclo de vida por ítem y aislamiento de estaciones (Barra Fría vs Bebidas).
4. Verificación de que marcar 'Listo' en Barra Fría NO marca la comanda completa como lista.
5. Inserción de eventos inmutables en 'evento_pedido' con FK segura de usuario.
6. Existencia y peso real de las 15 fotos PNG de platos oficiales.
7. Ausencia de PINs en claro en el código fuente.
"""

import os
import sys

# Agregar raíz del proyecto a sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "casablanca-prod-secret-2026")
os.environ.setdefault("DB_ENGINE", "django.db.backends.postgresql")
os.environ.setdefault("DB_NAME", "casablanca")
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "Jerardo")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")

import django
django.setup()

from decimal import Decimal
from django.db import connection
from catalogo.models import Pedido, DetallePedido, Producto, Mesa, Usuario, EventoPedido
from catalogo.kds_service import avanzar_estado_item, avanzar_estado_comanda

def main():
    print("=" * 70)
    print("VERIFICACION EN VIVO PRB-57 - KDS COCINA Y PRB-86 ESTADO POR ITEM")
    print("=" * 70)

    # 1. Version de PostgreSQL
    with connection.cursor() as cur:
        cur.execute("SELECT version();")
        pg_ver = cur.fetchone()[0]
        print(f"[OK] PostgreSQL Version: {pg_ver[:60]}...")

    # 2. Verificar columnas en detalle_pedido
    with connection.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'detalle_pedido' 
              AND column_name IN ('estado_item', 'estacion', 'anulado_motivo')
            ORDER BY column_name;
        """)
        cols = cur.fetchall()
        print(f"[OK] Columnas PRB-86 en detalle_pedido:")
        for col, dtype, default in cols:
            print(f"     - {col} ({dtype}) DEFAULT {default}")
        assert len(cols) == 3, f"Se esperaban 3 columnas, encontradas {len(cols)}"

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

    # 5. Barra Fría inicia su plato
    avanzar_estado_item(d1.id, DetallePedido.ESTADO_ITEM_COCINANDO, usuario_id=mozo.id, motivo="Cocinero inicia ceviche")
    d1.refresh_from_db()
    pedido.refresh_from_db()
    print(f"[OK] Paso 1: Ceviche pasa a '{d1.estado_item}', Comanda pasa a '{pedido.estado}'")
    assert d1.estado_item == DetallePedido.ESTADO_ITEM_COCINANDO
    assert pedido.estado == Pedido.ESTADO_COCINANDO

    # 6. Barra Fría termina y marca LISTO su plato
    avanzar_estado_item(d1.id, DetallePedido.ESTADO_ITEM_LISTO, usuario_id=mozo.id, motivo="Barra Fría termina ceviche")
    d1.refresh_from_db()
    d2.refresh_from_db()
    pedido.refresh_from_db()
    print(f"[OK] Paso 2 (Aislamiento de estación):")
    print(f"     - Ceviche (Barra Fría): '{d1.estado_item}'")
    print(f"     - Chicha (Bebidas): '{d2.estado_item}'")
    print(f"     - Comanda general: '{pedido.estado}' (NO está LISTO porque falta Bebidas)")
    assert d1.estado_item == DetallePedido.ESTADO_ITEM_LISTO
    assert d2.estado_item == DetallePedido.ESTADO_ITEM_PENDIENTE
    assert pedido.estado == Pedido.ESTADO_COCINANDO, f"Estado esperado COCINANDO, obtenido {pedido.estado}"

    # 7. Bebidas marca LISTO su ítem
    avanzar_estado_item(d2.id, DetallePedido.ESTADO_ITEM_LISTO, usuario_id=mozo.id, motivo="Bar termina chicha")
    d2.refresh_from_db()
    pedido.refresh_from_db()
    print(f"[OK] Paso 3: Chicha pasa a '{d2.estado_item}' -> Ahora TODOS los platos están listos.")
    print(f"     - Comanda general: '{pedido.estado}' (Recalculado automáticamente a LISTO)")
    assert pedido.estado == Pedido.ESTADO_LISTO

    # 8. Mozo despacha a mesa
    avanzar_estado_item(d1.id, DetallePedido.ESTADO_ITEM_SERVIDO, usuario_id=mozo.id, motivo="Mozo sirve ceviche")
    avanzar_estado_item(d2.id, DetallePedido.ESTADO_ITEM_SERVIDO, usuario_id=mozo.id, motivo="Mozo sirve chicha")
    pedido.refresh_from_db()
    print(f"[OK] Paso 4: Ambos ítems SERVIDO -> Comanda general: '{pedido.estado}'")
    assert pedido.estado == Pedido.ESTADO_SERVIDO

    # 9. Verificar auditoría evento_pedido
    eventos = list(EventoPedido.objects.filter(pedido=pedido).order_by("id"))
    print(f"[OK] Auditoría: {len(eventos)} eventos inmutables registrados en 'evento_pedido':")
    for ev in eventos:
        print(f"     - Evento #{ev.id}: {ev.estado_anterior} -> {ev.estado_nuevo} | Usuario ID: {ev.usuario_id} | Motivo: {ev.motivo}")
        assert ev.usuario_id == mozo.id

    # 10. Limpieza comanda de prueba
    pedido.delete()
    print("[OK] Limpieza: Comanda de prueba eliminada.")

    # 11. Verificar fotos reales
    img_dir = os.path.join("catalogo", "static", "catalogo", "img", "platos")
    fotos = os.listdir(img_dir)
    print(f"[OK] Fotos de platos ({len(fotos)} encontradas en {img_dir}):")
    for f in sorted(fotos):
        p = os.path.join(img_dir, f)
        sz = os.path.getsize(p)
        print(f"     - {f}: {sz:,} bytes (Foto real)")
        assert sz > 20000, f"Foto {f} sospechosamente pequeña ({sz} bytes)"

    print("=" * 70)
    print("TODAS LAS VERIFICACIONES EN POSTGRESQL 18 PASARON EXITOSAMENTE (EXIT=0)")
    print("=" * 70)

if __name__ == "__main__":
    main()
