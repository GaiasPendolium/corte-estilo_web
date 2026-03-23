from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_estadopagoestilistadia'),
    ]

    operations = [
        migrations.CreateModel(
            name='EstadoPagoEstilistaHistorial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(verbose_name='Fecha Afectada')),
                ('estado_anterior', models.CharField(choices=[('pendiente', 'Pendiente'), ('cancelado', 'Cancelado')], default='pendiente', max_length=20, verbose_name='Estado Anterior')),
                ('estado_nuevo', models.CharField(choices=[('pendiente', 'Pendiente'), ('cancelado', 'Cancelado')], max_length=20, verbose_name='Estado Nuevo')),
                ('notas', models.CharField(blank=True, max_length=255, null=True, verbose_name='Notas')),
                ('fecha_cambio', models.DateTimeField(default=timezone.now, verbose_name='Fecha Cambio')),
                ('estilista', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='historial_estados_pago', to='api.estilista', verbose_name='Estilista')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cambios_estado_pago', to='api.usuario', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Historial Estado Pago Estilista',
                'verbose_name_plural': 'Historial Estados Pago Estilista',
                'db_table': 'estado_pago_estilista_historial',
                'ordering': ['-fecha_cambio', '-fecha'],
            },
        ),
    ]
