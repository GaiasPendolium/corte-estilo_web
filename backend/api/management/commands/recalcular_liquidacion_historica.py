from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import EstadoPagoEstilistaDia, Estilista
from api.views import calcular_liquidacion_dia_estilista


class Command(BaseCommand):
    help = "Recalcula estados y saldos de liquidacion historica por empleado/dia con la logica vigente."

    def add_arguments(self, parser):
        parser.add_argument(
            "--estilista-id",
            type=int,
            default=None,
            help="Opcional: recalcular solo un estilista por id.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        estilista_id = options.get("estilista_id")

        qs = EstadoPagoEstilistaDia.objects.select_related("estilista").order_by("estilista_id", "fecha", "id")
        if estilista_id:
            qs = qs.filter(estilista_id=estilista_id)

        registros = list(qs)
        if not registros:
            self.stdout.write(self.style.WARNING("No hay registros de liquidacion para recalcular."))
            return

        if estilista_id:
            estilistas_ids = [estilista_id]
        else:
            estilistas_ids = sorted({r.estilista_id for r in registros})

        actualizados = 0

        for est_id in estilistas_ids:
            diarios = [r for r in registros if r.estilista_id == est_id]
            if not diarios:
                continue

            estilista = diarios[0].estilista
            deuda_arrastre = Decimal(0)

            for d in diarios:
                calc = calcular_liquidacion_dia_estilista(estilista, d.fecha)
                ganancias = Decimal(calc.get("ganancias_totales") or 0)
                descuento = Decimal(calc.get("descuento_puesto") or 0)
                total_pagable = Decimal(calc.get("total_pagable") or 0)

                total_pagado = (
                    Decimal(d.pago_efectivo or 0)
                    + Decimal(d.pago_nequi or 0)
                    + Decimal(d.pago_daviplata or 0)
                    + Decimal(d.pago_otros or 0)
                )
                abono_puesto = Decimal(d.abono_puesto or 0)

                deuda_total = max(deuda_arrastre + max(descuento, Decimal(0)), Decimal(0))
                abono_aplicado = min(max(abono_puesto, Decimal(0)), deuda_total)
                saldo_puesto = max(deuda_total - abono_aplicado, Decimal(0))

                pendiente_liquidacion = max(total_pagable - total_pagado, Decimal(0))
                if pendiente_liquidacion > 0:
                    estado = "pendiente"
                elif saldo_puesto > 0:
                    estado = "debe"
                else:
                    estado = "cancelado"

                d.ganancias_totales = ganancias
                d.descuento_puesto = descuento
                d.total_pagable = total_pagable
                d.neto_dia = total_pagable
                d.saldo_puesto_pendiente = saldo_puesto
                d.pendiente_puesto = saldo_puesto
                d.estado = estado
                d.save(
                    update_fields=[
                        "ganancias_totales",
                        "descuento_puesto",
                        "total_pagable",
                        "neto_dia",
                        "saldo_puesto_pendiente",
                        "pendiente_puesto",
                        "estado",
                        "actualizado_en",
                    ]
                )

                deuda_arrastre = saldo_puesto
                actualizados += 1

        self.stdout.write(self.style.SUCCESS(f"Recalculo completado. Registros actualizados: {actualizados}"))
