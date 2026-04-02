from django.db import migrations


SQL_FORWARD = """
ALTER TABLE estado_pago_estilista_dia
ADD COLUMN IF NOT EXISTS medio_abono_puesto varchar(20) NOT NULL DEFAULT 'efectivo';

ALTER TABLE estado_pago_estilista_historial
ADD COLUMN IF NOT EXISTS medio_abono_puesto varchar(20) NOT NULL DEFAULT 'efectivo';
"""


SQL_REVERSE = """
ALTER TABLE estado_pago_estilista_dia
DROP COLUMN IF EXISTS medio_abono_puesto;

ALTER TABLE estado_pago_estilista_historial
DROP COLUMN IF EXISTS medio_abono_puesto;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_align_liquidacion_schema_safety'),
    ]

    operations = [
        migrations.RunSQL(SQL_FORWARD, SQL_REVERSE),
    ]