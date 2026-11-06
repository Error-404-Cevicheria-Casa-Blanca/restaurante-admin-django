"""Comando administrativo para migrar y auditar los datos reales de producción (PRB-52)."""

from django.core.management.base import BaseCommand, CommandError

from catalogo.produccion_seeds import auditar_datos_produccion, cargar_datos_produccion


class Command(BaseCommand):
    help = (
        "Carga de forma idempotente la carta oficial (15 platos con fotos), "
        "las 13 mesas reales, los 4 roles y los usuarios operativos con PIN BCrypt (PRB-52)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--solo-auditar",
            action="store_true",
            help="Solo verifica la integridad de los datos sin modificar la base de datos.",
        )

    def handle(self, *args, **options):
        if not options["solo_auditar"]:
            res = cargar_datos_produccion()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeds PRB-52 aplicados: roles +{res['roles_creados']}, "
                    f"usuarios +{res['usuarios_creados']}/~{res['usuarios_actualizados']}, "
                    f"platos +{res['platos_creados']}/~{res['platos_actualizados']}, "
                    f"mesas +{res['mesas_creadas']}/~{res['mesas_actualizadas']}."
                )
            )

        auditoria = auditar_datos_produccion()
        if not auditoria["ok"]:
            detalle = "; ".join(auditoria["errores"])
            raise CommandError(f"Auditoría PRB-52 falló: {detalle}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Auditoría PRB-52 OK: {auditoria['roles_total']} roles, "
                f"{auditoria['usuarios_con_pin']} usuarios con PIN BCrypt, "
                f"{auditoria['platos_oficiales']}/15 platos oficiales con foto y "
                f"{auditoria['mesas_total']}/13 mesas verificadas."
            )
        )
