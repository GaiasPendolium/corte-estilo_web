from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_serviciorealizado_usuario_facturador'),
    ]

    operations = [
        migrations.CreateModel(
            name='EstadoPagoEstilistaDia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha')),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('cancelado', 'Cancelado')], default='pendiente', max_length=20, verbose_name='Estado Pago')),
                ('notas', models.CharField(blank=True, max_length=255, null=True, verbose_name='Notas')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='Actualizado en')),
                ('estilista', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='estados_pago_diario', to='api.estilista', verbose_name='Estilista')),
            ],
            options={
                'verbose_name': 'Estado Pago Estilista Día',
                'verbose_name_plural': 'Estados Pago Estilista Día',
                'db_table': 'estado_pago_estilista_dia',
                'ordering': ['-fecha', 'estilista__nombre'],
                'unique_together': {('estilista', 'fecha')},
            },
        ),
    ]
