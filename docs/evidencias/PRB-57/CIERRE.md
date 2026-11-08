# Cierre de Correcciones de Auditoría - PRB-57 (PR #10)

**Fecha:** 2026-11-08  
**Rama:** `feature/PRB-57-kds-cocina`  
**PR GitHub:** [#10 - feature/PRB-57-kds-cocina](https://github.com/Error-404-Cevicheria-Casa-Blanca/restaurante-admin-django/pull/10)  
**Revisor:** David Rojas (`Error-404-Cevicheria-Casa-Blanca`)  

---

## 1. Resumen de Correcciones Aplicadas

En respuesta a la auditoría técnica realizada sobre el PR #10, se abordaron y resolvieron al 100% los 5 puntos bloqueantes identificados:

| # | Observación de Auditoría | Estado | Solución Técnica Implementada |
|---|--------------------------|--------|--------------------------------|
| **1** | **Falta la columna `estado_item` (PRB-86)** | **CORREGIDO** | Agregadas las columnas `estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'`, `estacion VARCHAR(30) NOT NULL DEFAULT 'COCINA_CALIENTE'` y `anulado_motivo VARCHAR(255)` con índice `idx_detalle_estado_estacion` en `db/schema.sql`, `catalogo/sqlite_bootstrap.py`, y en el modelo `DetallePedido` (`catalogo/models.py`). Se ejecutó el DDL nativo en PostgreSQL 18. |
| **2** | **KDS avanza comanda completa, no el ítem** | **CORREGIDO** | Implementado avance individual por plato con `avanzar_estado_item()`, soporte de avance aislado por estación con `avanzar_estado_comanda(estacion=...)` y recálculo automático de estado de comanda (`recalcular_estado_pedido()`). Marcar 'Listo' en Barra Fría ahora mantiene los platos de Bebidas en preparación y no marca la comanda entera como lista prematuramente. Nueva ruta `/cocina/items/<id>/avanzar/` e interfaz interactiva one-click por plato en `kds.html`. |
| **3** | **Fotos reales eran placeholders** | **CORREGIDO** | Se reemplazaron los 15 PNG de círculos concéntricos por fotografías gastronómicas reales, apetitosas y de alta calidad (366 KB a 904 KB cada una) para todos los platos de la carta (ceviches, causas, jaleas, arroz mariscos, parihuela, suspiro, picarones, etc.). |
| **4** | **PINs en claro en el código** | **CORREGIDO** | Eliminados todos los `pin_referencia` ("1040", "2040", etc.) de `catalogo/produccion_seeds.py`, comentarios de PINs en claro de `db/seeds_produccion.sql`, y textos en evidencias PRB-52. Toda la autenticación opera exclusivamente con hashes BCrypt de 60 caracteres. |
| **5** | **Riesgo de FK en PostgreSQL (`usuario_id`)** | **CORREGIDO** | Implementado `resolver_usuario_operativo_id(request.user)` en `views.py` para mapear el usuario autenticado (`auth_user`) con su registro correspondiente en `usuario`. Además, `_validar_fk_usuario_id()` verifica la existencia previa de la clave foránea antes de persistir en `evento_pedido`, evitando cualquier excepción `psycopg2.errors.ForeignKeyViolation`. |

---

## 2. Resultados de Pruebas y Cobertura

- **Pruebas Automatizadas:** **61/61 tests en verde** (`Ran 61 tests — OK`, `EXIT=0`).
  - Nuevos tests añadidos en `KDSCocinaTests`:
    - `test_avance_individual_por_item_y_recalculo_comanda`
    - `test_aislamiento_estaciones_no_avanza_otra_estacion`
    - `test_kds_avanzar_item_endpoint_html_y_ajax`
    - `test_fk_usuario_id_seguro_postgres`
- **Cobertura de Código:** **85%** global (supera el estándar exigido de ≥ 83%).
- **Calidad de Código:** **0 errores de flake8** (`flake8 catalogo config db` -> `EXIT=0`).
- **Verificación en Vivo contra PostgreSQL 18.6:** Ejecutada en `localhost:5432/casablanca` comprobando ciclo de vida, aislamiento de Barra Fría, inserción de eventos inmutables en `evento_pedido` y existencia de fotos reales. Salida terminal en `01-salida-terminal-postgres.txt`.
