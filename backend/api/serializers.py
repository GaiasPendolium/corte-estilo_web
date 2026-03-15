from rest_framework import serializers
from django.utils import timezone
from .models import (
    Usuario, Estilista, Servicio, Cliente, Producto,
    ServicioRealizado, VentaProducto, MovimientoInventario
)


class UsuarioSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Usuario"""
    
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Usuario
        fields = [
            'id', 'username', 'password', 'nombre_completo',
            'rol', 'activo', 'fecha_creacion'
        ]
        read_only_fields = ['fecha_creacion']
    
    def create(self, validated_data):
        """Crear usuario con contraseña hasheada"""
        password = validated_data.pop('password', None)
        usuario = Usuario.objects.create(**validated_data)
        if password:
            usuario.set_password(password)
            usuario.save()
        return usuario
    
    def update(self, instance, validated_data):
        """Actualizar usuario, hasheando la contraseña si se proporciona"""
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance


class EstilistaSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Estilista"""
    
    servicios_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Estilista
        fields = [
            'id', 'nombre', 'telefono', 'email',
            'comision_porcentaje', 'tipo_cobro_espacio', 'valor_cobro_espacio', 'comision_ventas_productos',
            'activo', 'fecha_ingreso',
            'servicios_count'
        ]
    
    def get_servicios_count(self, obj):
        """Obtener el número de servicios realizados por el estilista"""
        return obj.servicios_realizados.count()


class ServicioSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Servicio"""
    
    class Meta:
        model = Servicio
        fields = [
            'id', 'nombre', 'descripcion', 'precio',
            'duracion_minutos', 'es_adicional', 'activo'
        ]


class ClienteSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Cliente"""

    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'telefono', 'fecha_nacimiento', 'fecha_creacion']
        read_only_fields = ['fecha_creacion']


class ProductoSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Producto"""
    
    necesita_reposicion = serializers.ReadOnlyField()
    
    class Meta:
        model = Producto
        fields = [
            'id', 'codigo_barras', 'nombre', 'marca', 'presentacion', 'descripcion',
            'precio_compra', 'precio_venta', 'comision_estilista', 'stock',
            'stock_minimo', 'activo', 'necesita_reposicion'
        ]


class ServicioRealizadoSerializer(serializers.ModelSerializer):
    """Serializador para el modelo ServicioRealizado"""
    
    estilista_nombre = serializers.CharField(source='estilista.nombre', read_only=True)
    servicio_nombre = serializers.CharField(source='servicio.nombre', read_only=True)
    servicio_duracion = serializers.IntegerField(source='servicio.duracion_minutos', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)
    adicional_otro_producto_nombre = serializers.CharField(source='adicional_otro_producto.nombre', read_only=True)
    
    class Meta:
        model = ServicioRealizado
        fields = [
            'id', 'estilista', 'estilista_nombre', 'servicio',
            'servicio_nombre', 'servicio_duracion', 'cliente', 'cliente_nombre',
            'usuario', 'usuario_nombre',
            'estado', 'fecha_inicio', 'fecha_fin', 'fecha_hora',
            'precio_cobrado', 'medio_pago', 'tipo_reparto_establecimiento',
            'valor_reparto_establecimiento', 'monto_establecimiento',
            'monto_estilista', 'neto_servicio', 'tiene_adicionales',
            'adicional_shampoo', 'adicional_guantes', 'adicional_otro_producto',
            'adicional_otro_producto_nombre', 'adicional_otro_cantidad', 'valor_adicionales',
            'numero_factura', 'factura_texto', 'notas'
        ]
        read_only_fields = ['monto_establecimiento', 'monto_estilista', 'neto_servicio', 'valor_adicionales', 'numero_factura', 'factura_texto']

    def validate(self, attrs):
        estado = attrs.get('estado') or getattr(self.instance, 'estado', 'en_proceso')

        if estado == 'finalizado':
            medio_pago = attrs.get('medio_pago') if 'medio_pago' in attrs else getattr(self.instance, 'medio_pago', None)

            if not medio_pago:
                raise serializers.ValidationError({'medio_pago': 'El medio de pago es obligatorio al finalizar.'})

        tiene_adicionales = attrs.get('tiene_adicionales')
        if tiene_adicionales is None and self.instance is not None:
            tiene_adicionales = self.instance.tiene_adicionales

        adicional_otro_cantidad = attrs.get('adicional_otro_cantidad')
        if adicional_otro_cantidad is None and self.instance is not None:
            adicional_otro_cantidad = self.instance.adicional_otro_cantidad

        if adicional_otro_cantidad is not None and int(adicional_otro_cantidad) < 1:
            raise serializers.ValidationError({'adicional_otro_cantidad': 'La cantidad debe ser mayor o igual a 1.'})

        if tiene_adicionales:
            adicional_otro_producto = attrs.get('adicional_otro_producto')
            if adicional_otro_producto is None and self.instance is not None:
                adicional_otro_producto = self.instance.adicional_otro_producto

            if adicional_otro_producto and adicional_otro_producto.stock < int(adicional_otro_cantidad or 1):
                raise serializers.ValidationError(
                    {'adicional_otro_producto': f'Stock insuficiente para adicional. Disponible: {adicional_otro_producto.stock}'}
                )

        return attrs

    def _valor_adicional_rapido(self, nombre_servicio, valor_default):
        servicio_cfg = Servicio.objects.filter(nombre__iexact=nombre_servicio, activo=True).first()
        if not servicio_cfg:
            # Fallback por tipo adicional para no depender del nombre exacto.
            nombre_lower = str(nombre_servicio or '').lower()
            if 'shampoo' in nombre_lower:
                servicio_cfg = Servicio.objects.filter(es_adicional=True, nombre__icontains='shampoo', activo=True).first()
            elif 'guantes' in nombre_lower:
                servicio_cfg = Servicio.objects.filter(es_adicional=True, nombre__icontains='guantes', activo=True).first()
        if not servicio_cfg:
            return float(valor_default)
        return float(servicio_cfg.precio or valor_default)

    def _calcular_adicionales(self, servicio):
        if not servicio.tiene_adicionales:
            servicio.valor_adicionales = 0
            return

        valor_shampoo = self._valor_adicional_rapido('Adicional Shampoo', 4000)
        valor_guantes = self._valor_adicional_rapido('Adicional Guantes', 1500)

        total_adicionales = 0
        if servicio.adicional_shampoo:
            total_adicionales += valor_shampoo
        if servicio.adicional_guantes:
            total_adicionales += valor_guantes

        if servicio.adicional_otro_producto:
            cantidad = int(servicio.adicional_otro_cantidad or 1)
            total_adicionales += float(servicio.adicional_otro_producto.precio_venta or 0) * cantidad

        servicio.valor_adicionales = total_adicionales

    def _calcular_reparto(self, servicio):
        precio = float(servicio.precio_cobrado or 0)
        neto = max(precio - float(servicio.valor_adicionales or 0), 0)
        tipo_cobro = servicio.estilista.tipo_cobro_espacio or 'sin_cobro'
        valor_cobro = float(servicio.estilista.valor_cobro_espacio or 0)

        monto_establecimiento = 0
        if tipo_cobro == 'porcentaje_neto':
            monto_establecimiento = (neto * valor_cobro) / 100
        elif tipo_cobro == 'costo_fijo_neto':
            # El cobro fijo de espacio se liquida por día trabajado en Reportes BI,
            # para evitar descontarlo múltiples veces por cada servicio del mismo día.
            monto_establecimiento = 0

        if monto_establecimiento < 0:
            monto_establecimiento = 0
        if monto_establecimiento > neto:
            monto_establecimiento = neto

        servicio.neto_servicio = neto
        servicio.monto_establecimiento = monto_establecimiento
        servicio.monto_estilista = neto - monto_establecimiento

    def _generar_factura(self, servicio):
        if not servicio.numero_factura:
            servicio.numero_factura = f"FS-{timezone.now().strftime('%Y%m%d')}-{servicio.id:06d}"

        cliente = servicio.cliente.nombre if servicio.cliente else 'Cliente no registrado'
        valor_shampoo = self._valor_adicional_rapido('Adicional Shampoo', 4000)
        valor_guantes = self._valor_adicional_rapido('Adicional Guantes', 1500)
        adicionales = []
        if servicio.adicional_shampoo:
            adicionales.append(f'Shampoo ${valor_shampoo:.2f}')
        if servicio.adicional_guantes:
            adicionales.append(f'Guantes ${valor_guantes:.2f}')
        if servicio.adicional_otro_producto:
            adicionales.append(
                f"{servicio.adicional_otro_producto.nombre} x{servicio.adicional_otro_cantidad} = ${float((servicio.adicional_otro_producto.precio_venta or 0) * servicio.adicional_otro_cantidad):.2f}"
            )
        adicionales_texto = ', '.join(adicionales) if adicionales else 'Sin adicionales'
        nota_liquidacion = ''
        if (servicio.estilista.tipo_cobro_espacio or 'sin_cobro') == 'costo_fijo_neto':
            nota_liquidacion = '\nNota: El cobro fijo de espacio se aplica en liquidación diaria/semanal, no por cada servicio.'

        servicio.factura_texto = (
            f"Factura: {servicio.numero_factura}\n"
            f"Tipo: Servicio\n"
            f"Fecha: {timezone.localtime(servicio.fecha_hora).strftime('%Y-%m-%d %H:%M')}\n"
            f"Cliente: {cliente}\n"
            f"Facturado por: {(servicio.usuario.username if servicio.usuario else 'No especificado')}\n"
            f"Estilista: {servicio.estilista.nombre}\n"
            f"Servicio: {servicio.servicio.nombre}\n"
            f"Total: ${float(servicio.precio_cobrado):.2f}\n"
            f"Adicionales: {adicionales_texto}\n"
            f"Valor adicionales: ${float(servicio.valor_adicionales):.2f}\n"
            f"Neto del servicio: ${float(servicio.neto_servicio):.2f}\n"
            f"Medio de pago: {servicio.get_medio_pago_display() if servicio.medio_pago else '-'}\n"
            f"Establecimiento: ${float(servicio.monto_establecimiento):.2f}\n"
            f"Empleado: ${float(servicio.monto_estilista):.2f}"
            f"{nota_liquidacion}"
        )

    def create(self, validated_data):
        if 'precio_cobrado' not in validated_data:
            validated_data['precio_cobrado'] = validated_data['servicio'].precio

        servicio_realizado = ServicioRealizado.objects.create(**validated_data)

        if servicio_realizado.estado == 'finalizado':
            self._calcular_adicionales(servicio_realizado)
            self._calcular_reparto(servicio_realizado)
            self._generar_factura(servicio_realizado)
            servicio_realizado.save()

        return servicio_realizado

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if instance.estado == 'finalizado' and not instance.fecha_fin:
            instance.fecha_fin = timezone.now()

        if instance.estado == 'finalizado':
            self._calcular_adicionales(instance)
            self._calcular_reparto(instance)
            self._generar_factura(instance)

        instance.save()
        return instance


class VentaProductoSerializer(serializers.ModelSerializer):
    """Serializador para el modelo VentaProducto"""
    
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)
    estilista_nombre = serializers.CharField(source='estilista.nombre', read_only=True)
    
    class Meta:
        model = VentaProducto
        fields = [
            'id', 'producto', 'producto_nombre', 'cantidad',
            'precio_unitario', 'total', 'fecha_hora',
            'cliente_nombre', 'medio_pago', 'numero_factura', 'factura_texto',
            'estilista', 'estilista_nombre',
            'usuario', 'usuario_nombre'
        ]
        read_only_fields = ['total', 'numero_factura', 'factura_texto']

    def _generar_factura(self, venta):
        if not venta.numero_factura:
            venta.numero_factura = f"FP-{timezone.now().strftime('%Y%m%d')}-{venta.id:06d}"
        cliente = venta.cliente_nombre or 'Cliente no registrado'
        comision_pct = float(venta.estilista.comision_ventas_productos) if venta.estilista else 0
        comision_valor = float(venta.total or 0) * comision_pct / 100
        venta.factura_texto = (
            f"Factura: {venta.numero_factura}\n"
            f"Tipo: Producto\n"
            f"Fecha: {timezone.localtime(venta.fecha_hora).strftime('%Y-%m-%d %H:%M')}\n"
            f"Cliente: {cliente}\n"
            f"Producto: {venta.producto.nombre}\n"
            f"Cantidad: {venta.cantidad}\n"
            f"Valor unitario: ${float(venta.precio_unitario):.2f}\n"
            f"Total: ${float(venta.total):.2f}\n"
            f"Comisión empleado por venta: {comision_pct:.2f}% (${comision_valor:.2f})\n"
            f"Medio de pago: {venta.get_medio_pago_display()}"
        )
    
    def create(self, validated_data):
        """Crear venta y actualizar stock del producto"""
        producto = validated_data['producto']
        cantidad = validated_data['cantidad']
        
        # Verificar stock disponible
        if producto.stock < cantidad:
            raise serializers.ValidationError({
                'cantidad': f'Stock insuficiente. Disponible: {producto.stock}'
            })
        
        # Calcular total
        validated_data['total'] = validated_data['precio_unitario'] * cantidad
        
        # Crear venta
        venta = VentaProducto.objects.create(**validated_data)
        
        # Actualizar stock
        producto.stock -= cantidad
        producto.save()
        
        # Registrar movimiento de inventario
        MovimientoInventario.objects.create(
            producto=producto,
            tipo_movimiento='salida',
            cantidad=cantidad,
            descripcion=f'Venta #{venta.id}',
            usuario=validated_data.get('usuario')
        )

        self._generar_factura(venta)
        venta.save(update_fields=['numero_factura', 'factura_texto'])

        return venta

    def update(self, instance, validated_data):
        producto_anterior = instance.producto
        cantidad_anterior = instance.cantidad

        producto_nuevo = validated_data.get('producto', instance.producto)
        cantidad_nueva = validated_data.get('cantidad', instance.cantidad)

        if producto_nuevo.id == producto_anterior.id:
            diferencia = int(cantidad_nueva) - int(cantidad_anterior)
            if diferencia > 0:
                if producto_nuevo.stock < diferencia:
                    raise serializers.ValidationError({'cantidad': f'Stock insuficiente. Disponible: {producto_nuevo.stock}'})
                producto_nuevo.stock -= diferencia
            elif diferencia < 0:
                producto_nuevo.stock += abs(diferencia)
            producto_nuevo.save()
        else:
            producto_anterior.stock += int(cantidad_anterior)
            if producto_nuevo.stock < int(cantidad_nueva):
                raise serializers.ValidationError({'cantidad': f'Stock insuficiente en nuevo producto. Disponible: {producto_nuevo.stock}'})
            producto_nuevo.stock -= int(cantidad_nueva)
            producto_anterior.save()
            producto_nuevo.save()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.total = instance.precio_unitario * instance.cantidad
        self._generar_factura(instance)
        instance.save()
        
        return instance


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    """Serializador para el modelo MovimientoInventario"""
    
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)
    
    class Meta:
        model = MovimientoInventario
        fields = [
            'id', 'producto', 'producto_nombre', 'tipo_movimiento',
            'cantidad', 'fecha_hora', 'descripcion',
            'usuario', 'usuario_nombre'
        ]
    
    def create(self, validated_data):
        """Crear movimiento y actualizar stock del producto"""
        producto = validated_data['producto']
        tipo_movimiento = validated_data['tipo_movimiento']
        cantidad = validated_data['cantidad']
        
        # Actualizar stock según el tipo de movimiento
        if tipo_movimiento == 'entrada':
            producto.stock += cantidad
        elif tipo_movimiento == 'salida':
            if producto.stock < cantidad:
                raise serializers.ValidationError({
                    'cantidad': f'Stock insuficiente. Disponible: {producto.stock}'
                })
            producto.stock -= cantidad
        elif tipo_movimiento == 'ajuste':
            # En ajuste, la cantidad es el nuevo stock total
            producto.stock = cantidad
        
        producto.save()
        
        # Crear movimiento
        movimiento = MovimientoInventario.objects.create(**validated_data)
        
        return movimiento


# Serializadores para reportes y estadísticas

class ReporteVentasSerializer(serializers.Serializer):
    """Serializador para reportes de ventas"""
    
    fecha = serializers.DateField()
    total_ventas = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_ventas = serializers.IntegerField()


class ReporteServiciosSerializer(serializers.Serializer):
    """Serializador para reportes de servicios"""
    
    fecha = serializers.DateField()
    total_servicios = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_servicios = serializers.IntegerField()


class EstadisticasGeneralesSerializer(serializers.Serializer):
    """Serializador para estadísticas generales"""
    
    total_ventas_productos = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_servicios = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_general = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_ventas = serializers.IntegerField()
    cantidad_servicios = serializers.IntegerField()
    productos_bajo_stock = serializers.IntegerField()
