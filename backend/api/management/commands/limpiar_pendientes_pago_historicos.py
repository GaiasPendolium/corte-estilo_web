from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from api.models import (
    EstadoPagoEstilistaDia,
    Estilista,
    FactLiquidacionEstilistaDia,
    ServicioRealizado,
    ServicioRealizadoAdicional,
    VentaProducto,
)
from api.views import _fecha_operativa_desde_dt, calcular_liquidacion_dia_estilista


class Command(BaseCommand):
    """
    Marca como pagados (pago_efectivo) los dias ANTERIORES a hoy que quedaron con
    "pendiente de pago al empleado" (generado > pagado), SIN tocar deuda de puesto
    (abono_puesto/saldo_puesto_pendiente/skip_descuento_puesto) ni facturas de
    consumo interno (DeudaConsumoEmpleado/AbonoDeudaEmpleado).

    Por defecto corre en modo dry-run (no escribe nada). Usa --apply para guardar.

    Ejemplos:
        python manage.py limpiar_pendientes_pago_historicos
        python manage.py limpiar_pendientes_pago_historicos --apply
        python manage.py limpiar_pendientes_pago_historicos --apply --hasta 2026-06-30
    """

    help = "Limpia el pendiente de pago al empleado de dias anteriores a hoy, sin afectar deuda de puesto ni consumo interno."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Aplica los cambios (por defecto solo hace dry-run).")
        parser.add_argument(
            "--hasta",
            type=str,
            default=None,
            help="Fecha limite (YYYY-MM-DD), inclusive. Por defecto: ayer (no toca el dia de hoy).",
        )
        parser.add_argument("--estilista-id", type=int, default=None, help="Opcional: limitar a un estilista por id.")

    def handle(self, *args, **options):
        aplicar = bool(options.get("apply"))
        estilista_id = options.get("estilista_id")
        hasta_raw = options.get("hasta")

        hoy = timezone.localdate()
        if hasta_raw:
            try:
                fecha_hasta = datetime.strptime(hasta_raw, "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("--hasta debe tener formato YYYY-MM-DD")
        else:
            fecha_hasta = hoy - timedelta(days=1)

        if fecha_hasta >= hoy:
            raise CommandError("--hasta debe ser una fecha anterior a hoy (este comando no toca el dia de hoy).")

        estilistas_qs = Estilista.objects.filter(activo=True).order_by("nombre")
        if estilista_id:
            estilistas_qs = estilistas_qs.filter(id=estilista_id)
        estilistas = list(estilistas_qs)
        if not estilistas:
            self.stdout.write(self.style.WARNING("No hay estilistas para procesar."))
            return

        estilista_ids = [int(e.id) for e in estilistas]

        # Dias con movimiento real (servicios/adicionales/ventas) hasta la fecha limite,
        # igual criterio que usa el reporte de Ajuste Diario para saber que dias existen.
        dias_con_movimiento = {}
        servicios_qs = ServicioRealizado.objects.filter(
            estado="finalizado", estilista_id__in=estilista_ids, fecha_hora__date__lte=fecha_hasta
        ).values_list("estilista_id", "fecha_hora")
        for est_id, dt in servicios_qs:
            f = _fecha_operativa_desde_dt(dt)
            if f and f <= fecha_hasta:
                dias_con_movimiento.setdefault(int(est_id), set()).add(f)

        adic_qs = ServicioRealizadoAdicional.objects.filter(
            estilista_id__in=estilista_ids,
            servicio_realizado__estado="finalizado",
            servicio_realizado__fecha_hora__date__lte=fecha_hasta,
        ).values_list("estilista_id", "servicio_realizado__fecha_hora")
        for est_id, dt in adic_qs:
            f = _fecha_operativa_desde_dt(dt)
            if f and f <= fecha_hasta:
                dias_con_movimiento.setdefault(int(est_id), set()).add(f)

        ventas_qs = VentaProducto.objects.filter(
            tipo_operacion="venta", estilista_id__in=estilista_ids, fecha_hora__date__lte=fecha_hasta
        ).values_list("estilista_id", "fecha_hora")
        for est_id, dt in ventas_qs:
            f = _fecha_operativa_desde_dt(dt)
            if f and f <= fecha_hasta:
                dias_con_movimiento.setdefault(int(est_id), set()).add(f)

        # Tambien incluir dias que ya tengan un registro diario (por si acaso).
        for ep in EstadoPagoEstilistaDia.objects.filter(estilista_id__in=estilista_ids, fecha__lte=fecha_hasta):
            dias_con_movimiento.setdefault(int(ep.estilista_id), set()).add(ep.fecha)

        cambios = []  # [(estilista_nombre, fecha, gap)]
        total_gap = Decimal(0)

        with transaction.atomic():
            for est in estilistas:
                est_id = int(est.id)
                dias = sorted(dias_con_movimiento.get(est_id, set()))
                for dia in dias:
                    ep = EstadoPagoEstilistaDia.objects.filter(estilista=est, fecha=dia).first()

                    fact = None
                    aplica_comision_ventas = True
                    if ep is not None:
                        fact = FactLiquidacionEstilistaDia.objects.filter(
                            estilista=est, fecha=dia, vigente=True
                        ).first()
                        if fact is not None:
                            aplica_comision_ventas = bool(getattr(fact, "aplica_comision_ventas", True))

                    calc = calcular_liquidacion_dia_estilista(est, dia, aplica_comision_ventas=aplica_comision_ventas)
                    generado = Decimal(calc.get("total_pagable") or 0)

                    pago_efectivo = Decimal(ep.pago_efectivo or 0) if ep else Decimal(0)
                    pago_nequi = Decimal(ep.pago_nequi or 0) if ep else Decimal(0)
                    pago_daviplata = Decimal(ep.pago_daviplata or 0) if ep else Decimal(0)
                    pago_otros = Decimal(ep.pago_otros or 0) if ep else Decimal(0)
                    pagado_total = pago_efectivo + pago_nequi + pago_daviplata + pago_otros

                    gap = max(generado - pagado_total, Decimal(0))
                    if gap <= 0:
                        continue

                    cambios.append((est.nombre, dia.strftime("%Y-%m-%d"), gap))
                    total_gap += gap

                    if not aplicar:
                        continue

                    if ep is None:
                        # La deuda de puesto DEBE arrancar en lo que traiga el dia anterior
                        # mas reciente (arrastre), nunca en 0 -- forzar 0 aqui rompe la cadena
                        # para el resto de dias posteriores que ya tenian su propio registro.
                        ep_previo = EstadoPagoEstilistaDia.objects.filter(
                            estilista=est, fecha__lt=dia
                        ).order_by("-fecha").first()
                        saldo_arrastrado = max(
                            Decimal(getattr(ep_previo, "saldo_puesto_pendiente", None) or getattr(ep_previo, "pendiente_puesto", 0) or 0),
                            Decimal(0),
                        ) if ep_previo else Decimal(0)
                        ep = EstadoPagoEstilistaDia(
                            estilista=est,
                            fecha=dia,
                            ganancias_totales=Decimal(calc.get("ganancias_totales") or 0),
                            descuento_puesto=Decimal(calc.get("descuento_puesto") or 0),
                            total_pagable=generado,
                            neto_dia=generado,
                            saldo_puesto_pendiente=saldo_arrastrado,
                            pendiente_puesto=saldo_arrastrado,
                            abono_puesto=Decimal(0),
                        )

                    # Solo tocamos el pago al empleado. abono_puesto, saldo_puesto_pendiente,
                    # skip_descuento_puesto y todo lo de consumo interno quedan intactos.
                    ep.pago_efectivo = pago_efectivo + gap
                    saldo_puesto_actual = Decimal(ep.saldo_puesto_pendiente or 0)
                    ep.estado = "debe" if saldo_puesto_actual > 0 else "cancelado"
                    notas_actual = str(ep.notas or "")
                    nota_extra = f"Pendiente de pago historico saldado automaticamente (${gap:,.2f})."
                    ep.notas = f"{notas_actual} | {nota_extra}".strip(" |")[:255]
                    ep.save()

                    if fact is not None:
                        fact.pago_efectivo = Decimal(fact.pago_efectivo or 0) + gap
                        fact.pago_total_empleado = (
                            Decimal(fact.pago_total_empleado or 0) + gap
                        )
                        fact.estado_liquidacion = ep.estado
                        fact.save()

        self.stdout.write("")
        if not cambios:
            self.stdout.write(self.style.SUCCESS("No hay pendientes de pago historicos que limpiar."))
            return

        for nombre, fecha_str, gap in cambios:
            self.stdout.write(f"  {nombre:20s} {fecha_str}  +${gap:,.2f}")

        self.stdout.write("")
        self.stdout.write(f"Total dias afectados: {len(cambios)}")
        self.stdout.write(f"Total ${total_gap:,.2f}")

        if aplicar:
            self.stdout.write(self.style.SUCCESS("Cambios aplicados y guardados."))
        else:
            self.stdout.write(self.style.WARNING("DRY-RUN: no se guardo nada. Vuelve a correr con --apply para aplicar."))
