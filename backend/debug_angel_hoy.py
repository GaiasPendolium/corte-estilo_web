#!/usr/bin/env python
"""
Script de debugging para Angel (ID=12) en la fecha de hoy.
Ejecutar: cd backend && railway run python debug_angel_hoy.py
"""
import os
import django
from decimal import Decimal
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from django.utils import timezone
from api.models import (
    Estilista, ServicioRealizado, VentaProducto,
    EstadoPagoEstilistaDia
)

# Fecha de hoy
fecha_hoy = timezone.localdate()

print(f"\n{'='*100}")
print(f"🔍 DEBUGGING BI PARA ANGEL (ID=12) - {fecha_hoy}")
print(f"{'='*100}\n")

# Obtener estilista
try:
    angel = Estilista.objects.get(id=12)
    print(f"✅ Estilista encontrado: {angel.nombre}")
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

print(f"   - Tipo cobro espacio: {angel.tipo_cobro_espacio}")
print(f"   - Valor cobro espacio: {angel.valor_cobro_espacio}\n")

# Consultar servicios
servicios = ServicioRealizado.objects.filter(
    estilista=angel,
    estado='finalizado',
    fecha_hora__date=fecha_hoy,
)

print(f"📋 SERVICIOS REALIZADOS HOY ({len(servicios)}):")
total_servicios_precio = Decimal(0)
for s in servicios:
    print(f"   - {s.fecha_hora.time()}: Precio=${s.precio_cobrado} | Adicionales=${s.valor_adicionales}")
    total_servicios_precio += Decimal(s.precio_cobrado or 0)
print(f"   TOTAL BASE: ${total_servicios_precio}\n")

# Consultar ventas
ventas = VentaProducto.objects.filter(
    estilista=angel,
    fecha_hora__date=fecha_hoy,
)

print(f"🛍️ VENTAS DE PRODUCTOS HOY ({len(ventas)}):")
comision_total = Decimal(0)
for v in ventas:
    pct = Decimal(v.producto.comision_estilista or 0)
    valor_comision = (Decimal(v.total) * pct) / Decimal(100)
    comision_total += valor_comision
    print(f"   - Producto: {v.producto.nombre}")
    print(f"     Total venta: ${v.total}")
    print(f"     Comisión configurada: {pct}%")
    print(f"     Comisión calculada: ${valor_comision}")
print(f"   TOTAL COMISIÓN: ${comision_total}\n")

# Cargar estado de pago
try:
    estado_pago = EstadoPagoEstilistaDia.objects.filter(
        estilista=angel,
        fecha=fecha_hoy,
    ).first()
    estado = estado_pago.estado if estado_pago else 'pendiente'
    print(f"🔐 ESTADO DE PAGO EN BD: {estado}")
    if estado_pago:
        print(f"   - Actualizado: {estado_pago.actualizado_en}")
        print(f"   - Notas: {estado_pago.notas}\n")
    else:
        print(f"   (No hay registro explícito, por defecto es 'pendiente')\n")
except Exception as e:
    print(f"⚠️ Error al cargar estado: {e}\n")
    estado = 'pendiente'

# CÁLCULO
print(f"💹 CÁLCULO DEL NETO:")
print(f"{'─'*100}")

base_servicio = total_servicios_precio
comision = comision_total

# Descuento
descuento = Decimal(0)
if angel.tipo_cobro_espacio == 'porcentaje_neto':
    descuento = (base_servicio * Decimal(angel.valor_cobro_espacio or 0)) / Decimal(100)
    if descuento > base_servicio:
        descuento = base_servicio
    print(f"Descuento (% de base):  {angel.valor_cobro_espacio}% × ${base_servicio} = ${descuento}")
elif angel.tipo_cobro_espacio == 'costo_fijo_neto':
    descuento = Decimal(angel.valor_cobro_espacio or 0)
    print(f"Descuento (fijo):  ${descuento}")
else:
    print(f"Descuento: Sin cobro")

print(f"\n  Base servicios:        ${base_servicio}")
print(f"  Menos descuento:       ${descuento}")
print(f"  Base neta:             ${base_servicio - descuento}")
print(f"  Más comisión:          ${comision}")
print(f"\n  = NETO DEL DÍA:        ${(base_servicio - descuento) + comision}")

neto_dia = (base_servicio - descuento) + comision

print(f"\n🎯 RESULTADO FINAL:")
print(f"{'─'*100}")

if estado == 'cancelado':
    print(f"Estado: CANCELADO")
    print(f"  Neto pendiente: $0 (ya fue pagado)")
    print(f"  Neto cancelado: ${neto_dia}")
else:
    print(f"Estado: PENDIENTE")
    print(f"  Neto pendiente: ${neto_dia}")
    print(f"  Neto cancelado: $0")

print(f"\n{'='*100}\n")

# Análisis
if neto_dia < 0:
    print(f"⚠️ ALERTA: El descuento es MAYOR que servicios + comisión")
    print(f"   Angel queda debiendo ${abs(neto_dia)} al establecimiento")
elif neto_dia == 0:
    print(f"⚠️ El neto calculado es exactamente $0")
    print(f"   Este es el valor que se mostrará")
else:
    print(f"✅ Todo normal. Angel debe recibir ${neto_dia}")
