# Turnos de Salón, Terminales POS y Sesiones de Mozo (`PRB-84`)

**Fecha:** 2026-11-09  
**Referencia:** Jira `PRB-84` (Desbloquea `PRB-85` en Backend Java y `PRB-91` en App Android)  
**Regla de Arquitectura:** **Regla D7** (`db/schema.sql` como dueño exclusivo del DDL en PostgreSQL; modelos en Django con `managed = False`).

---

## 1. Propósito

Soportar la trazabilidad operativa y el Perfil del Mesero en la aplicación móvil Android, registrando:
1. Los **Turnos de Salón** oficiales del restaurante (`turno`).
2. Las **Terminales Físicas / Tablets** desplegadas en salón y terraza (`terminal`).
3. La **Auditoría de Sesiones de Mozo** (`sesion_mozo`), vinculando qué usuario utilizó qué terminal y en qué turno.

---

## 2. Esquema DDL (`db/schema.sql` y `db/migrations/V5__turnos_terminales.sql`)

```sql
-- 1. Turnos operativos de atención en salón
CREATE TABLE turno (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. Tablets / terminales físicas registradas en el local
CREATE TABLE terminal (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. Auditoría de sesión de mozo por tablet y turno
CREATE TABLE sesion_mozo (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    terminal_id INT NOT NULL REFERENCES terminal(id) ON DELETE RESTRICT,
    turno_id INT NOT NULL REFERENCES turno(id) ON DELETE RESTRICT,
    inicio TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fin TIMESTAMP WITH TIME ZONE
);

-- Índices estratégicos para Foreign Keys y consultas por turno / fecha
CREATE INDEX idx_fk_sesion_mozo_usuario ON sesion_mozo(usuario_id);
CREATE INDEX idx_fk_sesion_mozo_terminal ON sesion_mozo(terminal_id);
CREATE INDEX idx_fk_sesion_mozo_turno ON sesion_mozo(turno_id);
CREATE INDEX idx_sesion_mozo_turno_inicio ON sesion_mozo(turno_id, inicio);
CREATE INDEX idx_sesion_mozo_activas ON sesion_mozo(usuario_id, fin);
```

---

## 3. Valores Sembrados Oficiales (Seeds Idempotentes)

### 3.1 Tabla `turno`

| `nombre` | `hora_inicio` | `hora_fin` | `activo` |
| :--- | :---: | :---: | :---: |
| `Mañana` | `08:00:00` | `16:00:00` | `TRUE` |
| `Tarde` | `16:00:00` | `23:30:00` | `TRUE` |

### 3.2 Tabla `terminal`

| `codigo` | `nombre` | `activo` |
| :--- | :--- | :---: |
| `TERM-01` | `Tablet Salón Principal` | `TRUE` |
| `TERM-02` | `Tablet Segundo Piso / Terraza` | `TRUE` |

---

## 4. Aplicación y Rollback en PostgreSQL

- **Aplicar migración:**
  ```bash
  psql -U postgres -d casablanca -f db/migrations/V5__turnos_terminales.sql
  ```
- **Revertir migración (Rollback):**
  ```bash
  psql -U postgres -d casablanca -f db/migrations/V5__turnos_terminales_rollback.sql
  ```
