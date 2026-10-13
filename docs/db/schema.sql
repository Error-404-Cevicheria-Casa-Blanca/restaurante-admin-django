-- Schema inicial para PostgreSQL con restricciones de integridad y catálogos

CREATE TABLE rol (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE usuario (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol_id INT NOT NULL REFERENCES rol(id) ON DELETE RESTRICT
);

CREATE TABLE mesa (
    id SERIAL PRIMARY KEY,
    numero INT NOT NULL UNIQUE CHECK (numero > 0),
    capacidad INT NOT NULL CHECK (capacidad > 0),
    ubicacion VARCHAR(100) NOT NULL,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('LIBRE', 'OCUPADA', 'ATENDIDA', 'CUENTA_SOLICITADA')) DEFAULT 'LIBRE'
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
    categoria_id INT NOT NULL REFERENCES categoria(id) ON DELETE RESTRICT
);

CREATE TABLE pedido (
    id SERIAL PRIMARY KEY,
    mesa_id INT NOT NULL REFERENCES mesa(id) ON DELETE RESTRICT,
    mozo_id INT NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('Pendiente', 'Cocinando', 'Listo', 'Servido', 'Cobrado')) DEFAULT 'Pendiente',
    total NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE detalle_pedido (
    id SERIAL PRIMARY KEY,
    pedido_id INT NOT NULL REFERENCES pedido(id) ON DELETE CASCADE,
    producto_id INT NOT NULL REFERENCES producto(id) ON DELETE RESTRICT,
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