# CIERRE — PRB-86: Columna `estado_item` en `detalle_pedido` y coherencia KDS/Java

**Fecha de verificación:** 2026-11-14  
**Rama Git:** `fix/PRB-86-estado-item-y-evidencias` (hacia `develop`)  
**Tareas relacionadas:** `PRB-86`, `PRB-57` (KDS Cocina), `PRB-77` (Anulación de ítems), `PRB-87` (`EstadoItem.java` en Java)

---

## 1. Coherencia de estados entre Django, PostgreSQL, Java y Kotlin ("Una sola verdad")

De común acuerdo con Backend Java (`PR #12` en `restaurante-backend-java`, rama `feature/PRB-87-89-fix-estado-item-y-evidencias`, commit `1dc2782`) y App Android (`EstadoPlato.kt` en `restaurante-app-kotlin`), el conjunto canónico de `detalle_pedido.estado_item` es de **6 estados**:

`PENDIENTE`, `COCINANDO`, `EN_PREPARACION`, `LISTO`, `SERVIDO`, `ANULADO`

- **DDL ([`db/schema.sql`](../../../db/schema.sql) y [`db/migrations/V4__kds_estado_item.sql`](../../../db/migrations/V4__kds_estado_item.sql)):**
  - Columna: `estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'`
  - Constraint: `CHECK (estado_item IN ('PENDIENTE', 'COCINANDO', 'EN_PREPARACION', 'LISTO', 'SERVIDO', 'ANULADO'))`
  - Índice: `idx_detalle_estado_estacion ON detalle_pedido(estado_item, estacion)`
- **Backend / KDS Django ([`catalogo/models.py`](../../../catalogo/models.py), [`catalogo/kds_service.py`](../../../catalogo/kds_service.py)):**
  - `DetallePedido.ESTADOS_ITEM_CHOICES` incluye los 6 estados canónicos y soporta `COCINANDO`, `EN_PREPARACION` y `ANULADO` (registrando `anulado_motivo` para `PRB-77`).
  - Compatible con `@Enumerated(EnumType.STRING)` en `EstadoItem.java` (`PR #12` de Java) y `EstadoPlato.desdeApi()` en Kotlin.

---

## 2. Advertencia documentada del rollback de V4

El script [`db/migrations/V4__kds_estado_item_rollback.sql`](../../../db/migrations/V4__kds_estado_item_rollback.sql) revierte **todo el bloque V4** sobre `detalle_pedido`:

1. `idx_detalle_estado_estacion` (`PRB-57` / `PRB-86`)
2. `chk_detalle_pedido_estado_item` (`PRB-86`)
3. Columna `estado_item` (`PRB-86`)
4. Columna `estacion` (`PRB-57`)
5. Columna `anulado_motivo` (`PRB-77`)

> **Importante:** Al revertir `V4`, también se eliminan `estacion` (`PRB-57`) y `anulado_motivo` (`PRB-77`). Esto es intencional cuando se revierte la migración V4 completa, pero no debe ejecutarse si se requiere conservar `estacion` o `anulado_motivo` de forma aislada.

---

## 3. Evidencia cruda generada y reproducibilidad

| Evidencia | Archivo | Alcance verificado |
|---|---|---|
| Suite completa Django (`manage.py test`) | [`01-tests.txt`](01-tests.txt) | 78/78 pruebas pasando con `DJANGO_SECRET_KEY` y coherencia de los 6 estados |
| Migración V4 UP en PostgreSQL 18 | [`02-migracion-up.txt`](02-migracion-up.txt) | Ejecutada en BD de prueba aislada `casablanca_restore_test` (partiendo de esquema pre-V4); columnas, índice y `CHECK` de 6 estados verificados con `\d detalle_pedido` |
| Migración V4 DOWN (rollback) en PostgreSQL 18 | [`03-migracion-down.txt`](03-migracion-down.txt) | Ejecutada en `casablanca_restore_test`; remoción limpia de índice, constraint y las 3 columnas verificada con `\d detalle_pedido` |
| Trazabilidad Git | [`04-git.txt`](04-git.txt) | Salida cruda de `git log`, `git branch --show-current` y `git show --stat --oneline` del commit principal de `PRB-86` |
| Reproducibilidad de ejecución | [`README.md`](../../../README.md) y [`scripts/test.ps1`](../../../scripts/test.ps1) | Soluciona `KeyError: 'DJANGO_SECRET_KEY'` al correr `manage.py test` |
| Seguridad operativa sidebar | [`base.html`](../../../catalogo/templates/catalogo/base.html) | Restringe el enlace a `/admin/` exclusivamente a cuentas con `request.user.is_superuser` |
