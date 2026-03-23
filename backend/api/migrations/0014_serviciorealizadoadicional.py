from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_abonodeudaempleado_medio_pago'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServicioRealizadoAdicional',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valor_cobrado', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Valor cobrado')),
                ('fecha_creacion', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha de creación')),
                (
                    'estilista',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='servicios_adicionales_realizados',
                        to='api.estilista',
                        verbose_name='Empleado que realiza adicional',
                    ),
                ),
                (
                    'servicio',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='adicionales_realizados',
                        to='api.servicio',
                        verbose_name='Servicio adicional',
                    ),
                ),
                (
                    'servicio_realizado',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='adicionales_asignados',
                        to='api.serviciorealizado',
                        verbose_name='Servicio realizado',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Servicio adicional realizado',
                'verbose_name_plural': 'Servicios adicionales realizados',
                'db_table': 'servicios_realizados_adicionales',
                'ordering': ['servicio_realizado_id', 'id'],
            },
        ),
    ]
