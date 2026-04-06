from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_add_medio_abono_puesto'),
    ]

    operations = [
        migrations.CreateModel(
            name='FactLiquidacionEstilistaDia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha operativa')),
                ('version', models.PositiveIntegerField(default=1, verbose_name='Version de calculo')),
                ('vigente', models.BooleanField(default=True, verbose_name='Version vigente')),
                ('origen_calculo', models.CharField(default='engine_v2', max_length=40, verbose_name='Origen calculo')),
                ('ganancias_servicios', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('comision_producto_caja', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('comision_producto_servicios', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('ganancias_totales', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('descuento_puesto_dia', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('deuda_puesto_anterior', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('abono_puesto_dia', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('deuda_puesto_cierre', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pago_efectivo', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pago_nequi', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pago_daviplata', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pago_otros', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pago_total_empleado', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('pendiente_pago_empleado', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('cobro_consumo_dia', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('estado_liquidacion', models.CharField(choices=[('pendiente', 'Pendiente'), ('debe', 'Debe'), ('cancelado', 'Cancelado')], default='pendiente', max_length=20)),
                ('forzar_reemplazo_dia', models.BooleanField(default=False)),
                ('notas', models.TextField(blank=True, null=True)),
                ('payload_fuente', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('estilista', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='facts_liquidacion_diaria', to='api.estilista', verbose_name='Empleado')),
                ('usuario_liquida', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='facts_liquidacion_generados', to='api.usuario')),
            ],
            options={
                'verbose_name': 'Fact Liquidacion Estilista Dia',
                'verbose_name_plural': 'Facts Liquidacion Estilista Dia',
                'db_table': 'fact_liquidacion_estilista_dia',
                'ordering': ['-fecha', 'estilista__nombre', '-version'],
            },
        ),
        migrations.AddConstraint(
            model_name='factliquidacionestilistadia',
            constraint=models.UniqueConstraint(fields=('estilista', 'fecha', 'version'), name='uq_fact_liq_est_fecha_ver'),
        ),
        migrations.AddConstraint(
            model_name='factliquidacionestilistadia',
            constraint=models.UniqueConstraint(condition=models.Q(('vigente', True)), fields=('estilista', 'fecha'), name='uq_fact_liq_est_fecha_vigente'),
        ),
        migrations.AddIndex(
            model_name='factliquidacionestilistadia',
            index=models.Index(fields=['fecha'], name='ix_fact_liq_fecha'),
        ),
        migrations.AddIndex(
            model_name='factliquidacionestilistadia',
            index=models.Index(fields=['estilista', '-fecha'], name='ix_fact_liq_est_fecha'),
        ),
        migrations.AddIndex(
            model_name='factliquidacionestilistadia',
            index=models.Index(fields=['estado_liquidacion', '-fecha'], name='ix_fact_liq_estado_fecha'),
        ),
    ]
