from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_estadopagoestilistahistorial_monto_liquidado'),
    ]

    operations = [
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='pago_daviplata',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Pago Daviplata'),
        ),
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='pago_efectivo',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Pago efectivo'),
        ),
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='pago_nequi',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Pago Nequi'),
        ),
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='pago_otros',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Pago otros'),
        ),
    ]
