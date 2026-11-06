-- =============================================================================
-- SEEDS DE PRODUCCIÓN: CARTA MARINA REAL Y CONFIGURACIÓN DE MESAS
-- Tarea: PRB-52 [P-04] Migración de datos reales del restaurante
-- Base de datos: PostgreSQL (casablanca)
-- =============================================================================

BEGIN;

-- 1. Categorías oficiales
INSERT INTO categoria (nombre) VALUES
    ('Entradas Marinas'),
    ('Ceviches y Tiraditos'),
    ('Platos de Fondo'),
    ('Bebidas'),
    ('Postres')
ON CONFLICT (nombre) DO NOTHING;

-- 1.1. Limpieza segura de platos demo obsoletos de seed.sql (si no tienen comandas)
DELETE FROM producto
WHERE nombre IN ('Ceviche Clásico', 'Leche de Tigre', 'Jalea Mixta', 'Chicha Morada')
  AND id NOT IN (SELECT producto_id FROM detalle_pedido);

-- 2. Platos de la Carta Real (Idempotencia garantizada por UNIQUE en producto.nombre)
INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Leche de Tigre Clásica', 'Concentrado cítrico de pescado del día con cancha chulpi y choclo.', 25.00, true, id, 'platos/leche_tigre.webp'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Causa de Pulpa de Cangrejo', 'Masa de papa amarilla al ají amarillo rellena de pulpa de cangrejo.', 32.00, true, id, 'platos/causa_cangrejo.webp'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Choros a la Chalaca', 'Media docena de choros con zarza criolla, choclo tierno y limón.', 24.00, true, id, 'platos/choros_chalaca.webp'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche Clásico Casa Blanca', 'Pesca blanca del día marinada al instante en limón sutil y ají limo.', 48.00, true, id, 'platos/ceviche_clasico.webp'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche Mixto Especial', 'Pescado del día, langostinos, pulpo y calamar con camote glaseado.', 54.00, true, id, 'platos/ceviche_mixto.webp'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Tiradito en Crema de Ají Amarillo', 'Láminas de corvina fresca bañadas en emulsión suave de ají amarillo.', 49.00, true, id, 'platos/tiradito_aji.webp'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche de Conchas Negras', 'Conchas negras de Tumbes con cebolla roja, culantro y limón.', 56.00, true, id, 'platos/conchas_negras.webp'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Jalea Mixta Real', 'Chicharrón crujiente de pescado y mariscos con yucas doradas y tártara.', 58.00, true, id, 'platos/jalea_mixta.webp'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Arroz con Mariscos', 'Arroz norteño al culantro y coral con mariscos seleccionados.', 50.00, true, id, 'platos/arroz_mariscos.webp'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Parihuela Concentrada', 'Sudado tradicional de cabrilla, cangrejo y mariscos al vino blanco.', 55.00, true, id, 'platos/parihuela.webp'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Corvina a lo Macho', 'Filete de corvina a la plancha en salsa cremosa de mariscos.', 62.00, true, id, 'platos/corvina_macho.webp'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Chicha Morada de la Casa (1 L)', 'Jarra de maíz morado hervido con piña, membrillo, canela y clavo.', 16.00, true, id, 'platos/chicha_morada.webp'
FROM categoria WHERE nombre = 'Bebidas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Limonada Frozen (1 L)', 'Jarra refrescante de limón sutil recién exprimido.', 18.00, true, id, 'platos/limonada_frozen.webp'
FROM categoria WHERE nombre = 'Bebidas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Suspiro a la Limeña', 'Manjar de yemas perfumado al oporto con merengue italiano.', 14.00, true, id, 'platos/suspiro_limena.webp'
FROM categoria WHERE nombre = 'Postres'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Picarones con Miel de Chancaca', 'Porción tradicional de zapallo y camote con miel de higo.', 15.00, true, id, 'platos/picarones.webp'
FROM categoria WHERE nombre = 'Postres'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    disponible = EXCLUDED.disponible,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

-- 3. Distribución arquitectónica de las 13 mesas (Piso 1 y Piso 2)
INSERT INTO mesa (numero, capacidad, ubicacion, estado) VALUES
    (1, 4, 'Primer piso - Salón', 'LIBRE'),
    (2, 4, 'Primer piso - Salón', 'LIBRE'),
    (3, 4, 'Primer piso - Salón', 'LIBRE'),
    (4, 6, 'Primer piso - Familiar', 'LIBRE'),
    (5, 6, 'Primer piso - Familiar', 'LIBRE'),
    (6, 2, 'Primer piso - Barra Marina', 'LIBRE'),
    (7, 2, 'Primer piso - Barra Marina', 'LIBRE'),
    (8, 4, 'Segundo piso - Salón', 'LIBRE'),
    (9, 4, 'Segundo piso - Salón', 'LIBRE'),
    (10, 4, 'Segundo piso - Salón', 'LIBRE'),
    (11, 6, 'Segundo piso - Vista Mar', 'LIBRE'),
    (12, 6, 'Segundo piso - Vista Mar', 'LIBRE'),
    (13, 8, 'Segundo piso - Terraza VIP', 'LIBRE')
ON CONFLICT (numero) DO UPDATE SET
    capacidad = EXCLUDED.capacidad,
    ubicacion = EXCLUDED.ubicacion;

COMMIT;
