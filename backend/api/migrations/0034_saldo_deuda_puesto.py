from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


def inicializar_saldos(apps, schema_editor):
    """
    Inicializa SaldoDeudaPuesto para cada empleado con el saldo del registro más reciente.
    """
    Estilista = apps.get_model('api', 'Estilista')
    EstadoPagoEstilistaDia = apps.get_model('api', 'EstadoPagoEstilistaDia')
    SaldoDeudaPuesto = apps.get_model('api', 'SaldoDeudaPuesto')

    for estilista in Estilista.objects.filter(activo=True):
        ultimo = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista,
        ).order_by('-fecha').first()
        saldo = Decimal(0)
        if ultimo and ultimo.saldo_puesto_pendiente:
            saldo = max(Decimal(str(ultimo.saldo_puesto_pendiente)), Decimal(0))
        SaldoDeudaPuesto.objects.update_or_create(
            estilista=estilista,
            defaults={'saldo': saldo},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0033_estadopagoestilistadia_skip_descuento_puesto'),
    ]

    operations = [
        migrations.CreateModel(
            name='SaldoDeudaPuesto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('saldo', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Saldo acumulado deuda de puesto')),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('estilista', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='saldo_deuda_puesto',
                    to='api.estilista',
                    verbose_name='Estilista',
                )),
            ],
            options={
                'verbose_name': 'Saldo deuda de puesto',
                'verbose_name_plural': 'Saldos deuda de puesto',
            },
        ),
        migrations.RunPython(inicializar_saldos, migrations.RunPython.noop),
    ]
