-- =============================================================================
-- MIGRACIÓN DE PRODUCCIÓN V2: GESTIÓN DE CAJA, PAGOS E IDEMPOTENCIA
-- Tarea: PRB-51 [P-03] Esquema BD v2 y migración V2__produccion.sql
-- Base de datos: PostgreSQL 15+ (casablanca)
-- Fecha: 2026-11-05
-- Autor: Jerardo Cutipa (Owner de DDL según Regla D7)
-- =============================================================================

BEGIN;

-- 1. TABLA: sesion_caja (Gestión de turnos de caja, arqueo Z y diferencias - PRB-60)
CREATE TABLE IF NOT EXISTS sesion_caja (
    id SERIAL PRIMARY KEY,
    cajero_id INT NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    fecha_apertura TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre TIMESTAMP WITH TIME ZONE,
    monto_inicial NUMERIC(10,2) NOT NULL DEFAULT 0.00 CHECK (monto_inicial >= 0),
    monto_ventas_efectivo NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    monto_ventas_digital NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    monto_esperado NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    monto_real NUMERIC(10,2),
    diferencia NUMERIC(10,2),
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('ABIERTA', 'CERRADA')) DEFAULT 'ABIERTA',
    observaciones TEXT
);

-- 2. TABLA: pago (Registro transaccional de pagos multimoneda e idempotencia - PRB-51, PRB-55, PRB-56)
CREATE TABLE IF NOT EXISTS pago (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL REFERENCES pedido(id) ON DELETE RESTRICT,
    mesa_id INT REFERENCES mesa(id) ON DELETE RESTRICT,
    mozo_id INT REFERENCES usuario(id) ON DELETE SET NULL,
    sesion_caja_id INT REFERENCES sesion_caja(id) ON DELETE SET NULL,
    metodo VARCHAR(20) NOT NULL CHECK (metodo IN ('EFECTIVO', 'YAPE', 'PLIN', 'TARJETA')),
    monto NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    propina NUMERIC(10,2) NOT NULL DEFAULT 0.00 CHECK (propina >= 0),
    referencia VARCHAR(100),
    client_request_id VARCHAR(64) NOT NULL UNIQUE,
    fecha_pago TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2.1. ALINEACIÓN CON BACKEND v2.0.0-prod (PRB-53 Anulación y PRB-79 Para llevar sin mesa)
ALTER TABLE pedido ALTER COLUMN mesa_id DROP NOT NULL;
ALTER TABLE pago ALTER COLUMN mesa_id DROP NOT NULL;

ALTER TABLE pedido DROP CONSTRAINT IF EXISTS pedido_estado_check;
ALTER TABLE pedido ADD CONSTRAINT pedido_estado_check
    CHECK (estado IN ('PENDIENTE', 'COCINANDO', 'LISTO', 'SERVIDO', 'COBRADO', 'ANULADO'));

-- 2.2. CAMPOS DE AUDITORÍA, CONCURRENCIA E IDEMPOTENCIA DEL PLAN POS (PRB-49, PRB-53, PRB-54, PRB-69, PRB-74, PRB-79)
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS pin_hash VARCHAR(255);
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS intentos_fallidos INT NOT NULL DEFAULT 0;
ALTER TABLE usuario ADD COLUMN IF NOT EXISTS bloqueado_hasta TIMESTAMP;
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS client_request_id VARCHAR(64);
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS motivo_anulacion VARCHAR(255);
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS tipo_pedido VARCHAR(30) NOT NULL DEFAULT 'SALON';
ALTER TABLE pedido ADD COLUMN IF NOT EXISTS cliente_nombre VARCHAR(120);
ALTER TABLE detalle_pedido ADD COLUMN IF NOT EXISTS modificadores_json TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_pedido_client_request_id'
    ) THEN
        ALTER TABLE pedido ADD CONSTRAINT uq_pedido_client_request_id UNIQUE (client_request_id);
    END IF;

    -- Eliminar duplicados no referenciados de producto antes de crear el índice único
    DELETE FROM producto p1
    USING producto p2
    WHERE p1.nombre = p2.nombre AND p1.id > p2.id
      AND NOT EXISTS (SELECT 1 FROM detalle_pedido dp WHERE dp.producto_id = p1.id);

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_producto_nombre'
    ) THEN
        ALTER TABLE producto ADD CONSTRAINT uq_producto_nombre UNIQUE (nombre);
    END IF;
END $$;

-- 2.3. TABLAS DE EVENTOS AUDITABLES Y COLA DE IMPRESIÓN
CREATE TABLE IF NOT EXISTS evento_pedido (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    estado_anterior VARCHAR(20),
    estado_nuevo VARCHAR(20) NOT NULL,
    usuario_id INT REFERENCES usuario(id) ON DELETE SET NULL,
    motivo VARCHAR(255),
    fecha TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS impresion_cola (
    id SERIAL PRIMARY KEY,
    pedido_id INT REFERENCES pedido(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('COMANDA', 'PRECUENTA')),
    estacion VARCHAR(30),
    payload TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('PENDIENTE', 'IMPRESO', 'FALLIDO')) DEFAULT 'PENDIENTE',
    intentos INT NOT NULL DEFAULT 0,
    error TEXT,
    fecha_creacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_impresion TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS token_revocado (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    fecha_revocacion TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. ÍNDICES ESTRATÉGICOS PARA RENDIMIENTO Y CONSULTAS DE COBRO / REPORTES
CREATE INDEX IF NOT EXISTS idx_fk_pago_pedido ON pago(pedido_id);
CREATE INDEX IF NOT EXISTS idx_fk_pago_mesa ON pago(mesa_id);
CREATE INDEX IF NOT EXISTS idx_fk_pago_sesion_caja ON pago(sesion_caja_id);
CREATE INDEX IF NOT EXISTS idx_fk_pago_mozo ON pago(mozo_id);
CREATE INDEX IF NOT EXISTS idx_pago_metodo_fecha ON pago(metodo, fecha_pago);
CREATE INDEX IF NOT EXISTS idx_sesion_caja_estado ON sesion_caja(estado);
CREATE INDEX IF NOT EXISTS idx_sesion_caja_cajero ON sesion_caja(cajero_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sesion_caja_unica_abierta ON sesion_caja (estado) WHERE estado = 'ABIERTA';
CREATE INDEX IF NOT EXISTS idx_pedido_client_request_id ON pedido(client_request_id);
CREATE INDEX IF NOT EXISTS idx_evento_pedido ON evento_pedido(pedido_id, fecha);
CREATE INDEX IF NOT EXISTS idx_impresion_pendiente ON impresion_cola(estado, fecha_creacion);

COMMIT;
