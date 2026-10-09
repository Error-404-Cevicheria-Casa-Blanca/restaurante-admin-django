"""Pruebas del esqueleto PE-6: la configuración por entorno carga correctamente."""

import os
import subprocess
import sys

from django.conf import settings

RUTA_PROYECTO = str(settings.BASE_DIR)


def _importar_settings_en_subproceso(entorno_extra):
    """Importa config.settings en un proceso limpio, sin variables heredadas."""
    entorno = dict(os.environ)
    entorno.pop("DJANGO_SECRET_KEY", None)
    entorno.pop("DJANGO_DEBUG", None)
    entorno.update(entorno_extra)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        capture_output=True,
        text=True,
        cwd=RUTA_PROYECTO,
        env=entorno,
        check=False,
    )


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
