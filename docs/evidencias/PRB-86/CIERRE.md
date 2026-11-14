# CIERRE — PRB-86: Columna `estado_item` en `detalle_pedido` y coherencia KDS/Java

**Fecha de verificación:** 2026-11-13  
**Rama Git:** `feature/PRB-84-turnos-terminales` (pendiente merge hacia `develop`)  
**Tareas relacionadas:** `PRB-86`, `PRB-57` (KDS Cocina), `PRB-87` (`EstadoItem.java` en Java)

---

## 1. Coherencia de estados entre Django, PostgreSQL, Java y Kotlin ("Una sola verdad")

Se adoptó el conjunto canónico de `CONTRATO-API-V2.md` §2.3.1 y `EstadoItem.java` (`PRB-87`) para `detalle_pedido.estado_item`:

$$\text{PENDIENTE} \longrightarrow \text{EN\_PREPARACION} \longrightarrow \text{LISTO} \longrightarrow \text{SERVIDO}$$

- **DDL (`db/schema.sql` y `db/migrations/V4__kds_estado_item.sql`):**
  - Columna: `estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'`
  - Constraint: `CHECK (estado_item IN ('PENDIENTE', 'EN_PREPARACION', 'LISTO', 'SERVIDO'))`
  - Índice: `idx_detalle_estado_estacion ON detalle_pedido(estado_item, estacion)`
- **Backend / KDS Django (`catalogo/models.py`, `catalogo/kds_service.py`, `catalogo/templates/catalogo/kds.html`):**
  - `DetallePedido.ESTADOS_ITEM_CHOICES` restringido a los 4 estados canónicos (`PENDIENTE`, `EN_PREPARACION`, `LISTO`, `SERVIDO`).
  - Django dejó de escribir `COCINANDO` y `ANULADO` en `detalle_pedido.estado_item` (evitando incompatibilidad con `@Enumerated(EnumType.STRING)` en `EstadoItem.java` de Spring Boot).
  - Cuando una comanda completa avanza en KDS a `Pedido.ESTADO_COCINANDO`, `MAPA_PEDIDO_A_ESTADO_ITEM` traduce el estado de sus ítems a `DetallePedido.ESTADO_ITEM_EN_PREPARACION`; cuando una comanda se anula (`Pedido.ESTADO_ANULADO`), solo cambia `pedido.estado` sin escribir valores fuera del enum en `detalle_pedido.estado_item`.

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
| Suite completa Django (`manage.py test`) | [`01-tests.txt`](01-tests.txt) | 78/78 pruebas pasando tras alineación `EN_PREPARACION` y pruebas de coherencia DDL/V4 |
| Migración V4 UP en PostgreSQL 18 | [`02-migracion-up.txt`](02-migracion-up.txt) | Ejecutada en BD de prueba aislada `casablanca_restore_test` (partiendo de esquema pre-V4); columnas, índice y `CHECK` verificados con `\d detalle_pedido` |
| Migración V4 DOWN (rollback) en PostgreSQL 18 | [`03-migracion-down.txt`](03-migracion-down.txt) | Ejecutada en `casablanca_restore_test`; remoción limpia de índice, constraint y las 3 columnas verificada con `\d detalle_pedido` |
| Reproducibilidad de ejecución | [`README.md`](../../../README.md) y [`scripts/test.ps1`](../../../scripts/test.ps1) | Soluciona `KeyError: 'DJANGO_SECRET_KEY'` al correr `manage.py test` documentando la variable y añadiendo launcher reutilizable |
