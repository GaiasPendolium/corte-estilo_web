#!/usr/bin/env python
"""
Script de debugging para ver el cálculo del BI de Angel.
"""
import os
import django
from decimal import Decimal
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from django.utils import timezone
from api.models import (
    Estilista, ServicioRealizado, VentaProducto,
    EstadoPagoEstilistaDia, Producto
)

# Obtener hoy o fecha configurada
hoy = timezone.localdate()
fecha_inicio_dt = hoy
fecha_fin_dt = hoy

# Buscar estilista Angel
try:
    angel = Estilista.objects.get(nombre__iexact='Angel')
except Exception as e:
    print(f"❌ No se encontró estilista 'Angel': {e}")
    exit(1)

print(f"\n🔍 DEBUG BI para: {angel.nombre}")
print(f"📅 Período: {fecha_inicio_dt} a {fecha_fin_dt}")
print(f"📊 Tipo cobro espacio: {angel.tipo_cobro_espacio}")
print(f"💰 Valor cobro espacio: {angel.valor_cobro_espacio}")

# Cargar servicios
servicios_est = ServicioRealizado.objects.select_related('estilista').filter(
    estilista=angel,
    estado='finalizado',
    fecha_hora__date__gte=fecha_inicio_dt,
    fecha_hora__date__lte=fecha_fin_dt,
)

# Cargar ventas
ventas_est = VentaProducto.objects.select_related('producto', 'estilista').filter(
    estilista=angel,
    fecha_hora__date__gte=fecha_inicio_dt,
    fecha_hora__date__lte=fecha_fin_dt,
)

print(f"\n📋 SERVICIOS ({len(servicios_est)}):")
total_servicios_precio = Decimal(0)
for s in servicios_est:
    print(f"   - {s.fecha_hora.date()}: ${s.precio_cobrado} (adicionales: ${s.valor_adicionales})")
    total_servicios_precio += Decimal(s.precio_cobrado or 0)

print(f"\n🛍️ VENTAS PRODUCTOS ({len(ventas_est)}):")
comision_total = Decimal(0)
for v in ventas_est:
    pct = Decimal(v.producto.comision_estilista or 0)
    valor_comision = (Decimal(v.total) * pct) / Decimal(100)
    comision_total += valor_comision
    print(f"   - {v.fecha_hora.date()}: ${v.total} x {pct}% = ${valor_comision} (producto: {v.producto.nombre})")

# Calcular diagrama por fecha
dias_trabajados = {
    *servicios_est.values_list('fecha_hora__date', flat=True).distinct(),
    *ventas_est.values_list('fecha_hora__date', flat=True).distinct(),
}

print(f"\n📆 DÍAS TRABAJADOS: {sorted(dias_trabajados)}")

# Cargar estados
try:
    estados_pago_map = {
        (ep.estilista_id, ep.fecha): ep.estado
        for ep in EstadoPagoEstilistaDia.objects.filter(
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
            estilista=angel
        )
    }
except Exception as e:
    print(f"⚠️ No se pudo cargar estados: {e}")
    estados_pago_map = {}

print(f"\n🔐 ESTADOS EN BD: {estados_pago_map}")

# Reconstruir los cálculos
servicios_por_dia = {}
for srv in servicios_est:
    fecha_srv = srv.fecha_hora.date()
    servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + Decimal(srv.precio_cobrado or 0)

comision_por_dia = {}
for v in ventas_est:
    pct = Decimal(v.producto.comision_estilista or 0)
    valor_comision = (Decimal(v.total) * pct) / Decimal(100)
    fecha_v = v.fecha_hora.date()
    comision_por_dia[fecha_v] = comision_por_dia.get(fecha_v, Decimal(0)) + valor_comision

pago_neto_pendiente = Decimal(0)
pago_neto_cancelado = Decimal(0)
pago_neto_periodo = Decimal(0)
dias_cancelados = 0

print(f"\n💹 CÁLCULO POR DÍA:")
print("─" * 100)

for dia in sorted(dias_trabajados):
    base_servicio_dia = servicios_por_dia.get(dia, Decimal(0))
    comision_dia = comision_por_dia.get(dia, Decimal(0))

    descuento_dia = Decimal(0)
    if angel.tipo_cobro_espacio == 'porcentaje_neto':
        descuento_dia = (base_servicio_dia * Decimal(angel.valor_cobro_espacio or 0)) / Decimal(100)
        if descuento_dia > base_servicio_dia:
            descuento_dia = base_servicio_dia
    elif angel.tipo_cobro_espacio == 'costo_fijo_neto':
        descuento_dia = Decimal(angel.valor_cobro_espacio or 0)

    neto_dia = (base_servicio_dia - descuento_dia) + comision_dia
    estado_dia = estados_pago_map.get((angel.id, dia), 'pendiente')

    pago_neto_periodo += neto_dia

    if estado_dia == 'cancelado':
        pago_neto_cancelado += neto_dia
        dias_cancelados += 1
        print(f"  {dia} [CANCELADO]:")
    else:
        pago_neto_pendiente += neto_dia
        print(f"  {dia} [PENDIENTE]:")

    print(f"    Base servicios: ${base_servicio_dia}")
    print(f"    Descuento espacio ({angel.tipo_cobro_espacio}): ${descuento_dia}")
    print(f"    Comisión productos: ${comision_dia}")
    print(f"    Neto del día: ${neto_dia}")
    print()

print("─" * 100)
print(f"\n📊 RESUMEN FINAL:")
print(f"   Neto pendiente: ${pago_neto_pendiente}")
print(f"   Neto cancelado: ${pago_neto_cancelado}")
print(f"   Neto período total: ${pago_neto_periodo}")
print(f"   Días cancelados: {dias_cancelados}")
print(f"   Total días: {len(dias_trabajados)}")
