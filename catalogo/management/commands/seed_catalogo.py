"""Comando para poblar de forma idempotente el catálogo marino de ejemplo."""

from django.core.management.base import BaseCommand, CommandError

from catalogo.sqlite_bootstrap import poblar_carta_ejemplo


class Command(BaseCommand):
    help = (
        "Inicializa tablas locales SQLite (si aplica) y carga categorías "
        "y platos marinos de muestra de forma idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--permitir-postgres",
            action="store_true",
            help="Permite cargar los datos de ejemplo sobre PostgreSQL (solo demo).",
        )

    def handle(self, *args, **options):
        try:
            cat_nuevas, platos_nuevos = poblar_carta_ejemplo(
                permitir_postgres=options["permitir_postgres"]
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo listo: {cat_nuevas} categorías nuevas y "
                f"{platos_nuevos} platos nuevos registrados."
            )
        )
