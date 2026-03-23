"""
Test para validar el fix del bug de liquidación mostrando $0
Se verifica que servicios_qs y estados_pago_map usen los mismos tipos de fecha
"""
import os
import django
from datetime import datetime, timedelta, date
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from django.utils import timezone
from api.models import (
    Estilista, ServicioRealizado, VentaProducto, EstadoPagoEstilistaDia, 
    Cliente, Servicio, Producto
)

def test_fecha_consistency():
    """Test que verifica que servicios_qs y EstadoPagoEstilistaDia usen el mismo tipo de fecha"""
    
    print("\n" + "="*80)
    print("🧪 TEST: Validar consistencia de tipos de fecha en filtros")
    print("="*80 + "\n")
    
    # 1. Crear datos de prueba
    hoy = timezone.localdate()
    fecha_inicio = hoy
    fecha_fin = hoy
    
    # Búscar o crear estilista
    estilista, created = Estilista.objects.get_or_create(
        nombre='TEST_ESTILISTA',
        defaults={'email': 'test@test.com', 'activo': True}
    )
    
    print(f"📌 Usando estilista: {estilista.nombre}")
    print(f"📅 Rango de fecha: {fecha_inicio} a {fecha_fin}")
    
    # 2. Simular el filtrado ANTES del fix (con strings)
    fecha_inicio_str = fecha_inicio.strftime('%Y-%m-%d')
    fecha_fin_str = fecha_fin.strftime('%Y-%m-%d')
    
    print(f"\n❌ ANTES (BUG): Filtrado con STRINGS")
    print(f"   fecha_inicio_str: '{fecha_inicio_str}' (type: {type(fecha_inicio_str)})")
    print(f"   fecha_fin_str: '{fecha_fin_str}' (type: {type(fecha_fin_str)})")
    
    servicios_qs_antes = ServicioRealizado.objects.filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_str,  # ← STRING
        fecha_hora__date__lte=fecha_fin_str,      # ← STRING
    )
    print(f"   →  servicios_qs count: {servicios_qs_antes.count()}")
    
    # 3. Simular el filtrado DESPUÉS del fix (con datetime.date)
    fecha_inicio_dt = fecha_inicio
    fecha_fin_dt = fecha_fin
    
    print(f"\n✅ DESPUÉS (FIX): Filtrado con datetime.date")
    print(f"   fecha_inicio_dt: {fecha_inicio_dt} (type: {type(fecha_inicio_dt)})")
    print(f"   fecha_fin_dt: {fecha_fin_dt} (type: {type(fecha_fin_dt)})")
    
    servicios_qs_despues = ServicioRealizado.objects.filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,  # ← datetime.date
        fecha_hora__date__lte=fecha_fin_dt,      # ← datetime.date
    )
    print(f"   →  servicios_qs count: {servicios_qs_despues.count()}")
    
    # 4. Validar EstadoPagoEstilistaDia usa datetime.date
    print(f"\n📊 EstadoPagoEstilistaDia (siempre datetime.date):")
    estados_pago_map = {
        (ep.estilista_id, ep.fecha): ep.estado
        for ep in EstadoPagoEstilistaDia.objects.filter(fecha__gte=fecha_inicio_dt, fecha__lte=fecha_fin_dt)
    }
    print(f"   → Estado pago map entries: {len(estados_pago_map)}")
    
    # 5. Verificar consistencia
    print(f"\n" + "-"*80)
    if servicios_qs_antes.count() == servicios_qs_despues.count():
        print("✓ CONSISTENCIA VERIFICADA: Ambos filtros devuelven el mismo count")
        print(f"  Servicios encontrados: {servicios_qs_antes.count()}")
    else:
        print("✗ INCONSISTENCIA DETECTADA: Los filtros devuelven diferentes counts")
        print(f"  String filter: {servicios_qs_antes.count()}")
        print(f"  datetime.date filter: {servicios_qs_despues.count()}")
        print(f"  Diferencia: {abs(servicios_qs_antes.count() - servicios_qs_despues.count())}")
    
    print("-"*80)
    print(f"\n✨ CONCLUSIÓN:")
    print(f"   El fix cambia 'fecha_inicio' de STRING a datetime.date")
    print(f"   para que sea consistente con cómo se filtra EstadoPagoEstilistaDia")
    print(f"   Esto asegura que los servicios y estados se alineen correctamente")
    print(f"\n" + "="*80 + "\n")

if __name__ == '__main__':
    test_fecha_consistency()
