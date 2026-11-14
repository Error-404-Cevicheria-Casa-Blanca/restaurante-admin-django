"""Inicialización segura de tablas SQLite locales y datos de ejemplo (PE-19).

Cumple estrictamente la regla D7 (docs/db/DDL-OWNERSHIP.md):
- En PostgreSQL NUNCA ejecuta DDL (el esquema pertenece a db/schema.sql).
- Solo cuando el motor activo es SQLite local (desarrollo o pruebas), garantiza
  que existan las tablas `categoria` y `producto` para que `manage.py runserver`
  funcione sin errores tras `manage.py migrate`.
"""

from decimal import Decimal

from django.db import connections, transaction

CARTA_INICIAL = [
    (
        "Entradas Marinas",
        [
            (
                "Leche de Tigre Clásica",
                "Concentrado cítrico de pescado del día con cancha chulpi y choclo.",
                Decimal("25.00"),
                True,
            ),
            (
                "Causa de Pulpa de Cangrejo",
                "Masa de papa amarilla al ají amarillo rellena de pulpa de cangrejo.",
                Decimal("32.00"),
                True,
            ),
            (
                "Choros a la Chalaca",
                "Media docena de choros con zarza criolla, choclo tierno y limón.",
                Decimal("24.00"),
                False,
            ),
        ],
    ),
    (
        "Ceviches y Tiraditos",
        [
            (
                "Ceviche Clásico Casa Blanca",
                "Pesca blanca del día marinada al instante en limón sutil y ají limo.",
                Decimal("48.00"),
                True,
            ),
            (
                "Ceviche Mixto Especial",
                "Pescado del día, langostinos, pulpo y calamar con camote glaseado.",
                Decimal("54.00"),
                True,
            ),
            (
                "Tiradito en Crema de Ají Amarillo",
                "Láminas de corvina fresca bañadas en emulsión suave de ají amarillo.",
                Decimal("49.00"),
                True,
            ),
            (
                "Ceviche de Conchas Negras",
                "Conchas negras de Tumbes con cebolla roja, culantro y limón.",
                Decimal("56.00"),
                False,
            ),
        ],
    ),
    (
        "Platos de Fondo",
        [
            (
                "Jalea Mixta Real",
                "Chicharrón crujiente de pescado y mariscos con yucas doradas y tártara.",
                Decimal("58.00"),
                True,
            ),
            (
                "Arroz con Mariscos",
                "Arroz norteño al culantro y coral con mariscos seleccionados.",
                Decimal("50.00"),
                True,
            ),
            (
                "Parihuela Concentrada",
                "Sudado tradicional de cabrilla, cangrejo y mariscos al vino blanco.",
                Decimal("55.00"),
                True,
            ),
            (
                "Corvina a lo Macho",
                "Filete de corvina a la plancha en salsa cremosa de mariscos.",
                Decimal("62.00"),
                False,
            ),
        ],
    ),
    (
        "Bebidas",
        [
            (
                "Chicha Morada de la Casa (1 L)",
                "Jarra de maíz morado hervido con piña, membrillo, canela y clavo.",
                Decimal("16.00"),
                True,
            ),
            (
                "Limonada Frozen (1 L)",
                "Jarra refrescante de limón sutil recién exprimido.",
                Decimal("18.00"),
                True,
            ),
        ],
    ),
    (
        "Postres",
        [
            (
                "Suspiro a la Limeña",
                "Manjar de yemas perfumado al oporto con merengue italiano.",
                Decimal("14.00"),
                True,
            ),
            (
                "Picarones con Miel de Chancaca",
                "Porción tradicional de zapallo y camote con miel de higo.",
                Decimal("15.00"),
                True,
            ),
        ],
    ),
]


_TABLAS_ASEGURADAS = set()


def asegurar_tablas_sqlite(using="default", **kwargs):
    """Crea `categoria` y `producto` únicamente si el motor activo es SQLite."""
    conn = connections[using]
    if conn.vendor != "sqlite" or using in _TABLAS_ASEGURADAS:
        return

    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS categoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(100) NOT NULL UNIQUE
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS producto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(150) NOT NULL UNIQUE,
                descripcion TEXT,
                precio NUMERIC(10, 2) NOT NULL CHECK (precio > 0),
                disponible BOOLEAN NOT NULL DEFAULT 1,
                stock_disponible INTEGER CHECK (stock_disponible IS NULL OR stock_disponible >= 0),
                stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK (stock_minimo >= 0),
                categoria_id INTEGER NOT NULL
                    REFERENCES categoria(id) ON DELETE RESTRICT,
                imagen_url VARCHAR(255)
            );
            """)
        for col_def in (
            "stock_disponible INTEGER",
            "stock_minimo INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                cur.execute(f"ALTER TABLE producto ADD COLUMN {col_def}")
            except Exception:
                pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mesa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero INTEGER NOT NULL UNIQUE,
                capacidad INTEGER NOT NULL,
                ubicacion VARCHAR(50) NOT NULL,
                estado VARCHAR(20) NOT NULL DEFAULT 'LIBRE',
                mozo_id INTEGER,
                fecha_apertura TIMESTAMP,
                fecha_cierre TIMESTAMP
            );
            """)
        for col_def in (
            "mozo_id INTEGER",
            "fecha_apertura TIMESTAMP",
            "fecha_cierre TIMESTAMP",
        ):
            try:
                cur.execute(f"ALTER TABLE mesa ADD COLUMN {col_def}")
            except Exception:
                pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pedido (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mesa_id INTEGER REFERENCES mesa(id) ON DELETE RESTRICT,
                mozo_id INTEGER NOT NULL,
                fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
                total NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                client_request_id VARCHAR(64) UNIQUE,
                version INTEGER NOT NULL DEFAULT 1
            );
            """)
        for col_def in (
            "client_request_id VARCHAR(64)",
            "version INTEGER NOT NULL DEFAULT 1",
        ):
            try:
                cur.execute(f"ALTER TABLE pedido ADD COLUMN {col_def}")
            except Exception:
                pass
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sesion_caja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cajero_id INTEGER NOT NULL,
                fecha_apertura TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_cierre TIMESTAMP,
                monto_inicial NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                monto_ventas_efectivo NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                monto_ventas_digital NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                monto_esperado NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                monto_real NUMERIC(10, 2),
                diferencia NUMERIC(10, 2),
                estado VARCHAR(20) NOT NULL DEFAULT 'ABIERTA',
                observaciones TEXT
            );
            """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sesion_caja_unica_abierta
            ON sesion_caja (estado) WHERE estado = 'ABIERTA';
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pago (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL REFERENCES pedido(id) ON DELETE RESTRICT,
                mesa_id INTEGER REFERENCES mesa(id) ON DELETE RESTRICT,
                mozo_id INTEGER,
                sesion_caja_id INTEGER REFERENCES sesion_caja(id) ON DELETE SET NULL,
                metodo VARCHAR(20) NOT NULL,
                monto NUMERIC(10, 2) NOT NULL,
                propina NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
                referencia VARCHAR(100),
                client_request_id VARCHAR(64) NOT NULL UNIQUE,
                fecha_pago TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evento_pedido (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
                estado_anterior VARCHAR(20),
                estado_nuevo VARCHAR(20) NOT NULL,
                usuario_id INTEGER,
                motivo VARCHAR(255),
                fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS impresion_cola (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER REFERENCES pedido(id) ON DELETE CASCADE,
                tipo VARCHAR(20) NOT NULL,
                estacion VARCHAR(30),
                payload TEXT NOT NULL,
                estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
                intentos INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_impresion TIMESTAMP
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS detalle_pedido (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
                producto_id INTEGER NOT NULL REFERENCES producto(id) ON DELETE RESTRICT,
                precio_unitario NUMERIC(10, 2) NOT NULL CHECK (precio_unitario > 0),
                cantidad INTEGER NOT NULL CHECK (cantidad >= 1),
                notas VARCHAR(255),
                subtotal NUMERIC(10, 2) NOT NULL CHECK (subtotal >= 0),
                estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
                    CHECK (estado_item IN ('PENDIENTE', 'EN_PREPARACION', 'LISTO', 'SERVIDO')),
                estacion VARCHAR(30) DEFAULT 'COCINA_CALIENTE',
                anulado_motivo VARCHAR(255)
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movimiento_stock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER NOT NULL REFERENCES producto(id) ON DELETE CASCADE,
                pedido_id INTEGER REFERENCES pedido(id) ON DELETE SET NULL,
                tipo VARCHAR(20) NOT NULL,
                cantidad INTEGER NOT NULL CHECK (cantidad >= 0),
                stock_anterior INTEGER,
                stock_resultante INTEGER,
                motivo VARCHAR(255),
                registrado_por VARCHAR(100),
                fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rol (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(50) NOT NULL UNIQUE
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                clave_hash VARCHAR(255) NOT NULL,
                pin_hash VARCHAR(255),
                intentos_fallidos INTEGER NOT NULL DEFAULT 0,
                bloqueado_hasta TIMESTAMP,
                rol_id INTEGER NOT NULL REFERENCES rol(id) ON DELETE RESTRICT
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS turno (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(50) NOT NULL UNIQUE,
                hora_inicio TIME NOT NULL,
                hora_fin TIME NOT NULL,
                activo BOOLEAN NOT NULL DEFAULT 1
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS terminal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo VARCHAR(30) NOT NULL UNIQUE,
                nombre VARCHAR(100) NOT NULL,
                activo BOOLEAN NOT NULL DEFAULT 1
            );
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sesion_mozo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
                terminal_id INTEGER NOT NULL REFERENCES terminal(id) ON DELETE RESTRICT,
                turno_id INTEGER NOT NULL REFERENCES turno(id) ON DELETE RESTRICT,
                inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fin TIMESTAMP
            );
            """)
    _TABLAS_ASEGURADAS.add(using)


def poblar_carta_ejemplo(permitir_postgres=False):
    """Inserta de forma idempotente categorías y platos marinos de muestra."""
    from catalogo.models import Categoria, Producto, Mesa

    if connections["default"].vendor != "sqlite" and not permitir_postgres:
        raise ValueError(
            "poblar_carta_ejemplo es solo para SQLite. "
            "Para una demo sobre PostgreSQL usa permitir_postgres=True de forma explícita."
        )

    asegurar_tablas_sqlite()
    categorias_creadas = 0
    platos_creados = 0

    with transaction.atomic():
        if Mesa.objects.count() == 0:
            mesas_def = [
                (1, 4, "Primer piso"),
                (2, 4, "Primer piso"),
                (3, 4, "Primer piso"),
                (4, 6, "Primer piso"),
                (5, 6, "Primer piso"),
                (6, 2, "Primer piso"),
                (7, 2, "Primer piso"),
                (8, 4, "Segundo piso"),
                (9, 4, "Segundo piso"),
                (10, 4, "Segundo piso"),
                (11, 6, "Segundo piso"),
                (12, 6, "Segundo piso"),
                (13, 8, "Segundo piso (Terraza)"),
            ]
            for num, cap, ubi in mesas_def:
                Mesa.objects.get_or_create(
                    numero=num,
                    defaults={"capacidad": cap, "ubicacion": ubi, "estado": "LIBRE"},
                )

    with transaction.atomic():
        for nombre_categoria, platos in CARTA_INICIAL:
            categoria, cat_nueva = Categoria.objects.get_or_create(
                nombre=nombre_categoria,
            )
            if cat_nueva:
                categorias_creadas += 1

            for nombre_plato, descripcion, precio, disponible in platos:
                _, plato_nuevo = Producto.objects.get_or_create(
                    nombre=nombre_plato,
                    defaults={
                        "descripcion": descripcion,
                        "precio": precio,
                        "disponible": disponible,
                        "categoria": categoria,
                    },
                )
                if plato_nuevo:
                    platos_creados += 1

    return categorias_creadas, platos_creados
