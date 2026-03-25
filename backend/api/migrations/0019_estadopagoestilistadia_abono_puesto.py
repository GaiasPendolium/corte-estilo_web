from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_estadopagoestilistadia_pagos_por_medio'),
    ]

    operations = [
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='abono_puesto',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Abono a puesto'),
        ),
    ]
