import os
import django
from datetime import datetime, timedelta
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from api.models import ServicioRealizado, VentaProducto, EstadoPagoEstilistaDia, Estilista

hoy = datetime.now().date()
hace_7_dias = hoy - timedelta(days=7)

print("="*80)
print("📅 DATOS DE LOS ÚLTIMOS 7 DÍAS")
print("="*80)

print("\n📋 SERVICIOS:")
servicios = ServicioRealizado.objects.filter(
    fecha_hora__date__gte=hace_7_dias, 
    estado='finalizado'
).order_by('-fecha_hora')
print(f"   Total: {servicios.count()}")
for srv in servicios[:10]:
    nombre = srv.estilista.nombre if srv.estilista else "Sin estilista"
    print(f"   - {srv.fecha_hora.date()}: {nombre} (${srv.precio_cobrado})")

print("\n🛍️  VENTAS:")
ventas = VentaProducto.objects.filter(fecha_hora__date__gte=hace_7_dias).order_by('-fecha_hora')
print(f"   Total: {ventas.count()}")
for v in ventas[:10]:
    nombre = v.estilista.nombre if v.estilista else "Sin estilista"
    print(f"   - {v.fecha_hora.date()}: {nombre} (${v.total})")

print("\n📊 ESTADOS DE PAGO REGISTRADOS:")
estados = EstadoPagoEstilistaDia.objects.filter(
    fecha__gte=hace_7_dias
).order_by('-fecha')
print(f"   Total registros: {estados.count()}")
for ep in estados[:10]:
    print(f"   - {ep.fecha}: {ep.estilista.nombre} → {ep.estado}")

print("\n👥 ESTILISTAS ACTIVOS:")
for est in Estilista.objects.filter(activo=True):
    print(f"   - {est.nombre}")

print("\n" + "="*80)
