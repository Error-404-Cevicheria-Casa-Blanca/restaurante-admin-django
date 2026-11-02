-- =============================================================================
-- SUITE DE PRUEBAS DE CONSISTENCIA E INTEGRIDAD RELACIONAL (PE-8 / PE-15)
-- Cevichería La Casa Blanca · Base de Datos: casablanca
-- =============================================================================

\echo '----------------------------------------------------------------------'
\echo '1. VERIFICACION DE TABLAS DEL MODELO (7 tablas)'
\echo '----------------------------------------------------------------------'
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

\echo '----------------------------------------------------------------------'
\echo '2. VERIFICACION DE INDICES ESTRATEGICOS (6 indices)'
\echo '----------------------------------------------------------------------'
SELECT indexname, tablename 
FROM pg_indexes 
WHERE schemaname = 'public' AND indexname LIKE 'idx_%' 
ORDER BY indexname;

\echo '----------------------------------------------------------------------'
\echo '3. VERIFICACION DE DATOS SEMILLA (seed.sql)'
\echo '----------------------------------------------------------------------'
SELECT '1. rol' AS entidad, count(*) AS total, '4 esperados' AS criterio FROM rol
UNION ALL SELECT '2. usuario', count(*), '5 esperados (mozos/admin/cocina/caja)' FROM usuario
UNION ALL SELECT '3. mesa', count(*), '13 esperadas (1-7 p1, 8-13 p2)' FROM mesa
UNION ALL SELECT '4. categoria', count(*), '4 esperadas' FROM categoria
UNION ALL SELECT '5. producto', count(*), '5 esperados' FROM producto
UNION ALL SELECT '6. pedido', count(*), '0 (transaccional)' FROM pedido
UNION ALL SELECT '7. detalle_pedido', count(*), '0 (transaccional)' FROM detalle_pedido
ORDER BY entidad;

\echo '----------------------------------------------------------------------'
\echo '4. PRUEBAS DE RESTRICCIONES CHECK'
\echo '----------------------------------------------------------------------'

-- 4.1 Precio de producto > 0
DO $$
BEGIN
    INSERT INTO producto (nombre, precio, disponible, categoria_id) 
    VALUES ('Plato Invalido Negativo', -10.00, true, 1);
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio precio negativo';
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE '[PASS] CHECK precio > 0 funcionando correctamente.';
END $$;

-- 4.2 Estado de mesa permitido
DO $$
BEGIN
    INSERT INTO mesa (numero, capacidad, ubicacion, estado) 
    VALUES (999, 4, 'Salon', 'ESTADO_INEXISTENTE');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio estado de mesa no contemplado';
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE '[PASS] CHECK estado IN (LIBRE, OCUPADA, ATENDIDA, CUENTA_SOLICITADA) verificado.';
END $$;

-- 4.3 Numero de mesa > 0 y capacidad > 0
DO $$
BEGIN
    INSERT INTO mesa (numero, capacidad, ubicacion, estado) 
    VALUES (0, 0, 'Salon', 'LIBRE');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio mesa con numero o capacidad 0';
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE '[PASS] CHECK numero > 0 y capacidad > 0 verificado.';
END $$;

-- 4.4 Estado de pedido permitido
DO $$
BEGIN
    INSERT INTO pedido (mesa_id, mozo_id, estado) 
    VALUES (1, 2, 'INVALIDO');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio estado de pedido no valido';
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE '[PASS] CHECK pedido.estado IN (PENDIENTE, COCINANDO, LISTO, SERVIDO, COBRADO) verificado.';
END $$;

\echo '----------------------------------------------------------------------'
\echo '5. PRUEBAS DE UNICIDAD (UNIQUE CONSTRAINTS)'
\echo '----------------------------------------------------------------------'

-- 5.1 Rol duplicado
DO $$
BEGIN
    INSERT INTO rol (nombre) VALUES ('ADMIN');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio rol duplicado';
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE '[PASS] UNIQUE rol.nombre verificado.';
END $$;

-- 5.2 Username duplicado
DO $$
BEGIN
    INSERT INTO usuario (username, clave_hash, rol_id) 
    VALUES ('admin_test', 'hash_falso', 1);
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio username duplicado';
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE '[PASS] UNIQUE usuario.username verificado.';
END $$;

-- 5.3 Numero de mesa duplicado
DO $$
BEGIN
    INSERT INTO mesa (numero, capacidad, ubicacion) 
    VALUES (1, 4, 'Cualquiera');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio numero de mesa duplicado';
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE '[PASS] UNIQUE mesa.numero verificado.';
END $$;

-- 5.4 Categoria duplicada
DO $$
BEGIN
    INSERT INTO categoria (nombre) VALUES ('Entradas');
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio categoria duplicada';
EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE '[PASS] UNIQUE categoria.nombre verificado.';
END $$;

\echo '----------------------------------------------------------------------'
\echo '6. PRUEBAS DE INTEGRIDAD REFERENCIAL Y LLAVES FORANEAS'
\echo '----------------------------------------------------------------------'

-- 6.1 Insertar usuario con rol_id inexistente
DO $$
BEGIN
    INSERT INTO usuario (username, clave_hash, rol_id) 
    VALUES ('usuario_huerfano', 'hash', 9999);
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio usuario con rol inexistente';
EXCEPTION WHEN foreign_key_violation THEN
    RAISE NOTICE '[PASS] FK usuario -> rol (ON DELETE RESTRICT) verificado.';
END $$;

-- 6.2 Borrar categoria en uso (ON DELETE RESTRICT)
DO $$
BEGIN
    DELETE FROM categoria WHERE id = 1;
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio borrar categoria que tiene productos';
EXCEPTION 
    WHEN foreign_key_violation OR SQLSTATE '23001' OR SQLSTATE '23503' THEN
        RAISE NOTICE '[PASS] FK producto -> categoria (RESTRICT) bloquea borrado en cascada indebido.';
END $$;

-- 6.3 Borrar rol en uso (ON DELETE RESTRICT)
DO $$
BEGIN
    DELETE FROM rol WHERE id = 2;
    RAISE EXCEPTION 'TEST FALLIDO: Se permitio borrar rol que tiene usuarios asignados';
EXCEPTION 
    WHEN foreign_key_violation OR SQLSTATE '23001' OR SQLSTATE '23503' THEN
        RAISE NOTICE '[PASS] FK usuario -> rol (RESTRICT) protege catalogo de roles activos.';
END $$;

\echo '----------------------------------------------------------------------'
\echo '7. PRUEBA DE FLUJO TRANSACCIONAL COMPLETO Y CASCADE'
\echo '----------------------------------------------------------------------'

DO $$
DECLARE
    v_pedido_id INT;
    v_det1_id INT;
    v_det2_id INT;
    v_total NUMERIC(10,2);
BEGIN
    -- 7.1 Crear pedido para mesa 1 atendida por mozo_01 (id 2)
    INSERT INTO pedido (mesa_id, mozo_id, estado, total)
    VALUES (1, 2, 'PENDIENTE', 73.00)
    RETURNING id INTO v_pedido_id;

    -- 7.2 Insertar dos detalles de comanda (Ceviche Clásico + Leche de Tigre)
    INSERT INTO detalle_pedido (pedido_id, producto_id, precio_unitario, cantidad, subtotal)
    VALUES (v_pedido_id, 1, 48.00, 1, 48.00)
    RETURNING id INTO v_det1_id;

    INSERT INTO detalle_pedido (pedido_id, producto_id, precio_unitario, cantidad, subtotal)
    VALUES (v_pedido_id, 2, 25.00, 1, 25.00)
    RETURNING id INTO v_det2_id;

    -- 7.3 Verificar calculo del subtotal
    SELECT sum(subtotal) INTO v_total FROM detalle_pedido WHERE pedido_id = v_pedido_id;
    IF v_total <> 73.00 THEN
        RAISE EXCEPTION 'TEST FALLIDO: Suma de subtotales no coincide con pedido';
    END IF;
    RAISE NOTICE '[PASS] Insercion transaccional de Pedido y Detalle con calculos correctos.';

    -- 7.4 Verificar ON DELETE CASCADE de detalle_pedido al eliminar pedido
    DELETE FROM pedido WHERE id = v_pedido_id;
    IF EXISTS (SELECT 1 FROM detalle_pedido WHERE id IN (v_det1_id, v_det2_id)) THEN
        RAISE EXCEPTION 'TEST FALLIDO: Los detalles de comanda no se eliminaron en cascada';
    END IF;
    RAISE NOTICE '[PASS] FK detalle_pedido -> pedido (ON DELETE CASCADE) verificado exitosamente.';
END $$;

\echo '----------------------------------------------------------------------'
\echo '8. PRUEBA DE CONSISTENCIA DE HASH BCRYPT DE CONTRASENAS (D8)'
\echo '----------------------------------------------------------------------'
SELECT username, 
       clave_hash,
       CASE 
           WHEN clave_hash LIKE '$2b$10$%' OR clave_hash LIKE '$2a$10$%' THEN 'VALIDO (BCrypt cost 10)'
           ELSE 'INVALIDO'
       END AS formato_hash
FROM usuario
ORDER BY id;
