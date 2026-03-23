from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_serviciorealizadoadicional_porcentaje_establecimiento'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviciorealizado',
            name='adicional_otro_estilista',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='servicios_adicional_producto_comision',
                to='api.estilista',
                verbose_name='Estilista comisión producto adicional',
            ),
        ),
    ]
