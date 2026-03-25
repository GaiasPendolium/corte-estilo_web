from django.db import migrations
from django.utils import timezone


def backfill_historial_debe(apps, schema_editor):
    EstadoPagoEstilistaDia = apps.get_model('api', 'EstadoPagoEstilistaDia')
    EstadoPagoEstilistaHistorial = apps.get_model('api', 'EstadoPagoEstilistaHistorial')

    diarios_debe = EstadoPagoEstilistaDia.objects.filter(estado='debe')

    for d in diarios_debe.iterator():
        existe = EstadoPagoEstilistaHistorial.objects.filter(
            estilista_id=d.estilista_id,
            fecha=d.fecha,
            estado_nuevo='debe',
        ).exists()
        if existe:
            continue

        monto_liquidado = (
            (d.pago_efectivo or 0)
            + (d.pago_nequi or 0)
            + (d.pago_daviplata or 0)
            + (d.pago_otros or 0)
        )

        pendiente = (d.saldo_puesto_pendiente or 0) or (d.pendiente_puesto or 0) or 0

        EstadoPagoEstilistaHistorial.objects.create(
            estilista_id=d.estilista_id,
            fecha=d.fecha,
            estado_anterior='pendiente',
            estado_nuevo='debe',
            notas=d.notas,
            usuario_id=d.usuario_liquida_id,
            monto_liquidado=monto_liquidado,
            abono_puesto=(d.abono_puesto or 0),
            pendiente_puesto=pendiente,
            fecha_cambio=(d.actualizado_en or timezone.now()),
        )


def noop_reverse(apps, schema_editor):
    # No revertimos para no eliminar historial válido creado por operación.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_alter_estadopagoestilistahistorial_estado_anterior_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_historial_debe, noop_reverse),
    ]
