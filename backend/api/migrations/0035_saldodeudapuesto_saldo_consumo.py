from django.db import migrations, models
from decimal import Decimal


def inicializar_saldo_consumo(apps, schema_editor):
    """
    Inicializa saldo_consumo desde DeudaConsumoEmpleado.saldo_pendiente activos.
    Re-inicializa saldo (puesto) usando el registro más reciente con saldo>0 por empleado,
    cubriendo todos los empleados (no solo activos).
    """
    Estilista = apps.get_model('api', 'Estilista')
    EstadoPagoEstilistaDia = apps.get_model('api', 'EstadoPagoEstilistaDia')
    DeudaConsumoEmpleado = apps.get_model('api', 'DeudaConsumoEmpleado')
    SaldoDeudaPuesto = apps.get_model('api', 'SaldoDeudaPuesto')

    for estilista in Estilista.objects.all():
        # Saldo puesto: registro más reciente con saldo_puesto_pendiente > 0
        # Esto captura empleados cuya liquidación más reciente zeroeó incorrectamente la deuda
        ultimo_con_saldo = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista,
            saldo_puesto_pendiente__gt=0,
        ).order_by('-fecha').first()

        ultimo_registro = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista,
        ).order_by('-fecha').first()

        saldo_puesto = Decimal(0)
        if ultimo_registro and ultimo_registro.saldo_puesto_pendiente:
            # El registro más reciente tiene saldo > 0: es el valor correcto
            saldo_puesto = max(Decimal(str(ultimo_registro.saldo_puesto_pendiente)), Decimal(0))
        elif ultimo_con_saldo and ultimo_registro:
            # El registro más reciente tiene saldo=0 pero hay registros anteriores con saldo>0
            # Verificar si el más reciente hizo un abono suficiente para cubrir la deuda
            abono_final = Decimal(str(ultimo_registro.abono_puesto or 0))
            saldo_previo = max(Decimal(str(ultimo_con_saldo.saldo_puesto_pendiente)), Decimal(0))
            if abono_final >= saldo_previo:
                # Abono cubrió la deuda — saldo=0 es correcto
                saldo_puesto = Decimal(0)
            else:
                # Saldo zeroeado sin abono suficiente — fue el bug del código antiguo
                saldo_puesto = saldo_previo

        # Saldo consumo: suma de saldo_pendiente de facturas activas
        saldo_consumo = Decimal(0)
        for deuda in DeudaConsumoEmpleado.objects.filter(
            estilista=estilista,
            saldo_pendiente__gt=0,
        ).exclude(estado='cancelado'):
            saldo_consumo += Decimal(str(deuda.saldo_pendiente or 0))

        SaldoDeudaPuesto.objects.update_or_create(
            estilista=estilista,
            defaults={
                'saldo': max(saldo_puesto, Decimal(0)),
                'saldo_consumo': max(saldo_consumo, Decimal(0)),
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0034_saldo_deuda_puesto'),
    ]

    operations = [
        migrations.AddField(
            model_name='saldodeudapuesto',
            name='saldo_consumo',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name='Saldo acumulado consumo empleado (facturas)',
            ),
        ),
        migrations.RunPython(inicializar_saldo_consumo, migrations.RunPython.noop),
    ]
