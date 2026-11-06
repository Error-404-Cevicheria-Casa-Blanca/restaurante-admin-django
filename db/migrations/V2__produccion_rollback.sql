-- =============================================================================
-- ROLLBACK DE PRODUCCIÓN V2: REVERSIÓN DE TABLAS PAGO Y SESION_CAJA
-- Tarea: PRB-51 [P-03]
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS impresion_cola CASCADE;
DROP TABLE IF EXISTS evento_pedido CASCADE;
DROP TABLE IF EXISTS pago CASCADE;
DROP TABLE IF EXISTS sesion_caja CASCADE;

ALTER TABLE pedido DROP CONSTRAINT IF EXISTS uq_pedido_client_request_id;
ALTER TABLE pedido DROP COLUMN IF EXISTS client_request_id;
ALTER TABLE pedido DROP COLUMN IF EXISTS version;
ALTER TABLE usuario DROP COLUMN IF EXISTS pin_hash;
ALTER TABLE producto DROP CONSTRAINT IF EXISTS uq_producto_nombre;

COMMIT;
