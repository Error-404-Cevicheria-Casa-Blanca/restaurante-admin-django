"""Entorno mínimo de pruebas para pytest.

Se importa como plugin (ver `addopts` en `pytest.ini`) ANTES de que
pytest-django cargue `config.settings`, de modo que la suite corre sin definir
`DJANGO_SECRET_KEY` en el entorno. La clave solo existe dentro del proceso de
pruebas; `settings.py` sigue exigiendo la variable real fuera de él.
"""

import os

os.environ.setdefault(
    "DJANGO_SECRET_KEY",
    "clave-solo-pruebas-pytest-NO-USAR-en-produccion",
)
