# Generated for PRB-86 / PRB-57: Soporte para migración de bases de datos existentes
from django.db import migrations


def aplicar_alter_columnas(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute("""
                ALTER TABLE detalle_pedido ADD COLUMN IF NOT EXISTS estado_item VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE';
                ALTER TABLE detalle_pedido ADD COLUMN IF NOT EXISTS estacion VARCHAR(50);
                ALTER TABLE detalle_pedido ADD COLUMN IF NOT EXISTS anulado_motivo VARCHAR(255);
                CREATE INDEX IF NOT EXISTS idx_detalle_estado_estacion ON detalle_pedido(estado_item, estacion);
            """)


def revertir_alter_columnas(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cur:
            cur.execute("""
                DROP INDEX IF EXISTS idx_detalle_estado_estacion;
                ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS estado_item;
                ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS estacion;
                ALTER TABLE detalle_pedido DROP COLUMN IF EXISTS anulado_motivo;
            """)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0008_eventopedido"),
    ]

    operations = [
        migrations.RunPython(
            code=aplicar_alter_columnas,
            reverse_code=revertir_alter_columnas,
        ),
    ]
