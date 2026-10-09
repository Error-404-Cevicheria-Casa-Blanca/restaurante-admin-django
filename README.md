# restaurante-admin-django

Panel administrativo de la Cevichería "La Casa Blanca" - gestión de carta, precios, insumos y usuarios.

## Stack

- Python 3.14
- Django 5.2 LTS
- Django REST Framework
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

Si no defines las variables `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y
`DB_PORT`, el panel usa SQLite local (`db.sqlite3`). Si defines las cinco, usa
PostgreSQL. Si defines solo algunas, el arranque falla con
`ImproperlyConfigured` indicando cuáles faltan (no cae a SQLite en silencio).

### 3. Comandos diarios

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m flake8
.\.venv\Scripts\python.exe manage.py check
```

## Equipo

- Jerardo Cutipa - Backoffice Django Lead
- David Gabriel Rojas Garcia - Mobile Lead (Kotlin)
- Max Erick Munoz Paredes - Backend Lead (Java)
- Julio Alexander Perez Muñoz - QA & DevOps Lead
