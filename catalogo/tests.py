"""Pruebas del esqueleto PE-6: la configuración por entorno carga correctamente."""

import os
import subprocess
import sys

from django.conf import settings

RUTA_PROYECTO = str(settings.BASE_DIR)

# Variables que definen la conexión a PostgreSQL (las mismas de config.settings).
POSTGRES_VARS = ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")

_DB_COMPLETAS = {
    "DB_NAME": "panel_pruebas",
    "DB_USER": "panel_pruebas",
    "DB_PASSWORD": "falsa-clave",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
}

_CLAVE_PRUEBAS = "clave-solo-pruebas-subproceso-NO-USAR-en-produccion"


def _ejecutar_en_subproceso(codigo, entorno_extra):
    """Ejecuta código Python en un proceso limpio, sin variables heredadas."""
    entorno = dict(os.environ)
    for nombre in ("DJANGO_SECRET_KEY", "DJANGO_DEBUG", *POSTGRES_VARS):
        entorno.pop(nombre, None)
    entorno.update(entorno_extra)
    return subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        cwd=RUTA_PROYECTO,
        env=entorno,
        check=False,
    )


def _importar_settings_en_subproceso(entorno_extra):
    """Importa config.settings en un proceso limpio, sin variables heredadas."""
    return _ejecutar_en_subproceso("import config.settings", entorno_extra)


def _motor_bd_en_subproceso(entorno_extra):
    """Devuelve el ENGINE de la BD leído en un proceso limpio, o el error."""
    codigo = "import config.settings as s; print(s.DATABASES['default']['ENGINE'])"
    return _ejecutar_en_subproceso(codigo, entorno_extra)


def test_settings_carga_sin_error():
    """La configuración carga y trae lo mínimo del panel."""
    assert "catalogo" in settings.INSTALLED_APPS
    assert "inventario" in settings.INSTALLED_APPS
    assert settings.LANGUAGE_CODE == "es-pe"
    assert settings.TIME_ZONE == "America/Lima"
    assert settings.USE_TZ is True


def test_debug_es_falso_por_defecto():
    """Sin DJANGO_DEBUG=1 el modo DEBUG queda apagado."""
    assert os.environ.get("DJANGO_DEBUG") != "1"
    assert settings.DEBUG is False


def test_basada_en_sqlite_sin_variables_de_entorno():
    """Sin variables DB_* la BD por defecto es SQLite local."""
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_clave_secreta_obligatoria_sin_debug():
    """Sin DJANGO_SECRET_KEY (y sin DEBUG) la importación falla: no hay clave default."""
    resultado = _importar_settings_en_subproceso({})
    assert resultado.returncode != 0
    assert "DJANGO_SECRET_KEY" in (resultado.stderr + resultado.stdout)


def test_clave_de_desarrollo_solo_con_django_debug():
    """Solo con DJANGO_DEBUG=1 se permite importar sin clave explícita."""
    resultado = _importar_settings_en_subproceso({"DJANGO_DEBUG": "1"})
    assert resultado.returncode == 0


def test_sin_variables_db_usa_sqlite_en_subproceso():
    """Sin ninguna variable DB_* la BD por defecto es SQLite local."""
    resultado = _motor_bd_en_subproceso({"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS})
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "django.db.backends.sqlite3"


def test_con_las_cinco_variables_db_usa_postgresql():
    """Con las 5 variables DB_* la BD por defecto es PostgreSQL (sin conectar)."""
    entorno = {"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS, **_DB_COMPLETAS}
    resultado = _motor_bd_en_subproceso(entorno)
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "django.db.backends.postgresql"


def test_con_variables_db_parciales_falla_indicando_faltantes():
    """Con solo 3 de 5 variables DB_* la importación falla listando las faltantes."""
    parciales = {
        nombre: _DB_COMPLETAS[nombre]
        for nombre in ("DB_NAME", "DB_USER", "DB_PASSWORD")
    }
    entorno = {"DJANGO_SECRET_KEY": _CLAVE_PRUEBAS, **parciales}
    resultado = _motor_bd_en_subproceso(entorno)
    assert resultado.returncode != 0
    salida = resultado.stderr + resultado.stdout
    assert "ImproperlyConfigured" in salida
    assert "DB_HOST" in salida
    assert "DB_PORT" in salida
