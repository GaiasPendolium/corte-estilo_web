from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_fact_liquidacion_estilista_dia'),
    ]

    operations = [
        migrations.AddField(
            model_name='factliquidacionestilistadia',
            name='medio_abono_puesto',
            field=models.CharField(
                choices=[
                    ('efectivo', 'Efectivo'),
                    ('nequi', 'Nequi'),
                    ('daviplata', 'Daviplata'),
                    ('otros', 'Otros'),
                ],
                default='efectivo',
                max_length=20,
                verbose_name='Medio abono puesto',
            ),
        ),
    ]
