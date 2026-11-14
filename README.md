# restaurante-admin-django

Panel administrativo de la Cevichería "La Casa Blanca" - gestión de carta, precios, insumos y usuarios.

## Stack

- Python 3.14
- Django 5.2 LTS
- Django REST Framework y django-cors-headers (previstos para tareas de backoffice; este módulo no expone API)
- PostgreSQL (producción), SQLite (desarrollo local)
- pytest-django, coverage, flake8

## Cómo ejecutar

Comandos reales en **PowerShell**, desde la raíz del repositorio (`repos\restaurante-admin-django`).

### 1. Entorno virtual e instalación (solo la primera vez)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 2. Variables de entorno

`.env.example` es **solo una referencia de nombres** (el proyecto no lee archivos
`.env` ni usa `python-dotenv`). Define cada variable en la sesión de PowerShell
con `$env:`, igual que en el backend Java. Con `DJANGO_DEBUG=1` (solo desarrollo
local) se usa una clave de desarrollo automática; sin DEBUG la variable
`DJANGO_SECRET_KEY` es obligatoria.

```powershell
$env:DJANGO_SECRET_KEY = "<genera-una-clave-real>"
$env:DJANGO_DEBUG = "0"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
```

> **Aviso de despliegue en LAN:** Para operar en el restaurante en producción local con `DJANGO_DEBUG=0`, define `DJANGO_ALLOWED_HOSTS` incluyendo la dirección IP local de la PC central (servidor). El panel está diseñado para operar por HTTP dentro de la red local Wi-Fi cerrada (LAN) y no debe exponerse directamente a Internet. `manage.py check --deploy` reportará 5 avisos de seguridad estructurales para HTTPS (W004, W008, W012, W016, W020), los cuales son esperados y aceptables en una LAN privada sin certificados TLS; no actives `SECURE_SSL_REDIRECT` para no bloquear el acceso local por HTTP.

Si no defines las variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y
`DB_PORT`, el panel usa SQLite local (`db.sqlite3`). Si defines las cinco, usa
PostgreSQL. Si defines solo algunas, el arranque falla con
`ImproperlyConfigured` indicando cuáles faltan (no cae a SQLite en silencio).

### 3. Comandos diarios

```powershell
$env:DJANGO_DEBUG = "1"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py seed_catalogo
.\.venv\Scripts\python.exe manage.py runserver
```

> **Nota sobre credenciales:** `createsuperuser` es obligatorio la primera vez. El panel web autentica contra `auth_user` (`D8-PASSWORD-HASHING.md`, punto 3), no contra la tabla `usuario` de `db/seed.sql`. Las cuentas `admin_test` / `password123` son para el backend Java/Android y no sirven para entrar al panel web.

- **Panel web de catálogo y pesca del día (PRB-19):** `http://127.0.0.1:8000/`
- **Sitio administrativo técnico Django:** `http://127.0.0.1:8000/admin/`

```powershell
# Opción A: script reproducible (configura DJANGO_SECRET_KEY de sesión si no existe)
.\scripts\test.ps1

# Opción B: comando explícito con manage.py test (requiere DJANGO_SECRET_KEY definida)
$env:DJANGO_SECRET_KEY = "clave-temporal-solo-para-tests-locales"
.\.venv\Scripts\python.exe manage.py test

# Otras verificaciones (pytest ya inyecta clave efímera vía pytest_entorno.py)
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flake8
.\.venv\Scripts\python.exe manage.py check
```

> **Nota sobre `manage.py test`:** Por seguridad (`config/settings.py`), ejecutar `python manage.py test` sin `DJANGO_SECRET_KEY` (ni `DJANGO_DEBUG=1`) falla con `KeyError: 'DJANGO_SECRET_KEY'`. Usa `.\scripts\test.ps1` o define `$env:DJANGO_SECRET_KEY` antes de correr la suite. Si el entorno local usa `venv\` en lugar de `.venv\`, `.\scripts\test.ps1` detecta automáticamente el entorno con Django instalado.

## Equipo

- Jerardo Cutipa - Backoffice Django Lead
- David Gabriel Rojas Garcia - Mobile Lead (Kotlin)
- Max Erick Munoz Paredes - Backend Lead (Java)
- Julio Alexander Perez Muñoz - QA & DevOps Lead
