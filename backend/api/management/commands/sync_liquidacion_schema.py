from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Alinea el esquema de tablas de liquidacion en PostgreSQL (idempotente)."

    def handle(self, *args, **options):
        sql_statements = [
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS ganancias_totales numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS descuento_puesto numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS total_pagable numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_efectivo numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_nequi numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_daviplata numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pago_otros numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS abono_puesto numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS saldo_puesto_pendiente numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS neto_dia numeric(12,2) NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS pendiente_puesto numeric(12,2) NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_dia ADD COLUMN IF NOT EXISTS usuario_liquida_id bigint NULL",
            "ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS monto_liquidado numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS abono_puesto numeric(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE estado_pago_estilista_historial ADD COLUMN IF NOT EXISTS pendiente_puesto numeric(12,2) NOT NULL DEFAULT 0",
        ]

        with connection.cursor() as cursor:
            for stmt in sql_statements:
                cursor.execute(stmt)

        self.stdout.write(self.style.SUCCESS("Schema de liquidacion alineado correctamente."))
