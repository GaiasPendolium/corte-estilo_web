from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from .models import (
    Usuario, Estilista, Servicio, Cliente, Producto,
    ServicioRealizado, ServicioRealizadoAdicional, VentaProducto, MovimientoInventario
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
    adicional_otro_estilista_nombre = serializers.CharField(source='adicional_otro_estilista.nombre', read_only=True)
    adicional_otro_total = serializers.SerializerMethodField(read_only=True)
    adicional_otro_comision_estilista = serializers.SerializerMethodField(read_only=True)
    factura_texto = serializers.SerializerMethodField(read_only=True)
    adicionales_servicio_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )
    adicionales_servicio_items = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
    )
    adicionales_asignados = serializers.SerializerMethodField(read_only=True)
    adicional_otro_descuento_empleado = serializers.BooleanField(write_only=True, required=False, default=False)
    adicional_otro_precio_unitario = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
        write_only=True,
    )
    
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
            'adicional_otro_estilista',
            'adicionales_servicio_ids', 'adicionales_servicio_items',
            'adicionales_asignados',
            'adicional_otro_producto_nombre', 'adicional_otro_estilista_nombre',
            'adicional_otro_cantidad', 'adicional_otro_total', 'adicional_otro_comision_estilista',
            'valor_adicionales',
            'adicional_otro_descuento_empleado', 'adicional_otro_precio_unitario',
            'numero_factura', 'factura_texto', 'notas'
        ]
        read_only_fields = ['monto_establecimiento', 'monto_estilista', 'neto_servicio', 'valor_adicionales', 'numero_factura', 'factura_texto']

    def get_adicional_otro_total(self, obj):
        if not obj.adicional_otro_producto_id:
            return 0
        qty = int(obj.adicional_otro_cantidad or 1)
        unit = float(obj.adicional_otro_producto.precio_venta or 0)
        return float(unit * qty)

    def get_adicional_otro_comision_estilista(self, obj):
        if not obj.adicional_otro_producto_id or not obj.adicional_otro_estilista_id:
            return 0
        qty = int(obj.adicional_otro_cantidad or 1)
        unit = float(obj.adicional_otro_producto.precio_venta or 0)
        total = unit * qty
        pct = float(obj.adicional_otro_producto.comision_estilista or 0)
        if pct < 0:
            pct = 0
        if pct > 100:
            pct = 100
        return float((total * pct) / 100)

    def _usa_reparto_explicito(self, servicio):
        return str(getattr(servicio, 'tipo_reparto_establecimiento', '') or '').strip().lower() in {'porcentaje', 'monto'}

    def _resolver_montos_servicio(self, servicio):
        neto = float(getattr(servicio, 'neto_servicio', None) or getattr(servicio, 'precio_cobrado', 0) or 0)
        neto = max(neto, 0)
        es_shampoo_principal = self._es_servicio_shampoo(getattr(servicio, 'servicio', None))

        if es_shampoo_principal:
            return {
                'monto_establecimiento': neto,
                'monto_estilista': 0.0,
                'reparto_origen': 'shampoo',
            }

        if self._usa_reparto_explicito(servicio):
            monto_establecimiento = float(getattr(servicio, 'monto_establecimiento', 0) or 0)
            monto_establecimiento = min(max(monto_establecimiento, 0.0), neto)
            return {
                'monto_establecimiento': monto_establecimiento,
                'monto_estilista': neto - monto_establecimiento,
                'reparto_origen': 'explicito',
            }

        # Sin reparto explícito: el servicio pertenece completo al empleado.
        return {
            'monto_establecimiento': 0.0,
            'monto_estilista': neto,
            'reparto_origen': 'sin_reparto',
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        montos = self._resolver_montos_servicio(instance)
        data['monto_establecimiento'] = montos['monto_establecimiento']
        data['monto_estilista'] = montos['monto_estilista']
        data['reparto_origen'] = montos['reparto_origen']
        return data

    def _es_servicio_shampoo(self, servicio_obj):
        nombre = str(getattr(servicio_obj, 'nombre', '') or '').lower()
        return 'shampoo' in nombre

    def _es_servicio_depilacion(self, servicio_obj):
        nombre = str(getattr(servicio_obj, 'nombre', '') or '').lower()
        return 'depilacion' in nombre or 'depilación' in nombre

    def _es_servicio_adicional_permitido(self, servicio_obj):
        if not servicio_obj:
            return False
        if bool(getattr(servicio_obj, 'es_adicional', False)):
            return True
        return self._es_servicio_shampoo(servicio_obj) or self._es_servicio_depilacion(servicio_obj)

    def get_adicionales_asignados(self, obj):
        detalles = obj.adicionales_asignados.select_related('servicio', 'estilista').all()

        return [
            {
                'id': d.id,
                'servicio_id': d.servicio_id,
                'servicio_nombre': d.servicio.nombre,
                'estilista_id': d.estilista_id,
                'estilista_nombre': d.estilista.nombre,
                'valor': float(d.valor_cobrado or 0),
                'aplica_porcentaje_establecimiento': bool(d.aplica_porcentaje_establecimiento),
                'porcentaje_establecimiento': float(d.porcentaje_establecimiento or 0),
            }
            for d in detalles
        ]

    def validate(self, attrs):
        estado = attrs.get('estado') or getattr(self.instance, 'estado', 'en_proceso')

        if estado == 'finalizado':
            medio_pago = attrs.get('medio_pago') if 'medio_pago' in attrs else getattr(self.instance, 'medio_pago', None)

            if not medio_pago:
                raise serializers.ValidationError({'medio_pago': 'El medio de pago es obligatorio al finalizar.'})

            tipo_reparto = attrs.get('tipo_reparto_establecimiento')
            if tipo_reparto is None and self.instance is not None:
                tipo_reparto = self.instance.tipo_reparto_establecimiento
            valor_reparto = attrs.get('valor_reparto_establecimiento')
            if valor_reparto is None and self.instance is not None:
                valor_reparto = self.instance.valor_reparto_establecimiento

            if tipo_reparto:
                tipo_reparto_str = str(tipo_reparto).strip().lower()
                if tipo_reparto_str not in {'porcentaje', 'monto'}:
                    raise serializers.ValidationError({'tipo_reparto_establecimiento': 'Tipo de reparto inválido.'})
                try:
                    valor_num = float(valor_reparto or 0)
                except Exception:
                    raise serializers.ValidationError({'valor_reparto_establecimiento': 'Valor de reparto inválido.'})
                if valor_num < 0:
                    raise serializers.ValidationError({'valor_reparto_establecimiento': 'El valor de reparto no puede ser negativo.'})
                if tipo_reparto_str == 'porcentaje' and valor_num > 100:
                    raise serializers.ValidationError({'valor_reparto_establecimiento': 'El porcentaje no puede ser mayor a 100.'})

        tiene_adicionales = attrs.get('tiene_adicionales')
        if tiene_adicionales is None and self.instance is not None:
            tiene_adicionales = self.instance.tiene_adicionales

        adicional_otro_cantidad = attrs.get('adicional_otro_cantidad')
        if adicional_otro_cantidad is None and self.instance is not None:
            adicional_otro_cantidad = self.instance.adicional_otro_cantidad

        if adicional_otro_cantidad is not None and int(adicional_otro_cantidad) < 1:
            raise serializers.ValidationError({'adicional_otro_cantidad': 'La cantidad debe ser mayor o igual a 1.'})

        if tiene_adicionales:
            adicionales_ids = attrs.get('adicionales_servicio_ids')
            if adicionales_ids is not None:
                ids_norm = sorted({int(x) for x in adicionales_ids if x is not None})
                if ids_norm:
                    candidatos = list(Servicio.objects.filter(id__in=ids_norm, activo=True))
                    validos_set = {
                        int(s.id)
                        for s in candidatos
                        if self._es_servicio_adicional_permitido(s)
                    }
                    faltantes = [x for x in ids_norm if x not in validos_set]
                    if faltantes:
                        raise serializers.ValidationError(
                            {'adicionales_servicio_ids': f'Servicios adicionales no válidos o inactivos: {faltantes}'}
                        )

            adicionales_items = attrs.get('adicionales_servicio_items')
            if adicionales_items is not None:
                ids_items = []
                for item in adicionales_items:
                    sid = item.get('id')
                    valor = item.get('valor')
                    if sid is None:
                        raise serializers.ValidationError({'adicionales_servicio_items': 'Cada item debe incluir id del servicio.'})
                    if valor is None or float(valor) <= 0:
                        raise serializers.ValidationError({'adicionales_servicio_items': 'Cada servicio adicional debe tener valor mayor a 0.'})
                    ids_items.append(int(sid))

                servicios_mapa = {}
                if ids_items:
                    servicios_candidatos = list(Servicio.objects.filter(id__in=ids_items, activo=True))
                    servicios_validos = [s for s in servicios_candidatos if self._es_servicio_adicional_permitido(s)]
                    validos_set = {int(s.id) for s in servicios_validos}
                    servicios_mapa = {int(s.id): s for s in servicios_validos}
                    faltantes = [x for x in ids_items if x not in validos_set]
                    if faltantes:
                        raise serializers.ValidationError(
                            {'adicionales_servicio_items': f'Servicios adicionales no válidos o inactivos: {faltantes}'}
                        )

                estilistas_ids_items = []
                for item in adicionales_items:
                    sid = int(item.get('id'))
                    estilista_id = item.get('estilista_id')
                    aplica_pct = bool(item.get('aplica_porcentaje_establecimiento', False))
                    pct_est = item.get('porcentaje_establecimiento', 0)

                    try:
                        pct_num = float(pct_est or 0)
                    except Exception:
                        raise serializers.ValidationError({'adicionales_servicio_items': 'Porcentaje de establecimiento inválido.'})
                    if aplica_pct and (pct_num <= 0 or pct_num > 100):
                        raise serializers.ValidationError({'adicionales_servicio_items': 'Si aplica porcentaje, debe estar entre 0.01 y 100.'})

                    servicio_item = servicios_mapa.get(sid)
                    es_shampoo = self._es_servicio_shampoo(servicio_item)
                    if es_shampoo:
                        if estilista_id not in (None, ''):
                            raise serializers.ValidationError(
                                {'adicionales_servicio_items': 'Shampoo no asigna ganancia al empleado; no debe llevar empleado asignado.'}
                            )
                        if aplica_pct:
                            raise serializers.ValidationError(
                                {'adicionales_servicio_items': 'Shampoo no requiere porcentaje; su ganancia es 100% para establecimiento.'}
                            )
                    if estilista_id in (None, ''):
                        if not es_shampoo:
                            raise serializers.ValidationError(
                                {'adicionales_servicio_items': 'Cada servicio adicional (excepto shampoo) debe tener empleado asignado.'}
                            )
                    else:
                        estilistas_ids_items.append(int(estilista_id))

                if estilistas_ids_items:
                    estilistas_validos = Estilista.objects.filter(id__in=estilistas_ids_items, activo=True).values_list('id', flat=True)
                    estilistas_validos_set = {int(v) for v in estilistas_validos}
                    faltantes_est = [x for x in estilistas_ids_items if x not in estilistas_validos_set]
                    if faltantes_est:
                        raise serializers.ValidationError(
                            {'adicionales_servicio_items': f'Empleados no válidos o inactivos: {faltantes_est}'}
                        )

            adicional_otro_producto = attrs.get('adicional_otro_producto')
            if adicional_otro_producto is None and self.instance is not None:
                adicional_otro_producto = self.instance.adicional_otro_producto

            cantidad_requerida = int(adicional_otro_cantidad or 1)
            stock_disponible = int(adicional_otro_producto.stock or 0) if adicional_otro_producto else 0

            # En update, si mantiene el mismo producto adicional ya descontado,
            # validamos contra stock + cantidad previa para evaluar solo el delta real.
            if (
                self.instance
                and adicional_otro_producto
                and self.instance.adicional_otro_producto
                and int(self.instance.adicional_otro_producto.id) == int(adicional_otro_producto.id)
                and self.instance.estado == 'finalizado'
                and self.instance.tiene_adicionales
            ):
                stock_disponible += int(self.instance.adicional_otro_cantidad or 1)

            if adicional_otro_producto and stock_disponible < cantidad_requerida:
                raise serializers.ValidationError(
                    {'adicional_otro_producto': f'Stock insuficiente para adicional. Disponible: {stock_disponible}'}
                )

            adicional_otro_estilista = attrs.get('adicional_otro_estilista')
            if adicional_otro_estilista is None and self.instance is not None:
                adicional_otro_estilista = self.instance.adicional_otro_estilista

            if adicional_otro_producto and not adicional_otro_estilista:
                raise serializers.ValidationError(
                    {'adicional_otro_estilista': 'Debes seleccionar el empleado que gana la comisión del producto adicional.'}
                )

            if adicional_otro_estilista and not adicional_otro_producto:
                raise serializers.ValidationError(
                    {'adicional_otro_producto': 'Si seleccionas empleado para comisión, debes seleccionar producto adicional.'}
                )

            descuento_empleado = attrs.get('adicional_otro_descuento_empleado', False)
            precio_manual = attrs.get('adicional_otro_precio_unitario')
            if descuento_empleado and adicional_otro_producto:
                if precio_manual in (None, ''):
                    raise serializers.ValidationError({'adicional_otro_precio_unitario': 'Debes ingresar el nuevo precio con descuento empleado.'})

                precio_venta = float(adicional_otro_producto.precio_venta or 0)
                minimo_permitido = precio_venta * 0.8
                if float(precio_manual) < minimo_permitido:
                    raise serializers.ValidationError(
                        {'adicional_otro_precio_unitario': f'Descuento maximo 20%. Precio minimo unitario: ${minimo_permitido:.0f}.'}
                    )

        return attrs

    def _sincronizar_adicionales_asignados(self, servicio, adicionales_servicio_items=None):
        ServicioRealizadoAdicional.objects.filter(servicio_realizado=servicio).delete()
        if not adicionales_servicio_items:
            return

        ids_items = sorted({int(item.get('id')) for item in adicionales_servicio_items if item.get('id') is not None})
        servicios_mapa = {
            int(s.id): s
            for s in Servicio.objects.filter(id__in=ids_items, activo=True)
        }

        detalles = []
        for item in adicionales_servicio_items:
            sid = item.get('id')
            eid = item.get('estilista_id')
            valor = item.get('valor')
            aplica_pct = bool(item.get('aplica_porcentaje_establecimiento', False))
            pct_est = item.get('porcentaje_establecimiento', 0)

            srv_ad = servicios_mapa.get(int(sid)) if sid is not None else None
            if self._es_servicio_shampoo(srv_ad):
                # Shampoo siempre se contabiliza para establecimiento y no se asigna al empleado.
                # Se guarda como detalle con 100% establecimiento para trazabilidad
                # en factura y reportes (evita que aparezca como "adicional no desglosado").
                if sid is None or valor is None:
                    continue
                try:
                    valor_num = float(valor or 0)
                except Exception:
                    valor_num = 0
                if valor_num <= 0:
                    continue

                detalles.append(
                    ServicioRealizadoAdicional(
                        servicio_realizado=servicio,
                        servicio_id=int(sid),
                        estilista_id=int(servicio.estilista_id),
                        valor_cobrado=valor_num,
                        aplica_porcentaje_establecimiento=True,
                        porcentaje_establecimiento=100,
                    )
                )
                continue

            if sid is None or eid is None or valor is None:
                continue

            try:
                pct_num = float(pct_est or 0)
            except Exception:
                pct_num = 0
            if pct_num < 0:
                pct_num = 0
            if pct_num > 100:
                pct_num = 100

            detalles.append(
                ServicioRealizadoAdicional(
                    servicio_realizado=servicio,
                    servicio_id=int(sid),
                    estilista_id=int(eid),
                    valor_cobrado=valor,
                    aplica_porcentaje_establecimiento=aplica_pct,
                    porcentaje_establecimiento=pct_num if aplica_pct else 0,
                )
            )

        if detalles:
            ServicioRealizadoAdicional.objects.bulk_create(detalles)

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

    def _aplica_descuento_inventario_adicional(self, servicio):
        return bool(
            servicio.estado == 'finalizado'
            and servicio.tiene_adicionales
            and servicio.adicional_otro_producto
            and int(servicio.adicional_otro_cantidad or 1) > 0
        )

    def _tag_movimiento_adicional(self, servicio):
        return f"adicional servicio #{servicio.id}"

    def _descontar_inventario_adicional(self, servicio, cantidad, producto=None):
        producto_obj = producto or servicio.adicional_otro_producto
        qty = int(cantidad or 0)
        if not producto_obj or qty <= 0:
            return

        if producto_obj.stock < qty:
            raise serializers.ValidationError(
                {'adicional_otro_producto': f'Stock insuficiente para adicional. Disponible: {producto_obj.stock}'}
            )

        producto_obj.stock -= qty
        producto_obj.save(update_fields=['stock'])

        MovimientoInventario.objects.create(
            producto=producto_obj,
            tipo_movimiento='salida',
            cantidad=qty,
            descripcion=f"{self._tag_movimiento_adicional(servicio)} (factura {servicio.numero_factura or '-'})",
            usuario=servicio.usuario,
        )

    def _reponer_inventario_adicional(self, servicio, cantidad, producto=None):
        producto_obj = producto or servicio.adicional_otro_producto
        qty = int(cantidad or 0)
        if not producto_obj or qty <= 0:
            return

        producto_obj.stock += qty
        producto_obj.save(update_fields=['stock'])

        MovimientoInventario.objects.create(
            producto=producto_obj,
            tipo_movimiento='entrada',
            cantidad=qty,
            descripcion=f"reverso {self._tag_movimiento_adicional(servicio)} (factura {servicio.numero_factura or '-'})",
            usuario=servicio.usuario,
        )

    def _calcular_adicionales(
        self,
        servicio,
        adicionales_servicio_ids=None,
        adicionales_servicio_items=None,
        adicional_otro_descuento_empleado=False,
        adicional_otro_precio_unitario=None,
    ):
        if not servicio.tiene_adicionales:
            servicio.valor_adicionales = 0
            servicio._adicionales_detalle = []
            self._sincronizar_adicionales_asignados(servicio, [])
            return

        total_adicionales = 0
        adicionales_detalle = []

        # Prioriza items con valor manual por servicio adicional.
        if adicionales_servicio_items is not None:
            ids_items = sorted({int(item.get('id')) for item in adicionales_servicio_items if item.get('id') is not None})
            servicios_mapa = {
                int(s.id): s
                for s in Servicio.objects.filter(id__in=ids_items, activo=True)
                if self._es_servicio_adicional_permitido(s)
            }
            estilistas_ids = sorted({int(item.get('estilista_id')) for item in adicionales_servicio_items if item.get('estilista_id') is not None})
            estilistas_mapa = {int(e.id): e for e in Estilista.objects.filter(id__in=estilistas_ids)}
            nombres_lower = []
            for item in adicionales_servicio_items:
                sid = int(item.get('id'))
                srv_ad = servicios_mapa.get(sid)
                if not srv_ad:
                    continue
                eid = item.get('estilista_id')
                estilista_ad = estilistas_mapa.get(int(eid)) if eid is not None else None
                valor_item = float(item.get('valor') or 0)
                aplica_pct = bool(item.get('aplica_porcentaje_establecimiento', False))
                pct_est = float(item.get('porcentaje_establecimiento') or 0)
                total_adicionales += valor_item
                nombres_lower.append((srv_ad.nombre or '').lower())
                if aplica_pct and pct_est > 0:
                    valor_est = (valor_item * pct_est) / 100
                    valor_emp = valor_item - valor_est
                    reparto = f" (Emp {valor_emp:.2f} / Est {valor_est:.2f})"
                else:
                    reparto = ''
                if estilista_ad:
                    adicionales_detalle.append(f"{srv_ad.nombre} ({estilista_ad.nombre}) ${valor_item:.2f}{reparto}")
                else:
                    if 'shampoo' in (srv_ad.nombre or '').lower():
                        adicionales_detalle.append(f"{srv_ad.nombre} (Establecimiento) ${valor_item:.2f}")
                    else:
                        adicionales_detalle.append(f"{srv_ad.nombre} ${valor_item:.2f}{reparto}")

            servicio.adicional_shampoo = any('shampoo' in nombre for nombre in nombres_lower)
            servicio.adicional_guantes = any('guantes' in nombre for nombre in nombres_lower)
        # Si llegan IDs dinámicos, se calcula por precio del catálogo.
        elif adicionales_servicio_ids is not None:
            ids_norm = sorted({int(x) for x in adicionales_servicio_ids if x is not None})
            servicios_adicionales = [
                s for s in Servicio.objects.filter(id__in=ids_norm, activo=True)
                if self._es_servicio_adicional_permitido(s)
            ] if ids_norm else []

            for srv_ad in servicios_adicionales:
                total_adicionales += float(srv_ad.precio or 0)
                adicionales_detalle.append(f"{srv_ad.nombre} ({servicio.estilista.nombre}) ${float(srv_ad.precio or 0):.2f}")

            # Mantener flags legacy sincronizados cuando aplica.
            nombres_lower = [(srv_ad.nombre or '').lower() for srv_ad in servicios_adicionales]
            servicio.adicional_shampoo = any('shampoo' in nombre for nombre in nombres_lower)
            servicio.adicional_guantes = any('guantes' in nombre for nombre in nombres_lower)
        else:
            valor_shampoo = self._valor_adicional_rapido('Adicional Shampoo', 4000)
            valor_guantes = self._valor_adicional_rapido('Adicional Guantes', 1500)
            if servicio.adicional_shampoo:
                total_adicionales += valor_shampoo
            if servicio.adicional_guantes:
                total_adicionales += valor_guantes

        if servicio.adicional_otro_producto:
            cantidad = int(servicio.adicional_otro_cantidad or 1)
            if adicional_otro_descuento_empleado and adicional_otro_precio_unitario not in (None, ''):
                precio_unitario = float(adicional_otro_precio_unitario)
                detalle_tag = ' (descuento empleado)'
            else:
                precio_unitario = float(servicio.adicional_otro_producto.precio_venta or 0)
                detalle_tag = ''

            total_adicionales += precio_unitario * cantidad
            comision_pct = float(servicio.adicional_otro_producto.comision_estilista or 0)
            if comision_pct < 0:
                comision_pct = 0
            if comision_pct > 100:
                comision_pct = 100
            comision_valor = (precio_unitario * cantidad) * (comision_pct / 100.0)
            estilista_comision = servicio.adicional_otro_estilista.nombre if servicio.adicional_otro_estilista else 'Sin empleado'
            adicionales_detalle.append(
                (
                    f"{servicio.adicional_otro_producto.nombre} x{cantidad} = ${(precio_unitario * cantidad):.2f}{detalle_tag}"
                    f" (Comision {estilista_comision}: ${comision_valor:.2f})"
                )
            )

        servicio.valor_adicionales = total_adicionales
        servicio._adicionales_detalle = adicionales_detalle

        if adicionales_servicio_items is not None:
            self._sincronizar_adicionales_asignados(servicio, adicionales_servicio_items)
        elif adicionales_servicio_ids is not None:
            servicios_legacy = {
                int(s.id): s
                for s in Servicio.objects.filter(
                    id__in=[int(x) for x in adicionales_servicio_ids if x is not None],
                    activo=True,
                )
                if self._es_servicio_adicional_permitido(s)
            }
            legacy_items = [
                {
                    'id': int(sid),
                    'estilista_id': int(servicio.estilista_id),
                    'valor': float(servicios_legacy[int(sid)].precio or 0),
                    'aplica_porcentaje_establecimiento': False,
                    'porcentaje_establecimiento': 0,
                }
                for sid in sorted({int(x) for x in adicionales_servicio_ids if x is not None})
                if int(sid) in servicios_legacy
            ]
            self._sincronizar_adicionales_asignados(servicio, legacy_items)

    def _calcular_reparto(self, servicio):
        precio = float(servicio.precio_cobrado or 0)
        # La base del servicio para liquidar al estilista es el precio del servicio.
        # Los adicionales (shampoo/guantes/otros) son ingreso del establecimiento,
        # no un descuento sobre la base del servicio.
        neto = max(precio, 0)

        es_shampoo_principal = self._es_servicio_shampoo(servicio.servicio)
        tipo_reparto = str(servicio.tipo_reparto_establecimiento or '').strip().lower()
        valor_reparto = float(servicio.valor_reparto_establecimiento or 0)

        monto_establecimiento = 0
        if es_shampoo_principal:
            # Regla de negocio: shampoo principal es 100% para establecimiento.
            servicio.tipo_reparto_establecimiento = 'porcentaje'
            servicio.valor_reparto_establecimiento = 100
            monto_establecimiento = neto
        elif tipo_reparto == 'porcentaje':
            if valor_reparto < 0:
                valor_reparto = 0
            if valor_reparto > 100:
                valor_reparto = 100
            monto_establecimiento = (neto * valor_reparto) / 100
        elif tipo_reparto == 'monto':
            if valor_reparto < 0:
                valor_reparto = 0
            monto_establecimiento = valor_reparto
        else:
            # Sin reparto explícito, el servicio queda 100% para el empleado.
            # El cobro de espacio del estilista se maneja únicamente en Liquidación.
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

        servicio.factura_texto = self._construir_factura_texto(servicio)

    def _construir_factura_texto(self, servicio):
        numero_factura = servicio.numero_factura or f"FS-{timezone.now().strftime('%Y%m%d')}-{servicio.id:06d}"

        cliente = servicio.cliente.nombre if servicio.cliente else 'Cliente no registrado'
        montos_principal = self._resolver_montos_servicio(servicio)
        valor_principal_total = float(servicio.neto_servicio or servicio.precio_cobrado or 0)

        detalle_servicios = [
            {
                'servicio': servicio.servicio.nombre,
                'estilista': servicio.estilista.nombre,
                'valor': float(servicio.precio_cobrado or 0),
            }
        ]

        adicionales_asignados = list(
            servicio.adicionales_asignados.select_related('servicio', 'estilista').all()
        )
        for adicional in adicionales_asignados:
            detalle_servicios.append(
                {
                    'servicio': adicional.servicio.nombre,
                    'estilista': adicional.estilista.nombre,
                    'valor': float(adicional.valor_cobrado or 0),
                }
            )

        valor_producto_adicional = 0.0
        if servicio.adicional_otro_producto_id:
            qty_prod = int(servicio.adicional_otro_cantidad or 1)
            unit_prod = float(servicio.adicional_otro_producto.precio_venta or 0)
            valor_producto_adicional = unit_prod * qty_prod
            detalle_servicios.append(
                {
                    'servicio': f"Producto: {servicio.adicional_otro_producto.nombre} x{qty_prod}",
                    'estilista': servicio.adicional_otro_estilista.nombre if servicio.adicional_otro_estilista else '-',
                    'valor': valor_producto_adicional,
                }
            )

        if len(adicionales_asignados) == 0:
            valor_adicionales_remanente = float(servicio.valor_adicionales or 0) - valor_producto_adicional
            if valor_adicionales_remanente > 0:
                # Fallback para facturas antiguas sin detalle puntual de adicionales.
                detalle_servicios.append(
                    {
                        'servicio': 'Adicionales',
                        'estilista': servicio.estilista.nombre,
                        'valor': valor_adicionales_remanente,
                    }
                )

        total_cobrado = sum(item['valor'] for item in detalle_servicios)

        col_servicio = 22
        col_estilista = 16
        col_valor = 12
        tabla_linea = f"+{'-' * col_servicio}+{'-' * col_estilista}+{'-' * col_valor}+"

        def _recortar(texto, ancho):
            txt = str(texto or '')
            if len(txt) <= ancho:
                return txt
            if ancho <= 3:
                return txt[:ancho]
            return f"{txt[:ancho - 3]}..."

        tabla_header = (
            f"| {_recortar('Servicio', col_servicio - 2).ljust(col_servicio - 2)} "
            f"| {_recortar('Estilista', col_estilista - 2).ljust(col_estilista - 2)} "
            f"| {_recortar('Valor', col_valor - 2).rjust(col_valor - 2)} |"
        )

        tabla_rows = []
        for item in detalle_servicios:
            valor_txt = f"${item['valor']:.2f}"
            tabla_rows.append(
                f"| {_recortar(item['servicio'], col_servicio - 2).ljust(col_servicio - 2)} "
                f"| {_recortar(item['estilista'], col_estilista - 2).ljust(col_estilista - 2)} "
                f"| {valor_txt.rjust(col_valor - 2)} |"
            )

        tabla_texto = '\n'.join([tabla_linea, tabla_header, tabla_linea, *tabla_rows, tabla_linea])

        comisiones_adicionales = []
        for adicional in adicionales_asignados:
            valor_adicional = float(adicional.valor_cobrado or 0)
            aplica_pct = bool(adicional.aplica_porcentaje_establecimiento)
            pct_est = float(adicional.porcentaje_establecimiento or 0)
            if pct_est < 0:
                pct_est = 0
            if pct_est > 100:
                pct_est = 100

            valor_est = valor_adicional * (pct_est / 100.0) if aplica_pct else 0.0
            comision_empleado = valor_adicional - valor_est
            comisiones_adicionales.append(
                f"- {adicional.servicio.nombre} ({adicional.estilista.nombre}): empleado ${comision_empleado:.2f} | establecimiento ${valor_est:.2f}"
            )

        bloque_comision = ''
        if comisiones_adicionales:
            bloque_comision = (
                "\nComision por servicios adicionales:\n"
                + "\n".join(comisiones_adicionales)
            )

        bloque_comision_producto = ''
        if servicio.adicional_otro_producto_id and servicio.adicional_otro_estilista_id:
            qty_prod = int(servicio.adicional_otro_cantidad or 1)
            unit_prod = float(servicio.adicional_otro_producto.precio_venta or 0)
            total_prod = unit_prod * qty_prod
            pct_prod = float(servicio.adicional_otro_producto.comision_estilista or 0)
            if pct_prod < 0:
                pct_prod = 0
            if pct_prod > 100:
                pct_prod = 100
            comision_prod = total_prod * (pct_prod / 100.0)
            valor_est_prod = total_prod - comision_prod
            bloque_comision_producto = (
                "\nComision producto adicional:\n"
                f"- {servicio.adicional_otro_producto.nombre} ({servicio.adicional_otro_estilista.nombre}): empleado ${comision_prod:.2f} | establecimiento ${valor_est_prod:.2f}"
            )

        return (
            f"CORTE Y ESTILO\n"
            f"Factura: {numero_factura}\n"
            f"Tipo: Servicio\n"
            f"Fecha: {timezone.localtime(servicio.fecha_hora).strftime('%Y-%m-%d %H:%M')}\n"
            f"Cliente: {cliente}\n"
            f"Facturado por: {(servicio.usuario.username if servicio.usuario else 'No especificado')}\n"
            f"\n"
            f"{tabla_texto}\n"
            f"\nReparto servicio principal:\n"
            f"- Total servicio: ${valor_principal_total:.2f}\n"
            f"- Para empleado: ${float(montos_principal['monto_estilista']):.2f}\n"
            f"- Para establecimiento: ${float(montos_principal['monto_establecimiento']):.2f}\n"
            f"{bloque_comision}\n"
            f"{bloque_comision_producto}\n"
            f"Total: ${total_cobrado:.2f}\n"
            f"Medio de pago: {servicio.get_medio_pago_display() if servicio.medio_pago else '-'}"
        )

    def get_factura_texto(self, obj):
        # NO recalcular en lectura. Simplemente usar valores guardados en BD.
        # La recalculación solo ocurre en create() y update() con parámetros completos.
        return self._construir_factura_texto(obj)

    def create(self, validated_data):
        adicionales_servicio_ids = validated_data.pop('adicionales_servicio_ids', None)
        adicionales_servicio_items = validated_data.pop('adicionales_servicio_items', None)
        adicional_otro_descuento_empleado = validated_data.pop('adicional_otro_descuento_empleado', False)
        adicional_otro_precio_unitario = validated_data.pop('adicional_otro_precio_unitario', None)
        if 'precio_cobrado' not in validated_data:
            validated_data['precio_cobrado'] = validated_data['servicio'].precio
        if validated_data.get('estado') == 'finalizado' and not validated_data.get('fecha_fin'):
            validated_data['fecha_fin'] = timezone.now()

        with transaction.atomic():
            servicio_realizado = ServicioRealizado.objects.create(**validated_data)

            if servicio_realizado.estado == 'finalizado':
                self._calcular_adicionales(
                    servicio_realizado,
                    adicionales_servicio_ids=adicionales_servicio_ids,
                    adicionales_servicio_items=adicionales_servicio_items,
                    adicional_otro_descuento_empleado=adicional_otro_descuento_empleado,
                    adicional_otro_precio_unitario=adicional_otro_precio_unitario,
                )
                self._calcular_reparto(servicio_realizado)
                self._generar_factura(servicio_realizado)
                servicio_realizado.save()

                if self._aplica_descuento_inventario_adicional(servicio_realizado):
                    self._descontar_inventario_adicional(
                        servicio_realizado,
                        int(servicio_realizado.adicional_otro_cantidad or 1),
                    )

            return servicio_realizado

    def update(self, instance, validated_data):
        adicionales_servicio_ids = validated_data.pop('adicionales_servicio_ids', None)
        adicionales_servicio_items = validated_data.pop('adicionales_servicio_items', None)
        adicional_otro_descuento_empleado = validated_data.pop('adicional_otro_descuento_empleado', False)
        adicional_otro_precio_unitario = validated_data.pop('adicional_otro_precio_unitario', None)

        aplica_prev = self._aplica_descuento_inventario_adicional(instance)
        producto_prev = instance.adicional_otro_producto
        cantidad_prev = int(instance.adicional_otro_cantidad or 1)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if instance.estado == 'finalizado' and not instance.fecha_fin:
            instance.fecha_fin = timezone.now()

        with transaction.atomic():
            if instance.estado == 'finalizado':
                self._calcular_adicionales(
                    instance,
                    adicionales_servicio_ids=adicionales_servicio_ids,
                    adicionales_servicio_items=adicionales_servicio_items,
                    adicional_otro_descuento_empleado=adicional_otro_descuento_empleado,
                    adicional_otro_precio_unitario=adicional_otro_precio_unitario,
                )
                self._calcular_reparto(instance)
                self._generar_factura(instance)

            aplica_nuevo = self._aplica_descuento_inventario_adicional(instance)
            producto_nuevo = instance.adicional_otro_producto
            cantidad_nueva = int(instance.adicional_otro_cantidad or 1)

            if aplica_prev and not aplica_nuevo:
                self._reponer_inventario_adicional(instance, cantidad_prev, producto=producto_prev)
            elif not aplica_prev and aplica_nuevo:
                self._descontar_inventario_adicional(instance, cantidad_nueva, producto=producto_nuevo)
            elif aplica_prev and aplica_nuevo:
                if producto_prev and producto_nuevo and int(producto_prev.id) == int(producto_nuevo.id):
                    delta = cantidad_nueva - cantidad_prev
                    if delta > 0:
                        self._descontar_inventario_adicional(instance, delta, producto=producto_nuevo)
                    elif delta < 0:
                        self._reponer_inventario_adicional(instance, abs(delta), producto=producto_nuevo)
                else:
                    self._reponer_inventario_adicional(instance, cantidad_prev, producto=producto_prev)
                    self._descontar_inventario_adicional(instance, cantidad_nueva, producto=producto_nuevo)

            instance.save()
            return instance


class VentaProductoSerializer(serializers.ModelSerializer):
    """Serializador para el modelo VentaProducto"""
    
    producto_nombre = serializers.CharField(source='producto.nombre', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)
    estilista_nombre = serializers.CharField(source='estilista.nombre', read_only=True)
    deuda_consumo_estado = serializers.CharField(source='deuda_consumo.estado', read_only=True)
    deuda_consumo_saldo = serializers.DecimalField(
        source='deuda_consumo.saldo_pendiente',
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    
    class Meta:
        model = VentaProducto
        fields = [
            'id', 'producto', 'producto_nombre', 'cantidad',
            'precio_unitario', 'total', 'fecha_hora',
            'cliente_nombre', 'medio_pago', 'numero_factura', 'factura_texto',
            'tipo_operacion',
            'estilista', 'estilista_nombre',
            'deuda_consumo', 'deuda_consumo_estado', 'deuda_consumo_saldo',
            'usuario', 'usuario_nombre'
        ]
        read_only_fields = ['total', 'numero_factura', 'factura_texto']

    def _generar_factura(self, venta):
        if not venta.numero_factura:
            prefijo = 'FC' if venta.tipo_operacion == 'consumo_empleado' else 'FP'
            venta.numero_factura = f"{prefijo}-{timezone.now().strftime('%Y%m%d')}-{venta.id:06d}"
        if venta.tipo_operacion == 'consumo_empleado':
            cliente = venta.estilista.nombre if venta.estilista else 'Empleado no registrado'
        else:
            cliente = venta.cliente_nombre or 'Cliente no registrado'
        if venta.tipo_operacion == 'consumo_empleado':
            comision_pct = 0
        else:
            comision_pct = float(venta.estilista.comision_ventas_productos) if venta.estilista else 0
        comision_valor = float(venta.total or 0) * comision_pct / 100
        etiqueta_operacion = 'Consumo empleado' if venta.tipo_operacion == 'consumo_empleado' else 'Producto'
        linea_comision = '' if venta.tipo_operacion == 'consumo_empleado' else f"Comisión empleado por venta: {comision_pct:.2f}% (${comision_valor:.2f})\\n"
        linea_medio_pago = '' if venta.tipo_operacion == 'consumo_empleado' else f"Medio de pago: {venta.get_medio_pago_display()}"
        detalle_deuda = ''
        if venta.tipo_operacion == 'consumo_empleado' and venta.deuda_consumo:
            detalle_deuda = (
                f"\nCuenta por cobrar: {venta.deuda_consumo.numero_factura}"
                f"\nSaldo pendiente: ${float(venta.deuda_consumo.saldo_pendiente or 0):.2f}"
            )
        venta.factura_texto = (
            f"Factura: {venta.numero_factura}\n"
            f"Tipo: {etiqueta_operacion}\n"
            f"Fecha: {timezone.localtime(venta.fecha_hora).strftime('%Y-%m-%d %H:%M')}\n"
            f"Cliente: {cliente}\n"
            f"Producto: {venta.producto.nombre}\n"
            f"Cantidad: {venta.cantidad}\n"
            f"Valor unitario: ${float(venta.precio_unitario):.2f}\n"
            f"Total: ${float(venta.total):.2f}\n"
            f"{linea_comision}"
            f"{linea_medio_pago}"
            f"{detalle_deuda}"
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
