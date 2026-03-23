from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_estadopagoestilistahistorial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeudaConsumoEmpleado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_factura', models.CharField(max_length=40, unique=True, verbose_name='Numero Factura')),
                ('total_cargo', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Total Cargo')),
                ('total_abonado', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Total Abonado')),
                ('saldo_pendiente', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Saldo Pendiente')),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('parcial', 'Parcial'), ('cancelado', 'Cancelado')], default='pendiente', max_length=20, verbose_name='Estado')),
                ('fecha_hora', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha y Hora')),
                ('notas', models.CharField(blank=True, max_length=255, null=True, verbose_name='Notas')),
                ('estilista', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deudas_consumo', to='api.estilista', verbose_name='Empleado')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deudas_consumo_registradas', to='api.usuario', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Deuda Consumo Empleado',
                'verbose_name_plural': 'Deudas Consumo Empleado',
                'db_table': 'deudas_consumo_empleado',
                'ordering': ['-fecha_hora'],
            },
        ),
        migrations.CreateModel(
            name='AbonoDeudaEmpleado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Monto Abono')),
                ('fecha_hora', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fecha y Hora')),
                ('notas', models.CharField(blank=True, max_length=255, null=True, verbose_name='Notas')),
                ('deuda', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abonos', to='api.deudaconsumoempleado', verbose_name='Deuda')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='abonos_deuda_empleado', to='api.usuario', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Abono Deuda Empleado',
                'verbose_name_plural': 'Abonos Deuda Empleado',
                'db_table': 'abonos_deuda_empleado',
                'ordering': ['-fecha_hora'],
            },
        ),
        migrations.AddField(
            model_name='ventaproducto',
            name='tipo_operacion',
            field=models.CharField(choices=[('venta', 'Venta'), ('consumo_empleado', 'Consumo empleado')], default='venta', max_length=30, verbose_name='Tipo de Operación'),
        ),
        migrations.AddField(
            model_name='ventaproducto',
            name='deuda_consumo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ventas_items', to='api.deudaconsumoempleado', verbose_name='Deuda consumo'),
        ),
    ]
