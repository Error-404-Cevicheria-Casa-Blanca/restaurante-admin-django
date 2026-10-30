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


def asegurar_tablas_sqlite(using="default", **kwargs):
    """Crea `categoria` y `producto` únicamente si el motor activo es SQLite."""
    conn = connections[using]
    if conn.vendor != "sqlite":
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS categoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(100) NOT NULL UNIQUE
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS producto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(150) NOT NULL,
                descripcion TEXT,
                precio NUMERIC(10, 2) NOT NULL CHECK (precio > 0),
                disponible BOOLEAN NOT NULL DEFAULT 1,
                categoria_id INTEGER NOT NULL
                    REFERENCES categoria(id) ON DELETE RESTRICT,
                imagen_url VARCHAR(255)
            );
            """
        )


def poblar_carta_ejemplo():
    """Inserta de forma idempotente categorías y platos marinos de muestra."""
    from catalogo.models import Categoria, Producto

    asegurar_tablas_sqlite()
    categorias_creadas = 0
    platos_creados = 0

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
