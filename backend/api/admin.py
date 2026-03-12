from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Usuario, Estilista, Servicio, Cliente, Producto, ServicioRealizado, VentaProducto, MovimientoInventario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    list_display = ('username', 'nombre_completo', 'rol', 'activo', 'fecha_creacion')
    list_filter = ('rol', 'activo', 'fecha_creacion')
    search_fields = ('username', 'nombre_completo')
    ordering = ('-fecha_creacion',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('nombre_completo', 'rol')}),
        ('Permisos', {'fields': ('activo', 'is_active', 'is_staff', 'is_superuser')}),
        ('Fechas importantes', {'fields': ('last_login', 'fecha_creacion')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'nombre_completo', 'rol', 'activo'),
        }),
    )


@admin.register(Estilista)
class EstilistaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'email', 'comision_porcentaje', 'tipo_cobro_espacio', 'valor_cobro_espacio', 'activo', 'fecha_ingreso')
    list_filter = ('activo', 'fecha_ingreso')
    search_fields = ('nombre', 'telefono', 'email')
    ordering = ('nombre',)


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio', 'duracion_minutos', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'descripcion')
    ordering = ('nombre',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'fecha_nacimiento', 'fecha_creacion')
    search_fields = ('nombre', 'telefono')
    ordering = ('nombre',)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'marca', 'presentacion', 'codigo_barras', 'precio_compra', 'precio_venta', 'comision_estilista', 'stock', 'stock_minimo', 'activo')
    list_filter = ('activo',)
    search_fields = ('nombre', 'marca', 'presentacion', 'codigo_barras', 'descripcion')
    ordering = ('nombre',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs


@admin.register(ServicioRealizado)
class ServicioRealizadoAdmin(admin.ModelAdmin):
    list_display = ('servicio', 'estilista', 'cliente', 'estado', 'fecha_hora', 'precio_cobrado', 'monto_estilista', 'monto_establecimiento')
    list_filter = ('estado', 'medio_pago', 'fecha_hora', 'estilista', 'servicio')
    search_fields = ('notas', 'cliente__nombre', 'estilista__nombre', 'servicio__nombre')
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)


@admin.register(VentaProducto)
class VentaProductoAdmin(admin.ModelAdmin):
    list_display = ('numero_factura', 'producto', 'cliente_nombre', 'estilista', 'medio_pago', 'cantidad', 'precio_unitario', 'total', 'fecha_hora', 'usuario')
    list_filter = ('fecha_hora', 'medio_pago')
    search_fields = ('numero_factura', 'cliente_nombre', 'producto__nombre', 'producto__codigo_barras')
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('producto', 'tipo_movimiento', 'cantidad', 'fecha_hora', 'usuario')
    list_filter = ('tipo_movimiento', 'fecha_hora')
    search_fields = ('producto__nombre', 'descripcion')
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)
