from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="categoria",
            field=models.ForeignKey(
                db_column="categoria_id",
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="productos",
                to="catalogo.categoria",
                verbose_name="Categoría",
            ),
        ),
    ]
