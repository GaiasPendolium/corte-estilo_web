from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


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


class VentaProducto(models.Model):
    """Modelo de Ventas de Productos"""

    MEDIOS_PAGO = [
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
        ('efectivo', 'Efectivo'),
        ('otros', 'Otros'),
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


class EstadoPagoEstilistaDia(models.Model):
    """Estado de pago por estilista y por día para control de cartera."""

    ESTADOS = [
        ('pendiente', 'Pendiente'),
        ('cancelado', 'Cancelado'),
    ]

    estilista = models.ForeignKey(
        Estilista,
        on_delete=models.CASCADE,
        related_name='estados_pago_diario',
        verbose_name='Estilista'
    )
    fecha = models.DateField(verbose_name='Fecha')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name='Estado Pago')
    notas = models.CharField(max_length=255, blank=True, null=True, verbose_name='Notas')
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        db_table = 'estado_pago_estilista_dia'
        verbose_name = 'Estado Pago Estilista Día'
        verbose_name_plural = 'Estados Pago Estilista Día'
        unique_together = ('estilista', 'fecha')
        ordering = ['-fecha', 'estilista__nombre']

    def __str__(self):
        return f"{self.estilista.nombre} - {self.fecha} - {self.estado}"
