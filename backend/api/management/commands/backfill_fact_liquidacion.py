from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from api.models import (
    AbonoDeudaEmpleado,
    EstadoPagoEstilistaDia,
    Estilista,
    FactLiquidacionEstilistaDia,
)
from api.views import calcular_liquidacion_dia_estilista


class Command(BaseCommand):
    help = 'Backfill de fact_liquidacion_estilista_dia por rango de fechas y estilista.'

    def add_arguments(self, parser):
        parser.add_argument('--fecha-inicio', required=True, help='YYYY-MM-DD')
        parser.add_argument('--fecha-fin', required=True, help='YYYY-MM-DD')
        parser.add_argument('--estilista-id', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        fecha_inicio = datetime.strptime(options['fecha_inicio'], '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(options['fecha_fin'], '%Y-%m-%d').date()
        estilista_id = options.get('estilista_id')
        dry_run = bool(options.get('dry_run'))

        if fecha_inicio > fecha_fin:
            self.stderr.write(self.style.ERROR('fecha_inicio no puede ser mayor que fecha_fin'))
            return

        estilistas_qs = Estilista.objects.filter(activo=True).order_by('id')
        if estilista_id:
            estilistas_qs = estilistas_qs.filter(id=estilista_id)

        estilistas = list(estilistas_qs)
        if not estilistas:
            self.stdout.write(self.style.WARNING('No se encontraron estilistas para backfill.'))
            return

        total_upserts = 0

        for estilista in estilistas:
            deuda_running = self._deuda_inicial(estilista, fecha_inicio)

            fecha_cursor = fecha_inicio
            while fecha_cursor <= fecha_fin:
                calc = calcular_liquidacion_dia_estilista(estilista, fecha_cursor)
                estado = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha_cursor).first()

                pago_efectivo = Decimal(getattr(estado, 'pago_efectivo', 0) or 0)
                pago_nequi = Decimal(getattr(estado, 'pago_nequi', 0) or 0)
                pago_daviplata = Decimal(getattr(estado, 'pago_daviplata', 0) or 0)
                pago_otros = Decimal(getattr(estado, 'pago_otros', 0) or 0)
                pago_total = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
                abono_puesto = Decimal(getattr(estado, 'abono_puesto', 0) or 0)
                medio_abono_puesto = (getattr(estado, 'medio_abono_puesto', None) or 'efectivo').strip().lower()
                if medio_abono_puesto not in {'efectivo', 'nequi', 'daviplata', 'otros'}:
                    medio_abono_puesto = 'efectivo'

                descuento = Decimal(calc.get('descuento_puesto') or 0)
                ganancias = Decimal(calc.get('ganancias_totales') or 0)
                ganancias_servicios = Decimal(calc.get('servicios_base') or 0) + Decimal(calc.get('comisiones_adicionales') or 0)
                comision_producto_caja = Decimal(calc.get('comisiones_ventas_caja') or 0)
                comision_producto_servicios = Decimal(calc.get('comisiones_ventas_servicios') or 0)

                deuda_anterior = deuda_running
                deuda_running = max(deuda_running + descuento - max(abono_puesto, Decimal(0)), Decimal(0))

                cobro_consumo = self._consumo_cobrado_dia(estilista.id, fecha_cursor)
                pendiente_pago = max(Decimal(calc.get('total_pagable') or 0) - pago_total, Decimal(0))

                estado_liq = 'pendiente'
                if pendiente_pago <= 0:
                    estado_liq = 'debe' if deuda_running > 0 else 'cancelado'

                if not dry_run:
                    with transaction.atomic():
                        fact, created = FactLiquidacionEstilistaDia.objects.get_or_create(
                            estilista=estilista,
                            fecha=fecha_cursor,
                            version=1,
                            defaults={
                                'vigente': True,
                            },
                        )
                        if not created and not fact.vigente:
                            fact.vigente = True

                        fact.origen_calculo = 'backfill_v1'
                        fact.ganancias_servicios = ganancias_servicios
                        fact.comision_producto_caja = comision_producto_caja
                        fact.comision_producto_servicios = comision_producto_servicios
                        fact.ganancias_totales = ganancias
                        fact.descuento_puesto_dia = descuento
                        fact.deuda_puesto_anterior = deuda_anterior
                        fact.abono_puesto_dia = abono_puesto
                        fact.medio_abono_puesto = medio_abono_puesto
                        fact.deuda_puesto_cierre = deuda_running
                        fact.pago_efectivo = pago_efectivo
                        fact.pago_nequi = pago_nequi
                        fact.pago_daviplata = pago_daviplata
                        fact.pago_otros = pago_otros
                        fact.pago_total_empleado = pago_total
                        fact.pendiente_pago_empleado = pendiente_pago
                        fact.cobro_consumo_dia = cobro_consumo
                        fact.estado_liquidacion = estado_liq
                        fact.forzar_reemplazo_dia = False
                        fact.usuario_liquida = getattr(estado, 'usuario_liquida', None)
                        fact.notas = getattr(estado, 'notas', None)
                        fact.payload_fuente = {
                            'from_estado_pago': bool(estado),
                            'estado_pago_id': int(estado.id) if estado else None,
                            'command': 'backfill_fact_liquidacion',
                        }
                        fact.save()

                total_upserts += 1
                fecha_cursor += timedelta(days=1)

        msg = f'Backfill finalizado. Filas procesadas: {total_upserts}'
        if dry_run:
            msg = f'[DRY RUN] {msg}'
        self.stdout.write(self.style.SUCCESS(msg))

    def _consumo_cobrado_dia(self, estilista_id, fecha_dia):
        inicio = datetime.combine(fecha_dia, datetime.min.time())
        fin = datetime.combine(fecha_dia, datetime.max.time())
        total = AbonoDeudaEmpleado.objects.filter(
            deuda__estilista_id=estilista_id,
            fecha_hora__gte=inicio,
            fecha_hora__lte=fin,
        ).aggregate(total=Sum('monto'))['total']
        return Decimal(total or 0)

    def _deuda_inicial(self, estilista, fecha_inicio):
        previo = FactLiquidacionEstilistaDia.objects.filter(
            estilista=estilista,
            fecha__lt=fecha_inicio,
            vigente=True,
        ).order_by('-fecha').first()
        if previo:
            return Decimal(previo.deuda_puesto_cierre or 0)

        estado_previo = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista,
            fecha__lt=fecha_inicio,
        ).order_by('-fecha').first()
        if estado_previo:
            return Decimal(
                getattr(estado_previo, 'saldo_puesto_pendiente', None)
                or getattr(estado_previo, 'pendiente_puesto', 0)
                or 0
            )
        return Decimal(0)
