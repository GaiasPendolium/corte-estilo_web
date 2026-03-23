#!/usr/bin/env python
"""
Debug script para investigar problema de liquidación de estilista mostrando $0
"""
import os
import django
from datetime import datetime, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from api.models import (
    Estilista, ServicioRealizado, VentaProducto, EstadoPagoEstilistaDia
)

def debug_liquidacion(estilista_nombre, fecha_str):
    """Debug de liquidación para un estilista en una fecha específica"""
    
    try:
        estilista = Estilista.objects.get(nombre=estilista_nombre)
    except Estilista.DoesNotExist:
        print(f"❌ Estilista '{estilista_nombre}' no encontrado")
        return
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except:
        print(f"❌ Formato de fecha inválido. Usa YYYY-MM-DD")
        return
    
    print(f"\n{'='*80}")
    print(f"🔍 DEBUG LIQUIDACIÓN: {estilista_nombre} - {fecha_str}")
    print(f"{'='*80}\n")
    
    # 1. Servicios del día
    print("📋 SERVICIOS DEL DÍA:")
    servicios = ServicioRealizado.objects.filter(
        estilista=estilista,
        fecha_hora__date=fecha,
        estado='finalizado'
    )
    
    print(f"   Total servicios finalizados: {servicios.count()}")
    for srv in servicios:
        print(f"   - {srv.id}: ${srv.precio_cobrado} (estado: {srv.estado})")
    
    total_servicios = Decimal(servicios.aggregate(total=sum('precio_cobrado') or 0)['total'] or 0) if servicios else Decimal(0)
    print(f"   ✓ Total base del día: ${total_servicios}\n")
    
    # 2. Ventas del día
    print("🛍️  VENTAS DEL DÍA:")
    ventas = VentaProducto.objects.filter(
        estilista=estilista,
        fecha_hora__date=fecha
    )
    
    print(f"   Total ventas: {ventas.count()}")
    comision_total = Decimal(0)
    for v in ventas:
        pct = Decimal(v.producto.comision_estilista or 0)
        valor_comision = (Decimal(v.total) * pct) / Decimal(100)
        comision_total += valor_comision
        print(f"   - {v.id}: ${v.total} * {pct}% = ${valor_comision}")
    
    print(f"   ✓ Total comisión: ${comision_total}\n")
    
    # 3. Estado de pago del día
    print("📊 ESTADO DE PAGO DEL DÍA:")
    estado_pago = EstadoPagoEstilistaDia.objects.filter(
        estilista=estilista,
        fecha=fecha
    ).first()
    
    if estado_pago:
        print(f"   Estado registrado: {estado_pago.estado}")
        print(f"   Notas: {estado_pago.notas or 'N/A'}")
    else:
        print(f"   ⚠️  SIN REGISTRO en EstadoPagoEstilistaDia (default: pendiente)\n")
    
    # 4. Cálculo de descuento de espacio
    print("🏢 CÁLCULO DE DESCUENTO DE ESPACIO:")
    tipo_cobro = estilista.tipo_cobro_espacio
    valor_cobro = Decimal(estilista.valor_cobro_espacio or 0)
    
    print(f"   Tipo de cobro: {tipo_cobro}")
    print(f"   Valor configurado: ${valor_cobro}")
    
    descuento = Decimal(0)
    if tipo_cobro == 'porcentaje_neto':
        descuento = (total_servicios * valor_cobro) / Decimal(100)
        if descuento > total_servicios:
            descuento = total_servicios
        print(f"   Cálculo: ${total_servicios} * {valor_cobro}% = ${descuento}")
    elif tipo_cobro == 'costo_fijo_neto':
        descuento = valor_cobro
        print(f"   Cálculo: Costo fijo = ${descuento}")
    else:
        print(f"   Sin descuento")
    
    print(f"   ✓ Descuento final: ${descuento}\n")
    
    # 5. Resultado final
    print("💰 RESULTADO FINAL:")
    neto_dia = (total_servicios - descuento) + comision_total
    print(f"   Neto del día: (${total_servicios} - ${descuento}) + ${comision_total} = ${neto_dia}")
    print(f"   Estado: {estado_pago.estado if estado_pago else 'pendiente'}")
    
    if neto_dia == 0:
        print(f"\n   ⚠️  ALERTA: Neto del día es $0")
        if not servicios and not ventas:
            print(f"      → Causa probable: NO hay servicios ni ventas registrados")
        elif total_servicios == 0:
            print(f"      → Causa probable: Los servicios tienen precio_cobrado = 0")
        elif neto_dia < 0:
            print(f"      → Causa probable: El descuento es mayor al ingreso")
    
    print(f"\n{'='*80}\n")

if __name__ == '__main__':
    from django.utils import timezone
    
    # Valores por defecto: hoy y primer estilista
    hoy = timezone.localdate().strftime('%Y-%m-%d')
    
    print("\n📌 USO: debug_liquidacion('NOMBRE_ESTILISTA', 'YYYY-MM-DD')")
    print(f"   Ejemplo: debug_liquidacion('Angel', '{hoy}')\n")
    
    # Listar estilistas disponibles
    print("📖 Estilistas disponibles:")
    for est in Estilista.objects.filter(activo=True):
        print(f"   - {est.nombre}")
    
    # Debug por defecto para hoy
    print(f"\n🔄 Ejecutando debug automático para hoy ({hoy})...\n")
    for est in Estilista.objects.filter(activo=True)[:2]:
        debug_liquidacion(est.nombre, hoy)
