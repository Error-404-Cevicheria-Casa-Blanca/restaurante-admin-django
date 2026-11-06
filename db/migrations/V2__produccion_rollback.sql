-- =============================================================================
-- ROLLBACK DE PRODUCCIÓN V2: REVERSIÓN DE TABLAS PAGO Y SESION_CAJA
-- Tarea: PRB-51 [P-03]
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS pago CASCADE;
DROP TABLE IF EXISTS sesion_caja CASCADE;

COMMIT;
