# Generated for PRB-40 / PRB-46 (Máquina de estados de mesa)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0003_mesa_pedido"),
    ]

    operations = [
        migrations.AddField(
            model_name="mesa",
            name="mozo_id",
            field=models.IntegerField(
                blank=True, null=True, verbose_name="ID Mozo"
            ),
        ),
        migrations.AddField(
            model_name="mesa",
            name="fecha_apertura",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Fecha Apertura"
            ),
        ),
        migrations.AddField(
            model_name="mesa",
            name="fecha_cierre",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Fecha Cierre"
            ),
        ),
    ]
