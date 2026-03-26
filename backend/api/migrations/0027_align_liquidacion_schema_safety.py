from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_backfill_historial_debe_from_diaria'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS ganancias_totales numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS descuento_puesto numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS total_pagable numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_efectivo numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_nequi numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_daviplata numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_otros numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS abono_puesto numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS saldo_puesto_pendiente numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS neto_dia numeric(12,2) NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pendiente_puesto numeric(12,2) NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS usuario_liquida_id bigint NULL;

            ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS monto_liquidado numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS abono_puesto numeric(12,2) NOT NULL DEFAULT 0;
            ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS pendiente_puesto numeric(12,2) NOT NULL DEFAULT 0;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
