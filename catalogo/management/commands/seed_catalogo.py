"""Comando para poblar de forma idempotente el catálogo marino de ejemplo."""

from django.core.management.base import BaseCommand

from catalogo.sqlite_bootstrap import poblar_carta_ejemplo


class Command(BaseCommand):
    help = (
        "Inicializa tablas locales SQLite (si aplica) y carga categorías "
        "y platos marinos de muestra de forma idempotente."
    )

    def handle(self, *args, **options):
        cat_nuevas, platos_nuevos = poblar_carta_ejemplo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo listo: {cat_nuevas} categorías nuevas y "
                f"{platos_nuevos} platos nuevos registrados."
            )
        )
