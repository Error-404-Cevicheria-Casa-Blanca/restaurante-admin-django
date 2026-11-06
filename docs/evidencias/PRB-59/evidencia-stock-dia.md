# Evidencia Técnica · PRB-59

## PRB-59 · [P-13] Inventario reducido: stock del día por producto, descuento y reversión (sin recetas ni merma)

### 1. Cumplimiento de Alcance y Regla D7 (`docs/db/DDL-OWNERSHIP.md`)
- **Alcance reducido estricto (`PLAN-PRODUCCION-POS.md` §5.1, §8.5, §8.10c)**:
  - Control directo de cupo diario por plato terminado (`producto.stock_disponible` y `producto.stock_minimo`).
  - Sin tablas ni lógica de recetas, insumos crudos ni merma.
  - `stock_disponible IS NULL` conserva el modo libre/ilimitado tradicional.
- **Propiedad del DDL (Regla D7)**:
  - `db/schema.sql` actualizado con columnas `stock_disponible`, `stock_minimo` y tabla auditable `movimiento_stock`.
  - Migraciones SQL versionadas e idempotentes en `db/migrations/V3__stock_dia.sql` y `db/migrations/V3__stock_dia_rollback.sql`.
  - Modelos `DetallePedido` y `MovimientoStock` declarados con `managed = False` en `catalogo/models.py` (`0006_detallepedido_movimientostock.py`).
  - Compatibilidad 100% preservada con `ddl-auto: validate` del backend Spring Boot.

---

### 2. Reglas Transaccionales Verificadas
- **Carga diaria individual y masiva (`/stock-dia/`)**:
  - Permite definir cupo finito (`>= 0`) o ilimitado (`NULL`) y umbral de alerta (`stock_minimo`), registrando movimiento `CARGA_DIARIA`.
- **Descuento atómico por comanda (`descontar_stock_pedido`)**:
  - Bloqueo pesimista por fila (`select_for_update()`) ordenado por `producto_id` para evitar condiciones de carrera y *deadlocks*.
  - Idempotencia garantizada por `pedido_id`: reintentos sobre el mismo pedido no duplican descuentos.
  - Si un plato carece de cupo suficiente, lanza `StockInsuficienteError` (`codigo = "STOCK_INSUFICIENTE"`) y revierte atómicamente toda la operación.
  - Al llegar `stock_disponible` a `0`, conmuta automáticamente `disponible = False`, bloqueando de inmediato nuevos pedidos en Android y Java POS.
- **Reversión atómica e idempotente (`revertir_stock_pedido` y `revertir_stock_item`)**:
  - Anulación total de pedido o eliminación parcial de ítem restaura exactamente el saldo neto consumido (`SALIDA_VENTA - REVERSION`).
  - Cuando un plato agotado (`0`) recupera porciones (`> 0`), reactiva automáticamente `disponible = True`.
  - Guard en `toggle_disponibilidad_plato`: impide activar manualmente un plato cuyo `stock_disponible == 0` sin recargar antes su cupo.
- **Conciliación automática con comandas POS (`sincronizar_stock_con_pedidos`)**:
  - Sincroniza de forma idempotente consumos y anulaciones registradas desde Spring Boot posteriores a la última `CARGA_DIARIA` de cada plato, normalizando marcas temporales entre `TIMESTAMP` y `TIMESTAMPTZ`.

---

### 3. Resultados de Calidad y Base de Datos Real (PostgreSQL 18 `casablanca`)

```text
[PG OK] V3__stock_dia.sql aplicado de forma idempotente en PostgreSQL 18 (casablanca)
[PG OK] Carga diaria fijada en plato ID=1: stock=3, min=2
[PG OK] Descuento atomico a 0: disponible=False (bloqueo automatico agotado)
[PG OK] Bloqueo STOCK_INSUFICIENTE verificado en PostgreSQL: STOCK_INSUFICIENTE
[PG OK] Reversion parcial + total idempotente verificada: stock=3, disponible=True
[PG OK] Sincronizacion automatica con comandas Java verificada: stock=3
[PG OK] Rollback limpio ejecutado: BD casablanca intacta.

manage.py test -> 45 passed (0 fallos)
makemigrations --check --dry-run -> No changes detected
coverage -> 83% (catalogo/*)
flake8 -> 0 errores
black --check -> 0 archivos pendientes
```
