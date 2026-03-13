from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import (
    Cliente,
    Estilista,
    MovimientoInventario,
    Producto,
    Servicio,
    ServicioRealizado,
    Usuario,
    VentaProducto,
)


class Command(BaseCommand):
    help = "Inserta datos de prueba para peluqueria (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()

        # Usuarios demo
        _, created_admin = Usuario.objects.get_or_create(
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
            _.set_password("admin123")
            _.save(update_fields=["password"])

        recepcionista, created_recep = Usuario.objects.get_or_create(
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
            recepcionista.set_password("demo123")
            recepcionista.save(update_fields=["password"])

        # Estilistas demo
        estilista_1, _ = Estilista.objects.get_or_create(
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

        estilista_2, _ = Estilista.objects.get_or_create(
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

        # Servicios demo
        corte, _ = Servicio.objects.get_or_create(
            nombre="Corte Caballero",
            defaults={
                "descripcion": "Corte clasico con maquina y tijera",
                "precio": Decimal("25000.00"),
                "duracion_minutos": 35,
                "activo": True,
            },
        )

        color, _ = Servicio.objects.get_or_create(
            nombre="Color Completo",
            defaults={
                "descripcion": "Aplicacion de color completo",
                "precio": Decimal("120000.00"),
                "duracion_minutos": 120,
                "activo": True,
            },
        )

        # Clientes demo
        cliente_1, _ = Cliente.objects.get_or_create(
            nombre="Maria Gomez",
            defaults={"telefono": "3110001122"},
        )
        cliente_2, _ = Cliente.objects.get_or_create(
            nombre="Juan Lopez",
            defaults={"telefono": "3120003344"},
        )

        # Productos demo
        prod_1, _ = Producto.objects.get_or_create(
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

        prod_2, _ = Producto.objects.get_or_create(
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

        # Servicio realizado finalizado
        sr_1, created_sr1 = ServicioRealizado.objects.get_or_create(
            estilista=estilista_1,
            servicio=corte,
            cliente=cliente_2,
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

        sr_2, created_sr2 = ServicioRealizado.objects.get_or_create(
            estilista=estilista_2,
            servicio=color,
            cliente=cliente_1,
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

        # Venta de producto demo
        vp_1, created_vp1 = VentaProducto.objects.get_or_create(
            producto=prod_1,
            cantidad=1,
            numero_factura="FP-DEMO-0001",
            defaults={
                "precio_unitario": Decimal("32000.00"),
                "total": Decimal("32000.00"),
                "cliente_nombre": "Maria Gomez",
                "medio_pago": "daviplata",
                "estilista": estilista_1,
                "factura_texto": "Factura demo producto 1",
                "fecha_hora": now,
                "usuario": recepcionista,
            },
        )

        vp_2, created_vp2 = VentaProducto.objects.get_or_create(
            producto=prod_2,
            cantidad=2,
            numero_factura="FP-DEMO-0002",
            defaults={
                "precio_unitario": Decimal("25000.00"),
                "total": Decimal("50000.00"),
                "cliente_nombre": "Juan Lopez",
                "medio_pago": "efectivo",
                "estilista": estilista_2,
                "factura_texto": "Factura demo producto 2",
                "fecha_hora": now,
                "usuario": recepcionista,
            },
        )

        # Movimientos de inventario demo
        MovimientoInventario.objects.get_or_create(
            producto=prod_1,
            tipo_movimiento="entrada",
            cantidad=20,
            descripcion="Carga inicial demo shampoo",
            usuario=recepcionista,
        )
        MovimientoInventario.objects.get_or_create(
            producto=prod_2,
            tipo_movimiento="entrada",
            cantidad=15,
            descripcion="Carga inicial demo cera",
            usuario=recepcionista,
        )

        self.stdout.write(self.style.SUCCESS("Datos de prueba insertados/actualizados."))
        self.stdout.write(
            f"Usuarios: {Usuario.objects.count()} | "
            f"Estilistas: {Estilista.objects.count()} | "
            f"Servicios: {Servicio.objects.count()} | "
            f"Clientes: {Cliente.objects.count()} | "
            f"Productos: {Producto.objects.count()} | "
            f"Servicios realizados creados ahora: {int(created_sr1) + int(created_sr2)} | "
            f"Ventas creadas ahora: {int(created_vp1) + int(created_vp2)}"
        )
