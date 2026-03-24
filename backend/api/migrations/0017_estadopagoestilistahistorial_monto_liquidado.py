from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_serviciorealizado_adicional_otro_estilista'),
    ]

    operations = [
        migrations.AddField(
            model_name='estadopagoestilistahistorial',
            name='monto_liquidado',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Monto liquidado'),
        ),
    ]
