-- Schema inicial para PostgreSQL con restricciones de integridad y catálogos

CREATE TABLE rol (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE usuario (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    clave_hash VARCHAR(255) NOT NULL,
    rol_id INT NOT NULL REFERENCES rol(id) ON DELETE RESTRICT
);

CREATE TABLE mesa (
    id SERIAL PRIMARY KEY,
    numero INT NOT NULL UNIQUE CHECK (numero > 0),
    capacidad INT NOT NULL CHECK (capacidad > 0),
    ubicacion VARCHAR(100) NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('LIBRE', 'OCUPADA', 'ATENDIDA', 'CUENTA_SOLICITADA')) DEFAULT 'LIBRE',
    mozo_id INT REFERENCES usuario(id) ON DELETE SET NULL,
    fecha_apertura TIMESTAMP,
    fecha_cierre TIMESTAMP
);

CREATE TABLE categoria (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE producto (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    precio NUMERIC(10,2) NOT NULL CHECK (precio > 0),
    disponible BOOLEAN NOT NULL DEFAULT TRUE,
    categoria_id INT NOT NULL REFERENCES categoria(id) ON DELETE RESTRICT,
    imagen_url VARCHAR(255)
);

CREATE TABLE pedido (
    id SERIAL PRIMARY KEY,
    mesa_id INT NOT NULL REFERENCES mesa(id) ON DELETE RESTRICT,
    mozo_id INT NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('PENDIENTE', 'COCINANDO', 'LISTO', 'SERVIDO', 'COBRADO')) DEFAULT 'PENDIENTE',
    total NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE detalle_pedido (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    producto_id INT NOT NULL REFERENCES producto(id) ON DELETE RESTRICT,
    precio_unitario NUMERIC(10,2) NOT NULL CHECK (precio_unitario > 0),
    cantidad INT NOT NULL CHECK (cantidad >= 1),
    notas VARCHAR(255),
    subtotal NUMERIC(10,2) NOT NULL CHECK (subtotal >= 0)
);

-- Índices estratégicos para rendimiento y Foreign Keys
CREATE INDEX idx_pedido_mesa_estado ON pedido(mesa_id, estado);
CREATE INDEX idx_fk_usuario_rol ON usuario(rol_id);
CREATE INDEX idx_fk_producto_categoria ON producto(categoria_id);
CREATE INDEX idx_fk_pedido_mozo ON pedido(mozo_id);
CREATE INDEX idx_fk_detalle_pedido ON detalle_pedido(pedido_id);
CREATE INDEX idx_fk_detalle_producto ON detalle_pedido(producto_id);
CREATE INDEX idx_fk_mesa_mozo ON mesa(mozo_id);

-- =============================================================================
-- TABLA: sesion_caja (Gestión de turnos de caja, arqueo Z y diferencias - PRB-60)
-- =============================================================================
CREATE TABLE sesion_caja (
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

-- =============================================================================
-- TABLA: pago (Registro transaccional de pagos multimoneda e idempotencia - PRB-51, PRB-55, PRB-56)
-- =============================================================================
CREATE TABLE pago (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL REFERENCES pedido(id) ON DELETE RESTRICT,
    mesa_id INT NOT NULL REFERENCES mesa(id) ON DELETE RESTRICT,
    mozo_id INT REFERENCES usuario(id) ON DELETE SET NULL,
    sesion_caja_id INT REFERENCES sesion_caja(id) ON DELETE SET NULL,
    metodo VARCHAR(20) NOT NULL CHECK (metodo IN ('EFECTIVO', 'YAPE', 'PLIN', 'TARJETA')),
    monto NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    propina NUMERIC(10,2) NOT NULL DEFAULT 0.00 CHECK (propina >= 0),
    referencia VARCHAR(100),
    client_request_id VARCHAR(64) NOT NULL UNIQUE,
    fecha_pago TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fk_pago_pedido ON pago(pedido_id);
CREATE INDEX idx_fk_pago_mesa ON pago(mesa_id);
CREATE INDEX idx_fk_pago_sesion_caja ON pago(sesion_caja_id);
CREATE INDEX idx_fk_pago_mozo ON pago(mozo_id);
CREATE INDEX idx_pago_metodo_fecha ON pago(metodo, fecha_pago);
CREATE INDEX idx_sesion_caja_estado ON sesion_caja(estado);
CREATE INDEX idx_sesion_caja_cajero ON sesion_caja(cajero_id);

