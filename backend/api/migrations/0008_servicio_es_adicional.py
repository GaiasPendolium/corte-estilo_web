from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_roles_empleados_y_adicionales_servicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicio',
            name='es_adicional',
            field=models.BooleanField(default=False, verbose_name='Es Servicio Adicional'),
        ),
    ]
