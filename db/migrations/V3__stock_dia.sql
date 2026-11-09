-- =============================================================================
-- MIGRACIÓN DE PRODUCCIÓN V3: INVENTARIO REDUCIDO Y STOCK DEL DÍA POR PRODUCTO
-- Tarea: PRB-59 [P-13] Inventario reducido: stock del día, descuento y reversión
-- Base de datos: PostgreSQL 15+ (casablanca)
-- Fecha: 2026-11-06
-- Autor: Jerardo Cutipa (Owner de DDL según Regla D7)
-- =============================================================================

BEGIN;

-- 1. Columnas de control directo de stock diario en producto (sin recetas ni merma)
ALTER TABLE producto ADD COLUMN IF NOT EXISTS stock_disponible INT;
ALTER TABLE producto ADD COLUMN IF NOT EXISTS stock_minimo INT NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_producto_stock_disponible_no_negativo'
    ) THEN
        ALTER TABLE producto ADD CONSTRAINT chk_producto_stock_disponible_no_negativo
            CHECK (stock_disponible IS NULL OR stock_disponible >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_producto_stock_minimo_no_negativo'
    ) THEN
        ALTER TABLE producto ADD CONSTRAINT chk_producto_stock_minimo_no_negativo
            CHECK (stock_minimo >= 0);
    END IF;
END $$;

-- 2. Tabla de kardex auditable para cargas diarias, ventas, reversiones y ajustes
CREATE TABLE IF NOT EXISTS movimiento_stock (
    id SERIAL PRIMARY KEY,
    producto_id INT NOT NULL REFERENCES producto(id) ON DELETE CASCADE,
    pedido_id INT REFERENCES pedido(id) ON DELETE SET NULL,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('CARGA_DIARIA', 'SALIDA_VENTA', 'REVERSION', 'AJUSTE')),
    cantidad INT NOT NULL CHECK (cantidad >= 0),
    stock_anterior INT,
    stock_resultante INT CHECK (stock_resultante IS NULL OR stock_resultante >= 0),
    motivo VARCHAR(255),
    registrado_por VARCHAR(100),
    fecha TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Índices de rendimiento y verificación idempotente por pedido
CREATE INDEX IF NOT EXISTS idx_movimiento_stock_producto ON movimiento_stock(producto_id, fecha);
CREATE INDEX IF NOT EXISTS idx_movimiento_stock_pedido ON movimiento_stock(pedido_id, tipo);

COMMIT;
