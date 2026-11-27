# Evidencia PRB-107 y PRB-108: Worker `despachar_impresion` y Servicio Windows (Cierre PRB-58)

**Fecha de Ejecución:** 2026-11-20  
**Rama Git:** `feature/PRB-107-108-worker-impresion`  
**Base:** `develop` (`976045c`)  
**Tickets Jira:** `PRB-107` (`[Django] Worker despachar_impresion + ESC/POS`) y `PRB-108` (`[DevOps] Servicio Windows del worker de impresión`), subtareas de `PRB-58`.  
**Responsable:** Jerardo Cutipa

---

## 1. Resumen de Implementación

### 1.1 PRB-107 — Worker Django `despachar_impresion` + ESC/POS
- **Comando:** `catalogo/management/commands/despachar_impresion.py`
  - `--once`: ejecuta un ciclo FIFO sobre trabajos `PENDIENTE` en `impresion_cola` y termina.
  - `--loop`: ejecuta continuamente con `close_old_connections()` por ciclo, captura limpia de `SIGTERM`/`SIGINT`, pausa configurable (`--intervalo`, default `2.0s`) y `--max-ciclos` opcional para pruebas deterministas.
  - `--healthcheck`: valida edad y estado del archivo JSON de heartbeat (`--health-file`, `--max-age-seconds`).
  - `--log-file`: rotación automática UTF-8 vía `RotatingFileHandler` (`5 MB` × `5` respaldos).
  - Sobrescritura dinámica por argumentos (`--modo`, `--host`, `--port`, `--timeout`, `--limite`) o variables de entorno (`PRINTER_MODE`, `PRINTER_HOST`, `PRINTER_PORT`, `PRINTER_TIMEOUT`).
- **Servicio ESC/POS (`catalogo/impresion_service.py`):**
  - Resolución dinámica de configuración (`obtener_config_impresora()`).
  - Soporte directo para filas `COMANDA` por estación y `PRECUENTA` encoladas desde Java (`PRB-106`), tanto con `pedido_id` directo como con `mesa_id` en el payload (formato texto `"Mesa X precuenta"` o JSON `{"mesa_id": X}`), resolviendo el pedido activo de la mesa y regenerando el ticket oficial de 48 columnas + comandos binarios ESC/POS (`CMD_INIT` ... `CMD_FEED_CUT`).
  - Protección de idempotencia con `select_for_update()`: trabajos ya `IMPRESO` o `FALLIDO` no se vuelven a enviar.
  - Reintentos automáticos: ante error de impresora incrementa `intentos` manteniendo `PENDIENTE` hasta el límite de `3` intentos, marcando `FALLIDO` al 3er fallo y registrando `error`.
  - Filtro de estación: `COCINA_GENERAL` incluye todos los platos activos y excluye ítems `ANULADO`.

### 1.2 PRB-108 — Servicio Windows, Logs Rotativos y Healthcheck
- `scripts/impresion/run_worker_impresion.ps1`: carga `.env` del repositorio sin exponer secretos, crea `logs/impresion/` (ignorado en `.gitignore`) y lanza `manage.py despachar_impresion --loop` con `--log-file logs/impresion/worker.log` y `--health-file logs/impresion/health.json`.
- `scripts/impresion/instalar_servicio_windows.ps1`: soporta modo **NSSM** (servicio Windows `CasaBlancaImpresionWorker` con `SERVICE_AUTO_START`, `AppExit Default Restart`, rotación de logs `5 MB`) y modo nativo **TaskScheduler** (`AtStartup`, `RestartCount 999`, `RestartInterval 1 min`, sin límite de ejecución), más tarea periódica de monitoreo cada 5 minutos (`CasaBlancaImpresionWorker_Healthcheck`). Soporta `-DryRun` y `-Uninstall`.
- `scripts/impresion/healthcheck_worker_impresion.ps1`: verifica heartbeat JSON vigente (`--healthcheck`) y, con `-RestartOnFailure`, reinicia automáticamente el servicio o la tarea programada si detecta fallo o estancamiento.

---

## 2. Comandos de Operación en Producción (PC Central Windows)

```powershell
# 1. Validar instalación sin cambios (Dry-Run)
powershell -ExecutionPolicy Bypass -File .\scripts\impresion\instalar_servicio_windows.ps1 -DryRun

# 2. Instalar servicio Windows (NSSM si existe en PATH, o Tarea Programada AtStartup) — ejecutar como Administrador
powershell -ExecutionPolicy Bypass -File .\scripts\impresion\instalar_servicio_windows.ps1

# 3. Verificar salud del worker
powershell -ExecutionPolicy Bypass -File .\scripts\impresion\healthcheck_worker_impresion.ps1

# 4. Ejecución puntual manual (una pasada)
python manage.py despachar_impresion --once --modo NETWORK --host 192.168.1.200 --port 9100
```

---

## 3. Verificación Ejecutada (2026-11-20)

| Verificación | Comando | Resultado |
|---|---|---|
| Linter estático | `.\venv\Scripts\python.exe -m flake8` | `EXIT=0` (0 errores) |
| Integridad Django | `.\venv\Scripts\python.exe manage.py check` | `System check identified no issues (0 silenced)` (`EXIT=0`) |
| Tests impresión + worker | `manage.py test catalogo.tests.ImpresionTermicaTests catalogo.tests.WorkerDespacharImpresionTests -v 2` | **19/19 OK** (`12.596s`) |
| Suite completa Django (`pytest`) | `.\venv\Scripts\python.exe -m pytest -q` | **86 passed, 4 subtests passed** (`56.61s`, `EXIT=0`) |
| Instalador Windows (Dry-Run) | `.\scripts\impresion\instalar_servicio_windows.ps1 -DryRun` | `EXIT=0` (`Modo: TaskScheduler`) |
| Runner + Healthcheck real | `run_worker_impresion.ps1 -Once -Modo DUMMY` + `healthcheck_worker_impresion.ps1` | `HEALTHY \| modo=DUMMY \| ciclos=1 \| pendientes=0` (`EXIT=0`) |

---

## 4. Instalación Real en Windows y Validación contra PostgreSQL (`2026-11-27`)

- **Despliegue real en Windows Task Scheduler (ejecutado como Administrador):**
  - Se ejecutó `instalar_servicio_windows.ps1` registrando e iniciando `CasaBlancaImpresionWorker` (`AtStartup`, `SYSTEM`, `RestartCount=999`, `RestartInterval=1 min`, `Stop-ScheduledTask` previo para recarga limpia) y `CasaBlancaImpresionWorker_Healthcheck` (cada `5 min` con `-RestartOnFailure`).
- **Corrección de bloqueo `FOR UPDATE` sobre PostgreSQL (`impresion_service.py`):**
  - En PostgreSQL real (`casablanca` `:5432`), `select_for_update()` combinado con `select_related("pedido", "pedido__mesa")` sobre llaves foráneas nulables generaba `LEFT OUTER JOIN ... FOR UPDATE` (`FeatureNotSupported`). Se desacopló `ImpresionCola.objects.select_for_update().get(id=trabajo_id)` del `select_related`, quedando cubierto con test de regresión (`88 passed, 4 subtests passed` en `pytest`).
- **Compatibilidad HTTPS detrás de Caddy (`PRB-98`):**
  - Se incorporó `DJANGO_CSRF_TRUSTED_ORIGINS` y `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` en `config/settings.py` para permitir formularios `POST` del panel y KDS a través de `https://casa-blanca.local`.

### Nota de alcance hacia PRB-110
- La verificación física de papel en la impresora **Epson TM-T20III** (comanda por estación + pre-cuenta real originadas desde la tablet y Java `PRB-106`) corresponde a la subtarea **`PRB-110`**.
