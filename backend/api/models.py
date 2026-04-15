from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


def default_ui_permissions():
    return {}


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
    estado_liquidacion = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    forzar_reemplazo_dia = models.BooleanField(default=False)

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
