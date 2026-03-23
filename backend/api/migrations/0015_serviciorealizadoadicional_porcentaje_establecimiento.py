from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_serviciorealizadoadicional'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviciorealizadoadicional',
            name='aplica_porcentaje_establecimiento',
            field=models.BooleanField(default=False, verbose_name='Aplica porcentaje establecimiento'),
        ),
        migrations.AddField(
            model_name='serviciorealizadoadicional',
            name='porcentaje_establecimiento',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5, verbose_name='Porcentaje establecimiento'),
        ),
    ]
