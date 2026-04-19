from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0032_usuario_permisos_ui'),
    ]

    operations = [
        migrations.AddField(
            model_name='estadopagoestilistadia',
            name='skip_descuento_puesto',
            field=models.BooleanField(default=False, verbose_name='Omitir descuento de puesto'),
        ),
    ]
