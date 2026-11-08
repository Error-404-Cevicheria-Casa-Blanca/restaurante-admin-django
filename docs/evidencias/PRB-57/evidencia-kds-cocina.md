# Evidencia PRB-57: KDS Web de Cocina con Estaciones de Preparación y SLA

**Fecha de Ejecución:** 2026-11-08  
**Rama Git:** `feature/PRB-57-kds-cocina`  
**Base:** `feature/PRB-52-datos-reales-produccion`  
**Referencia:** Jira `PRB-57` | Epic `[P-10]` | `PLAN-PRODUCCION-POS.md` §5.1, §8.4 | ADR-01

---

## 1. Resumen Ejecutivo

Se implementó el **Kitchen Display System (KDS) Web** en tiempo real para las pantallas de cocina y tabletas de barra marina de la **Cevichería Restaurante Casa Blanca**.

Siguiendo el principio de arquitectura **ADR-01** (*Web sobre Django* para KDS de cocina, minimizando costo de hardware y reutilizando autenticación unificada) y la **Regla D7** (`db/schema.sql` como dueño del DDL de PostgreSQL), el KDS opera de forma transaccional, con soporte multi-estación, semáforo SLA de preparación y auditoría inmutable en `evento_pedido`.

---

## 2. Componentes Implementados

### 2.1 Estaciones Canónicas de Preparación
Alineadas con la lógica del backend Spring Boot (`Estacion.java`) y el catálogo oficial:
- **`BARRA_FRIA`** (Cevichería): Ceviches, tiraditos, causas, choros a la chalaca, leche de tigre.
- **`COCINA_CALIENTE`**: Jaleas mixtas, arroces marinos, parihuelas, sudados y platos de fondo calientes.
- **`BEBIDAS`**: Chicha morada, limonada frozen y bebidas del bar.
- **`POSTRES`**: Suspiros limeños, picarones y postres artesanales.

### 2.2 Semáforo SLA de Preparación
Temporizador automático desde la emisión del pedido:
- 🟢 **`NORMAL` (< 10 min):** Borde y badge verde suave; preparación dentro de tiempo estándar.
- 🟡 **`ALERTA` (10 a 20 min):** Borde y badge ámbar; aviso preventivo para jefatura de cocina.
- 🔴 **`CRITICO` (> 20 min):** Borde y badge rojo con animación pulsante (`kds-pulse`); alerta de demora excesiva.

### 2.3 Máquina de Estados y Auditoría Inmutable
Transiciones operativas controladas mediante `select_for_update()` atómico:
$$\text{PENDIENTE} \longrightarrow \text{COCINANDO} \longrightarrow \text{LISTO} \longrightarrow \text{SERVIDO}$$

Cada avance genera automáticamente un registro inmutable en la tabla compartida `evento_pedido`:
- `pedido_id`: Identificador del pedido.
- `estado_anterior`: Estado origen.
- `estado_nuevo`: Estado destino.
- `fecha`: Timestamp con zona horaria.
- `usuario_id`: Personal que accionó la comanda (cocinero/mozo/cajero).
- `motivo`: Descripción o trazabilidad de la acción.

### 2.4 Interfaz de Usuario y Actualización en Vivo
- **Ruta Web:** `/cocina/` (requiere autenticación con `is_staff` / perfil operativo).
- **Filtros Dinámicos:** Por estación (`Todas`, `Barra Fría`, `Cocina Caliente`, `Bebidas`, `Postres`) y por estado (`Activas`, `Pendientes`, `En Cocina`, `Listas para Servir`, `Histórico del Turno`).
- **Resumen KPIs del Turno:** Contadores en tiempo real de comandas pendientes, en cocción, listas, alertas SLA y tiempo promedio de espera.
- **Polling Automático Liviano:** Endpoint JSON `/cocina/api/comandas/` cada 6 segundos sin parpadeo visual ni recarga de página completa.
- **Reloj en Vivo por Tarjeta:** Actualización progresiva segundo a segundo del tiempo transcurrido en cada tarjeta sin saturar el servidor.
- **Avance One-Click:** Botón de acción context-aware ("Iniciar Preparación" ➔ "Marcar Listo" ➔ "Despachar a Mesa") con feedback AJAX instantáneo.

---

## 3. Pruebas Automatizadas y Cobertura

### 3.1 Suite de Tests Unitarios e Integración (`KDSCocinaTests`)
Se añadieron 12 casos de prueba exhaustivos en `catalogo/tests.py`:
1. `test_derivacion_de_estaciones_de_cocina_y_items`: Valida la asignación precisa de estación para ceviches, jaleas, chichas y postres.
2. `test_cronometro_sla_y_semaforo_de_tiempos`: Verifica los umbrales de minutos y etiquetas de semáforo (Normal < 10m, Alerta 10–20m, Crítico > 20m).
3. `test_avanzar_estado_comanda_y_auditoria_evento_pedido`: Valida la secuencia `PENDIENTE -> COCINANDO -> LISTO -> SERVIDO` y rechaza transiciones no permitidas (`ValidationError`).
4. `test_filtrado_por_estaciones_y_estados_en_kds`: Comprueba el aislamiento de comandas e ítems por estación de trabajo.
5. `test_kpis_kds_y_promedio_espera`: Valida el cálculo de métricas en cabecera del KDS.
6. `test_kds_seguridad_staff_y_render_pantalla`: Comprueba bloqueo de acceso a mozos no autorizados / anónimos y renderizado correcto para cocinero.
7. `test_kds_avanzar_pedido_html_y_ajax`: Verifica interoperabilidad tanto para POST HTML tradicional con redirección como para llamadas AJAX JSON (`XMLHttpRequest`).
8. `test_kds_api_comandas_polling_json`: Valida la respuesta del endpoint de sincronización JSON periódica.
9. `test_avance_individual_por_item_y_recalculo_comanda` (PRB-86): Comprueba ciclo de vida por plato y que marcar listo un plato no marque listo la comanda hasta que todos estén listos.
10. `test_aislamiento_estaciones_no_avanza_otra_estacion`: Comprueba que marcar lista Barra Fría no marca Bebidas ni la comanda general.
11. `test_kds_avanzar_item_endpoint_html_y_ajax`: Verifica el nuevo endpoint POST `/cocina/items/<id>/avanzar/`.
12. `test_fk_usuario_id_seguro_postgres`: Comprueba que pasar IDs inexistentes o de `auth_user` no provoque `ForeignKeyViolation` en PostgreSQL.

### 3.2 Resultado de Ejecución de Tests
```
Ran 61 tests in 105.333s
OK
System check identified no issues (0 silenced).
```

### 3.3 Reporte de Cobertura de Código (`coverage report`)
```
Name                                                                   Stmts   Miss  Cover
------------------------------------------------------------------------------------------
catalogo\admin.py                                                         67      2    97%
catalogo\apps.py                                                           9      0   100%
catalogo\forms.py                                                        114     23    80%
catalogo\kds_service.py                                                  199     35    82%
catalogo\management\commands\seed_produccion.py                           15      2    87%
catalogo\models.py                                                       339     18    95%
catalogo\produccion_seeds.py                                             140     29    79%
catalogo\sqlite_bootstrap.py                                              60     21    65%
catalogo\stock_service.py                                                242     32    87%
catalogo\tests.py                                                        889     11    99%
catalogo\urls.py                                                           4      0   100%
catalogo\views.py                                                        903    262    71%
------------------------------------------------------------------------------------------
TOTAL                                                                   3033    447    85%
```
*Cobertura global alcanzada:* **85%** (supera el estándar exigido de ≥ 83%).
Salida cruda completa preservada en: `docs/evidencias/PRB-57/02-salida-terminal-tests.txt`.

---

## 4. Verificación en Vivo contra PostgreSQL 18.6 (`casablanca`)

Se ejecutó verificación transaccional completa directamente contra la base de datos PostgreSQL local (`localhost:5432 / casablanca`) mediante el script `scripts/verificar_prb57_postgres.py`:
- Columnas PRB-86 verificadas en `detalle_pedido`: `estado_item`, `estacion`, `anulado_motivo`, e índice `idx_detalle_estado_estacion`.
- Ciclo de vida por plato y aislamiento de estaciones comprobado: Barra Fría (`LISTO`) vs Bebidas (`PENDIENTE`), manteniendo la comanda general en `COCINANDO`.
- Inserción de 5 eventos inmutables en `evento_pedido` con Foreign Key válida hacia `usuario.id`.
- Verificación física de las 15 fotos PNG de platos reales en `catalogo/static/catalogo/img/platos/` (pesos entre 366 KB y 904 KB).
- Salida cruda completa disponible en: `docs/evidencias/PRB-57/01-salida-terminal-postgres.txt`.
- Acta de subsanación de auditoría: `docs/evidencias/PRB-57/CIERRE.md`.

---

## 5. Control de Calidad y Formato

- `flake8`: 0 errores, 0 warnings.
- `black --check`: 100% formateado según PEP 8.
- `makemigrations --check --dry-run`: No hay cambios pendientes sin migrar.
