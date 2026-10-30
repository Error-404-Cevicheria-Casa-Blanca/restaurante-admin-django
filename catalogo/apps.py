from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CatalogoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'catalogo'
    verbose_name = 'Catálogo de Carta y Pesca del Día'

    def ready(self):
        from .sqlite_bootstrap import asegurar_tablas_sqlite

        post_migrate.connect(
            asegurar_tablas_sqlite,
            dispatch_uid="catalogo.asegurar_tablas_sqlite",
        )
