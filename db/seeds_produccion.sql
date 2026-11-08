-- =============================================================================
-- SEEDS DE PRODUCCIÓN: CARTA MARINA, 13 MESAS, ROLES, USUARIOS Y PIN (BCrypt 10)
-- Tarea: PRB-52 [P-04] Migración de datos reales del restaurante
-- Reglas cumplidas: D7 (DDL Ownership) y D8 (BCrypt cost 10 en clave_hash y pin_hash)
-- Base de datos: PostgreSQL 15+ (casablanca)
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. ROLES OPERATIVOS OFICIALES (4 roles canónicos)
-- =============================================================================
INSERT INTO rol (nombre) VALUES
    ('ADMIN'),
    ('MOZO'),
    ('COCINERO'),
    ('CAJERO')
ON CONFLICT (nombre) DO NOTHING;

-- =============================================================================
-- 2. SANEAMIENTO DE CREDENCIALES DEMO Y ALTA DE PERSONAL OPERATIVO CON PIN
--    Elimina la cuenta demo 'admin_test' si no tiene historial transaccional;
--    si tuviera referencias en pedido/pago/sesion_caja, invalida el hash débil
--    de 'password123' para cumplir PRB-67 / R9 (cero contraseñas de prueba).
-- =============================================================================
DELETE FROM usuario
WHERE username = 'admin_test'
  AND id NOT IN (SELECT DISTINCT mozo_id FROM pedido WHERE mozo_id IS NOT NULL)
  AND id NOT IN (SELECT DISTINCT mozo_id FROM mesa WHERE mozo_id IS NOT NULL)
  AND id NOT IN (SELECT DISTINCT cajero_id FROM sesion_caja WHERE cajero_id IS NOT NULL)
  AND id NOT IN (SELECT DISTINCT mozo_id FROM pago WHERE mozo_id IS NOT NULL);

UPDATE usuario
SET clave_hash = '$2b$10$DKEHgzLn6shfGj/CuZTVR.UM5yPWvDNcG3xmqm1fvHrvzq6eEMUnW',
    pin_hash = COALESCE(pin_hash, '$2b$10$nCEbqb1gjv2B9gH3BjYxhuYak2QeZcowFaNx1ecAo1ObCSuSu0og2')
WHERE username = 'admin_test'
  AND clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S';

-- Usuarios operativos reales con BCrypt cost 10 tanto en clave_hash como en pin_hash.
-- Nota: Si el administrador ya rotó manualmente la contraseña o el PIN en producción
-- (distinto del hash débil de seed.sql), el DO UPDATE respeta la rotación existente.

INSERT INTO usuario (username, clave_hash, pin_hash, intentos_fallidos, bloqueado_hasta, rol_id)
SELECT
    'admin_casablanca',
    '$2b$10$DKEHgzLn6shfGj/CuZTVR.UM5yPWvDNcG3xmqm1fvHrvzq6eEMUnW',
    '$2b$10$nCEbqb1gjv2B9gH3BjYxhuYak2QeZcowFaNx1ecAo1ObCSuSu0og2',
    0,
    NULL,
    id
FROM rol WHERE nombre = 'ADMIN'
ON CONFLICT (username) DO UPDATE SET
    rol_id = EXCLUDED.rol_id,
    clave_hash = CASE
        WHEN usuario.clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S'
        THEN EXCLUDED.clave_hash
        ELSE usuario.clave_hash
    END,
    pin_hash = COALESCE(NULLIF(usuario.pin_hash, ''), EXCLUDED.pin_hash);

INSERT INTO usuario (username, clave_hash, pin_hash, intentos_fallidos, bloqueado_hasta, rol_id)
SELECT
    'cajero_01',
    '$2b$10$q4uxzvPmonj4yAazKZTf9uRQzHhaOfREQBXIRzt0OZO.hlfAPrd/K',
    '$2b$10$2am1ckanDtp87GRVfMnI7.Cs5rzqp1UxnL0ZDbxVyDF1SYpn2BNRi',
    0,
    NULL,
    id
FROM rol WHERE nombre = 'CAJERO'
ON CONFLICT (username) DO UPDATE SET
    rol_id = EXCLUDED.rol_id,
    clave_hash = CASE
        WHEN usuario.clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S'
        THEN EXCLUDED.clave_hash
        ELSE usuario.clave_hash
    END,
    pin_hash = COALESCE(NULLIF(usuario.pin_hash, ''), EXCLUDED.pin_hash);

INSERT INTO usuario (username, clave_hash, pin_hash, intentos_fallidos, bloqueado_hasta, rol_id)
SELECT
    'mozo_01',
    '$2b$10$xPju1s2hMHa4jMUhW.vzCOT8Jxj7JeLs42H6DA73biyIBZXhBIXXO',
    '$2b$10$GfpUH9Hzg3yIwfN81Rb5bOBBlsFwpWU/TjBIkDZOZCyhWDPGYj0F.',
    0,
    NULL,
    id
FROM rol WHERE nombre = 'MOZO'
ON CONFLICT (username) DO UPDATE SET
    rol_id = EXCLUDED.rol_id,
    clave_hash = CASE
        WHEN usuario.clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S'
        THEN EXCLUDED.clave_hash
        ELSE usuario.clave_hash
    END,
    pin_hash = COALESCE(NULLIF(usuario.pin_hash, ''), EXCLUDED.pin_hash);

INSERT INTO usuario (username, clave_hash, pin_hash, intentos_fallidos, bloqueado_hasta, rol_id)
SELECT
    'mozo_02',
    '$2b$10$UdxWr.j7CveWqsLii4ohOeO4WJJVJRv.GHRvsier6SRf8aCZoc2la',
    '$2b$10$/AzYAZN9wyMUOQO.jiaCmOa.LJFVNw52q.eBLel.5gmxj0x2i4suC',
    0,
    NULL,
    id
FROM rol WHERE nombre = 'MOZO'
ON CONFLICT (username) DO UPDATE SET
    rol_id = EXCLUDED.rol_id,
    clave_hash = CASE
        WHEN usuario.clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S'
        THEN EXCLUDED.clave_hash
        ELSE usuario.clave_hash
    END,
    pin_hash = COALESCE(NULLIF(usuario.pin_hash, ''), EXCLUDED.pin_hash);

INSERT INTO usuario (username, clave_hash, pin_hash, intentos_fallidos, bloqueado_hasta, rol_id)
SELECT
    'cocinero_01',
    '$2b$10$4LKw5u8HgC/DRp0t6It8beUPuY9PO/hUkphPwcuC16/qkMdo0TAAC',
    '$2b$10$PLWdrtnbLZwZPumxGKSVLOPWIL.9aGcri2VPaO9ztWRlFyxpZ4sd2',
    0,
    NULL,
    id
FROM rol WHERE nombre = 'COCINERO'
ON CONFLICT (username) DO UPDATE SET
    rol_id = EXCLUDED.rol_id,
    clave_hash = CASE
        WHEN usuario.clave_hash = '$2b$10$b5o6bC2KfOaSLwhhC8UEjuD1ySzwScC7ZuSj82CCM6PYI4iNyQJ0S'
        THEN EXCLUDED.clave_hash
        ELSE usuario.clave_hash
    END,
    pin_hash = COALESCE(NULLIF(usuario.pin_hash, ''), EXCLUDED.pin_hash);

-- =============================================================================
-- 3. CATEGORÍAS OFICIALES Y DEPURACIÓN DE ÍTEMS DEMO (seed.sql)
-- =============================================================================
INSERT INTO categoria (nombre) VALUES
    ('Entradas Marinas'),
    ('Ceviches y Tiraditos'),
    ('Platos de Fondo'),
    ('Bebidas'),
    ('Postres')
ON CONFLICT (nombre) DO NOTHING;

-- Elimina platos demo de seed.sql si no tienen comandas históricas; si las tienen,
-- los desactiva y reasigna fuera de 'Entradas' para retirar la categoría obsoleta.
DELETE FROM producto
WHERE nombre IN ('Ceviche Clásico', 'Leche de Tigre', 'Jalea Mixta', 'Chicha Morada')
  AND id NOT IN (SELECT DISTINCT producto_id FROM detalle_pedido);

UPDATE producto
SET disponible = FALSE,
    categoria_id = (SELECT id FROM categoria WHERE nombre = 'Entradas Marinas')
WHERE nombre IN ('Ceviche Clásico', 'Leche de Tigre', 'Jalea Mixta', 'Chicha Morada');

DELETE FROM categoria
WHERE nombre = 'Entradas'
  AND id NOT IN (SELECT DISTINCT categoria_id FROM producto);

-- =============================================================================
-- 4. CARTA MARINA OFICIAL (15 platos reales con precios en S/ y fotos locales)
-- =============================================================================
INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Leche de Tigre Clásica', 'Concentrado cítrico de pescado del día con cancha chulpi y choclo.', 25.00, true, id, '/static/catalogo/img/platos/leche_tigre.png'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Causa de Pulpa de Cangrejo', 'Masa de papa amarilla al ají amarillo rellena de pulpa de cangrejo.', 32.00, true, id, '/static/catalogo/img/platos/causa_cangrejo.png'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Choros a la Chalaca', 'Media docena de choros con zarza criolla, choclo tierno y limón.', 24.00, true, id, '/static/catalogo/img/platos/choros_chalaca.png'
FROM categoria WHERE nombre = 'Entradas Marinas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche Clásico Casa Blanca', 'Pesca blanca del día marinada al instante en limón sutil y ají limo.', 48.00, true, id, '/static/catalogo/img/platos/ceviche_clasico.png'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche Mixto Especial', 'Pescado del día, langostinos, pulpo y calamar con camote glaseado.', 54.00, true, id, '/static/catalogo/img/platos/ceviche_mixto.png'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Tiradito en Crema de Ají Amarillo', 'Láminas de corvina fresca bañadas en emulsión suave de ají amarillo.', 49.00, true, id, '/static/catalogo/img/platos/tiradito_aji.png'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Ceviche de Conchas Negras', 'Conchas negras de Tumbes con cebolla roja, culantro y limón.', 56.00, true, id, '/static/catalogo/img/platos/conchas_negras.png'
FROM categoria WHERE nombre = 'Ceviches y Tiraditos'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Jalea Mixta Real', 'Chicharrón crujiente de pescado y mariscos con yucas doradas y tártara.', 58.00, true, id, '/static/catalogo/img/platos/jalea_mixta.png'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Arroz con Mariscos', 'Arroz norteño al culantro y coral con mariscos seleccionados.', 50.00, true, id, '/static/catalogo/img/platos/arroz_mariscos.png'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Parihuela Concentrada', 'Sudado tradicional de cabrilla, cangrejo y mariscos al vino blanco.', 55.00, true, id, '/static/catalogo/img/platos/parihuela.png'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Corvina a lo Macho', 'Filete de corvina a la plancha en salsa cremosa de mariscos.', 62.00, true, id, '/static/catalogo/img/platos/corvina_macho.png'
FROM categoria WHERE nombre = 'Platos de Fondo'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Chicha Morada de la Casa (1 L)', 'Jarra de maíz morado hervido con piña, membrillo, canela y clavo.', 16.00, true, id, '/static/catalogo/img/platos/chicha_morada.png'
FROM categoria WHERE nombre = 'Bebidas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Limonada Frozen (1 L)', 'Jarra refrescante de limón sutil recién exprimido.', 18.00, true, id, '/static/catalogo/img/platos/limonada_frozen.png'
FROM categoria WHERE nombre = 'Bebidas'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Suspiro a la Limeña', 'Manjar de yemas perfumado al oporto con merengue italiano.', 14.00, true, id, '/static/catalogo/img/platos/suspiro_limena.png'
FROM categoria WHERE nombre = 'Postres'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

INSERT INTO producto (nombre, descripcion, precio, disponible, categoria_id, imagen_url)
SELECT 'Picarones con Miel de Chancaca', 'Porción tradicional de zapallo y camote con miel de higo.', 15.00, true, id, '/static/catalogo/img/platos/picarones.png'
FROM categoria WHERE nombre = 'Postres'
ON CONFLICT (nombre) DO UPDATE SET
    descripcion = EXCLUDED.descripcion,
    precio = EXCLUDED.precio,
    categoria_id = EXCLUDED.categoria_id,
    imagen_url = EXCLUDED.imagen_url;

-- =============================================================================
-- 5. DISTRIBUCIÓN ARQUITECTÓNICA DE LAS 13 MESAS REALES (Piso 1: 1-7, Piso 2: 8-13)
-- =============================================================================
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
