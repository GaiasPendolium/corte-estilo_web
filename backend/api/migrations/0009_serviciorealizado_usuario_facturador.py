from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_servicio_es_adicional'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviciorealizado',
            name='usuario',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='servicios_facturados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Usuario Facturador',
            ),
        ),
    ]
