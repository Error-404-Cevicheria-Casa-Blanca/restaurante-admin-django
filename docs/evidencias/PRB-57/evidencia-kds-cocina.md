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
Se añadieron 8 casos de prueba exhaustivos en `catalogo/tests.py`:
1. `test_derivacion_estaciones_segun_categoria_y_nombre`: Valida la asignación precisa de estación para ceviches, jaleas, chichas y postres.
2. `test_semaforo_sla_tiempo_transcurrido`: Verifica los umbrales de minutos y etiquetas de semáforo (Normal < 10m, Alerta 10–20m, Crítico > 20m).
3. `test_transiciones_estados_comanda_y_auditoria_evento_pedido`: Valida la secuencia `PENDIENTE -> COCINANDO -> LISTO -> SERVIDO` y rechaza transiciones no permitidas (`ValidationError`).
4. `test_filtrado_por_estaciones_y_estados_en_kds`: Comprueba el aislamiento de comandas e ítems por estación de trabajo.
5. `test_kpis_kds_y_promedio_espera`: Valida el cálculo de métricas en cabecera del KDS.
6. `test_kds_seguridad_staff_y_render_pantalla`: Comprueba bloqueo de acceso a mozos no autorizados / anónimos y renderizado correcto para cocinero.
7. `test_kds_avanzar_pedido_html_y_ajax`: Verifica interoperabilidad tanto para POST HTML tradicional con redirección como para llamadas AJAX JSON (`XMLHttpRequest`).
8. `test_kds_api_comandas_polling_json`: Valida la respuesta del endpoint de sincronización JSON periódica.

### 3.2 Resultado de Ejecución de Tests
```
Ran 57 tests in 32.207s
OK
System check identified no issues (0 silenced).
```

### 3.3 Reporte de Cobertura de Código (`coverage report`)
```
Name                                Stmts   Miss  Cover
-------------------------------------------------------
catalogo\admin.py                      67      2    97%
catalogo\kds_service.py                95     13    86%
catalogo\models.py                    320     15    95%
catalogo\tests.py                     829     11    99%
catalogo\urls.py                        4      0   100%
catalogo\views.py                     856    247    71%
-------------------------------------------------------
TOTAL                                2803    407    85%
```
*Cobertura global alcanzada:* **85%** (supera el estándar exigido de ≥ 83%).

---

## 4. Verificación en Vivo contra PostgreSQL 18 (`casablanca`)

Se ejecutó verificación transaccional completa directamente contra la base de datos PostgreSQL local:
- Conexión: `localhost:5432 / casablanca`
- Creación de comanda de prueba para mesa real con mozo asignado.
- Avance PENDIENTE ➔ COCINANDO ➔ LISTO ➔ SERVIDO por cocinero y mozo.
- Verificación de inserción de 3 eventos inmutables en `evento_pedido`.
- Salida del script de verificación:
```
=== Test en vivo sobre PostgreSQL casablanca ===
KPIs antes: {'pendientes': 0, 'cocinando': 0, 'listos': 0, 'total_activos': 0, 'alertas_sla': 0, 'promedio_espera_minutos': 0.0, 'total_hoy': 0}
Pedido creado ID: 1121 en estado: PENDIENTE
Comandas activas en KDS hoy: 1
Avanzado a: COCINANDO
Avanzado a: LISTO
Avanzado a: SERVIDO
Total eventos auditados para pedido: 3
  Evento 1: PENDIENTE -> COCINANDO | usuario=4 | motivo=Cocinero acepto comanda
  Evento 2: COCINANDO -> LISTO | usuario=4 | motivo=Plato emplatado
  Evento 3: LISTO -> SERVIDO | usuario=2 | motivo=Mozo retiro de barra
Limpieza completada OK!
=== Fin de verificacion PostgreSQL casablanca: EXITO TOTAL ===
```

---

## 5. Control de Calidad y Formato

- `flake8`: 0 errores, 0 warnings.
- `black --check`: 100% formateado según PEP 8.
- `makemigrations --check --dry-run`: No hay cambios pendientes sin migrar.
