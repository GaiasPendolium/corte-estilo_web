import inspect

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


def default_ui_permissions():
    return {}


# El kwarg de CheckConstraint para la condición se llamó "check" en versiones
# viejas de Django y pasó a llamarse "condition" en versiones más nuevas (se
# vieron ambas variantes instaladas en distintos entornos de este proyecto).
# Se detecta en tiempo de import para que la migración/arranque no dependa de
# qué build exacto de Django tenga cada máquina.
_CHECK_CONSTRAINT_KWARG = (
    'condition' if 'condition' in inspect.signature(models.CheckConstraint.__init__).parameters else 'check'
)


def _check_constraint(condition, **kwargs):
    return models.CheckConstraint(**{_CHECK_CONSTRAINT_KWARG: condition}, **kwargs)


class UsuarioManager(BaseUserManager):
    """Manager personalizado para el modelo Usuario"""
    
    def create_user(self, username, password=None, **extra_fields):
        """Crea y guarda un usuario regular"""
        if not username:
            raise ValueError('El usuario debe tener un nombre de usuario')
        
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password=None, **extra_fields):
        """Crea y guarda un superusuario"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('rol', 'administrador')
        extra_fields.setdefault('activo', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')
        
        return self.create_user(username, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Modelo personalizado de Usuario"""
    
    ROLES = [
        ('administrador', 'Administrador'),
        ('gerente', 'Gerente'),
        ('recepcion', 'Recepción'),
    ]
    
    username = models.CharField(max_length=150, unique=True, verbose_name='Usuario')
    nombre_completo = models.CharField(max_length=255, verbose_name='Nombre Completo')
    rol = models.CharField(max_length=20, choices=ROLES, default='recepcion', verbose_name='Rol')
    permisos_ui = models.JSONField(default=default_ui_permissions, blank=True, verbose_name='Permisos UI')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_creacion = models.DateTimeField(default=timezone.now, verbose_name='Fecha de Creación')
    
    # Campos requeridos por Django para autenticación
    is_staff = models.BooleanField(default=False, verbose_name='Es staff')
    is_active = models.BooleanField(default=True, verbose_name='Es activo')
    
    objects = UsuarioManager()
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['nombre_completo']
    
    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"{self.username} - {self.nombre_completo}"


class Estilista(models.Model):
    """Modelo de Estilista"""
    
    TIPOS_COBRO_ESPACIO = [
        ('sin_cobro', 'Sin cobro (100% empleado)'),
        ('porcentaje_neto', '% sobre neto del empleado'),
        ('costo_fijo_neto', 'Costo fijo sobre neto del empleado'),
    ]

    nombre = models.CharField(max_length=255, verbose_name='Nombre')
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    comision_porcentaje = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0, 
        verbose_name='Comisión (%)'
    )
    tipo_cobro_espacio = models.CharField(
        max_length=20,
        choices=TIPOS_COBRO_ESPACIO,
        default='ninguno',
        verbose_name='Tipo Cobro Espacio'
    )
    valor_cobro_espacio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Valor Cobro Espacio'
    )
    comision_ventas_productos = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Comisión Ventas Productos (%)'
    )
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_ingreso = models.DateField(blank=True, null=True, verbose_name='Fecha de Ingreso')

    # Datos de pago electrónico del empleado (régimen "solo efectivo"): el
    # cliente le paga directo a él, no al negocio. El QR es la imagen real
    # que ya emite el banco/billetera del empleado (no se genera, se sube).
    qr_nequi = models.ImageField(upload_to='qr_empleados/nequi/', blank=True, null=True, verbose_name='QR Nequi')
    qr_daviplata = models.ImageField(upload_to='qr_empleados/daviplata/', blank=True, null=True, verbose_name='QR Daviplata')
    qr_otros = models.ImageField(upload_to='qr_empleados/otros/', blank=True, null=True, verbose_name='QR otro medio')
    datos_transferencia = models.TextField(
        blank=True, null=True, verbose_name='Datos de transferencia',
        help_text='Banco, número de cuenta, titular -- para cuando el cliente prefiere transferir en vez de escanear.',
    )

    class Meta:
        db_table = 'estilistas'
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre


class Servicio(models.Model):
    """Modelo de Servicio"""
    
    nombre = models.CharField(max_length=255, verbose_name='Nombre')
    descripcion = models.TextField(blank=True, null=True, verbose_name='Descripción')
    precio = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio')
    duracion_minutos = models.IntegerField(blank=True, null=True, verbose_name='Duración (minutos)')
    es_adicional = models.BooleanField(default=False, verbose_name='Es Servicio Adicional')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    
    class Meta:
        db_table = 'servicios'
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} - ${self.precio}"


class Cliente(models.Model):
    """Modelo de Cliente"""

    nombre = models.CharField(max_length=255, verbose_name='Nombre')
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    fecha_nacimiento = models.DateField(blank=True, null=True, verbose_name='Fecha de Nacimiento')
    fecha_creacion = models.DateTimeField(default=timezone.now, verbose_name='Fecha de Creación')

    class Meta:
        db_table = 'clientes'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    """Modelo de Producto (Inventario)"""
    
    codigo_barras = models.CharField(
        max_length=50, 
        unique=True, 
        blank=True, 
        null=True, 
        verbose_name='Código de Barras'
    )
    nombre = models.CharField(max_length=255, verbose_name='Nombre')
    marca = models.CharField(max_length=120, blank=True, null=True, verbose_name='Marca')
    presentacion = models.CharField(max_length=120, blank=True, null=True, verbose_name='Presentación')
    descripcion = models.TextField(blank=True, null=True, verbose_name='Descripción')
    precio_compra = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        verbose_name='Precio de Compra'
    )
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio de Venta')
    comision_estilista = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Comisión Estilista (%)'
    )
    stock = models.IntegerField(default=0, verbose_name='Stock')
    stock_minimo = models.IntegerField(default=5, verbose_name='Stock Mínimo')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    
    class Meta:
        db_table = 'productos'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} (Stock: {self.stock})"
    
    @property
    def necesita_reposicion(self):
        """Verifica si el producto necesita reposición"""
        return self.stock <= self.stock_minimo


class ServicioRealizado(models.Model):
    """Modelo de Servicios Realizados"""

    ESTADOS = [
        ('en_proceso', 'En Proceso'),
        ('finalizado', 'Finalizado'),
    ]

    MEDIOS_PAGO = [
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
        ('efectivo', 'Efectivo'),
        ('otros', 'Otros'),
    ]

    TIPOS_REPARTO = [
        ('porcentaje', 'Porcentaje'),
        ('monto', 'Monto Fijo'),
    ]
    
    estilista = models.ForeignKey(
        Estilista, 
        on_delete=models.PROTECT, 
        related_name='servicios_realizados',
        verbose_name='Estilista'
    )
    servicio = models.ForeignKey(
        Servicio, 
        on_delete=models.PROTECT, 
        related_name='servicios_realizados',
        verbose_name='Servicio'
    )
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        related_name='servicios_realizados',
        null=True,
        blank=True,
        verbose_name='Cliente'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='en_proceso',
        verbose_name='Estado'
    )
    fecha_inicio = models.DateTimeField(default=timezone.now, verbose_name='Fecha Inicio')
    fecha_fin = models.DateTimeField(blank=True, null=True, verbose_name='Fecha Fin')
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name='Fecha y Hora')
    precio_cobrado = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Precio Cobrado')
    medio_pago = models.CharField(
        max_length=20,
        choices=MEDIOS_PAGO,
        blank=True,
        null=True,
        verbose_name='Medio de Pago'
    )
    tipo_reparto_establecimiento = models.CharField(
        max_length=20,
        choices=TIPOS_REPARTO,
        blank=True,
        null=True,
        verbose_name='Tipo Reparto Establecimiento'
    )
    valor_reparto_establecimiento = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Valor Reparto Establecimiento'
    )
    monto_establecimiento = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Monto Establecimiento')
    monto_estilista = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Monto Estilista')
    neto_servicio = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Neto Servicio')
    tiene_adicionales = models.BooleanField(default=False, verbose_name='Tiene Adicionales')
    adicional_shampoo = models.BooleanField(default=False, verbose_name='Adicional Shampoo')
    adicional_guantes = models.BooleanField(default=False, verbose_name='Adicional Guantes')
    adicional_otro_producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='servicios_adicionales',
        verbose_name='Adicional Otro Producto'
    )
    adicional_otro_estilista = models.ForeignKey(
        Estilista,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='servicios_adicional_producto_comision',
        verbose_name='Estilista comisión producto adicional'
    )
    adicional_otro_cantidad = models.IntegerField(default=1, verbose_name='Cantidad Adicional Otro')
    valor_adicionales = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Valor Adicionales')
    numero_factura = models.CharField(max_length=40, blank=True, null=True, verbose_name='Número Factura')
    factura_texto = models.TextField(blank=True, null=True, verbose_name='Texto Factura')
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='servicios_facturados',
        verbose_name='Usuario Facturador'
    )
    cobrado_por = models.ForeignKey(
        Estilista,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='servicios_cobrados_de_companeros',
        verbose_name='Cobrado por (si fue otro empleado)',
        help_text='Empleado que efectivamente recibió el pago electrónico de este servicio, si fue distinto al que lo realizó (servicios cobrados en conjunto).',
    )
    notas = models.TextField(blank=True, null=True, verbose_name='Notas')

    class Meta:
        db_table = 'servicios_realizados'
        verbose_name = 'Servicio Realizado'
        verbose_name_plural = 'Servicios Realizados'
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.servicio.nombre} - {self.estilista.nombre} - {self.fecha_hora.strftime('%Y-%m-%d %H:%M')}"


class ServicioRealizadoAdicional(models.Model):
    """Detalle de servicios adicionales cobrados dentro de un servicio principal."""

    servicio_realizado = models.ForeignKey(
        ServicioRealizado,
        on_delete=models.CASCADE,
        related_name='adicionales_asignados',
        verbose_name='Servicio realizado'
    )
    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.PROTECT,
        related_name='adicionales_realizados',
        verbose_name='Servicio adicional'
    )
    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.PROTECT,
        related_name='servicios_adicionales_realizados',
        verbose_name='Empleado que realiza adicional'
    )
    valor_cobrado = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Valor cobrado')
    aplica_porcentaje_establecimiento = models.BooleanField(default=False, verbose_name='Aplica porcentaje establecimiento')
    porcentaje_establecimiento = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Porcentaje establecimiento')
    fecha_creacion = models.DateTimeField(default=timezone.now, verbose_name='Fecha de creación')

    class Meta:
        db_table = 'servicios_realizados_adicionales'
        verbose_name = 'Servicio adicional realizado'
        verbose_name_plural = 'Servicios adicionales realizados'
        ordering = ['servicio_realizado_id', 'id']

    def __str__(self):
        return f"{self.servicio.nombre} - {self.estilista.nombre} (${self.valor_cobrado})"


class VentaProducto(models.Model):
    """Modelo de Ventas de Productos"""

    MEDIOS_PAGO = [
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
        ('efectivo', 'Efectivo'),
        ('otros', 'Otros'),
    ]

    TIPOS_OPERACION = [
        ('venta', 'Venta'),
        ('consumo_empleado', 'Consumo empleado'),
    ]
    
    producto = models.ForeignKey(
        Producto, 
        on_delete=models.PROTECT, 
        related_name='ventas',
        verbose_name='Producto'
    )
    cantidad = models.IntegerField(verbose_name='Cantidad')
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Precio Unitario')
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Total')
    cliente_nombre = models.CharField(max_length=255, blank=True, null=True, verbose_name='Nombre Cliente')
    medio_pago = models.CharField(max_length=20, choices=MEDIOS_PAGO, verbose_name='Medio de Pago', default='efectivo')
    tipo_operacion = models.CharField(
        max_length=30,
        choices=TIPOS_OPERACION,
        default='venta',
        verbose_name='Tipo de Operación'
    )
    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ventas_productos',
        verbose_name='Estilista'
    )
    numero_factura = models.CharField(max_length=40, blank=True, null=True, verbose_name='Número Factura')
    factura_texto = models.TextField(blank=True, null=True, verbose_name='Texto Factura')
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name='Fecha y Hora')
    usuario = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='ventas',
        verbose_name='Usuario'
    )
    deuda_consumo = models.ForeignKey(
        'DeudaConsumoEmpleado',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ventas_items',
        verbose_name='Deuda consumo'
    )
    
    class Meta:
        db_table = 'ventas_productos'
        verbose_name = 'Venta de Producto'
        verbose_name_plural = 'Ventas de Productos'
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.producto.nombre} x{self.cantidad} - ${self.total}"


class MovimientoInventario(models.Model):
    """Modelo de Movimientos de Inventario"""
    
    TIPOS_MOVIMIENTO = [
        ('entrada', 'Entrada'),
        ('salida', 'Salida'),
        ('ajuste', 'Ajuste'),
    ]
    
    producto = models.ForeignKey(
        Producto, 
        on_delete=models.PROTECT, 
        related_name='movimientos',
        verbose_name='Producto'
    )
    tipo_movimiento = models.CharField(
        max_length=20, 
        choices=TIPOS_MOVIMIENTO, 
        verbose_name='Tipo de Movimiento'
    )
    cantidad = models.IntegerField(verbose_name='Cantidad')
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name='Fecha y Hora')
    descripcion = models.TextField(blank=True, null=True, verbose_name='Descripción')
    usuario = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='movimientos_inventario',
        verbose_name='Usuario'
    )
    
    class Meta:
        db_table = 'movimientos_inventario'
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario'
        ordering = ['-fecha_hora']
    
    def __str__(self):
        return f"{self.tipo_movimiento} - {self.producto.nombre} ({self.cantidad})"


class DeudaConsumoEmpleado(models.Model):
    """Cuenta por cobrar por consumo de productos del empleado."""

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('parcial', 'Parcial'),
        ('cancelado', 'Cancelado'),
    ]

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.PROTECT,
        related_name='deudas_consumo',
        verbose_name='Empleado'
    )
    numero_factura = models.CharField(max_length=40, unique=True, verbose_name='Numero Factura')
    total_cargo = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total Cargo')
    total_abonado = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Total Abonado')
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Saldo Pendiente')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name='Estado')
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name='Fecha y Hora')
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deudas_consumo_registradas',
        verbose_name='Usuario'
    )
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')

    class Meta:
        db_table = 'deudas_consumo_empleado'
        verbose_name = 'Deuda Consumo Empleado'
        verbose_name_plural = 'Deudas Consumo Empleado'
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"{self.numero_factura} - {self.estilista.nombre} - {self.estado}"


class AbonoDeudaEmpleado(models.Model):
    """Registro de abonos aplicados a deudas de consumo de empleados."""

    MEDIOS_PAGO = [
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
        ('efectivo', 'Efectivo'),
        ('otros', 'Otros'),
    ]

    deuda = models.ForeignKey(
        DeudaConsumoEmpleado,
        on_delete=models.CASCADE,
        related_name='abonos',
        verbose_name='Deuda'
    )
    monto = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Monto Abono')
    medio_pago = models.CharField(max_length=20, choices=MEDIOS_PAGO, default='efectivo', verbose_name='Medio de Pago')
    fecha_hora = models.DateTimeField(default=timezone.now, verbose_name='Fecha y Hora')
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_deuda_empleado',
        verbose_name='Usuario'
    )
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    origen_liquidacion_fecha = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de la liquidación que generó este abono',
        help_text='Fecha operativa de la liquidación (solo efectivo) que aplicó este abono automáticamente, para poder revertirlo si se elimina esa liquidación.',
    )

    class Meta:
        db_table = 'abonos_deuda_empleado'
        verbose_name = 'Abono Deuda Empleado'
        verbose_name_plural = 'Abonos Deuda Empleado'
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"Abono {self.deuda.numero_factura}: ${self.monto}"


class EstadoPagoEstilistaDia(models.Model):
    """
    Estado de pago por estilista y por día - LIQUIDADOR SIMPLIFICADO
    
    ESTRUCTURA CLARA:
    1. ganancias_totales = servicios base + comisiones caja + comisiones adicionales
    2. descuento_puesto = ganancias_totales × % (o costo fijo)
    3. total_pagable = ganancias_totales del empleado
    4. total_pagado = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
    5. saldo_pendiente_puesto = max(descuento_puesto - abono_puesto, 0)
    
    TODO SE CALCULA Y SE GUARDA AQUÍ PARA CLARIDAD TOTAL.
    """

    ESTADOS = [
        ('pendiente', 'Pendiente de pago'),
        ('debe', 'Con deuda del puesto'),
        ('cancelado', 'Pagado/Cancelado'),
    ]

    # IDENTIFCACIÓN
    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='estados_pago_diario',
        verbose_name='Estilista'
    )
    fecha = models.DateField(verbose_name='Fecha del día')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name='Estado')
    
    # [1] GANANCIAS DEL DÍA (CÁLCULO BASE)
    ganancias_totales = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Ganancias totales (servicios + comisiones)'
    )
    
    # [2] DESCUENTO POR PUESTO (GASTO FIJO/VARIABLE)
    descuento_puesto = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Descuento por alquiler puesto/espacio'
    )
    
    # [3] TOTAL PAGABLE AL EMPLEADO
    # El descuento del puesto genera deuda aparte y no reduce el pago al empleado.
    total_pagable = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Total pagable al empleado'
    )
    
    # [4] PAGOS DESGLOSADOS (cómo se pagó)
    pago_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pago efectivo')
    pago_nequi = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pago Nequi')
    pago_daviplata = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pago Daviplata')
    pago_otros = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pago otros')
    
    # Cálculo automático: total_pagado
    @property
    def total_pagado(self):
        """Suma de todos los medios de pago"""
        return self.pago_efectivo + self.pago_nequi + self.pago_daviplata + self.pago_otros
    
    # [5] PUESTO: ABONO Y DEUDA
    abono_puesto = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Abono realizado al puesto'
    )

    medio_abono_puesto = models.CharField(
        max_length=20,
        choices=[
            ('efectivo', 'Efectivo'),
            ('nequi', 'Nequi'),
            ('daviplata', 'Daviplata'),
            ('otros', 'Otros'),
        ],
        default='efectivo',
        verbose_name='Medio de pago abono puesto'
    )
    
    saldo_puesto_pendiente = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Saldo pendiente del puesto después de pago'
    )
    
    # CAMPOS LEGACY (compatibilidad)
    neto_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Neto del día (DEPRECATED)', null=True, blank=True)
    pendiente_puesto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pendiente puesto (DEPRECATED)', null=True, blank=True)
    
    # CONFIGURACIÓN DE LIQUIDACIÓN
    skip_descuento_puesto = models.BooleanField(
        default=False,
        verbose_name='Omitir descuento de puesto',
        help_text='Si es True, ese día NO se descuenta puesto del pago. El descuento se suma a la deuda.'
    )
    saltar_descuento_consumo = models.BooleanField(
        default=False,
        verbose_name='Omitir descuento de consumo',
        help_text='Análogo a skip_descuento_puesto pero para la deuda de consumo de productos del empleado.'
    )
    skip_descuento_vale = models.BooleanField(
        default=False,
        verbose_name='Omitir descuento de Vale',
        help_text='Análogo a skip_descuento_puesto pero para el Vale (deuda entre empleados). Si es True, ese día no se descuenta y el Vale queda pendiente para otro día.'
    )

    # RÉGIMEN "SOLO EFECTIVO" (desde la fecha de corte LIQUIDACION_CASH_ONLY_DESDE):
    # el negocio ya no recibe Nequi/Daviplata en su cuenta -- ese dinero lo recibe
    # directo el empleado. Estos campos son informativos/de cálculo para ese
    # régimen; para fechas anteriores al corte quedan en su valor por defecto.
    ganancia_efectivo_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Ganancia del día pagada en efectivo (dinero real en caja)'
    )
    ganancia_electronica_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Ganancia del día pagada por medio electrónico (informativo, ya en manos del empleado)'
    )
    ganancia_electronica_nequi = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Ganancia electrónica Nequi')
    ganancia_electronica_daviplata = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Ganancia electrónica Daviplata')
    ganancia_electronica_otros = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Ganancia electrónica otros')
    comision_producto_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Comisión por venta/consumo de producto del día',
        help_text='No es efectivo físico en mano del empleado (ya entró a caja al vender el producto); solo sirve para cubrir deducciones.'
    )
    reparto_establecimiento_electronico_pendiente = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='% de establecimiento de servicios pagados electrónico, pendiente de recuperar',
        help_text='Se suma a las deducciones del día (el negocio siempre recupera su parte).'
    )
    descuento_consumo_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Deuda de consumo aplicada/cobrada ese día'
    )
    descuento_vale_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Vale (deuda entre empleados) aplicado/cobrado ese día'
    )
    total_deducciones_dia = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Total deducciones del día (puesto + consumo + vale + reparto electrónico pendiente)'
    )
    monto_transferir_empleado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Monto que el empleado debe transferir (si el efectivo no alcanzó para cubrir deducciones)'
    )
    monto_transferir_recibido = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Monto ya confirmado recibido de la transferencia del empleado'
    )
    monto_pagar_establecimiento = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Monto que el negocio debe entregar en efectivo al empleado (sobrante tras deducciones)'
    )
    monto_pagar_entregado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name='Monto ya confirmado entregado al empleado'
    )
    motor_calculo = models.CharField(
        max_length=20, default='v2_mixed',
        verbose_name='Motor de cálculo usado',
        help_text="'v2_mixed' (legacy, Nequi/Daviplata entraban a caja) o 'v3_efectivo' (solo efectivo)."
    )

    @property
    def pendiente_transferencia_empleado(self):
        return max(self.monto_transferir_empleado - self.monto_transferir_recibido, 0)

    @property
    def pendiente_pago_empleado_efectivo(self):
        return max(self.monto_pagar_establecimiento - self.monto_pagar_entregado, 0)

    # AUDITORÍA
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    usuario_liquida = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='liquidaciones_realizadas',
        verbose_name='Usuario que realizó la liquidación'
    )
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        db_table = 'estado_pago_estilista_dia'
        verbose_name = 'Estado Pago Estilista Día'
        verbose_name_plural = 'Estados Pago Estilista Día'
        unique_together = ('estilista', 'fecha')
        ordering = ['-fecha', 'estilista__nombre']

    def __str__(self):
        return f"{self.estilista.nombre} - {self.fecha} - {self.estado}"


class EstadoPagoEstilistaHistorial(models.Model):
    """Bitácora de cambios de estado de pago por día y estilista."""

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('debe', 'Debe'),
        ('cancelado', 'Cancelado'),
    ]

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='historial_estados_pago',
        verbose_name='Estilista'
    )
    fecha = models.DateField(verbose_name='Fecha Afectada')
    estado_anterior = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name='Estado Anterior')
    estado_nuevo = models.CharField(max_length=20, choices=ESTADOS, verbose_name='Estado Nuevo')
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cambios_estado_pago',
        verbose_name='Usuario'
    )
    monto_liquidado = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Monto liquidado')
    abono_puesto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Abono puesto')
    medio_abono_puesto = models.CharField(
        max_length=20,
        choices=[
            ('efectivo', 'Efectivo'),
            ('nequi', 'Nequi'),
            ('daviplata', 'Daviplata'),
            ('otros', 'Otros'),
        ],
        default='efectivo',
        verbose_name='Medio abono puesto'
    )
    pendiente_puesto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Pendiente puesto')
    fecha_cambio = models.DateTimeField(default=timezone.now, verbose_name='Fecha Cambio')

    # Régimen "solo efectivo" -- ver EstadoPagoEstilistaDia para el detalle de estos campos.
    descuento_consumo_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Descuento consumo del día')
    descuento_vale_dia = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Vale (deuda entre empleados) aplicado del día')
    monto_transferir_empleado = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Monto a transferir por el empleado')
    monto_pagar_establecimiento = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Monto a pagar por el establecimiento')
    motor_calculo = models.CharField(max_length=20, default='v2_mixed', verbose_name='Motor de cálculo usado')

    class Meta:
        db_table = 'estado_pago_estilista_historial'
        verbose_name = 'Historial Estado Pago Estilista'
        verbose_name_plural = 'Historial Estados Pago Estilista'
        ordering = ['-fecha_cambio', '-fecha']

    def __str__(self):
        return f"{self.estilista.nombre} {self.fecha}: {self.estado_anterior} -> {self.estado_nuevo}"


class FactLiquidacionEstilistaDia(models.Model):
    """Hecho diario consolidado de liquidación por empleado con versionado."""

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('debe', 'Debe'),
        ('cancelado', 'Cancelado'),
    ]

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.PROTECT,
        related_name='facts_liquidacion_diaria',
        verbose_name='Empleado'
    )
    fecha = models.DateField(verbose_name='Fecha operativa')
    version = models.PositiveIntegerField(default=1, verbose_name='Version de calculo')
    vigente = models.BooleanField(default=True, verbose_name='Version vigente')
    origen_calculo = models.CharField(max_length=40, default='engine_v2', verbose_name='Origen calculo')

    ganancias_servicios = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comision_producto_caja = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    comision_producto_servicios = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    aplica_comision_ventas = models.BooleanField(default=True)
    ganancias_totales = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    descuento_puesto_dia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deuda_puesto_anterior = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    abono_puesto_dia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    medio_abono_puesto = models.CharField(
        max_length=20,
        choices=[
            ('efectivo', 'Efectivo'),
            ('nequi', 'Nequi'),
            ('daviplata', 'Daviplata'),
            ('otros', 'Otros'),
        ],
        default='efectivo',
        verbose_name='Medio abono puesto'
    )
    deuda_puesto_cierre = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    pago_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pago_nequi = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pago_daviplata = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pago_otros = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pago_total_empleado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pendiente_pago_empleado = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    cobro_consumo_dia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    saltar_descuento_consumo = models.BooleanField(default=False)
    descuento_vale_dia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    estado_liquidacion = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    forzar_reemplazo_dia = models.BooleanField(default=False)

    # Régimen "solo efectivo" -- ver EstadoPagoEstilistaDia para el detalle.
    ganancia_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ganancia_electronica = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ganancia_electronica_nequi = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ganancia_electronica_daviplata = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ganancia_electronica_otros = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reparto_establecimiento_electronico_pendiente = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deducciones_dia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_transferir_empleado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_transferir_recibido = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_pagar_establecimiento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_pagar_entregado = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    usuario_liquida = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='facts_liquidacion_generados',
    )
    notas = models.TextField(blank=True, null=True)
    payload_fuente = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fact_liquidacion_estilista_dia'
        verbose_name = 'Fact Liquidacion Estilista Dia'
        verbose_name_plural = 'Facts Liquidacion Estilista Dia'
        ordering = ['-fecha', 'estilista__nombre', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['estilista', 'fecha', 'version'],
                name='uq_fact_liq_est_fecha_ver',
            ),
            models.UniqueConstraint(
                fields=['estilista', 'fecha'],
                condition=models.Q(vigente=True),
                name='uq_fact_liq_est_fecha_vigente',
            ),
        ]
        indexes = [
            models.Index(fields=['fecha'], name='ix_fact_liq_fecha'),
            models.Index(fields=['estilista', '-fecha'], name='ix_fact_liq_est_fecha'),
            models.Index(fields=['estado_liquidacion', '-fecha'], name='ix_fact_liq_estado_fecha'),
        ]

    def __str__(self):
        return f"{self.estilista.nombre} {self.fecha} v{self.version} ({'vigente' if self.vigente else 'historico'})"


class SaldoDeudaPuesto(models.Model):
    """
    Una fila por empleado. Fuente de verdad del saldo acumulado de deuda de puesto
    y deuda de consumo (facturas internas). Se incrementa/decrementa en cada operación
    para que bi_resumen siempre lea el valor correcto sin depender del filtro de fechas.
    """
    estilista = models.OneToOneField(
        Estilista,
        on_delete=models.CASCADE,
        related_name='saldo_deuda_puesto',
        verbose_name='Estilista',
    )
    saldo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Saldo acumulado deuda de puesto',
    )
    saldo_consumo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Saldo acumulado consumo empleado (facturas)',
    )
    saldo_vale = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Saldo acumulado de Vale (debe a compañeros)',
        help_text='Suma de los Vales pendientes donde este empleado es el deudor (cobró de más).',
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Saldo deuda de puesto'
        verbose_name_plural = 'Saldos deuda de puesto'

    def __str__(self):
        return f"{self.estilista.nombre}: puesto=${self.saldo} consumo=${self.saldo_consumo} vale=${self.saldo_vale}"


class PersonaCredito(models.Model):
    """
    Persona externa que puede tener un crédito sin ser empleado del
    establecimiento (no participa en servicios, liquidación ni ningún otro
    módulo operativo). Deliberadamente simple.
    """

    nombre = models.CharField(max_length=150, verbose_name='Nombre')
    telefono = models.CharField(max_length=20, blank=True, null=True, verbose_name='Teléfono')
    documento = models.CharField(max_length=30, blank=True, null=True, verbose_name='Documento')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de registro')

    class Meta:
        db_table = 'personas_credito'
        verbose_name = 'Persona con crédito'
        verbose_name_plural = 'Personas con crédito'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Credito(models.Model):
    """
    Modelo para gestionar créditos otorgados a empleados o a personas
    externas (PersonaCredito). Completamente independiente del sistema de
    deudas y facturas.
    """

    ESTADOS = [
        ('activo', 'Activo'),
        ('cancelado', 'Cancelado'),
        ('vencido', 'Vencido'),
        ('proximo_vencer', 'Próximo a vencer'),
    ]

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='creditos',
        verbose_name='Empleado',
        null=True,
        blank=True,
    )

    persona_credito = models.ForeignKey(
        PersonaCredito,
        on_delete=models.CASCADE,
        related_name='creditos',
        verbose_name='Persona externa',
        null=True,
        blank=True,
    )

    valor_prestado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Valor prestado'
    )
    
    porcentaje_interes = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='Porcentaje de interés (%)'
    )
    
    valor_interes = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Valor del interés'
    )
    
    valor_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Valor total (prestado + interés)'
    )
    
    saldo_actual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Saldo actual pendiente'
    )
    
    fecha_inicio = models.DateField(verbose_name='Fecha de inicio')
    
    plazo_dias = models.IntegerField(
        default=30,
        verbose_name='Plazo en días'
    )
    
    fecha_vencimiento = models.DateField(verbose_name='Fecha de vencimiento')
    
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='activo',
        verbose_name='Estado'
    )
    
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones'
    )
    
    usuario_creador = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creditos_creados',
        verbose_name='Usuario que creó el crédito'
    )
    
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )

    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name='Última actualización'
    )

    usuario_editor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='creditos_editados',
        verbose_name='Usuario que modificó el crédito'
    )

    class Meta:
        db_table = 'creditos'
        verbose_name = 'Crédito'
        verbose_name_plural = 'Créditos'
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['estilista', '-fecha_creacion']),
            models.Index(fields=['persona_credito', '-fecha_creacion']),
            models.Index(fields=['estado', '-fecha_creacion']),
            models.Index(fields=['fecha_vencimiento']),
        ]
        constraints = [
            _check_constraint(
                (
                    (models.Q(estilista__isnull=False) & models.Q(persona_credito__isnull=True))
                    | (models.Q(estilista__isnull=True) & models.Q(persona_credito__isnull=False))
                ),
                name='credito_titular_unico',
            ),
        ]

    @property
    def titular_tipo(self):
        return 'empleado' if self.estilista_id else 'persona'

    @property
    def titular_nombre(self):
        if self.estilista_id:
            return self.estilista.nombre
        if self.persona_credito_id:
            return self.persona_credito.nombre
        return None

    def __str__(self):
        return f"Crédito {self.id} - {self.titular_nombre}: ${self.valor_total} ({self.estado})"


class AbonoCredito(models.Model):
    """
    Modelo para registrar abonos a créditos.
    """
    
    credito = models.ForeignKey(
        Credito,
        on_delete=models.CASCADE,
        related_name='abonos',
        verbose_name='Crédito'
    )
    
    fecha = models.DateField(verbose_name='Fecha del abono')
    
    valor_abono = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Valor abonado'
    )
    
    saldo_anterior = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Saldo anterior'
    )
    
    saldo_restante = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Saldo restante después del abono'
    )
    
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones'
    )
    
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_credito',
        verbose_name='Usuario que registró el abono'
    )
    
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    
    class Meta:
        db_table = 'abonos_credito'
        verbose_name = 'Abono de Crédito'
        verbose_name_plural = 'Abonos de Crédito'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['credito', '-fecha']),
        ]
    
    def __str__(self):
        return f"Abono {self.id} - Crédito {self.credito.id}: ${self.valor_abono}"


class CreditoHistorial(models.Model):
    """
    Bitácora de auditoría de créditos y sus abonos, para trazabilidad y
    consultas administrativas. Se conserva de forma permanente incluso si el
    crédito referenciado llega a eliminarse (estilista queda como ancla).
    """

    ACCIONES = [
        ('credito_creado', 'Crédito creado'),
        ('credito_editado', 'Crédito editado'),
        ('credito_cancelado', 'Crédito cancelado'),
        ('credito_eliminado', 'Crédito eliminado'),
        ('abono_creado', 'Abono registrado'),
        ('abono_editado', 'Abono editado'),
        ('abono_eliminado', 'Abono eliminado'),
    ]

    credito = models.ForeignKey(
        Credito,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial',
        verbose_name='Crédito'
    )

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='historial_creditos',
        verbose_name='Empleado',
        null=True,
        blank=True,
    )

    persona_credito = models.ForeignKey(
        PersonaCredito,
        on_delete=models.CASCADE,
        related_name='historial_creditos',
        verbose_name='Persona externa',
        null=True,
        blank=True,
    )

    accion = models.CharField(max_length=30, choices=ACCIONES, verbose_name='Acción')

    detalle = models.TextField(blank=True, null=True, verbose_name='Detalle')

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_creditos_generado',
        verbose_name='Usuario'
    )

    fecha = models.DateTimeField(auto_now_add=True, verbose_name='Fecha')

    class Meta:
        db_table = 'creditos_historial'
        verbose_name = 'Historial de crédito'
        verbose_name_plural = 'Historial de créditos'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['estilista', '-fecha']),
            models.Index(fields=['persona_credito', '-fecha']),
            models.Index(fields=['credito', '-fecha']),
        ]

    @property
    def titular_nombre(self):
        if self.estilista_id:
            return self.estilista.nombre
        if self.persona_credito_id:
            return self.persona_credito.nombre
        return None

    def __str__(self):
        return f"{self.get_accion_display()} - {self.titular_nombre} ({self.fecha:%Y-%m-%d %H:%M})"


class DeudaEntreEmpleados(models.Model):
    """
    "Vale": cuando un cliente recibe servicios de varios empleados en una
    sola visita pero paga una sola vez -- electrónico, con el QR de uno
    solo de ellos, y a cada uno se le factura por separado su propio
    servicio (uno electrónico, los demás en efectivo aunque no haya
    entrado efectivo físico) -- el que cobró de más le queda debiendo a
    sus compañeros la parte que a cada uno le corresponde. Se registra
    manualmente aquí (no automático) y se descuenta en la liquidación del
    deudor como una deducción más (ver _aplicar_abonos_vale_interno),
    igual que la deuda de puesto o de consumo -- el establecimiento
    recupera esa plata del deudor y le paga a cada compañero lo suyo
    normalmente en su propia liquidación (su servicio ya quedó marcado en
    efectivo). `servicio_realizado` es opcional porque un Vale puede
    originarse de varios servicios de una misma visita, no de uno solo.
    """

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('pagado', 'Pagado'),
    ]

    deudor = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='deudas_entre_empleados_debe',
        verbose_name='Empleado que cobró de más (debe)',
    )
    acreedor = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='deudas_entre_empleados_le_deben',
        verbose_name='Empleado al que se le debe',
    )
    servicio_realizado = models.ForeignKey(
        ServicioRealizado,
        on_delete=models.CASCADE,
        related_name='deudas_entre_empleados',
        verbose_name='Servicio de origen',
        null=True,
        blank=True,
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Monto')
    monto_abonado = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Monto abonado')
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Saldo pendiente')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name='Estado')
    fecha = models.DateField(null=True, blank=True, verbose_name='Fecha del Vale (registro manual)')
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')

    class Meta:
        db_table = 'deudas_entre_empleados'
        verbose_name = 'Vale entre empleados'
        verbose_name_plural = 'Vales entre empleados'
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['deudor', 'estado']),
            models.Index(fields=['acreedor', 'estado']),
        ]

    def __str__(self):
        return f"{self.deudor.nombre} le debe {self.saldo_pendiente} a {self.acreedor.nombre}"


class AbonoDeudaEntreEmpleados(models.Model):
    """Registro de cuándo un empleado le transfirió/entregó a otro su parte."""

    deuda = models.ForeignKey(
        DeudaEntreEmpleados,
        on_delete=models.CASCADE,
        related_name='abonos',
        verbose_name='Deuda',
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Monto abonado')
    fecha = models.DateTimeField(default=timezone.now, verbose_name='Fecha del abono')
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_deuda_entre_empleados',
        verbose_name='Usuario que registró el abono',
    )
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    origen_liquidacion_fecha = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de la liquidación que generó este abono',
        help_text='Fecha operativa de la liquidación (solo efectivo) que aplicó este abono automáticamente al descontar el Vale, para poder revertirlo si se elimina esa liquidación.',
    )

    class Meta:
        db_table = 'abonos_deuda_entre_empleados'
        verbose_name = 'Abono deuda entre empleados'
        verbose_name_plural = 'Abonos deuda entre empleados'
        ordering = ['-fecha']

    def __str__(self):
        return f"Abono {self.monto} - {self.deuda}"

