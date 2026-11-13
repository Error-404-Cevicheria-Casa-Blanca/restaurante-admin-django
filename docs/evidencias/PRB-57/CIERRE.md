# Cierre de Correcciones de Auditoría - PRB-57 (PR #10)

**Fecha:** 2026-11-08  
**Rama:** `feature/PRB-57-kds-cocina`  
**PR GitHub:** [#10 - feature/PRB-57-kds-cocina](https://github.com/Error-404-Cevicheria-Casa-Blanca/restaurante-admin-django/pull/10)  
**Revisor:** David Rojas (`Error-404-Cevicheria-Casa-Blanca`)  

---

## 1. Resumen de Correcciones Aplicadas (Rondas 1 y 2)

Se abordaron y resolvieron el 100% de las observaciones técnicas y arquitectónicas identificadas por el verificador sobre el PR #10:

### Ronda 1 — Observaciones funcionales y de integración

| # | Observación de Auditoría | Estado | Solución Técnica Implementada |
|---|--------------------------|--------|--------------------------------|
| **1** | **Falta la columna `estado_item` (PRB-86)** | **CORREGIDO** | Agregadas las columnas `estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'`, `estacion VARCHAR(30) NOT NULL DEFAULT 'COCINA_CALIENTE'` y `anulado_motivo VARCHAR(255)` con índice `idx_detalle_estado_estacion` en `db/schema.sql`, `db/migrations/V4__kds_estado_item.sql`, `catalogo/sqlite_bootstrap.py` y en el modelo `DetallePedido` (`catalogo/models.py`). |
| **2** | **KDS avanza comanda completa, no el ítem** | **CORREGIDO** | Implementado avance individual por plato con `avanzar_estado_item()`, soporte de avance aislado por estación con `avanzar_estado_comanda(estacion=...)` y recálculo automático de estado de comanda (`recalcular_estado_pedido()`). Marcar 'Listo' en Barra Fría mantiene los platos de Bebidas en preparación y no marca la comanda entera como lista prematuramente. Nueva ruta `/cocina/items/<id>/avanzar/` e interfaz interactiva one-click por plato en `kds.html`. |
| **3** | **Fotos reales eran placeholders** | **CORREGIDO** | Se reemplazaron los 15 PNG de círculos concéntricos por fotografías gastronómicas reales en alta resolución (366 KB a 904 KB cada una, entropía de Shannon 7.99–8.00 bits/byte verificada vía cabecera IHDR) para todos los platos oficiales de la carta. |
| **4** | **PINs en claro en el código** | **CORREGIDO** | Eliminados todos los `pin_referencia` de `catalogo/produccion_seeds.py`, comentarios de PINs en claro de `db/seeds_produccion.sql` y textos en evidencias PRB-52. Toda la autenticación opera exclusivamente con hashes BCrypt de 60 caracteres. |
| **5** | **Riesgo de FK en PostgreSQL (`usuario_id`)** | **CORREGIDO** | Implementado `resolver_usuario_operativo_id(request.user)` en `views.py` para mapear el usuario autenticado (`auth_user`) con su registro correspondiente en `usuario`. Además, `_validar_fk_usuario_id()` verifica la existencia previa de la clave foránea antes de persistir en `evento_pedido`. |

### Ronda 2 — Observaciones de arquitectura, seguridad y DDL (D1, D2, D3)

| # | Observación de Auditoría | Estado | Solución Técnica Implementada |
|---|--------------------------|--------|--------------------------------|
| **D1** | **Credenciales expuestas en `verificar_prb57_postgres.py` e `iniciar_servidor.bat`** | **CORREGIDO** | Eliminadas por completo las credenciales hardcodeadas (`DJANGO_SECRET_KEY` y `DB_PASSWORD`). Ahora se exigen estrictamente desde variables de entorno, abortando con `sys.exit()` / `exit /b 1` si no están definidas. En `iniciar_servidor.bat` se reemplazó la ruta absoluta por `cd /d "%~dp0"` portable y se eliminó `set /p` para no exponer la clave en consola. Además, se limpió el historial de commits de la rama para no dejar secretos en commits previos. |
| **D2** | **Descuento de stock en KDS (`descontar_stock_pedido`)** | **CORREGIDO** | Corregidas las llamadas en `catalogo/kds_service.py` pasando `pedido_id=pedido.id` (entero estricto), `motivo=...`, `registrado_por=...` y `estricto=False`. Se eliminó `except Exception: pass` reemplazándolo por `logger.warning(...)`. En `catalogo/stock_service.py` se valida explícitamente `isinstance(pedido_id, int)` lanzando `TypeError` si se pasa un objeto inválido. Se añadió el test `test_kds_descuento_stock_automatico_sin_typeerror` cubriendo pedido multi-ítem (`ceviche` + `jalea`), verificación de `registrado_por` e idempotencia. |
| **D3** | **Migración DDL `V4__kds_estado_item.sql`, cumplimiento de Regla D7 y verificador sin DDL** | **CORREGIDO** | 1) Eliminada la migración de Django `0009_detallepedido_estado_item.py` para cumplir estrictamente la **Regla D7** (*ningún ORM ejecuta DDL sobre tablas del dominio*).<br>2) Alineado `db/migrations/V4__kds_estado_item.sql` con `db/schema.sql:71` (`estacion VARCHAR(30) NOT NULL DEFAULT 'COCINA_CALIENTE'`).<br>3) Eliminada la ejecución automática de DDL dentro de `scripts/verificar_prb57_postgres.py`; ahora el verificador comprueba el esquema exclusivamente en modo lectura (`information_schema.columns` y `pg_indexes`). |
| **D5** | **Sanitización de PINs reales en `catalogo/tests.py` y rotación de credenciales (`PRB-96`)** | **CORREGIDO** | 1) Eliminadas de `catalogo/tests.py` todas las comprobaciones con PINs reales de producción.<br>2) Añadido usuario fixture aislado (`mozo_fixture_test`) con su propio PIN de prueba para validar `check_pin_bcrypt()` sin exponer secretos de producción.<br>3) Rotados los 5 PINs de producción y regenerados sus hashes BCrypt cost 10 (`$2b$10$...`) en `catalogo/produccion_seeds.py` y `db/seeds_produccion.sql` (cero referencias a los PINs ni hashes anteriores en todo el repositorio). |

---

## 2. Resultados de Pruebas, Cobertura y Reproducibilidad

- **Pruebas Automatizadas:** **62/62 tests en verde** (`Ran 62 tests — OK`, `EXIT=0`).
  - Comando reproducible (con `DJANGO_DEBUG=1` o `DJANGO_SECRET_KEY`):
    ```powershell
    $env:DJANGO_SECRET_KEY="casablanca-test-secret-key-2026"
    .\venv\Scripts\python.exe manage.py test catalogo
    ```
  - Nuevos tests añadidos en `KDSCocinaTests`:
    - `test_avance_individual_por_item_y_recalculo_comanda`
    - `test_aislamiento_estaciones_no_avanza_otra_estacion`
    - `test_kds_avanzar_item_endpoint_html_y_ajax`
    - `test_fk_usuario_id_seguro_postgres`
    - `test_kds_descuento_stock_automatico_sin_typeerror`
- **Cobertura de Código:** **86%** global (supera el estándar exigido de ≥ 85%). Salida cruda completa de Django test runner y `coverage report` en `docs/evidencias/PRB-57/02-salida-terminal-tests.txt`.
- **Calidad de Código:** **0 errores de flake8** (`flake8 catalogo config db scripts` -> `EXIT=0`).
- **Migraciones Django:** `python manage.py makemigrations --check --dry-run` -> `No changes detected` (`EXIT=0`).
- **Verificación en Vivo contra PostgreSQL 18.6:** Ejecutada con `scripts/verificar_prb57_postgres.py` sobre `localhost:5432/casablanca` (previa aplicación manual de `db/migrations/V4__kds_estado_item.sql`), comprobando columnas en modo lectura, descuento de stock KDS en `movimiento_stock`, aislamiento de estaciones, eventos en `evento_pedido` y verificación IHDR + entropía de Shannon de las 15 fotos PNG. Salida cruda actualizada en `docs/evidencias/PRB-57/01-salida-terminal-postgres.txt`.
