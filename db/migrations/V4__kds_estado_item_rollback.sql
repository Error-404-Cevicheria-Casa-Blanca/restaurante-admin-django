-- =============================================================================
-- ROLLBACK MIGRACIÓN DE PRODUCCIÓN V4
-- ADVERTENCIA: Esta reversión elimina TODO el bloque V4 en detalle_pedido:
--   - estado_item (PRB-86)
--   - estacion (PRB-57)
--   - anulado_motivo (PRB-77)
-- Ejecutar únicamente si se requiere revertir el bloque completo V4.
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_detalle_estado_estacion;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_detalle_pedido_estado_item'
    ) THEN
        ALTER TABLE detalle_pedido DROP CONSTRAINT chk_detalle_pedido_estado_item;
    END IF;
END $$;

ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS estado_item;
ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS estacion;
ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS anulado_motivo;

COMMIT;
