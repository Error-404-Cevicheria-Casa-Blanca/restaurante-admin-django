# Evidencia Técnica · PRB-60 y PRB-61

## 1. PRB-60 · [P-14] Cierre de caja y arqueo por turno

### Reglas verificadas
- **Turno único activo (`estado = 'ABIERTA'`)**: Validación transaccional con `select_for_update()` + índice único parcial `uq_sesion_caja_unica_abierta` en PostgreSQL y SQLite.
- **Cálculo en vivo del turno**:
  - `monto_esperado = monto_inicial + monto_ventas_efectivo`.
  - Desglose automático de cobros vinculados al turno (`EFECTIVO`, `YAPE`, `PLIN`, `TARJETA`) y propinas.
  - Compatibilidad con pedidos en salón (`mesa_id`) y pedidos **Para llevar** (`mesa_id IS NULL`).
- **Arqueo y Cierre Z**:
  - **Cierre cuadrado (`diferencia = 0.00`)**: Fondo inicial `S/ 100.00` + ventas en efectivo `S/ 80.00` = `S/ 180.00` esperado vs. `S/ 180.00` contado -> `diferencia = S/ 0.00` (`ESTADO = CERRADA`).
  - **Prueba de descuadre con diferencia explicada**:
    - Intento de cierre con faltante (`S/ 142.50` contado frente a `S/ 150.00` esperado) **sin observación** -> rechazado por validación de negocio.
    - Cierre con justificación (`"Faltante por error de vuelto en mesa 1"`) -> registrado con `diferencia = -S/ 7.50`.
    - Cierre con sobrante justificado (`"Sobrante por propina en efectivo dejada en caja"`) -> registrado con `diferencia = +S/ 5.00`.

---

## 2. PRB-61 · [P-15] Reportes básicos de ventas y medios de pago

### Alcance verificado
- **Ventas totales del día (`ventas_dia`)** y filtro por fecha operativa (`?fecha=YYYY-MM-DD`).
- **Pedidos cobrados únicos (`pedidos_cobrados`)** sin duplicar comandas con pago dividido (`COUNT(DISTINCT pedido_id)`).
- **Ticket promedio exacto (`ticket_promedio`)**: `S/ 240.00 / 3 pedidos = S/ 80.00`.
- **Desglose por medio de pago**: `EFECTIVO` (`S/ 40.00`), `YAPE` (`S/ 35.00`), `PLIN` (`S/ 60.00`), `TARJETA` (`S/ 105.00`) y propinas (`S/ 10.00`).
- **Conciliación directa con sesiones de caja**: Tabla comparativa en `/reportes/` contrastando el total del día frente a los turnos abiertos/cerrados de la fecha.
- *Nota de alcance*: El ranking de platos y la exportación CSV se mantienen fuera de esta entrega según especificación de `PRB-61`.

---

## 3. Resultados de Calidad y Base de Datos Real (PostgreSQL 18 `casablanca`)

```text
[PG OK] Sesion abierta ID=2, cajero_id=5, inicial=120.00
[PG OK] Bloqueo de doble apertura verificado en PostgreSQL
[PG OK] Reporte ventas_dia=150.00, pedidos=2, ticket_promedio=75.00
[PG OK] Cierre Z completado: esperado=170.00, real=170.00, dif=0.00
[PG OK] Rollback limpio ejecutado: BD casablanca intacta.

pytest -> 33 passed in 38.64s
coverage -> 82% (catalogo/*)
flake8 -> 0 errores
black --check -> 0 archivos pendientes
```
