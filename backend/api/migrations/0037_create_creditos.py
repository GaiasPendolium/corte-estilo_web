# Generated migration for Credito and AbonoCredito models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_estadopagoestilistadia_medio_abono_puesto_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Credito',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valor_prestado', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Valor prestado')),
                ('porcentaje_interes', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='Porcentaje de interés (%)')),
                ('valor_interes', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor del interés')),
                ('valor_total', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Valor total (prestado + interés)')),
                ('saldo_actual', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='Saldo actual pendiente')),
                ('fecha_inicio', models.DateField(verbose_name='Fecha de inicio')),
                ('plazo_dias', models.IntegerField(default=30, verbose_name='Plazo en días')),
                ('fecha_vencimiento', models.DateField(verbose_name='Fecha de vencimiento')),
                ('estado', models.CharField(choices=[('activo', 'Activo'), ('cancelado', 'Cancelado'), ('vencido', 'Vencido'), ('proximo_vencer', 'Próximo a vencer')], default='activo', max_length=20, verbose_name='Estado')),
                ('observaciones', models.TextField(blank=True, null=True, verbose_name='Observaciones')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True, verbose_name='Última actualización')),
                ('estilista', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='creditos', to='api.estilista', verbose_name='Empleado')),
                ('usuario_creador', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='creditos_creados', to=settings.AUTH_USER_MODEL, verbose_name='Usuario que creó el crédito')),
            ],
            options={
                'verbose_name': 'Crédito',
                'verbose_name_plural': 'Créditos',
                'db_table': 'creditos',
                'ordering': ['-fecha_creacion'],
            },
        ),
        migrations.CreateModel(
            name='AbonoCredito',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha del abono')),
                ('valor_abono', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Valor abonado')),
                ('saldo_anterior', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Saldo anterior')),
                ('saldo_restante', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Saldo restante después del abono')),
                ('observaciones', models.TextField(blank=True, null=True, verbose_name='Observaciones')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')),
                ('credito', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abonos', to='api.credito', verbose_name='Crédito')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='abonos_credito', to=settings.AUTH_USER_MODEL, verbose_name='Usuario que registró el abono')),
            ],
            options={
                'verbose_name': 'Abono de Crédito',
                'verbose_name_plural': 'Abonos de Crédito',
                'db_table': 'abonos_credito',
                'ordering': ['-fecha'],
            },
        ),
        migrations.AddIndex(
            model_name='credito',
            index=models.Index(fields=['estilista', '-fecha_creacion'], name='ix_credito_est_fecha'),
        ),
        migrations.AddIndex(
            model_name='credito',
            index=models.Index(fields=['estado', '-fecha_creacion'], name='ix_credito_estado_fecha'),
        ),
        migrations.AddIndex(
            model_name='credito',
            index=models.Index(fields=['fecha_vencimiento'], name='ix_credito_vencimiento'),
        ),
        migrations.AddIndex(
            model_name='abonocredito',
            index=models.Index(
                fields=['credito', '-fecha'],
                name='ix_abono_credito_fecha',
            ),
        ),
    ]
