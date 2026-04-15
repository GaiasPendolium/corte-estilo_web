from django.db import migrations, models
import api.models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0031_fact_liquidacion_aplica_comision_ventas'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='permisos_ui',
            field=models.JSONField(blank=True, default=api.models.default_ui_permissions, verbose_name='Permisos UI'),
        ),
    ]