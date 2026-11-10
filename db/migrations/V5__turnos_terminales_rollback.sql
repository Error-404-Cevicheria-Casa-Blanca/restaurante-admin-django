-- =============================================================================
-- ROLLBACK MIGRACIÓN V5: TURNOS DE SALÓN, TERMINALES POS Y SESIÓN DE MOZO
-- Tarea: PRB-84
-- =============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_sesion_mozo_activas;
DROP INDEX IF EXISTS idx_sesion_mozo_turno_inicio;
DROP INDEX IF EXISTS idx_fk_sesion_mozo_turno;
DROP INDEX IF EXISTS idx_fk_sesion_mozo_terminal;
DROP INDEX IF EXISTS idx_fk_sesion_mozo_usuario;

DROP TABLE IF EXISTS sesion_mozo;
DROP TABLE IF EXISTS terminal;
DROP TABLE IF EXISTS turno;

COMMIT;
