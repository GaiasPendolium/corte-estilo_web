from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.http import HttpResponse
from datetime import datetime, timedelta
from decimal import Decimal
import csv
import io

from .models import (
    Usuario, Estilista, Servicio, Cliente, Producto,
    ServicioRealizado, VentaProducto, MovimientoInventario
)
from .serializers import (
    UsuarioSerializer, EstilistaSerializer, ServicioSerializer, ClienteSerializer,
    ProductoSerializer, ServicioRealizadoSerializer, VentaProductoSerializer,
    MovimientoInventarioSerializer, ReporteVentasSerializer,
    ReporteServiciosSerializer, EstadisticasGeneralesSerializer
)


def _es_admin_o_gerente(user):
    return getattr(user, 'rol', None) in ['administrador', 'gerente']


def _validar_edicion_admin_gerente(user, recurso):
    if not _es_admin_o_gerente(user):
        raise PermissionDenied(f'Solo administrador o gerente puede modificar {recurso}.')


class UsuarioViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo Usuario"""
    
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['rol', 'activo']
    search_fields = ['username', 'nombre_completo']
    ordering_fields = ['username', 'fecha_creacion']
    ordering = ['-fecha_creacion']
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Obtener información del usuario actual"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cambiar_password(self, request, pk=None):
        """Cambiar contraseña de un usuario"""
        usuario = self.get_object()
        password = request.data.get('password')
        
        if not password:
            return Response(
                {'error': 'La contraseña es requerida'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        usuario.set_password(password)
        usuario.save()
        
        return Response({'message': 'Contraseña actualizada exitosamente'})


class EstilistaViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo Estilista"""
    
    queryset = Estilista.objects.all()
    serializer_class = EstilistaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['activo']
    search_fields = ['nombre', 'telefono', 'email']
    ordering_fields = ['nombre', 'fecha_ingreso']
    ordering = ['nombre']
    
    @action(detail=True, methods=['get'])
    def estadisticas(self, request, pk=None):
        """Obtener estadísticas de un estilista"""
        estilista = self.get_object()
        
        # Obtener rango de fechas de los parámetros
        fecha_inicio = request.query_params.get('fecha_inicio')
        fecha_fin = request.query_params.get('fecha_fin')
        
        servicios = estilista.servicios_realizados.all()
        
        if fecha_inicio:
            servicios = servicios.filter(fecha_hora__gte=fecha_inicio)
        if fecha_fin:
            servicios = servicios.filter(fecha_hora__lte=fecha_fin)
        
        total_servicios = servicios.count()
        total_ingresos = servicios.aggregate(total=Sum('precio_cobrado'))['total'] or 0
        comision = float(total_ingresos) * float(estilista.comision_porcentaje) / 100
        
        return Response({
            'total_servicios': total_servicios,
            'total_ingresos': total_ingresos,
            'comision': comision,
            'comision_porcentaje': estilista.comision_porcentaje
        })


class ServicioViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo Servicio"""
    
    queryset = Servicio.objects.all()
    serializer_class = ServicioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['activo']
    search_fields = ['nombre', 'descripcion']
    ordering_fields = ['nombre', 'precio']
    ordering = ['nombre']

    def create(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios')
        return super().destroy(request, *args, **kwargs)


class ClienteViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo Cliente"""

    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'telefono']
    ordering_fields = ['nombre', 'fecha_creacion']
    ordering = ['nombre']


class ProductoViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo Producto"""
    
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['activo']
    search_fields = ['nombre', 'codigo_barras', 'marca', 'presentacion', 'descripcion']
    ordering_fields = ['nombre', 'precio_venta', 'precio_compra', 'stock']
    ordering = ['nombre']

    def create(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'productos')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'productos')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'productos')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'productos')
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'])
    def bajo_stock(self, request):
        """Obtener productos con bajo stock"""
        productos = Producto.objects.filter(
            activo=True,
            stock__lte=F('stock_minimo')
        )
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def ajustar_stock(self, request, pk=None):
        """Ajustar stock de un producto"""
        producto = self.get_object()
        nuevo_stock = request.data.get('stock')
        descripcion = request.data.get('descripcion', 'Ajuste manual de stock')
        
        if nuevo_stock is None:
            return Response(
                {'error': 'El nuevo stock es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            nuevo_stock = int(nuevo_stock)
            if nuevo_stock < 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response(
                {'error': 'El stock debe ser un número entero positivo'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crear movimiento de inventario
        MovimientoInventario.objects.create(
            producto=producto,
            tipo_movimiento='ajuste',
            cantidad=nuevo_stock,
            descripcion=descripcion,
            usuario=request.user
        )
        
        producto.stock = nuevo_stock
        producto.save()
        
        serializer = self.get_serializer(producto)
        return Response(serializer.data)


class ServicioRealizadoViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo ServicioRealizado"""
    
    queryset = ServicioRealizado.objects.select_related('estilista', 'servicio', 'cliente').all()
    serializer_class = ServicioRealizadoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['estilista', 'servicio', 'cliente', 'estado', 'medio_pago']
    search_fields = ['notas', 'estilista__nombre', 'servicio__nombre', 'cliente__nombre']
    ordering_fields = ['fecha_hora', 'precio_cobrado']
    ordering = ['-fecha_hora']
    
    def get_queryset(self):
        """Filtrar por rango de fechas si se proporciona"""
        queryset = super().get_queryset()
        
        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        
        if fecha_inicio:
            queryset = queryset.filter(fecha_hora__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha_hora__lte=fecha_fin)
        
        return queryset

    @action(detail=False, methods=['get'])
    def estado_estilistas(self, request):
        """Retorna estilistas libres y ocupados"""
        estilistas = Estilista.objects.filter(activo=True).order_by('nombre')
        servicios_en_proceso = ServicioRealizado.objects.filter(estado='en_proceso').select_related('servicio', 'cliente', 'estilista')
        mapa_ocupados = {srv.estilista_id: srv for srv in servicios_en_proceso}

        data = []
        for estilista in estilistas:
            servicio_activo = mapa_ocupados.get(estilista.id)
            if servicio_activo:
                data.append(
                    {
                        'estilista_id': estilista.id,
                        'estilista_nombre': estilista.nombre,
                        'estado': 'ocupado',
                        'servicio_realizado_id': servicio_activo.id,
                        'servicio_nombre': servicio_activo.servicio.nombre,
                        'cliente_nombre': servicio_activo.cliente.nombre if servicio_activo.cliente else None,
                        'fecha_inicio': servicio_activo.fecha_inicio,
                    }
                )
            else:
                data.append(
                    {
                        'estilista_id': estilista.id,
                        'estilista_nombre': estilista.nombre,
                        'estado': 'libre',
                        'servicio_realizado_id': None,
                        'servicio_nombre': None,
                        'cliente_nombre': None,
                        'fecha_inicio': None,
                    }
                )

        return Response(data)

    @action(detail=True, methods=['post'])
    def finalizar(self, request, pk=None):
        """Finaliza un servicio en proceso y calcula reparto"""
        servicio_realizado = self.get_object()

        if servicio_realizado.estado == 'finalizado':
            return Response({'error': 'El servicio ya está finalizado.'}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'estado': 'finalizado',
            'precio_cobrado': request.data.get('precio_cobrado', servicio_realizado.precio_cobrado),
            'medio_pago': request.data.get('medio_pago'),
            'tipo_reparto_establecimiento': request.data.get('tipo_reparto_establecimiento'),
            'valor_reparto_establecimiento': request.data.get('valor_reparto_establecimiento'),
            'notas': request.data.get('notas', servicio_realizado.notas),
            'fecha_fin': timezone.now(),
        }

        serializer = self.get_serializer(servicio_realizado, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def factura(self, request, pk=None):
        servicio_realizado = self.get_object()
        return Response(
            {
                'numero_factura': servicio_realizado.numero_factura,
                'factura_texto': servicio_realizado.factura_texto,
            }
        )


class VentaProductoViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo VentaProducto"""
    
    queryset = VentaProducto.objects.select_related('producto', 'usuario').all()
    serializer_class = VentaProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['producto', 'usuario']
    search_fields = ['producto__nombre', 'producto__codigo_barras', 'cliente_nombre', 'numero_factura']
    ordering_fields = ['fecha_hora', 'total']
    ordering = ['-fecha_hora']

    def create(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')
        return super().destroy(request, *args, **kwargs)
    
    def get_queryset(self):
        """Filtrar por rango de fechas si se proporciona"""
        queryset = super().get_queryset()
        
        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        
        if fecha_inicio:
            queryset = queryset.filter(fecha_hora__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha_hora__lte=fecha_fin)
        
        return queryset
    
    def perform_create(self, serializer):
        """Asignar usuario actual a la venta"""
        serializer.save(usuario=self.request.user)

    def perform_destroy(self, instance):
        """Al eliminar una venta, devuelve stock al inventario"""
        producto = instance.producto
        producto.stock += instance.cantidad
        producto.save()

        MovimientoInventario.objects.create(
            producto=producto,
            tipo_movimiento='entrada',
            cantidad=instance.cantidad,
            descripcion=f'Reverso por eliminación factura {instance.numero_factura or instance.id}',
            usuario=self.request.user,
        )
        instance.delete()

    @action(detail=True, methods=['get'])
    def factura(self, request, pk=None):
        venta = self.get_object()
        return Response(
            {
                'numero_factura': venta.numero_factura,
                'factura_texto': venta.factura_texto,
            }
        )


class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    """ViewSet para el modelo MovimientoInventario"""
    
    queryset = MovimientoInventario.objects.select_related('producto', 'usuario').all()
    serializer_class = MovimientoInventarioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['producto', 'tipo_movimiento']
    search_fields = ['producto__nombre', 'descripcion']
    ordering_fields = ['fecha_hora']
    ordering = ['-fecha_hora']
    
    def get_queryset(self):
        """Filtrar por rango de fechas si se proporciona"""
        queryset = super().get_queryset()
        
        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        
        if fecha_inicio:
            queryset = queryset.filter(fecha_hora__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha_hora__lte=fecha_fin)
        
        return queryset
    
    def perform_create(self, serializer):
        """Asignar usuario actual al movimiento"""
        serializer.save(usuario=self.request.user)


# Vistas para reportes y estadísticas

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estadisticas_generales(request):
    """Obtener estadísticas generales del negocio"""
    
    # Obtener rango de fechas
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin = request.query_params.get('fecha_fin')
    
    # Si no se proporcionan fechas, usar el mes actual
    if not fecha_inicio or not fecha_fin:
        hoy = timezone.now()
        fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
        fecha_fin = hoy.strftime('%Y-%m-%d')
    
    # Filtrar ventas
    ventas = VentaProducto.objects.filter(
        fecha_hora__gte=fecha_inicio,
        fecha_hora__lte=fecha_fin
    )
    
    # Filtrar servicios
    servicios = ServicioRealizado.objects.filter(
        fecha_hora__gte=fecha_inicio,
        fecha_hora__lte=fecha_fin
    )
    
    # Calcular totales
    total_ventas = ventas.aggregate(total=Sum('total'))['total'] or 0
    total_servicios = servicios.aggregate(total=Sum('precio_cobrado'))['total'] or 0
    
    # Productos bajo stock
    productos_bajo_stock = Producto.objects.filter(
        activo=True,
        stock__lte=F('stock_minimo')
    ).count()
    
    data = {
        'total_ventas_productos': total_ventas,
        'total_servicios': total_servicios,
        'total_general': float(total_ventas) + float(total_servicios),
        'cantidad_ventas': ventas.count(),
        'cantidad_servicios': servicios.count(),
        'productos_bajo_stock': productos_bajo_stock
    }
    
    serializer = EstadisticasGeneralesSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_ventas(request):
    """Generar reporte de ventas por fecha"""
    
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin = request.query_params.get('fecha_fin')
    
    if not fecha_inicio or not fecha_fin:
        return Response(
            {'error': 'Fecha de inicio y fin son requeridas'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    ventas = VentaProducto.objects.filter(
        fecha_hora__gte=fecha_inicio,
        fecha_hora__lte=fecha_fin
    ).extra(select={'fecha': 'date(fecha_hora)'}).values('fecha').annotate(
        total_ventas=Sum('total'),
        cantidad_ventas=Count('id')
    ).order_by('fecha')
    
    serializer = ReporteVentasSerializer(ventas, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_servicios(request):
    """Generar reporte de servicios por fecha"""
    
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin = request.query_params.get('fecha_fin')
    
    if not fecha_inicio or not fecha_fin:
        return Response(
            {'error': 'Fecha de inicio y fin son requeridas'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    servicios = ServicioRealizado.objects.filter(
        fecha_hora__gte=fecha_inicio,
        fecha_hora__lte=fecha_fin
    ).extra(select={'fecha': 'date(fecha_hora)'}).values('fecha').annotate(
        total_servicios=Sum('precio_cobrado'),
        cantidad_servicios=Count('id')
    ).order_by('fecha')
    
    serializer = ReporteServiciosSerializer(servicios, many=True)
    return Response(serializer.data)


def _resolver_rango_fechas(request):
    periodo = request.query_params.get('periodo', 'mes')
    fecha_inicio = request.query_params.get('fecha_inicio')
    fecha_fin = request.query_params.get('fecha_fin')

    hoy = timezone.localdate()
    if fecha_inicio and fecha_fin:
        return fecha_inicio, fecha_fin

    if periodo == 'semana':
        inicio = hoy - timedelta(days=hoy.weekday())
        fin = hoy
    else:
        inicio = hoy.replace(day=1)
        fin = hoy

    return inicio.strftime('%Y-%m-%d'), fin.strftime('%Y-%m-%d')


def _calcular_datos_bi(request):
    """Función helper que calcula todos los datos de BI y retorna un diccionario"""
    fecha_inicio, fecha_fin = _resolver_rango_fechas(request)

    ventas_qs = VentaProducto.objects.select_related('producto', 'estilista').filter(
        fecha_hora__date__gte=fecha_inicio,
        fecha_hora__date__lte=fecha_fin,
    )
    servicios_qs = ServicioRealizado.objects.select_related('estilista').filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio,
        fecha_hora__date__lte=fecha_fin,
    )

    ingresos_productos = Decimal(ventas_qs.aggregate(total=Sum('total'))['total'] or 0)
    costo_productos = Decimal(0)
    comision_producto_estilistas = Decimal(0)

    top_productos_mapa = {}
    for venta in ventas_qs:
        costo_unitario = Decimal(venta.producto.precio_compra or 0)
        costo_productos += costo_unitario * Decimal(venta.cantidad)

        if venta.estilista:
            pct = Decimal(venta.estilista.comision_ventas_productos or 0)
            comision_producto_estilistas += (Decimal(venta.total) * pct) / Decimal(100)

        key = venta.producto_id
        if key not in top_productos_mapa:
            top_productos_mapa[key] = {
                'producto_id': venta.producto_id,
                'producto_nombre': venta.producto.nombre,
                'cantidad': 0,
                'total': Decimal(0),
            }
        top_productos_mapa[key]['cantidad'] += int(venta.cantidad)
        top_productos_mapa[key]['total'] += Decimal(venta.total)

    utilidad_productos = ingresos_productos - costo_productos
    ganancia_establecimiento_productos = utilidad_productos - comision_producto_estilistas

    comision_servicios_establecimiento = Decimal(servicios_qs.aggregate(total=Sum('monto_establecimiento'))['total'] or 0)
    pago_base_servicios_estilistas = Decimal(servicios_qs.aggregate(total=Sum('monto_estilista'))['total'] or 0)
    ingresos_servicios = Decimal(servicios_qs.aggregate(total=Sum('precio_cobrado'))['total'] or 0)

    estilistas_data = []
    total_descuentos_espacio = Decimal(0)
    total_pago_neto_estilistas = Decimal(0)

    for estilista in Estilista.objects.filter(activo=True):
        servicios_est = servicios_qs.filter(estilista=estilista)
        ventas_est = ventas_qs.filter(estilista=estilista)

        ganancia_servicios_est = Decimal(servicios_est.aggregate(total=Sum('monto_estilista'))['total'] or 0)
        total_servicios_est = Decimal(servicios_est.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
        dias_con_servicios = servicios_est.values_list('fecha_hora__date', flat=True).distinct().count()
        comision_ventas_producto_est = Decimal(0)
        for v in ventas_est:
            pct = Decimal(estilista.comision_ventas_productos or 0)
            comision_ventas_producto_est += (Decimal(v.total) * pct) / Decimal(100)

        ganancias_brutas_est = ganancia_servicios_est + comision_ventas_producto_est

        descuento_espacio = Decimal(0)
        if estilista.tipo_cobro_espacio == 'porcentaje_neto':
            descuento_espacio = (ganancias_brutas_est * Decimal(estilista.valor_cobro_espacio or 0)) / Decimal(100)
        elif estilista.tipo_cobro_espacio == 'costo_fijo_neto':
            descuento_espacio = Decimal(estilista.valor_cobro_espacio or 0)

        if descuento_espacio > ganancias_brutas_est:
            descuento_espacio = ganancias_brutas_est

        pago_neto = ganancias_brutas_est - descuento_espacio

        total_descuentos_espacio += descuento_espacio
        total_pago_neto_estilistas += pago_neto

        estilistas_data.append(
            {
                'estilista_id': estilista.id,
                'estilista_nombre': estilista.nombre,
                'tipo_cobro_espacio': estilista.tipo_cobro_espacio,
                'valor_cobro_espacio': float(estilista.valor_cobro_espacio or 0),
                'base_cobro_espacio': float(total_servicios_est if estilista.tipo_cobro_espacio == 'comision' else ganancias_brutas_est),
                'dias_cobrados_alquiler': int(dias_con_servicios if estilista.tipo_cobro_espacio == 'alquiler' else 0),
                'ganancias_servicios': float(ganancia_servicios_est),
                'comision_ventas_producto': float(comision_ventas_producto_est),
                'ganancias_totales_brutas': float(ganancias_brutas_est),
                'descuento_espacio': float(descuento_espacio),
                'pago_neto_estilista': float(pago_neto),
            }
        )

    ganancia_establecimiento_total = (
        ganancia_establecimiento_productos
        + comision_servicios_establecimiento
        + total_descuentos_espacio
    )

    venta_neta_total = ingresos_productos + ingresos_servicios

    productos_bajo_stock_qs = Producto.objects.filter(activo=True, stock__lte=F('stock_minimo')).order_by('stock')
    top_productos = sorted(top_productos_mapa.values(), key=lambda x: x['cantidad'], reverse=True)[:10]

    series_diaria = []
    cursor = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
    fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    while cursor <= fin:
        ventas_dia = Decimal(ventas_qs.filter(fecha_hora__date=cursor).aggregate(total=Sum('total'))['total'] or 0)
        servicios_dia = Decimal(servicios_qs.filter(fecha_hora__date=cursor).aggregate(total=Sum('precio_cobrado'))['total'] or 0)
        series_diaria.append(
            {
                'fecha': cursor.strftime('%Y-%m-%d'),
                'ventas_productos': float(ventas_dia),
                'ventas_servicios': float(servicios_dia),
                'total': float(ventas_dia + servicios_dia),
            }
        )
        cursor += timedelta(days=1)

    return {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'kpis': {
            'venta_neta_total': float(venta_neta_total),
            'ingresos_productos': float(ingresos_productos),
            'ingresos_servicios': float(ingresos_servicios),
            'costo_productos': float(costo_productos),
            'utilidad_productos': float(utilidad_productos),
            'comision_producto_estilistas': float(comision_producto_estilistas),
            'comision_servicios_establecimiento': float(comision_servicios_establecimiento),
            'ganancia_establecimiento_productos': float(ganancia_establecimiento_productos),
            'ganancia_establecimiento_total': float(ganancia_establecimiento_total),
            'pago_total_estilistas': float(total_pago_neto_estilistas),
            'descuentos_espacio_estilistas': float(total_descuentos_espacio),
            'cantidad_ventas_productos': ventas_qs.count(),
            'cantidad_servicios': servicios_qs.count(),
            'productos_bajo_stock': productos_bajo_stock_qs.count(),
        },
        'estilistas': estilistas_data,
        'productos_bajo_stock': [
            {
                'id': p.id,
                'nombre': p.nombre,
                'stock': p.stock,
                'stock_minimo': p.stock_minimo,
            }
            for p in productos_bajo_stock_qs
        ],
        'top_ventas_productos': [
            {
                **x,
                'total': float(x['total']),
            }
            for x in top_productos
        ],
        'serie_diaria': series_diaria,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_resumen(request):
    """Vista API que retorna datos de BI como JSON"""
    data = _calcular_datos_bi(request)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_export_csv(request):
    try:
        data = _calcular_datos_bi(request)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="reporte_bi_{data["fecha_inicio"]}_{data["fecha_fin"]}.csv"'

        writer = csv.writer(response)
        writer.writerow(['REPORTE BI'])
        writer.writerow(['Rango', f"{data['fecha_inicio']} a {data['fecha_fin']}"])
        writer.writerow([])
        writer.writerow(['KPI', 'Valor'])
        for k, v in data['kpis'].items():
            writer.writerow([k, v])
        writer.writerow([])
        writer.writerow(['Estilista', 'Ganancias Brutas', 'Descuento Espacio', 'Pago Neto'])
        for est in data['estilistas']:
            writer.writerow([
                est['estilista_nombre'],
                est['ganancias_totales_brutas'],
                est['descuento_espacio'],
                est['pago_neto_estilista'],
            ])

        return response
    except Exception as e:
        return Response(
            {'error': f'Error generando CSV: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_export_pdf(request):
    try:
        data = _calcular_datos_bi(request)
    except Exception as e:
        return Response(
            {'error': f'Error obteniendo datos para PDF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        return Response(
            {'error': 'La exportación PDF requiere instalar reportlab.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        y = height - 40
        pdf.setFont('Helvetica-Bold', 14)
        pdf.drawString(40, y, 'Reporte Ejecutivo BI')
        y -= 20
        pdf.setFont('Helvetica', 10)
        pdf.drawString(40, y, f"Rango: {data['fecha_inicio']} a {data['fecha_fin']}")
        y -= 25

        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(40, y, 'KPIs')
        y -= 15
        pdf.setFont('Helvetica', 9)
        for k, v in data['kpis'].items():
            pdf.drawString(50, y, f"- {k}: {v}")
            y -= 12
            if y < 60:
                pdf.showPage()
                y = height - 40
                pdf.setFont('Helvetica', 9)

        y -= 10
        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(40, y, 'Liquidacion por Estilista')
        y -= 15
        pdf.setFont('Helvetica', 9)
        for est in data['estilistas']:
            line = (
                f"{est['estilista_nombre']} | Bruto: {est['ganancias_totales_brutas']} | "
                f"Descuento: {est['descuento_espacio']} | Neto: {est['pago_neto_estilista']}"
            )
            pdf.drawString(50, y, line[:110])
            y -= 12
            if y < 60:
                pdf.showPage()
                y = height - 40
                pdf.setFont('Helvetica', 9)

        pdf.save()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="reporte_bi_{data["fecha_inicio"]}_{data["fecha_fin"]}.pdf"'
        return response
    except Exception as e:
        return Response(
            {'error': f'Error generando PDF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_resumen_diario(request):
    hoy = timezone.localdate().strftime('%Y-%m-%d')

    ventas = VentaProducto.objects.filter(fecha_hora__date=hoy)
    servicios = ServicioRealizado.objects.filter(estado='finalizado', fecha_hora__date=hoy)

    ventas_total = Decimal(ventas.aggregate(total=Sum('total'))['total'] or 0)
    servicios_total = Decimal(servicios.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
    total_dia = ventas_total + servicios_total

    costo_productos = Decimal(0)
    for v in ventas.select_related('producto'):
        costo_productos += Decimal(v.producto.precio_compra or 0) * Decimal(v.cantidad)

    utilidad_productos = ventas_total - costo_productos
    comision_servicios_est = Decimal(servicios.aggregate(total=Sum('monto_establecimiento'))['total'] or 0)

    texto = (
        f"Resumen diario {hoy}\n"
        f"Ventas productos: ${float(ventas_total):.2f}\n"
        f"Ventas servicios: ${float(servicios_total):.2f}\n"
        f"Venta neta total: ${float(total_dia):.2f}\n"
        f"Costo productos: ${float(costo_productos):.2f}\n"
        f"Utilidad productos: ${float(utilidad_productos):.2f}\n"
        f"Comisión establecimiento por servicios: ${float(comision_servicios_est):.2f}\n"
        f"Facturas productos: {ventas.count()}\n"
        f"Servicios finalizados: {servicios.count()}"
    )

    return Response(
        {
            'fecha': hoy,
            'ventas_productos': float(ventas_total),
            'ventas_servicios': float(servicios_total),
            'venta_neta_total': float(total_dia),
            'utilidad_productos': float(utilidad_productos),
            'comision_servicios_establecimiento': float(comision_servicios_est),
            'facturas_productos': ventas.count(),
            'servicios_finalizados': servicios.count(),
            'texto_resumen': texto,
        }
    )
