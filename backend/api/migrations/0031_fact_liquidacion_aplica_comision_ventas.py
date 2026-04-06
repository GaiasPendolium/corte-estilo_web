from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_fact_liquidacion_medio_abono_puesto'),
    ]

    operations = [
        migrations.AddField(
            model_name='factliquidacionestilistadia',
            name='aplica_comision_ventas',
            field=models.BooleanField(default=True),
        ),
    ]
