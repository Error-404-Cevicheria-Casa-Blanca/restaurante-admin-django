-- =============================================================================
-- MIGRACIÓN DE PRODUCCIÓN V4: ESTADO POR ÍTEM EN DETALLE_PEDIDO Y ESTACIONES KDS
-- Tareas: PRB-57 (KDS Cocina) / PRB-86 (Columna estado_item por plato) / PRB-77 (Anulación)
-- Base de datos: PostgreSQL 15+ (casablanca)
-- Fecha: 2026-11-08
-- Autor: Jerardo Cutipa (Owner de DDL según Regla D7)
-- =============================================================================

BEGIN;

-- 1. Agregar columna estado_item a detalle_pedido (PRB-86)
-- Permite que cada plato avance independientemente en su estación de cocina.
ALTER TABLE detalle_pedido
    ADD COLUMN IF NOT EXISTS estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE';

-- 2. Agregar columna estacion a detalle_pedido (PRB-57)
-- Alineado con db/schema.sql:71 (VARCHAR(30) NOT NULL DEFAULT 'COCINA_CALIENTE')
ALTER TABLE detalle_pedido
    ADD COLUMN IF NOT EXISTS estacion VARCHAR(30) NOT NULL DEFAULT 'COCINA_CALIENTE';

-- 3. Agregar columna anulado_motivo a detalle_pedido (PRB-77)
ALTER TABLE detalle_pedido
    ADD COLUMN IF NOT EXISTS anulado_motivo VARCHAR(255);

-- 4. Constraint de validación de estados por plato (alineado a EstadoItem.java y CONTRATO-API-V2)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_detalle_pedido_estado_item'
    ) THEN
        ALTER TABLE detalle_pedido ADD CONSTRAINT chk_detalle_pedido_estado_item
            CHECK (estado_item IN ('PENDIENTE', 'EN_PREPARACION', 'LISTO', 'SERVIDO'));
    END IF;
END $$;

-- 5. Índice de consulta para KDS por estado de plato y estación
CREATE INDEX IF NOT EXISTS idx_detalle_estado_estacion ON detalle_pedido(estado_item, estacion);

COMMIT;
