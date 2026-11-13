-- =============================================================================
-- MIGRACIÓN DE PRODUCCIÓN V5: TURNOS DE SALÓN, TERMINALES POS Y SESIÓN DE MOZO
-- Tarea: PRB-84 (Base de datos: modelos Turno, Terminal y Asignación sesion_mozo)
-- Base de datos: PostgreSQL 15+ (casablanca)
-- Fecha: 2026-11-09
-- Autor: Jerardo Cutipa (Owner de DDL según Regla D7)
-- =============================================================================

BEGIN;

-- 1. TABLA: turno (Turnos operativos de atención en salón)
CREATE TABLE IF NOT EXISTS turno (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. TABLA: terminal (Tablets / terminales físicas registradas en el local)
CREATE TABLE IF NOT EXISTS terminal (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. TABLA: sesion_mozo (Auditoría de qué mozo usó qué tablet y en qué turno)
CREATE TABLE IF NOT EXISTS sesion_mozo (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    terminal_id INT NOT NULL REFERENCES terminal(id) ON DELETE RESTRICT,
    turno_id INT NOT NULL REFERENCES turno(id) ON DELETE RESTRICT,
    inicio TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fin TIMESTAMP WITH TIME ZONE
);

-- 4. ÍNDICES ESTRATÉGICOS PARA FOREIGN KEYS Y CONSULTAS POR TURNO / FECHA
CREATE INDEX IF NOT EXISTS idx_fk_sesion_mozo_usuario ON sesion_mozo(usuario_id);
CREATE INDEX IF NOT EXISTS idx_fk_sesion_mozo_terminal ON sesion_mozo(terminal_id);
CREATE INDEX IF NOT EXISTS idx_fk_sesion_mozo_turno ON sesion_mozo(turno_id);
CREATE INDEX IF NOT EXISTS idx_sesion_mozo_turno_inicio ON sesion_mozo(turno_id, inicio);
CREATE INDEX IF NOT EXISTS idx_sesion_mozo_activas ON sesion_mozo(usuario_id, fin);

-- 5. SEEDS OFICIALES IDEMPOTENTES: 2 TURNOS Y 2 TERMINALES (TABLETS)
INSERT INTO turno (nombre, hora_inicio, hora_fin, activo) VALUES
    ('Mañana', '08:00:00', '16:00:00', TRUE),
    ('Tarde', '16:00:00', '23:30:00', TRUE)
ON CONFLICT (nombre) DO UPDATE SET
    hora_inicio = EXCLUDED.hora_inicio,
    hora_fin = EXCLUDED.hora_fin,
    activo = EXCLUDED.activo;

INSERT INTO terminal (codigo, nombre, activo) VALUES
    ('TERM-01', 'Tablet Salón Principal', TRUE),
    ('TERM-02', 'Tablet Segundo Piso / Terraza', TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    activo = EXCLUDED.activo;

COMMIT;
