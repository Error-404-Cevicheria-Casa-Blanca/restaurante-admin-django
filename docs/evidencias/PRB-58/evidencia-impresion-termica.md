# Evidencia PRB-58: Impresión Térmica ESC/POS de 80 mm con Cola y Reintentos

**Fecha de Ejecución:** 2026-11-08  
**Rama Git:** `feature/PRB-58-impresion-termica`  
**Base:** `feature/PRB-57-kds-cocina`  
**Referencia:** Jira `PRB-58` | Epic `[P-11]` | `PLAN-PRODUCCION-POS.md` §5.2, §8.4 | ADR-02

---

## 1. Resumen Ejecutivo

Se implementó el **Spooler Centralizado de Impresión Térmica ESC/POS de 80 mm** en el backend Django para la emisión de comandas de cocina y pre-cuentas de salón de la **Cevichería Restaurante Casa Blanca**.

Siguiendo el principio de arquitectura **ADR-02** (*Impresión centralizada en el backend con cola ESC/POS*, independiente de la conectividad de las tablets) y la **Regla D7** (`db/schema.sql` como dueño del DDL de PostgreSQL), el sistema garantiza:
1. Encolado transaccional y persistente en la tabla `impresion_cola`.
2. Formatos oficiales de ticket térmico de 80 mm (48 columnas, Fuente A, autocutter).
3. Conectividad RAW TCP sobre puerto 9100 con soporte de reintentos automáticos (límite de 3 intentos), registro de fallos y modo simulador (DUMMY).
4. Monitor web en tiempo real con previsualización fidedigna del ticket y reintentos manuales.

---

## 2. Componentes Implementados

### 2.1 Modelo de Cola de Impresión (`ImpresionCola`)
Mapea la tabla compartida `impresion_cola` ([`catalogo/models.py`](file:///c:/Users/LOQ/Documents/restaurante-admin-django/catalogo/models.py)) bajo la **Regla D7** (`managed = False`):
- `pedido_id`: Referencia foránea opcional (con `ON DELETE CASCADE`) al pedido.
- `tipo`: `'COMANDA'` o `'PRECUENTA'`.
- `estacion`: Estación de destino (`BARRA_FRIA`, `COCINA_CALIENTE`, `BEBIDAS`, `POSTRES`, `CAJA`).
- `payload`: Texto plano estructurado a 48 columnas y comandos ESC/POS.
- `estado`: `'PENDIENTE'`, `'IMPRESO'`, `'FALLIDO'`.
- `intentos`: Contador atómico de reintentos.
- `error`: Mensaje o excepción capturada ante cortes de red o timeout.
- `fecha_creacion`: Timestamp de encolado.
- `fecha_impresion`: Timestamp del despacho exitoso.

### 2.2 Formatos Térmicos Oficiales de 80 mm (48 Columnas)
Alineados con el hardware físico validado en PRB-50 (**Epson TM-T20III**):

#### Formato A: Comanda de Cocina / Barra
- Encabezado destacado con estación de trabajo.
- Número de comanda, mesa, mozo responsable, fecha y hora.
- Listado de platos filtrados por estación con cantidad destacada.
- Notas especiales de preparación (ej: `* NOTA: Sin culantro, extra ají limo`).
- Total consolidado de ítems y comando ESC/POS de avance con corte de papel (`GS V B 0`).

#### Formato B: Pre-cuenta de Mesa (Control Interno No Fiscal)
- Encabezado con identidad de la Cevichería Casa Blanca (RUC, dirección Jr. Dos de Mayo 456, teléfono).
- Leyenda destacada: `PRE-CUENTA DE CONSUMO (CONTROL INTERNO - NO FISCAL)`.
- Metadatos: Pedido #, Mesa, Mozo, Fecha y Hora.
- Detalle columnar formateado a 48 cols: `CANT(4)` + `DESCRIPCION(24)` + `P.UNIT(9)` + `SUBTOTAL(11)`.
- Discriminación contable informativa: Op. Gravada (Base), IGV (18% incluido según D13), y Total a Pagar en `S/`.
- Pie de ticket: `DOCUMENTO NO VÁLIDO COMO COMPROBANTE FISCAL` y mensaje de agradecimiento.

### 2.3 Spooler y Manejo de Reintentos (`catalogo/impresion_service.py`)
- **Modos de Operación:**
  - `NETWORK`: Conexión TCP socket directa hacia `PRINTER_HOST` (`192.168.1.200:9100`) con timeout configurable (3s).
  - `DUMMY`: Almacenamiento en buffer de memoria para entornos de desarrollo y pruebas automatizadas sin hardware físico conectado.
  - `FAIL_SIMULATED`: Simulación de fallas de red para verificación de políticas de resiliencia.
- **Transición Atómica y Límite de Reintentos:**
  - Despacho protegido con `select_for_update()`.
  - Si la conexión falla, `intentos += 1` y se captura el `error`.
  - Si `intentos >= 3`, el trabajo transiciona a estado `FALLIDO`.
  - Acción `reintentar_trabajo`: reinicia contadores a `0` y relanza el despacho.

### 2.4 Monitor Web y Panel Operativo
- **Ruta Web:** `/impresion/` (protegida con `@staff_required`).
- **Métricas en Cabecera:** Contadores en vivo de pendientes, impresos hoy y fallidos.
- **Filtros Dinámicos:** Por estado (`Todos`, `Pendientes`, `Impresos`, `Fallidos`) y por tipo (`Comandas`, `Pre-cuentas`).
- **Visor de Ticket 80 mm:** Despliegue interactivo de previsualización monoespaciada imitando el papel térmico real.
- **Acciones Rápidas:**
  - Despachar toda la cola pendiente con un solo clic (`/impresion/despachar/`).
  - Reintentar trabajo individual (`/impresion/<id>/reintentar/`).
  - Reimprimir pedido directo (`/impresion/pedidos/<id>/imprimir/`).
  - Endpoint de sincronización JSON (`/impresion/api/cola/`).
- **Django Admin:** Integración completa en [`catalogo/admin.py`](file:///c:/Users/LOQ/Documents/restaurante-admin-django/catalogo/admin.py) con `ImpresionColaAdmin` y acción masiva de reintento.

---

## 3. Pruebas Automatizadas y Cobertura

### 3.1 Suite de Tests Unitarios e Integración (`ImpresionTermicaTests`)
Se añadieron 11 casos de prueba en `catalogo/tests.py`:
1. `test_formateo_comanda_48_columnas`: Valida que cada línea no exceda 48 columnas, estación y notas.
2. `test_formateo_precuenta_48_columnas_e_igv`: Valida desglose contable a 48 columnas y aviso no fiscal.
3. `test_generacion_secuencias_escpos_bytes`: Verifica comandos binarios ESC/POS (reset `\x1b@` y corte `\x1dVB\x00`).
4. `test_encolado_y_despacho_modo_dummy`: Comprueba persistencia en `impresion_cola` y despacho a buffer en modo DUMMY.
5. `test_manejo_errores_y_limite_reintentos`: Verifica que los intentos suban (1, 2, 3) y al 3er fallo pase a `FALLIDO`.
6. `test_reintentar_trabajo_fallido`: Valida reseteo de trabajo fallido y despacho exitoso.
7. `test_despacho_cola_pendientes_fifo`: Valida procesamiento en lote de órdenes pendientes en cola.
8. `test_reimprimir_pedido_comanda_y_precuenta`: Verifica generación de nuevas impresiones a partir de un pedido existente.
9. `test_vistas_monitor_impresion_seguridad_staff`: Valida protección staff y renderizado del monitor térmico.
10. `test_acciones_reintentar_y_despachar_endpoints`: Prueba respuestas HTML con redirección y AJAX JSON.
11. `test_impresion_api_cola_json`: Valida el endpoint JSON para polling del monitor.

### 3.2 Resultado de Ejecución de Tests
```
Ran 68 tests in 43.809s
OK
System check identified no issues (0 silenced).
```

### 3.3 Reporte de Cobertura de Código (`coverage report`)
```
Name                                Stmts   Miss  Cover
-------------------------------------------------------
catalogo\admin.py                      83      9    89%
catalogo\impresion_service.py         206     27    87%
catalogo\kds_service.py                95     13    86%
catalogo\models.py                    361     22    94%
catalogo\tests.py                     978     12    99%
catalogo\urls.py                        4      0   100%
catalogo\views.py                     927    277    70%
-------------------------------------------------------
TOTAL                                3290    479    85%
```
*Cobertura global alcanzada:* **85%** (supera el estándar exigido de ≥ 83%).

---

## 4. Verificación en Vivo contra PostgreSQL 18 (`casablanca`)

Se ejecutó verificación transaccional completa directamente contra la base de datos PostgreSQL local:
- Conexión: `localhost:5432 / casablanca`
- Creación de comanda de prueba para mesa real con mozo asignado.
- Encolado y despacho de Comanda en 80 mm (`estado=IMPRESO`).
- Encolado y despacho de Pre-cuenta en 80 mm (`estado=IMPRESO`).
- Simulación de fallo de conexión y reintento exitoso (`estado=IMPRESO`).
- Limpieza automática de registros sin dejar residuos.

Salida del script de verificación:
```
=== Test en vivo sobre PostgreSQL casablanca (PRB-58) ===
Pedido de prueba creado ID: 1123
Comanda encolada ID: 2 Estado: IMPRESO Intentos: 1
Pre-cuenta encolada ID: 3 Estado: IMPRESO Intentos: 1
Trabajo con fallo simulado: 4 Estado: PENDIENTE Intentos: 1
Trabajo tras reintento: 4 Estado: IMPRESO Intentos: 1
Limpieza completada en PostgreSQL casablanca!
=== Fin de verificacion PostgreSQL: EXITO TOTAL ===
```

---

## 5. Control de Calidad y Formato

- `flake8`: 0 errores, 0 warnings.
- `black --check`: 100% formateado según PEP 8.
- `makemigrations --check --dry-run`: No hay cambios pendientes sin migrar.
