from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_consumo_empleado_deuda'),
    ]

    operations = [
        migrations.AddField(
            model_name='abonodeudaempleado',
            name='medio_pago',
            field=models.CharField(
                choices=[('nequi', 'Nequi'), ('daviplata', 'Daviplata'), ('efectivo', 'Efectivo'), ('otros', 'Otros')],
                default='efectivo',
                max_length=20,
                verbose_name='Medio de Pago',
            ),
        ),
    ]
