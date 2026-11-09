-- =============================================================================
-- ROLLBACK MIGRACIÓN V3: INVENTARIO REDUCIDO Y STOCK DEL DÍA POR PRODUCTO
-- Tarea: PRB-59 [P-13]
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_movimiento_stock_pedido;
DROP INDEX IF EXISTS idx_movimiento_stock_producto;
DROP TABLE IF EXISTS movimiento_stock;

ALTER TABLE producto DROP CONSTRAINT IF EXISTS chk_producto_stock_minimo_no_negativo;
ALTER TABLE producto DROP CONSTRAINT IF EXISTS chk_producto_stock_disponible_no_negativo;
ALTER TABLE producto DROP COLUMN IF EXISTS stock_minimo;
ALTER TABLE producto DROP COLUMN IF EXISTS stock_disponible;

COMMIT;
