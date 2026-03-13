from decimal import Decimal
from django.utils import timezone
from api.models import Usuario, Estilista, Servicio, Cliente, Producto, ServicioRealizado, VentaProducto, MovimientoInventario

now = timezone.now()

admin, created_admin = Usuario.objects.get_or_create(
    username="admin",
    defaults={
        "nombre_completo": "Administrador",
        "rol": "administrador",
        "activo": True,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    },
)
if created_admin:
    admin.set_password("admin123")
    admin.save(update_fields=["password"])

recep, created_recep = Usuario.objects.get_or_create(
    username="recep_demo",
    defaults={
        "nombre_completo": "Recepcion Demo",
        "rol": "recepcion",
        "activo": True,
        "is_staff": False,
        "is_superuser": False,
        "is_active": True,
    },
)
if created_recep:
    recep.set_password("demo123")
    recep.save(update_fields=["password"])

est1, _ = Estilista.objects.get_or_create(
    nombre="Laura Perez",
    defaults={
        "telefono": "3001112233",
        "email": "laura@example.com",
        "comision_porcentaje": Decimal("35.00"),
        "tipo_cobro_espacio": "porcentaje_neto",
        "valor_cobro_espacio": Decimal("10.00"),
        "comision_ventas_productos": Decimal("5.00"),
        "activo": True,
        "fecha_ingreso": now.date(),
    },
)

est2, _ = Estilista.objects.get_or_create(
    nombre="Camila Rojas",
    defaults={
        "telefono": "3004445566",
        "email": "camila@example.com",
        "comision_porcentaje": Decimal("40.00"),
        "tipo_cobro_espacio": "costo_fijo_neto",
        "valor_cobro_espacio": Decimal("200000.00"),
        "comision_ventas_productos": Decimal("3.00"),
        "activo": True,
        "fecha_ingreso": now.date(),
    },
)

srv1, _ = Servicio.objects.get_or_create(
    nombre="Corte Caballero",
    defaults={
        "descripcion": "Corte clasico con maquina y tijera",
        "precio": Decimal("25000.00"),
        "duracion_minutos": 35,
        "activo": True,
    },
)

srv2, _ = Servicio.objects.get_or_create(
    nombre="Color Completo",
    defaults={
        "descripcion": "Aplicacion de color completo",
        "precio": Decimal("120000.00"),
        "duracion_minutos": 120,
        "activo": True,
    },
)

cli1, _ = Cliente.objects.get_or_create(nombre="Maria Gomez", defaults={"telefono": "3110001122"})
cli2, _ = Cliente.objects.get_or_create(nombre="Juan Lopez", defaults={"telefono": "3120003344"})

prod1, _ = Producto.objects.get_or_create(
    codigo_barras="779900100001",
    defaults={
        "nombre": "Shampoo Hidratante",
        "marca": "CapilarPro",
        "presentacion": "500ml",
        "precio_compra": Decimal("18000.00"),
        "precio_venta": Decimal("32000.00"),
        "comision_estilista": Decimal("5.00"),
        "stock": 20,
        "stock_minimo": 5,
        "activo": True,
    },
)

prod2, _ = Producto.objects.get_or_create(
    codigo_barras="779900100002",
    defaults={
        "nombre": "Cera Mate",
        "marca": "StyleFix",
        "presentacion": "150g",
        "precio_compra": Decimal("12000.00"),
        "precio_venta": Decimal("25000.00"),
        "comision_estilista": Decimal("4.00"),
        "stock": 15,
        "stock_minimo": 4,
        "activo": True,
    },
)

ServicioRealizado.objects.get_or_create(
    estilista=est1,
    servicio=srv1,
    cliente=cli2,
    numero_factura="FS-DEMO-0001",
    defaults={
        "estado": "finalizado",
        "fecha_inicio": now,
        "fecha_fin": now,
        "fecha_hora": now,
        "precio_cobrado": Decimal("25000.00"),
        "medio_pago": "efectivo",
        "tipo_reparto_establecimiento": "porcentaje",
        "valor_reparto_establecimiento": Decimal("30.00"),
        "monto_establecimiento": Decimal("7500.00"),
        "monto_estilista": Decimal("17500.00"),
        "factura_texto": "Factura demo servicio 1",
        "notas": "Servicio de prueba",
    },
)

ServicioRealizado.objects.get_or_create(
    estilista=est2,
    servicio=srv2,
    cliente=cli1,
    numero_factura="FS-DEMO-0002",
    defaults={
        "estado": "finalizado",
        "fecha_inicio": now,
        "fecha_fin": now,
        "fecha_hora": now,
        "precio_cobrado": Decimal("120000.00"),
        "medio_pago": "nequi",
        "tipo_reparto_establecimiento": "monto",
        "valor_reparto_establecimiento": Decimal("50000.00"),
        "monto_establecimiento": Decimal("50000.00"),
        "monto_estilista": Decimal("70000.00"),
        "factura_texto": "Factura demo servicio 2",
        "notas": "Servicio de color de prueba",
    },
)

VentaProducto.objects.get_or_create(
    producto=prod1,
    cantidad=1,
    numero_factura="FP-DEMO-0001",
    defaults={
        "precio_unitario": Decimal("32000.00"),
        "total": Decimal("32000.00"),
        "cliente_nombre": "Maria Gomez",
        "medio_pago": "daviplata",
        "estilista": est1,
        "factura_texto": "Factura demo producto 1",
        "fecha_hora": now,
        "usuario": recep,
    },
)

VentaProducto.objects.get_or_create(
    producto=prod2,
    cantidad=2,
    numero_factura="FP-DEMO-0002",
    defaults={
        "precio_unitario": Decimal("25000.00"),
        "total": Decimal("50000.00"),
        "cliente_nombre": "Juan Lopez",
        "medio_pago": "efectivo",
        "estilista": est2,
        "factura_texto": "Factura demo producto 2",
        "fecha_hora": now,
        "usuario": recep,
    },
)

MovimientoInventario.objects.get_or_create(
    producto=prod1,
    tipo_movimiento="entrada",
    cantidad=20,
    descripcion="Carga inicial demo shampoo",
    usuario=recep,
)
MovimientoInventario.objects.get_or_create(
    producto=prod2,
    tipo_movimiento="entrada",
    cantidad=15,
    descripcion="Carga inicial demo cera",
    usuario=recep,
)

print("Seed completado")
print("Usuarios:", Usuario.objects.count())
print("Estilistas:", Estilista.objects.count())
print("Servicios:", Servicio.objects.count())
print("Clientes:", Cliente.objects.count())
print("Productos:", Producto.objects.count())
print("ServiciosRealizados:", ServicioRealizado.objects.count())
print("VentasProductos:", VentaProducto.objects.count())
print("MovimientosInventario:", MovimientoInventario.objects.count())
