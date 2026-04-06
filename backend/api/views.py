from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count, Q, F
from django.db import transaction, connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import HttpResponse
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import base64
import csv
import io
import os
import uuid
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .models import (
    Usuario, Estilista, Servicio, Cliente, Producto,
    ServicioRealizado, VentaProducto, MovimientoInventario, EstadoPagoEstilistaDia,
    DeudaConsumoEmpleado, AbonoDeudaEmpleado, ServicioRealizadoAdicional,
    EstadoPagoEstilistaHistorial, FactLiquidacionEstilistaDia
)
from .serializers import (
    UsuarioSerializer, EstilistaSerializer, ServicioSerializer, ClienteSerializer,
    ProductoSerializer, ServicioRealizadoSerializer, VentaProductoSerializer,
    MovimientoInventarioSerializer, ReporteVentasSerializer,
    ReporteServiciosSerializer, EstadisticasGeneralesSerializer
)


def _es_admin_o_gerente(user):
    rol_user = (getattr(user, 'rol', '') or '').strip().lower()
    return rol_user in {'administrador', 'gerente'}


def _qz_allowed_origins():
    raw = os.environ.get('QZ_ALLOWED_ORIGINS', '').strip()
    if not raw:
        return []
    return [item.strip().rstrip('/') for item in raw.split(',') if item.strip()]


def _qz_check_origin(request):
    allowed = _qz_allowed_origins()
    if not allowed:
        return None

    origin = (request.headers.get('Origin') or '').strip().rstrip('/')
    if origin in allowed:
        return None

    return HttpResponse('Origin no autorizado para firma QZ', status=403, content_type='text/plain; charset=utf-8')


@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def qz_certificate(request):
    blocked = _qz_check_origin(request)
    if blocked:
        return blocked

    cert = os.environ.get('QZ_CERT_PEM', '').strip()
    if not cert:
        return HttpResponse('QZ_CERT_PEM no configurado', status=500, content_type='text/plain; charset=utf-8')

    return HttpResponse(f'{cert}\n', content_type='text/plain; charset=utf-8')


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def qz_sign(request):
    blocked = _qz_check_origin(request)
    if blocked:
        return blocked

    to_sign = request.data.get('toSign', '')
    if not isinstance(to_sign, str) or not to_sign:
        return HttpResponse('Campo toSign requerido', status=400, content_type='text/plain; charset=utf-8')

    private_key_pem = os.environ.get('QZ_PRIVATE_KEY_PEM', '').strip()
    if not private_key_pem:
        return HttpResponse('QZ_PRIVATE_KEY_PEM no configurado', status=500, content_type='text/plain; charset=utf-8')

    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None,
        )
        signature = private_key.sign(
            to_sign.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        signature_b64 = base64.b64encode(signature).decode('ascii')
        return HttpResponse(signature_b64, content_type='text/plain; charset=utf-8')
    except Exception:
        return HttpResponse('No se pudo firmar la solicitud', status=500, content_type='text/plain; charset=utf-8')


def _es_recepcion(user):
    rol_user = (getattr(user, 'rol', '') or '').strip().lower()
    return rol_user in {'recepcion', 'recepcionista', 'recepción'}


def _validar_edicion_admin_gerente(user, recurso):
    if not _es_admin_o_gerente(user):
        raise PermissionDenied(f'Solo administrador o gerente puede modificar {recurso}.')


def _sanitizar_bi_para_recepcion(data):
    """Oculta datos de módulos restringidos para recepción."""
    if not isinstance(data, dict):
        return data
    data['productos_bajo_stock'] = []
    return data


def _fecha_operativa_desde_dt(fecha_hora):
    """Normaliza DateTime a fecha local para evitar descuadres UTC/local en BI."""
    if not fecha_hora:
        return None
    if timezone.is_aware(fecha_hora):
        return timezone.localtime(fecha_hora).date()
    return fecha_hora.date()


def _normalizar_fecha_hora_request(fecha_hora_raw):
    """Parsea fecha/hora de request y la normaliza a datetime aware local."""
    if fecha_hora_raw in (None, ''):
        return None

    dt = None
    if isinstance(fecha_hora_raw, datetime):
        dt = fecha_hora_raw
    else:
        raw = str(fecha_hora_raw).strip()
        dt = parse_datetime(raw)
        if dt is None:
            try:
                dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except Exception:
                dt = None

    if dt is None:
        raise ValueError('Formato de fecha_hora inválido. Usa ISO 8601 (YYYY-MM-DDTHH:MM).')

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _monto_estilista_resuelto(srv):
    """
    Calcula monto del estilista usando la regla vigente.

    Para servicios sin reparto explícito, el valor completo pertenece al empleado.
    Solo Shampoo o un reparto explícito generan ganancia directa del establecimiento.
    """
    neto = Decimal(srv.neto_servicio or srv.precio_cobrado or 0)
    if neto <= 0:
        return Decimal(0)

    tipo_reparto = str(srv.tipo_reparto_establecimiento or '').strip().lower()
    monto_establecimiento = Decimal(srv.monto_establecimiento or 0)
    nombre_servicio = str(getattr(getattr(srv, 'servicio', None), 'nombre', '') or '').lower()

    if 'shampoo' in nombre_servicio:
        return Decimal(0)

    # Si el servicio sí tiene reparto explícito, usarlo como fuente de verdad.
    if tipo_reparto in {'porcentaje', 'monto'}:
        monto_calc = neto - monto_establecimiento
        if monto_calc < 0:
            return Decimal(0)
        if monto_calc > neto:
            return neto
        return monto_calc

    return neto


def _monto_establecimiento_resuelto(srv):
    """Calcula la porción del establecimiento con la misma regla vigente."""
    neto = Decimal(srv.neto_servicio or srv.precio_cobrado or 0)
    if neto <= 0:
        return Decimal(0)

    tipo_reparto = str(srv.tipo_reparto_establecimiento or '').strip().lower()
    monto_establecimiento = Decimal(srv.monto_establecimiento or 0)
    nombre_servicio = str(getattr(getattr(srv, 'servicio', None), 'nombre', '') or '').lower()

    if 'shampoo' in nombre_servicio:
        return neto

    if tipo_reparto in {'porcentaje', 'monto'}:
        if monto_establecimiento < 0:
            return Decimal(0)
        if monto_establecimiento > neto:
            return neto
        return monto_establecimiento

    return Decimal(0)


def _descuento_puesto_dia(estilista, base_servicio_dia):
    """
    Calcula descuento diario de puesto sin doble descuento.

    Regla clave: el porcentaje de espacio se cobra aquí, en liquidación diaria,
    no en la factura del servicio.
    """
    tipo = str(getattr(estilista, 'tipo_cobro_espacio', '') or '').strip().lower()
    valor_cfg = Decimal(getattr(estilista, 'valor_cobro_espacio', 0) or 0)

    if tipo == 'costo_fijo_neto':
        return max(Decimal(0), valor_cfg)

    if tipo == 'porcentaje_neto':
        if valor_cfg < 0:
            valor_cfg = Decimal(0)
        if valor_cfg > 100:
            valor_cfg = Decimal(100)
        descuento = (Decimal(base_servicio_dia or 0) * valor_cfg) / Decimal(100)
        if descuento > Decimal(base_servicio_dia or 0):
            descuento = Decimal(base_servicio_dia or 0)
        return max(descuento, Decimal(0))

    return Decimal(0)


def _insertar_historial_legacy(estilista_id, fecha, estado_anterior, estado_nuevo, notas, usuario_id, monto_liquidado):
    """Inserta historial en esquema antiguo (sin columnas abono_puesto/pendiente_puesto)."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO estado_pago_estilista_historial
            (estilista_id, fecha, estado_anterior, estado_nuevo, notas, usuario_id, monto_liquidado, fecha_cambio)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                estilista_id,
                fecha,
                estado_anterior,
                estado_nuevo,
                notas,
                usuario_id,
                monto_liquidado,
                timezone.now(),
            ],
        )


def _listar_historial_legacy(fecha_inicio, fecha_fin, estilista_id=None, limit=100):
    """Lee historial desde esquema antiguo usando SQL crudo para compatibilidad."""
    sql = """
        SELECT
            h.id,
            h.estilista_id,
            e.nombre AS estilista_nombre,
            h.fecha,
            h.estado_anterior,
            h.estado_nuevo,
            h.notas,
            h.usuario_id,
            COALESCE(u.nombre_completo, 'Sistema') AS usuario_nombre,
            h.monto_liquidado,
            h.fecha_cambio
        FROM estado_pago_estilista_historial h
        INNER JOIN estilistas e ON e.id = h.estilista_id
        LEFT JOIN usuarios u ON u.id = h.usuario_id
        WHERE h.fecha >= %s AND h.fecha <= %s
    """
                # [3] TOTAL PAGABLE AL EMPLEADO = neto del día (ganancias menos puesto del día).

    if estilista_id:
        sql += " AND h.estilista_id = %s"
        params.append(int(estilista_id))

    sql += " ORDER BY h.fecha_cambio DESC, h.fecha DESC LIMIT %s"
    params.append(int(limit))

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    registros = []
    for row in rows:
        fecha_val = row[3]
        fecha_cambio_val = row[10]
        monto_liquidado = Decimal(str(row[9] or 0))

        if isinstance(fecha_val, datetime):
            fecha_str = fecha_val.strftime('%Y-%m-%d')
        else:
            fecha_str = str(fecha_val)

        if isinstance(fecha_cambio_val, datetime):
            try:
                fecha_cambio_str = timezone.localtime(fecha_cambio_val).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                fecha_cambio_str = fecha_cambio_val.strftime('%Y-%m-%d %H:%M:%S')
        else:
            fecha_cambio_str = str(fecha_cambio_val)

        descuento_dia_estimado = Decimal(0)
        ganancias_totales_estimadas = Decimal(0)
        try:
            estilista_hist = Estilista.objects.filter(id=row[1]).first()
            fecha_calc = fecha_val.date() if isinstance(fecha_val, datetime) else fecha_val
            if estilista_hist and fecha_calc:
                ganancias_totales_estimadas, descuento_dia_estimado, _ = _calcular_totales_dia_estilista(estilista_hist, fecha_calc)
        except Exception:
            descuento_dia_estimado = Decimal(0)
            ganancias_totales_estimadas = Decimal(0)

        abono_estimado = max(Decimal(0), ganancias_totales_estimadas - monto_liquidado)
        pendiente_estimado = max(Decimal(0), descuento_dia_estimado - abono_estimado)

        registros.append(
            {
                'id': row[0],
                'estilista_id': row[1],
                'estilista_nombre': row[2],
                'fecha': fecha_str,
                'estado_anterior': row[4],
                'estado_nuevo': row[5],
                'notas': row[6],
                'usuario_id': row[7],
                'usuario_nombre': row[8],
                'monto_liquidado': float(monto_liquidado),
                'abono_puesto': float(abono_estimado),
                'pendiente_puesto': float(pendiente_estimado),
                'fecha_cambio': fecha_cambio_str,
            }
        )

    return registros


def calcular_liquidacion_dia_estilista(estilista, fecha_dia):
    """
    LIQUIDADOR SIMPLIFICADO Y CLARO:
    
    Calcula para UN DÍA:
    1. GANANCIAS TOTALES = servicios base + comisiones (producto + adicionales)
    2. DESCUENTO PUESTO = ganancias × % (o monto fijo)
    3. TOTAL PAGABLE = ganancias - descuento
    
    Returns: dict con todos los cálculos {ganancias, descuento, pagable}
    """
    
    # ============ [1] SERVICIOS BASE (PAGABLE AL EMPLEADO) ============
    servicios_dia = ServicioRealizado.objects.select_related('servicio', 'estilista').filter(
        estado='finalizado',
        estilista=estilista,
        fecha_hora__date=fecha_dia,
    )
    servicios_base = Decimal(0)
    for srv in servicios_dia:
        servicios_base += _monto_estilista_resuelto(srv)
    
    # ============ [2] COMISIONES POR SERVICIOS ADICIONALES ============
    adicionales_dia = ServicioRealizadoAdicional.objects.filter(
        estilista=estilista,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date=fecha_dia,
    )
    comisiones_adicionales = Decimal(0)
    for ad in adicionales_dia:
        valor_cobrado = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        pct_est = max(Decimal(0), min(Decimal(100), pct_est))  # Clamp 0-100
        monto_estilista = valor_cobrado - (valor_cobrado * pct_est / Decimal(100))
        comisiones_adicionales += monto_estilista
    
    # ============ [3] COMISIONES POR VENTA DE PRODUCTOS (CAJA) ============
    ventas_dia = VentaProducto.objects.select_related('producto').filter(
        estilista=estilista,
        tipo_operacion='venta',
        fecha_hora__date=fecha_dia,
    )
    comisiones_ventas_caja = Decimal(0)
    for venta in ventas_dia:
        monto_venta = Decimal(venta.total or 0)
        pct_comision = Decimal(venta.producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))  # Clamp 0-100
        comisiones_ventas_caja += (monto_venta * pct_comision) / Decimal(100)

    # ============ [4] COMISIONES POR PRODUCTO ADICIONAL EN SERVICIOS ============
    servicios_con_producto_adicional = ServicioRealizado.objects.select_related('adicional_otro_producto').filter(
        estado='finalizado',
        fecha_hora__date=fecha_dia,
        adicional_otro_producto__isnull=False,
        adicional_otro_estilista=estilista,
    )
    comisiones_ventas_servicios = Decimal(0)
    for srv in servicios_con_producto_adicional:
        cantidad = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        monto_venta = precio_venta * cantidad
        pct_comision = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_servicios += (monto_venta * pct_comision) / Decimal(100)

    comisiones_ventas = comisiones_ventas_caja + comisiones_ventas_servicios
    
    # [1] GANANCIAS TOTALES = BASE + TODAS LAS COMISIONES
    ganancias_totales = servicios_base + comisiones_adicionales + comisiones_ventas
    
    # ============ [2] DESCUENTO POR PUESTO ============
    # La base del puesto debe usar el valor de servicios del empleado (incluye
    # servicios adicionales asignados), pero no comisiones de ventas de producto.
    base_puesto = servicios_base + comisiones_adicionales
    descuento_puesto = _descuento_puesto_dia(estilista, base_puesto)
    
    # [2] TOTAL PAGABLE AL EMPLEADO = ganancias completas del día.
    # La deuda del puesto se registra por separado y puede quedar pendiente.
    total_pagable = max(ganancias_totales - descuento_puesto, Decimal(0))
    
    return {
        'ganancias_totales': ganancias_totales,
        'servicios_base': servicios_base,
        'comisiones_adicionales': comisiones_adicionales,
        'comisiones_ventas_caja': comisiones_ventas_caja,
        'comisiones_ventas_servicios': comisiones_ventas_servicios,
        'comisiones_ventas': comisiones_ventas,
        'descuento_puesto': descuento_puesto,
        'total_pagable': total_pagable,
    }


def _calcular_totales_dia_estilista(estilista, fecha_dia):
    """LEGACY: Para compatibilidad con código antiguo"""
    calc = calcular_liquidacion_dia_estilista(estilista, fecha_dia)
    return calc['ganancias_totales'], calc['descuento_puesto'], calc['total_pagable']


def _calcular_neto_dia_estilista(estilista, fecha_dia):
    """LEGACY: Para compatibilidad"""
    calc = calcular_liquidacion_dia_estilista(estilista, fecha_dia)
    return calc['total_pagable']


def _usar_fact_liquidacion_en_reportes():
    raw = (os.environ.get('USE_FACT_LIQUIDACION_REPORTES') or '').strip().lower()
    return raw in {'1', 'true', 'si', 'sí', 'yes'}


def _cobro_consumo_dia_estilista(estilista_id, fecha_dia):
    total = Decimal(0)
    try:
        abonos_qs = AbonoDeudaEmpleado.objects.select_related('deuda').filter(deuda__estilista_id=estilista_id)
        for ab in abonos_qs:
            fecha_op = _fecha_operativa_desde_dt(ab.fecha_hora)
            if fecha_op == fecha_dia:
                total += Decimal(ab.monto or 0)
    except Exception:
        return Decimal(0)
    return total


def _upsert_fact_liquidacion_dia(
    *,
    estilista,
    fecha,
    calc,
    pago_efectivo,
    pago_nequi,
    pago_daviplata,
    pago_otros,
    abono_puesto,
    medio_abono_puesto,
    deuda_anterior,
    deuda_cierre,
    pendiente_pago,
    estado_liquidacion,
    forzar_reemplazo_dia,
    usuario,
    notas,
    origen='liquidar_dia_v2',
):
    """Sincroniza la versión vigente de fact diaria por estilista y fecha."""
    try:
        with transaction.atomic():
            FactLiquidacionEstilistaDia.objects.filter(
                estilista=estilista,
                fecha=fecha,
                vigente=True,
            ).exclude(version=1).update(vigente=False)

            fact, _ = FactLiquidacionEstilistaDia.objects.get_or_create(
                estilista=estilista,
                fecha=fecha,
                version=1,
                defaults={'vigente': True},
            )

            comision_caja = Decimal(calc.get('comisiones_ventas_caja') or 0)
            comision_servicios = Decimal(calc.get('comisiones_ventas_servicios') or 0)
            comisiones_totales = comision_caja + comision_servicios
            fact.vigente = True
            fact.origen_calculo = origen
            fact.ganancias_servicios = Decimal(calc.get('servicios_base') or 0) + Decimal(calc.get('comisiones_adicionales') or 0)
            fact.comision_producto_caja = comision_caja
            fact.comision_producto_servicios = comision_servicios
            fact.ganancias_totales = Decimal(calc.get('ganancias_totales') or 0)
            fact.descuento_puesto_dia = Decimal(calc.get('descuento_puesto') or 0)
            fact.deuda_puesto_anterior = Decimal(deuda_anterior or 0)
            fact.abono_puesto_dia = Decimal(abono_puesto or 0)
            fact.medio_abono_puesto = (medio_abono_puesto or 'efectivo').strip().lower()
            if fact.medio_abono_puesto not in {'efectivo', 'nequi', 'daviplata', 'otros'}:
                fact.medio_abono_puesto = 'efectivo'
            fact.deuda_puesto_cierre = Decimal(deuda_cierre or 0)
            fact.pago_efectivo = Decimal(pago_efectivo or 0)
            fact.pago_nequi = Decimal(pago_nequi or 0)
            fact.pago_daviplata = Decimal(pago_daviplata or 0)
            fact.pago_otros = Decimal(pago_otros or 0)
            fact.pago_total_empleado = (
                Decimal(pago_efectivo or 0)
                + Decimal(pago_nequi or 0)
                + Decimal(pago_daviplata or 0)
                + Decimal(pago_otros or 0)
            )
            fact.pendiente_pago_empleado = Decimal(pendiente_pago or 0)
            fact.cobro_consumo_dia = _cobro_consumo_dia_estilista(estilista.id, fecha)
            fact.estado_liquidacion = estado_liquidacion
            fact.forzar_reemplazo_dia = bool(forzar_reemplazo_dia)
            fact.usuario_liquida = usuario if getattr(usuario, 'is_authenticated', False) else None
            fact.notas = notas
            fact.payload_fuente = {
                'ganancias_totales': float(Decimal(calc.get('ganancias_totales') or 0)),
                'descuento_puesto': float(Decimal(calc.get('descuento_puesto') or 0)),
                'total_pagable': float(Decimal(calc.get('total_pagable') or 0)),
                'comisiones_ventas_caja': float(comision_caja),
                'comisiones_ventas_servicios': float(comision_servicios),
                'comisiones_ventas': float(comisiones_totales),
            }
            fact.save()
    except Exception:
        # No bloquear operaciones críticas de liquidación por falla de tabla fact.
        return


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

    def destroy(self, request, *args, **kwargs):
        """Elimina el empleado; si tiene historial lo desactiva en lugar de borrar."""
        from django.db.models import ProtectedError
        instance = self.get_object()
        try:
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ProtectedError:
            instance.activo = False
            instance.save()
            return Response(
                {'desactivado': True, 'mensaje': 'El empleado tiene historial de servicios y fue desactivado en lugar de eliminado, preservando sus registros.'},
                status=status.HTTP_200_OK
            )
    
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
    
    queryset = ServicioRealizado.objects.select_related(
        'estilista', 'servicio', 'cliente', 'usuario', 'adicional_otro_producto', 'adicional_otro_estilista'
    ).prefetch_related(
        'adicionales_asignados__servicio',
        'adicionales_asignados__estilista',
    ).all()
    serializer_class = ServicioRealizadoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['estilista', 'servicio', 'cliente', 'estado', 'medio_pago', 'usuario']
    search_fields = ['notas', 'estilista__nombre', 'servicio__nombre', 'cliente__nombre']
    ordering_fields = ['fecha_hora', 'precio_cobrado']
    ordering = ['-fecha_hora']

    def update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios facturados')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios facturados')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _validar_edicion_admin_gerente(request.user, 'servicios facturados')
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_destroy(self, instance):
        """Al eliminar un servicio, revierte inventario pendiente de su adicional de producto."""
        tag = f"adicional servicio #{instance.id}"

        movimientos = (
            MovimientoInventario.objects
            .filter(descripcion__icontains=tag)
            .values('producto_id', 'tipo_movimiento')
            .annotate(total=Sum('cantidad'))
        )

        saldo_por_producto = {}
        for mov in movimientos:
            pid = mov.get('producto_id')
            if not pid:
                continue
            saldo_por_producto.setdefault(pid, 0)
            if mov.get('tipo_movimiento') == 'salida':
                saldo_por_producto[pid] += int(mov.get('total') or 0)
            elif mov.get('tipo_movimiento') == 'entrada':
                saldo_por_producto[pid] -= int(mov.get('total') or 0)

        with transaction.atomic():
            for producto_id, saldo_pendiente in saldo_por_producto.items():
                if saldo_pendiente <= 0:
                    continue

                producto = Producto.objects.filter(id=producto_id).first()
                if not producto:
                    continue

                producto.stock += int(saldo_pendiente)
                producto.save(update_fields=['stock'])

                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento='entrada',
                    cantidad=int(saldo_pendiente),
                    descripcion=f"reverso final {tag} por eliminación factura {instance.numero_factura or instance.id}",
                    usuario=self.request.user,
                )

            instance.delete()
    
    def get_queryset(self):
        """Filtrar por rango de fechas si se proporciona"""
        queryset = super().get_queryset()
        
        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        
        if fecha_inicio:
            queryset = queryset.filter(fecha_hora__date__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha_hora__date__lte=fecha_fin)
        
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
            'tiene_adicionales': request.data.get('tiene_adicionales', servicio_realizado.tiene_adicionales),
            'adicionales_servicio_ids': request.data.get('adicionales_servicio_ids', []),
            'adicionales_servicio_items': request.data.get('adicionales_servicio_items', []),
            'adicional_shampoo': request.data.get('adicional_shampoo', servicio_realizado.adicional_shampoo),
            'adicional_guantes': request.data.get('adicional_guantes', servicio_realizado.adicional_guantes),
            'adicional_otro_producto': request.data.get('adicional_otro_producto', servicio_realizado.adicional_otro_producto_id),
            'adicional_otro_estilista': request.data.get('adicional_otro_estilista', servicio_realizado.adicional_otro_estilista_id),
            'adicional_otro_cantidad': request.data.get('adicional_otro_cantidad', servicio_realizado.adicional_otro_cantidad),
            'adicional_otro_descuento_empleado': request.data.get('adicional_otro_descuento_empleado', False),
            'adicional_otro_precio_unitario': request.data.get('adicional_otro_precio_unitario'),
            'tipo_reparto_establecimiento': request.data.get('tipo_reparto_establecimiento'),
            'valor_reparto_establecimiento': request.data.get('valor_reparto_establecimiento'),
            'notas': request.data.get('notas', servicio_realizado.notas),
            'usuario': request.user.id,
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
    
    queryset = VentaProducto.objects.select_related('producto', 'usuario', 'estilista', 'deuda_consumo').all()
    serializer_class = VentaProductoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['producto', 'usuario', 'tipo_operacion', 'deuda_consumo']
    search_fields = ['producto__nombre', 'producto__codigo_barras', 'cliente_nombre', 'numero_factura']
    ordering_fields = ['fecha_hora', 'total']
    ordering = ['-fecha_hora']

    def create(self, request, *args, **kwargs):
        # Cualquier usuario autenticado puede registrar ventas de productos en caja
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
            queryset = queryset.filter(fecha_hora__date__gte=fecha_inicio)
        if fecha_fin:
            queryset = queryset.filter(fecha_hora__date__lte=fecha_fin)
        
        return queryset
    
    def perform_create(self, serializer):
        """Asignar usuario actual a la venta"""
        serializer.save(usuario=self.request.user)

    @action(detail=False, methods=['post'], url_path='transaccion')
    def transaccion(self, request):
        """Registra una transacción de productos con una única factura."""
        items = request.data.get('items') or []
        if not isinstance(items, list) or len(items) == 0:
            return Response({'error': 'Debes enviar al menos un producto en items.'}, status=status.HTTP_400_BAD_REQUEST)

        cliente_nombre = request.data.get('cliente_nombre')
        estilista = request.data.get('estilista')
        medio_pago = request.data.get('medio_pago') or 'efectivo'
        tipo_operacion = (request.data.get('tipo_operacion') or 'venta').strip().lower()

        if tipo_operacion not in {'venta', 'consumo_empleado'}:
            return Response({'error': 'tipo_operacion inválido. Usa venta o consumo_empleado.'}, status=status.HTTP_400_BAD_REQUEST)

        if tipo_operacion == 'consumo_empleado' and not estilista:
            return Response({'error': 'Para consumo de empleado debes seleccionar un empleado.'}, status=status.HTTP_400_BAD_REQUEST)

        ahora = timezone.localtime()
        prefijo_tipo = 'FC' if tipo_operacion == 'consumo_empleado' else 'FP'
        prefijo = f"{prefijo_tipo}-{ahora.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        ventas_creadas = []
        deuda_obj = None

        try:
            with transaction.atomic():
                for item in items:
                    payload = {
                        'producto': item.get('producto'),
                        'cantidad': item.get('cantidad'),
                        'precio_unitario': item.get('precio_unitario'),
                        'cliente_nombre': cliente_nombre,
                        'estilista': estilista,
                        'medio_pago': medio_pago,
                        'tipo_operacion': tipo_operacion,
                    }
                    serializer = self.get_serializer(data=payload)
                    serializer.is_valid(raise_exception=True)
                    venta = serializer.save(usuario=request.user)
                    ventas_creadas.append(venta)

                total_transaccion = sum((Decimal(v.total or 0) for v in ventas_creadas), Decimal(0))

                if tipo_operacion == 'consumo_empleado':
                    deuda_obj = DeudaConsumoEmpleado.objects.create(
                        estilista_id=int(estilista),
                        numero_factura=prefijo,
                        total_cargo=total_transaccion,
                        total_abonado=Decimal(0),
                        saldo_pendiente=total_transaccion,
                        estado='pendiente',
                        fecha_hora=ahora,
                        usuario=request.user,
                        notas='Generada automaticamente desde consumo de empleado',
                    )

                if tipo_operacion == 'consumo_empleado':
                    cliente_txt = ventas_creadas[0].estilista.nombre if ventas_creadas and ventas_creadas[0].estilista else 'Empleado no registrado'
                else:
                    cliente_txt = cliente_nombre or 'Cliente no registrado'
                lineas = []
                for v in ventas_creadas:
                    lineas.append(
                        f"- {v.producto.nombre} x{v.cantidad} @ ${float(v.precio_unitario):.2f} = ${float(v.total):.2f}"
                    )

                texto_cuenta = ''
                if deuda_obj:
                    texto_cuenta = (
                        f"\nCuenta por cobrar: {deuda_obj.numero_factura}\n"
                        f"Saldo pendiente: ${float(deuda_obj.saldo_pendiente):.2f}"
                    )

                linea_medio_pago = '' if tipo_operacion == 'consumo_empleado' else f"Medio de pago: {ventas_creadas[0].get_medio_pago_display()}\\n"

                factura_texto = (
                    f"Factura: {prefijo}\n"
                    f"Tipo: {'Consumo Empleado' if tipo_operacion == 'consumo_empleado' else 'Producto'}\n"
                    f"Fecha: {ahora.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Cliente: {cliente_txt}\n"
                    f"{linea_medio_pago}"
                    f"Items:\n" + "\n".join(lineas) + "\n"
                    f"Total transacción: ${float(total_transaccion):.2f}"
                    f"{texto_cuenta}"
                )

                for v in ventas_creadas:
                    v.numero_factura = prefijo
                    v.factura_texto = factura_texto
                    v.deuda_consumo = deuda_obj
                    v.save(update_fields=['numero_factura', 'factura_texto', 'deuda_consumo'])

        except serializers.ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        output_serializer = self.get_serializer(ventas_creadas, many=True)
        return Response(
            {
                'numero_factura': prefijo,
                'tipo_operacion': tipo_operacion,
                'total_transaccion': float(total_transaccion),
                'cantidad_items': len(ventas_creadas),
                'factura_texto': factura_texto,
                'deuda': {
                    'id': deuda_obj.id,
                    'estado': deuda_obj.estado,
                    'saldo_pendiente': float(deuda_obj.saldo_pendiente),
                } if deuda_obj else None,
                'items': output_serializer.data,
                'venta_principal': output_serializer.data[0] if output_serializer.data else None,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'], url_path='cancelar-factura')
    def cancelar_factura(self, request):
        """Cancela una factura completa de productos y restablece inventario."""
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')

        numero_factura = (request.data.get('numero_factura') or '').strip()
        if not numero_factura:
            return Response({'error': 'Debes enviar numero_factura.'}, status=status.HTTP_400_BAD_REQUEST)

        ventas = list(self.get_queryset().filter(numero_factura=numero_factura).order_by('id'))
        if not ventas:
            return Response({'error': f'No se encontraron ventas para la factura {numero_factura}.'}, status=status.HTTP_404_NOT_FOUND)

        total_items = len(ventas)
        total_unidades = sum(int(v.cantidad or 0) for v in ventas)
        tipo_operacion = ventas[0].tipo_operacion if ventas else 'venta'
        deuda_obj = ventas[0].deuda_consumo if ventas else None

        with transaction.atomic():
            for venta in ventas:
                self.perform_destroy(venta)

        return Response(
            {
                'ok': True,
                'numero_factura': numero_factura,
                'items_eliminados': total_items,
                'unidades_restauradas': total_unidades,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='editar-factura')
    def editar_factura(self, request):
        """Edita una factura completa (items/precios/productos) preservando el número de factura."""
        _validar_edicion_admin_gerente(request.user, 'facturas de venta')

        numero_factura = (request.data.get('numero_factura') or '').strip()
        items = request.data.get('items') or []
        if not numero_factura:
            return Response({'error': 'Debes enviar numero_factura.'}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(items, list) or len(items) == 0:
            return Response({'error': 'Debes enviar al menos un item.'}, status=status.HTTP_400_BAD_REQUEST)

        ventas_actuales = list(self.get_queryset().filter(numero_factura=numero_factura).order_by('id'))
        if not ventas_actuales:
            return Response({'error': f'No se encontraron ventas para la factura {numero_factura}.'}, status=status.HTTP_404_NOT_FOUND)

        tipo_operacion = ventas_actuales[0].tipo_operacion or 'venta'
        deuda_obj = ventas_actuales[0].deuda_consumo
        cliente_nombre = request.data.get('cliente_nombre')
        estilista_id = request.data.get('estilista')
        fecha_hora_raw = request.data.get('fecha_hora')
        medio_pago = (request.data.get('medio_pago') or ventas_actuales[0].medio_pago or 'efectivo').strip().lower()

        try:
            fecha_hora_editada = _normalizar_fecha_hora_request(fecha_hora_raw)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if medio_pago not in {'nequi', 'daviplata', 'efectivo', 'otros'}:
            return Response({'error': 'Medio de pago inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        if tipo_operacion == 'consumo_empleado' and not estilista_id:
            estilista_id = ventas_actuales[0].estilista_id

        for it in items:
            try:
                if int(it.get('cantidad') or 0) <= 0:
                    return Response({'error': 'Cada item debe tener cantidad mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)
                if Decimal(str(it.get('precio_unitario') or 0)) <= 0:
                    return Response({'error': 'Cada item debe tener precio_unitario mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({'error': 'Formato inválido en items.'}, status=status.HTTP_400_BAD_REQUEST)

        nuevas_ventas = []
        total_transaccion = Decimal(0)
        fecha_referencia = fecha_hora_editada or ventas_actuales[0].fecha_hora or timezone.now()

        with transaction.atomic():
            # Revertir inventario de items actuales
            for venta in ventas_actuales:
                producto = venta.producto
                producto.stock += int(venta.cantidad or 0)
                producto.save(update_fields=['stock'])
                MovimientoInventario.objects.create(
                    producto=producto,
                    tipo_movimiento='entrada',
                    cantidad=int(venta.cantidad or 0),
                    descripcion=f'Reverso por edición factura {numero_factura}',
                    usuario=request.user,
                )

            VentaProducto.objects.filter(id__in=[v.id for v in ventas_actuales]).delete()

            # Validar stock de nuevos items
            for it in items:
                prod = Producto.objects.filter(id=int(it.get('producto'))).first()
                if not prod:
                    return Response({'error': f"Producto no encontrado: {it.get('producto')}"}, status=status.HTTP_400_BAD_REQUEST)
                qty = int(it.get('cantidad'))
                if prod.stock < qty:
                    return Response({'error': f'Stock insuficiente para {prod.nombre}. Disponible: {prod.stock}'}, status=status.HTTP_400_BAD_REQUEST)

            # Crear nuevos items de factura
            for it in items:
                prod = Producto.objects.get(id=int(it.get('producto')))
                qty = int(it.get('cantidad'))
                precio = Decimal(str(it.get('precio_unitario')))
                total_item = (precio * qty)

                nueva = VentaProducto.objects.create(
                    producto=prod,
                    cantidad=qty,
                    precio_unitario=precio,
                    total=total_item,
                    fecha_hora=fecha_referencia,
                    cliente_nombre=cliente_nombre,
                    medio_pago=medio_pago,
                    tipo_operacion=tipo_operacion,
                    estilista_id=int(estilista_id) if estilista_id else None,
                    numero_factura=numero_factura,
                    usuario=request.user,
                    deuda_consumo=deuda_obj,
                )
                nuevas_ventas.append(nueva)
                total_transaccion += total_item

                prod.stock -= qty
                prod.save(update_fields=['stock'])
                MovimientoInventario.objects.create(
                    producto=prod,
                    tipo_movimiento='salida',
                    cantidad=qty,
                    descripcion=f'Edición factura {numero_factura}',
                    usuario=request.user,
                )

            # Regenerar texto de factura homogéneo para todos los items
            fecha_referencia_local = timezone.localtime(fecha_referencia)
            if tipo_operacion == 'consumo_empleado':
                empleado_nombre = nuevas_ventas[0].estilista.nombre if nuevas_ventas and nuevas_ventas[0].estilista else 'Empleado no registrado'
                cliente_txt = empleado_nombre
                linea_medio_pago = ''
            else:
                cliente_txt = cliente_nombre or 'Cliente no registrado'
                linea_medio_pago = f"Medio de pago: {nuevas_ventas[0].get_medio_pago_display()}\\n"

            lineas = [
                f"- {v.producto.nombre} x{v.cantidad} @ ${float(v.precio_unitario):.2f} = ${float(v.total):.2f}"
                for v in nuevas_ventas
            ]
            texto_cuenta = ''
            if tipo_operacion == 'consumo_empleado' and deuda_obj:
                texto_cuenta = f"\nCuenta por cobrar: {numero_factura}"

            factura_texto = (
                f"Factura: {numero_factura}\n"
                f"Tipo: {'Consumo Empleado' if tipo_operacion == 'consumo_empleado' else 'Producto'}\n"
                f"Fecha: {fecha_referencia_local.strftime('%Y-%m-%d %H:%M')}\n"
                f"Cliente: {cliente_txt}\n"
                f"{linea_medio_pago}"
                f"Items:\n" + "\n".join(lineas) + "\n"
                f"Total transacción: ${float(total_transaccion):.2f}"
                f"{texto_cuenta}"
            )

            for v in nuevas_ventas:
                v.factura_texto = factura_texto
                v.save(update_fields=['factura_texto'])

            if tipo_operacion == 'consumo_empleado' and deuda_obj:
                deuda_obj.total_cargo = total_transaccion
                deuda_obj.fecha_hora = fecha_referencia
                _recalcular_estado_deuda(deuda_obj)
                deuda_obj.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado', 'fecha_hora'])

        output_serializer = self.get_serializer(nuevas_ventas, many=True)
        return Response(
            {
                'ok': True,
                'numero_factura': numero_factura,
                'tipo_operacion': tipo_operacion,
                'total_transaccion': float(total_transaccion),
                'items': output_serializer.data,
            },
            status=status.HTTP_200_OK,
        )

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
        deuda = instance.deuda_consumo
        instance.delete()

        if deuda:
            _sincronizar_deuda_desde_items(deuda)

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
    """
    Función interna que calcula todos los datos de BI.
    
    Query params opcionales:
    - periodo: 'hoy', 'semana', 'mes', 'personalizado'
    - fecha_inicio: YYYY-MM-DD
    - fecha_fin: YYYY-MM-DD
    - medio_pago: 'efectivo', 'transferencia', 'tarjeta', 'todos'
    - debug: 1 para devolver desglose detallado por estilista/día
    """
    """Función helper que calcula todos los datos de BI y retorna un diccionario"""
    fecha_inicio, fecha_fin = _resolver_rango_fechas(request)
    medio_pago = (request.query_params.get('medio_pago') or '').strip().lower()
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    except Exception:
        hoy = timezone.localdate()
        fecha_inicio_dt = hoy
        fecha_fin_dt = hoy
        fecha_inicio = hoy.strftime('%Y-%m-%d')
        fecha_fin = hoy.strftime('%Y-%m-%d')

    ventas_qs = VentaProducto.objects.select_related('producto', 'estilista').filter(
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    ventas_pagadas_qs = ventas_qs.exclude(tipo_operacion='consumo_empleado')
    servicios_qs = ServicioRealizado.objects.select_related(
        'estilista', 'adicional_otro_producto', 'adicional_otro_estilista'
    ).filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )

    if medio_pago and medio_pago != 'todos':
        ventas_qs = ventas_qs.filter(medio_pago=medio_pago)
        ventas_pagadas_qs = ventas_pagadas_qs.filter(medio_pago=medio_pago)
        servicios_qs = servicios_qs.filter(medio_pago=medio_pago)

    adicionales_asignados_qs = ServicioRealizadoAdicional.objects.select_related('servicio_realizado').filter(
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    )
    if medio_pago and medio_pago != 'todos':
        adicionales_asignados_qs = adicionales_asignados_qs.filter(servicio_realizado__medio_pago=medio_pago)

    abonos_consumo_qs = AbonoDeudaEmpleado.objects.select_related('deuda', 'deuda__estilista')
    if medio_pago and medio_pago != 'todos':
        abonos_consumo_qs = abonos_consumo_qs.filter(medio_pago=medio_pago)

    abonos_consumo_lista = []
    for ab in abonos_consumo_qs:
        try:
            fecha_operativa_ab = _fecha_operativa_desde_dt(ab.fecha_hora)
            if not fecha_operativa_ab:
                continue
            if fecha_inicio_dt <= fecha_operativa_ab <= fecha_fin_dt:
                abonos_consumo_lista.append(ab)
        except Exception:
            # Evita tumbar cierre por un registro inconsistente aislado.
            continue

    ingresos_abonos_consumo = Decimal(abonos_consumo_qs.aggregate(total=Sum('monto'))['total'] or 0)
    deuda_consumo_empleado_total = Decimal(
        DeudaConsumoEmpleado.objects.filter(saldo_pendiente__gt=0).aggregate(total=Sum('saldo_pendiente'))['total'] or 0
    )

    ingresos_productos_caja = Decimal(ventas_pagadas_qs.aggregate(total=Sum('total'))['total'] or 0)
    ingresos_productos = ingresos_productos_caja + ingresos_abonos_consumo
    ingresos_productos_en_servicios = Decimal(0)
    costo_productos = Decimal(0)
    costo_productos_en_servicios = Decimal(0)
    comision_producto_estilistas = Decimal(0)
    comision_producto_estilistas_en_servicios = Decimal(0)

    detalle_ganancia_productos_mapa = {}

    top_productos_mapa = {}
    for venta in ventas_pagadas_qs:
        costo_unitario = Decimal(venta.producto.precio_compra or 0)
        costo_productos += costo_unitario * Decimal(venta.cantidad)

        key_producto = int(venta.producto_id)
        if key_producto not in detalle_ganancia_productos_mapa:
            detalle_ganancia_productos_mapa[key_producto] = {
                'producto_id': key_producto,
                'producto_nombre': venta.producto.nombre,
                'producto_marca': venta.producto.marca,
                'cantidad': 0,
                'valor_vendido': Decimal(0),
                'valor_costo': Decimal(0),
                'valor_vendido_caja': Decimal(0),
                'valor_vendido_servicios': Decimal(0),
            }
        detalle_ganancia_productos_mapa[key_producto]['cantidad'] += int(venta.cantidad or 0)
        detalle_ganancia_productos_mapa[key_producto]['valor_vendido'] += Decimal(venta.total or 0)
        detalle_ganancia_productos_mapa[key_producto]['valor_costo'] += costo_unitario * Decimal(venta.cantidad or 0)
        detalle_ganancia_productos_mapa[key_producto]['valor_vendido_caja'] += Decimal(venta.total or 0)

        if venta.estilista and venta.tipo_operacion != 'consumo_empleado':
            # La comisión de venta se toma del producto vendido, no del estilista.
            pct = Decimal(venta.producto.comision_estilista or 0)
            comision_producto_estilistas += (Decimal(venta.total) * pct) / Decimal(100)

        key = venta.producto_id
        if key not in top_productos_mapa:
            top_productos_mapa[key] = {
                'producto_id': venta.producto_id,
                'producto_nombre': venta.producto.nombre,
                'producto_marca': venta.producto.marca,
                'cantidad': 0,
                'total': Decimal(0),
            }
        top_productos_mapa[key]['cantidad'] += int(venta.cantidad)
        top_productos_mapa[key]['total'] += Decimal(venta.total)

    utilidad_productos = ingresos_productos_caja - costo_productos

    comision_producto_servicios_por_estilista = {}
    comision_producto_servicios_por_estilista_dia = {}

    # Productos vendidos como adicional dentro de servicios finalizados.
    # Se valorizan para ingresos/costos de inventario y sí generan comisión al estilista seleccionado.
    for srv in servicios_qs:
        if srv.adicional_otro_producto_id:
            cantidad_ad = Decimal(srv.adicional_otro_cantidad or 1)
            precio_venta_ad = Decimal(srv.adicional_otro_producto.precio_venta or 0)
            precio_compra_ad = Decimal(srv.adicional_otro_producto.precio_compra or 0)
            ingresos_productos_en_servicios += precio_venta_ad * cantidad_ad
            costo_productos_en_servicios += precio_compra_ad * cantidad_ad

            key_producto_ad = int(srv.adicional_otro_producto_id)
            if key_producto_ad not in detalle_ganancia_productos_mapa:
                detalle_ganancia_productos_mapa[key_producto_ad] = {
                    'producto_id': key_producto_ad,
                    'producto_nombre': srv.adicional_otro_producto.nombre,
                    'producto_marca': srv.adicional_otro_producto.marca,
                    'cantidad': 0,
                    'valor_vendido': Decimal(0),
                    'valor_costo': Decimal(0),
                    'valor_vendido_caja': Decimal(0),
                    'valor_vendido_servicios': Decimal(0),
                }
            detalle_ganancia_productos_mapa[key_producto_ad]['cantidad'] += int(cantidad_ad)
            detalle_ganancia_productos_mapa[key_producto_ad]['valor_vendido'] += precio_venta_ad * cantidad_ad
            detalle_ganancia_productos_mapa[key_producto_ad]['valor_costo'] += precio_compra_ad * cantidad_ad
            detalle_ganancia_productos_mapa[key_producto_ad]['valor_vendido_servicios'] += precio_venta_ad * cantidad_ad

            if srv.adicional_otro_estilista_id:
                pct_srv = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
                if pct_srv < 0:
                    pct_srv = Decimal(0)
                if pct_srv > 100:
                    pct_srv = Decimal(100)

                valor_venta_srv = precio_venta_ad * cantidad_ad
                valor_comision_srv = (valor_venta_srv * pct_srv) / Decimal(100)
                comision_producto_estilistas_en_servicios += valor_comision_srv
                comision_producto_servicios_por_estilista[srv.adicional_otro_estilista_id] = (
                    comision_producto_servicios_por_estilista.get(srv.adicional_otro_estilista_id, Decimal(0))
                    + valor_comision_srv
                )

                fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
                key_dia = (srv.adicional_otro_estilista_id, fecha_srv)
                comision_producto_servicios_por_estilista_dia[key_dia] = (
                    comision_producto_servicios_por_estilista_dia.get(key_dia, Decimal(0))
                    + valor_comision_srv
                )

    comision_producto_estilistas_total = comision_producto_estilistas + comision_producto_estilistas_en_servicios

    ingresos_productos_totales = ingresos_productos + ingresos_productos_en_servicios
    costo_productos_totales = costo_productos + costo_productos_en_servicios
    utilidad_productos_total = ingresos_productos_totales - costo_productos_totales

    detalle_ganancia_productos = []
    for item in detalle_ganancia_productos_mapa.values():
        ganancia_item = item['valor_vendido'] - item['valor_costo']
        detalle_ganancia_productos.append(
            {
                'producto_id': item['producto_id'],
                'producto_nombre': item['producto_nombre'],
                'producto_marca': item['producto_marca'],
                'cantidad': int(item['cantidad']),
                'valor_vendido': float(item['valor_vendido']),
                'valor_costo': float(item['valor_costo']),
                'valor_ganancia': float(ganancia_item),
                'valor_vendido_caja': float(item['valor_vendido_caja']),
                'valor_vendido_servicios': float(item['valor_vendido_servicios']),
            }
        )
    detalle_ganancia_productos = sorted(detalle_ganancia_productos, key=lambda x: x['valor_ganancia'], reverse=True)

    ganancia_establecimiento_productos = utilidad_productos_total - comision_producto_estilistas_total
    ingresos_servicios = Decimal(servicios_qs.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
    ingresos_servicios_adicionales_facturados = Decimal(servicios_qs.aggregate(total=Sum('valor_adicionales'))['total'] or 0)

    adicionales_asignados_lista = list(adicionales_asignados_qs)
    total_adicionales_asignados_bruto_global = Decimal(0)
    total_adicionales_establecimiento_porcentaje_global = Decimal(0)
    total_adicionales_liquidos_global = Decimal(0)
    for ad in adicionales_asignados_lista:
        valor = Decimal(ad.valor_cobrado or 0)
        pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct < 0:
            pct = Decimal(0)
        if pct > 100:
            pct = Decimal(100)
        valor_est = (valor * pct) / Decimal(100)
        valor_emp = valor - valor_est
        total_adicionales_asignados_bruto_global += valor
        total_adicionales_establecimiento_porcentaje_global += valor_est
        total_adicionales_liquidos_global += valor_emp

    adicionales_no_asignados_global = ingresos_servicios_adicionales_facturados - total_adicionales_asignados_bruto_global
    if adicionales_no_asignados_global < 0:
        adicionales_no_asignados_global = Decimal(0)
    total_servicios_adicionales_establecimiento = total_adicionales_establecimiento_porcentaje_global + adicionales_no_asignados_global

    estilistas_data = []
    total_descuentos_espacio = Decimal(0)
    total_pago_neto_estilistas = Decimal(0)
    total_pago_neto_estilistas_periodo = Decimal(0)
    total_pago_estilistas_positivo = Decimal(0)
    total_deuda_estilistas = Decimal(0)

    try:
        estados_pago_diarios = list(
            EstadoPagoEstilistaDia.objects.filter(fecha__gte=fecha_inicio_dt, fecha__lte=fecha_fin_dt)
        )
        estados_pago_obj_map = {
            (ep.estilista_id, ep.fecha): ep
            for ep in estados_pago_diarios
        }
        estados_pago_map = {
            key: ep.estado
            for key, ep in estados_pago_obj_map.items()
        }
    except (OperationalError, ProgrammingError):
        # Fallback: si no existe tabla diaria, usar último estado del historial por estilista/fecha.
        estados_pago_obj_map = {}
        estados_pago_map = {}
        try:
            historial_qs = EstadoPagoEstilistaHistorial.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            ).order_by('estilista_id', 'fecha', '-fecha_cambio')
            vistos = set()
            for h in historial_qs:
                key = (h.estilista_id, h.fecha)
                if key in vistos:
                    continue
                estados_pago_map[key] = h.estado_nuevo
                vistos.add(key)
        except Exception:
            estados_pago_map = {}

    usar_fact = _usar_fact_liquidacion_en_reportes()
    facts_map = {}
    if usar_fact:
        try:
            facts_qs = FactLiquidacionEstilistaDia.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
                vigente=True,
            )
            facts_map = {(fact.estilista_id, fact.fecha): fact for fact in facts_qs}
        except Exception:
            facts_map = {}

    for estilista in Estilista.objects.filter(activo=True):
        servicios_est = servicios_qs.filter(estilista=estilista)
        ventas_est = ventas_pagadas_qs.filter(estilista=estilista)

        # Calcular totales de servicios
        total_servicios_precio_cobrado = Decimal(servicios_est.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
        total_servicios_pagables_est = sum((_monto_estilista_resuelto(srv) for srv in servicios_est), Decimal(0))
        adicionales_estilista = [ad for ad in adicionales_asignados_lista if ad.estilista_id == estilista.id]
        total_adicionales_asignados_bruto_est = Decimal(0)
        total_adicionales_asignados_est = Decimal(0)
        total_adicionales_deduccion_est = Decimal(0)
        for ad in adicionales_estilista:
            valor = Decimal(ad.valor_cobrado or 0)
            pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
            if pct < 0:
                pct = Decimal(0)
            if pct > 100:
                pct = Decimal(100)
            valor_est = (valor * pct) / Decimal(100)
            valor_emp = valor - valor_est
            total_adicionales_asignados_bruto_est += valor
            total_adicionales_asignados_est += valor_emp
            total_adicionales_deduccion_est += valor_est
        
        # Base para pagar al estilista = monto del estilista en servicios principales + adicionales asignados.
        ganancia_servicios_est = total_servicios_pagables_est + total_adicionales_asignados_est
        
        # Para liquidación del estilista, facturación atribuida = servicios base + adicionales asignados.
        total_facturado_cliente = total_servicios_precio_cobrado + total_adicionales_asignados_bruto_est
        
        comision_ventas_producto_caja_est = Decimal(0)
        comision_por_dia = {}
        for v in ventas_est:
            if v.tipo_operacion == 'consumo_empleado':
                continue
            pct = Decimal(v.producto.comision_estilista or 0)
            valor_comision = (Decimal(v.total) * pct) / Decimal(100)
            comision_ventas_producto_caja_est += valor_comision
            fecha_v = _fecha_operativa_desde_dt(v.fecha_hora)
            comision_por_dia[fecha_v] = comision_por_dia.get(fecha_v, Decimal(0)) + valor_comision

        comision_ventas_producto_servicios_est = comision_producto_servicios_por_estilista.get(estilista.id, Decimal(0))

        comision_ventas_producto_est = comision_ventas_producto_caja_est + comision_ventas_producto_servicios_est

        subtotal_ingresos_est = ganancia_servicios_est + comision_ventas_producto_est

        servicios_por_dia = {}
        for srv in servicios_est:
            fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
            servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + _monto_estilista_resuelto(srv)

        for ad in adicionales_estilista:
            fecha_ad = _fecha_operativa_desde_dt(ad.servicio_realizado.fecha_hora)
            valor = Decimal(ad.valor_cobrado or 0)
            pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
            if pct < 0:
                pct = Decimal(0)
            if pct > 100:
                pct = Decimal(100)
            valor_emp = valor - ((valor * pct) / Decimal(100))
            servicios_por_dia[fecha_ad] = servicios_por_dia.get(fecha_ad, Decimal(0)) + valor_emp

        for (est_id, fecha_est), valor_comision_srv in comision_producto_servicios_por_estilista_dia.items():
            if int(est_id) != int(estilista.id):
                continue
            comision_por_dia[fecha_est] = comision_por_dia.get(fecha_est, Decimal(0)) + valor_comision_srv

        # Días trabajados: usar la misma fecha operativa que los mapas por día.
        dias_trabajados = set(servicios_por_dia.keys()) | set(comision_por_dia.keys())

        descuento_espacio = Decimal(0)
        pago_neto_periodo = Decimal(0)
        pago_neto_pendiente = Decimal(0)
        pago_neto_cancelado = Decimal(0)
        total_pagado_empleado = Decimal(0)
        total_abono_puesto = Decimal(0)
        dias_cancelados = 0
        dias_con_pago = 0

        for dia in dias_trabajados:
            base_servicio_dia = servicios_por_dia.get(dia, Decimal(0))
            comision_dia = comision_por_dia.get(dia, Decimal(0))
            ganancias_dia = base_servicio_dia + comision_dia
            descuento_dia = _descuento_puesto_dia(estilista, base_servicio_dia)
            estado_dia_obj = estados_pago_obj_map.get((estilista.id, dia))
            fact_dia = facts_map.get((estilista.id, dia)) if usar_fact else None
            pago_empleado_dia = Decimal(0)
            abono_puesto_dia = Decimal(0)
            if fact_dia:
                pago_empleado_dia = Decimal(fact_dia.pago_total_empleado or 0)
                abono_puesto_dia = Decimal(fact_dia.abono_puesto_dia or 0)
                estado_dia = fact_dia.estado_liquidacion
            elif estado_dia_obj:
                pago_empleado_dia = (
                    Decimal(estado_dia_obj.pago_efectivo or 0)
                    + Decimal(estado_dia_obj.pago_nequi or 0)
                    + Decimal(estado_dia_obj.pago_daviplata or 0)
                    + Decimal(estado_dia_obj.pago_otros or 0)
                )
                abono_puesto_dia = Decimal(estado_dia_obj.abono_puesto or 0)
                estado_dia = estado_dia_obj.estado
            else:
                estado_dia = estados_pago_map.get((estilista.id, dia), 'pendiente')

            neto_dia = max(ganancias_dia - descuento_dia, Decimal(0))

            descuento_espacio += descuento_dia
            pago_neto_periodo += neto_dia
            total_pagado_empleado += pago_empleado_dia
            total_abono_puesto += abono_puesto_dia

            if pago_empleado_dia > 0:
                dias_con_pago += 1

            pendiente_empleado_dia = max(neto_dia - pago_empleado_dia, Decimal(0))
            pago_neto_pendiente += pendiente_empleado_dia
            if pendiente_empleado_dia <= 0 and neto_dia > 0:
                pago_neto_cancelado += neto_dia
                dias_cancelados += 1

        total_descuentos_espacio += descuento_espacio
        total_pago_neto_estilistas += pago_neto_pendiente
        total_pago_neto_estilistas_periodo += pago_neto_periodo
        total_pago_estilistas_positivo += total_pagado_empleado

        total_dias = len(dias_trabajados)
        # Deuda acumulada de puesto recalculada secuencialmente por fecha.
        # Esto evita arrastres incorrectos en datos históricos antiguos.
        deuda_puesto_inicial = Decimal(0)
        try:
            ultimo_estado_previo = EstadoPagoEstilistaDia.objects.filter(
                estilista=estilista,
                fecha__lt=fecha_inicio_dt,
            ).order_by('-fecha', '-actualizado_en').first()
            if ultimo_estado_previo:
                deuda_puesto_inicial = max(
                    Decimal(
                        getattr(ultimo_estado_previo, 'saldo_puesto_pendiente', None)
                        or getattr(ultimo_estado_previo, 'pendiente_puesto', 0)
                        or 0
                    ),
                    Decimal(0),
                )
        except (OperationalError, ProgrammingError):
            deuda_puesto_inicial = Decimal(0)
        except Exception:
            deuda_puesto_inicial = Decimal(0)

        deuda_puesto_running = deuda_puesto_inicial
        for dia in sorted(dias_trabajados):
            base_servicio_dia = servicios_por_dia.get(dia, Decimal(0))
            descuento_dia = max(_descuento_puesto_dia(estilista, base_servicio_dia), Decimal(0))
            estado_dia_obj = estados_pago_obj_map.get((estilista.id, dia))
            fact_dia = facts_map.get((estilista.id, dia)) if usar_fact else None
            if fact_dia:
                abono_puesto_dia = Decimal(fact_dia.abono_puesto_dia or 0)
            else:
                abono_puesto_dia = Decimal(estado_dia_obj.abono_puesto or 0) if estado_dia_obj else Decimal(0)
            deuda_puesto_running = max(deuda_puesto_running + descuento_dia - max(abono_puesto_dia, Decimal(0)), Decimal(0))

        deuda_puesto_historial = deuda_puesto_inicial
        deuda_total_acumulada = deuda_puesto_running
        total_deuda_estilistas += max(deuda_total_acumulada, Decimal(0))

        if total_dias == 0:
            estado_pago_rango = 'sin_movimiento'
        elif pago_neto_pendiente > 0 and total_pagado_empleado > 0:
            estado_pago_rango = 'parcial'
        elif pago_neto_pendiente > 0:
            estado_pago_rango = 'pendiente'
        elif deuda_total_acumulada > 0:
            estado_pago_rango = 'debe'
        else:
            estado_pago_rango = 'cancelado'

        estilistas_data.append(
            {
                'estilista_id': estilista.id,
                'estilista_nombre': estilista.nombre,
                'tipo_cobro_espacio': estilista.tipo_cobro_espacio,
                'valor_cobro_espacio': float(estilista.valor_cobro_espacio or 0),
                'base_cobro_espacio': float(ganancia_servicios_est),
                'dias_cobrados_alquiler': int(len(dias_trabajados)) if estilista.tipo_cobro_espacio == 'costo_fijo_neto' else 0,
                'total_dias_trabajados': int(len(dias_trabajados)),
                'facturacion_servicios': float(total_facturado_cliente),
                'valor_total_empleado': float(ganancia_servicios_est),
                'valor_servicios_adicionales': float(total_adicionales_asignados_est),
                'deduccion_servicios_adicionales': float(total_adicionales_deduccion_est),
                'ganancias_servicios': float(ganancia_servicios_est),
                'comision_ventas_producto': float(comision_ventas_producto_est),
                'comision_ventas_producto_caja': float(comision_ventas_producto_caja_est),
                'comision_ventas_producto_servicios': float(comision_ventas_producto_servicios_est),
                'ganancias_totales_brutas': float(subtotal_ingresos_est),
                'total_deducciones': float(descuento_espacio),
                'descuento_espacio': float(descuento_espacio),
                'debe_puesto_periodo': float(descuento_espacio),
                'pagado_empleado_periodo': float(total_pagado_empleado),
                'abono_puesto_periodo': float(total_abono_puesto),
                'pago_neto_estilista': float(pago_neto_pendiente),
                'pago_neto_pendiente': float(pago_neto_pendiente),
                'pago_neto_periodo': float(pago_neto_periodo),
                'pago_neto_cancelado': float(pago_neto_cancelado),
                # Campos consolidados para frontend: misma semántica en todos los módulos.
                'generado_total_empleado': float(pago_neto_periodo),
                'pendiente_pago_empleado': float(pago_neto_pendiente),
                'pagado_total_empleado': float(total_pagado_empleado),
                'deuda_puesto_pendiente': float(deuda_total_acumulada),
                'deuda_puesto_historica': float(deuda_puesto_historial),
                'deuda_total_acumulada': float(deuda_total_acumulada),
                'estado_pago_dia': estado_pago_rango,
                'estado_pago_rango': estado_pago_rango,
                'dias_cancelados_rango': int(dias_cancelados),
                'dias_pendientes_rango': int(max(total_dias - dias_cancelados, 0)),
                'fecha_estado_pago': fecha_fin,
            }
        )

    comision_servicios_establecimiento = total_descuentos_espacio
    ingresos_servicios_total_cliente = ingresos_servicios + ingresos_servicios_adicionales_facturados

    # Servicios adicionales distintos a producto (shampoo/guantes/u otros servicios)
    otros_servicios_no_producto = total_servicios_adicionales_establecimiento - ingresos_productos_en_servicios
    if otros_servicios_no_producto < 0:
        otros_servicios_no_producto = Decimal(0)
    ingresos_servicios_no_producto = ingresos_servicios + otros_servicios_no_producto

    # Ganancia bruta de establecimiento (incluye deuda como cuenta por cobrar del estilista)
    # = ventas productos caja + descuento espacios + servicios adicionales.
    ganancia_establecimiento_bruta = (
        ingresos_productos +
        total_descuentos_espacio +
        total_servicios_adicionales_establecimiento
    )

    # Total cobrado al cliente sin separar reparto empleado/establecimiento.
    venta_neta_total = ingresos_productos + ingresos_servicios_total_cliente

    # Ganancia de establecimiento para cuadre diario de caja:
    # Venta neta total - pago real del día a estilistas (solo saldos positivos).
    ganancia_establecimiento_total = venta_neta_total - total_pago_estilistas_positivo
    # Total ganancias: arriendo de espacios + utilidad neta productos (caja + adicionales)
    # + otros servicios no asociados a productos.
    total_ganancias_negocio = total_descuentos_espacio + utilidad_productos_total + otros_servicios_no_producto

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

    medios = ['efectivo', 'nequi', 'daviplata', 'otros']
    ingresos_por_medio = {m: Decimal(0) for m in medios}
    salidas_por_medio = {m: Decimal(0) for m in medios}

    for v in ventas_pagadas_qs:
        medio_v = (v.medio_pago or 'otros').strip().lower()
        if medio_v not in ingresos_por_medio:
            medio_v = 'otros'
        ingresos_por_medio[medio_v] += Decimal(v.total or 0)

    for ab in abonos_consumo_qs:
        medio_ab = (ab.medio_pago or 'otros').strip().lower()
        if medio_ab not in ingresos_por_medio:
            medio_ab = 'otros'
        ingresos_por_medio[medio_ab] += Decimal(ab.monto or 0)

    for srv in servicios_qs:
        medio_srv = (srv.medio_pago or 'otros').strip().lower()
        if medio_srv not in ingresos_por_medio:
            medio_srv = 'otros'
        ingresos_por_medio[medio_srv] += Decimal(srv.precio_cobrado or 0) + Decimal(srv.valor_adicionales or 0)

    try:
        if usar_fact:
            facts_medios_qs = FactLiquidacionEstilistaDia.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
                vigente=True,
            )
            for fact in facts_medios_qs:
                salidas_por_medio['efectivo'] += Decimal(fact.pago_efectivo or 0)
                salidas_por_medio['nequi'] += Decimal(fact.pago_nequi or 0)
                salidas_por_medio['daviplata'] += Decimal(fact.pago_daviplata or 0)
                salidas_por_medio['otros'] += Decimal(fact.pago_otros or 0)

                medio_abono = (getattr(fact, 'medio_abono_puesto', None) or 'efectivo').strip().lower()
                if medio_abono not in ingresos_por_medio:
                    medio_abono = 'otros'
                ingresos_por_medio[medio_abono] += Decimal(fact.abono_puesto_dia or 0)
        else:
            estados_pago_qs = EstadoPagoEstilistaDia.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            )
            for ep in estados_pago_qs:
                salidas_por_medio['efectivo'] += Decimal(ep.pago_efectivo or 0)
                salidas_por_medio['nequi'] += Decimal(ep.pago_nequi or 0)
                salidas_por_medio['daviplata'] += Decimal(ep.pago_daviplata or 0)
                salidas_por_medio['otros'] += Decimal(ep.pago_otros or 0)

                medio_abono = (getattr(ep, 'medio_abono_puesto', None) or 'efectivo').strip().lower()
                if medio_abono not in ingresos_por_medio:
                    medio_abono = 'otros'
                ingresos_por_medio[medio_abono] += Decimal(ep.abono_puesto or 0)
    except (OperationalError, ProgrammingError):
        salidas_por_medio = {m: Decimal(0) for m in medios}

    cierre_medios_detalle = []
    for m in medios:
        ingreso_m = ingresos_por_medio.get(m, Decimal(0))
        salida_m = salidas_por_medio.get(m, Decimal(0))
        cierre_medios_detalle.append(
            {
                'medio_pago': m,
                'ingresos': float(ingreso_m),
                'salidas': float(salida_m),
                'saldo': float(ingreso_m - salida_m),
            }
        )

    tot_ingresos_medios = sum(ingresos_por_medio.values(), Decimal(0))
    tot_salidas_medios = sum(salidas_por_medio.values(), Decimal(0))

    adicionales_por_servicio = {}
    for ad in adicionales_asignados_lista:
        sid = int(ad.servicio_realizado_id)
        valor = Decimal(ad.valor_cobrado or 0)
        pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct < 0:
            pct = Decimal(0)
        if pct > 100:
            pct = Decimal(100)
        valor_est = (valor * pct) / Decimal(100)
        valor_emp = valor - valor_est

        if sid not in adicionales_por_servicio:
            adicionales_por_servicio[sid] = {
                'bruto': Decimal(0),
                'empleado': Decimal(0),
                'establecimiento': Decimal(0),
                'cantidad': 0,
            }
        adicionales_por_servicio[sid]['bruto'] += valor
        adicionales_por_servicio[sid]['empleado'] += valor_emp
        adicionales_por_servicio[sid]['establecimiento'] += valor_est
        adicionales_por_servicio[sid]['cantidad'] += 1

    producto_adicional_por_servicio = {}
    for srv in servicios_qs:
        if not srv.adicional_otro_producto_id:
            continue

        qty = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        valor_bruto = precio_venta * qty
        comision_emp = Decimal(0)
        if srv.adicional_otro_estilista_id:
            pct = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
            if pct < 0:
                pct = Decimal(0)
            if pct > 100:
                pct = Decimal(100)
            comision_emp = (valor_bruto * pct) / Decimal(100)

        producto_adicional_por_servicio[int(srv.id)] = {
            'bruto': valor_bruto,
            'empleado': comision_emp,
            'establecimiento': valor_bruto - comision_emp,
        }

    detalle_servicios_reparto = []
    for srv in servicios_qs.order_by('-fecha_hora'):
        sid = int(srv.id)
        ad_info = adicionales_por_servicio.get(
            sid,
            {
                'bruto': Decimal(0),
                'empleado': Decimal(0),
                'establecimiento': Decimal(0),
                'cantidad': 0,
            },
        )
        prod_info = producto_adicional_por_servicio.get(
            sid,
            {
                'bruto': Decimal(0),
                'empleado': Decimal(0),
                'establecimiento': Decimal(0),
            },
        )

        base_emp = _monto_estilista_resuelto(srv)
        base_est = _monto_establecimiento_resuelto(srv)
        total_cliente = Decimal(srv.precio_cobrado or 0) + Decimal(srv.valor_adicionales or 0)
        total_empleado = base_emp + ad_info['empleado'] + prod_info['empleado']
        total_establecimiento = base_est + ad_info['establecimiento'] + prod_info['establecimiento']

        detalle_servicios_reparto.append(
            {
                'servicio_realizado_id': sid,
                'numero_factura': srv.numero_factura,
                'fecha_hora': timezone.localtime(srv.fecha_hora).strftime('%Y-%m-%d %H:%M') if srv.fecha_hora else None,
                'medio_pago': srv.medio_pago or 'otros',
                'servicio_nombre': srv.servicio.nombre if srv.servicio_id else '',
                'cliente_nombre': srv.cliente.nombre if srv.cliente_id else '',
                'estilista_nombre': srv.estilista.nombre if srv.estilista_id else '',
                'total_cliente': float(total_cliente),
                'base_empleado': float(base_emp),
                'base_establecimiento': float(base_est),
                'adicionales_cantidad': int(ad_info['cantidad']),
                'adicionales_bruto': float(ad_info['bruto']),
                'adicionales_empleado': float(ad_info['empleado']),
                'adicionales_establecimiento': float(ad_info['establecimiento']),
                'producto_adicional_bruto': float(prod_info['bruto']),
                'producto_adicional_empleado': float(prod_info['empleado']),
                'producto_adicional_establecimiento': float(prod_info['establecimiento']),
                'total_empleado': float(total_empleado),
                'total_establecimiento': float(total_establecimiento),
            }
        )

    # Resumen diario de productos (venta directa + producto adicional en servicio)
    # y recaudo por abonos de consumo de empleado.
    productos_diario_map = {}

    for venta in ventas_pagadas_qs:
        fecha_venta = _fecha_operativa_desde_dt(venta.fecha_hora)
        key = fecha_venta.strftime('%Y-%m-%d')
        if key not in productos_diario_map:
            productos_diario_map[key] = {
                'fecha': key,
                'monto_vendido_producto': Decimal(0),
                'valor_reserva': Decimal(0),
                'abonos_consumo_empleado': Decimal(0),
            }

        productos_diario_map[key]['monto_vendido_producto'] += Decimal(venta.total or 0)
        productos_diario_map[key]['valor_reserva'] += Decimal(venta.producto.precio_compra or 0) * Decimal(venta.cantidad or 0)

    for srv in servicios_qs:
        if not srv.adicional_otro_producto_id:
            continue

        fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
        key = fecha_srv.strftime('%Y-%m-%d')
        if key not in productos_diario_map:
            productos_diario_map[key] = {
                'fecha': key,
                'monto_vendido_producto': Decimal(0),
                'valor_reserva': Decimal(0),
                'abonos_consumo_empleado': Decimal(0),
            }

        cantidad_ad = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta_ad = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        precio_compra_ad = Decimal(srv.adicional_otro_producto.precio_compra or 0)

        productos_diario_map[key]['monto_vendido_producto'] += precio_venta_ad * cantidad_ad
        productos_diario_map[key]['valor_reserva'] += precio_compra_ad * cantidad_ad

    # Consumo de empleado: se reconoce por abonos (no por el valor del cargo).
    for ab in abonos_consumo_qs:
        fecha_ab = _fecha_operativa_desde_dt(ab.fecha_hora)
        key = fecha_ab.strftime('%Y-%m-%d')
        if key not in productos_diario_map:
            productos_diario_map[key] = {
                'fecha': key,
                'monto_vendido_producto': Decimal(0),
                'valor_reserva': Decimal(0),
                'abonos_consumo_empleado': Decimal(0),
            }
        productos_diario_map[key]['abonos_consumo_empleado'] += Decimal(ab.monto or 0)

    productos_diario = []
    for item in sorted(productos_diario_map.values(), key=lambda x: x['fecha']):
        ingreso_reconocido = item['monto_vendido_producto'] + item['abonos_consumo_empleado']
        valor_ganancia = ingreso_reconocido - item['valor_reserva']
        productos_diario.append(
            {
                'fecha': item['fecha'],
                'monto_vendido_producto': float(item['monto_vendido_producto']),
                'abonos_consumo_empleado': float(item['abonos_consumo_empleado']),
                'ingreso_total_reconocido': float(ingreso_reconocido),
                'valor_reserva': float(item['valor_reserva']),
                'valor_ganancia': float(valor_ganancia),
            }
        )

    # Fallback: si no hay detalle por día pero sí hay totales en el rango,
    # devolver una fila resumen para evitar tablas en cero.
    if not productos_diario and (
        ingresos_productos_totales > 0
        or costo_productos_totales > 0
        or ingresos_abonos_consumo > 0
    ):
        productos_diario.append(
            {
                'fecha': f'{fecha_inicio} a {fecha_fin}',
                'monto_vendido_producto': float(ingresos_productos_totales),
                'abonos_consumo_empleado': float(ingresos_abonos_consumo),
                'ingreso_total_reconocido': float(ingresos_productos_totales + ingresos_abonos_consumo),
                'valor_reserva': float(costo_productos_totales),
                'valor_ganancia': float((ingresos_productos_totales + ingresos_abonos_consumo) - costo_productos_totales),
            }
        )

    # Otros servicios por fecha y tipo (valor original vs valor recibido por el establecimiento).
    otros_servicios_map = {}
    for ad in adicionales_asignados_lista:
        fecha_ad = _fecha_operativa_desde_dt(ad.servicio_realizado.fecha_hora).strftime('%Y-%m-%d')
        tipo_servicio = ad.servicio.nombre if ad.servicio_id else 'Servicio adicional'
        key = (fecha_ad, tipo_servicio)

        if key not in otros_servicios_map:
            otros_servicios_map[key] = {
                'fecha': fecha_ad,
                'tipo_servicio': tipo_servicio,
                'valor_original': Decimal(0),
                'valor_recibido': Decimal(0),
            }

        valor = Decimal(ad.valor_cobrado or 0)
        pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct < 0:
            pct = Decimal(0)
        if pct > 100:
            pct = Decimal(100)

        valor_recibido = (valor * pct) / Decimal(100)
        otros_servicios_map[key]['valor_original'] += valor
        otros_servicios_map[key]['valor_recibido'] += valor_recibido

    # Capturar adicionales no asignados por servicio (si existen en valor_adicionales)
    # restando lo ya asignado y el valor de producto adicional del servicio.
    asignado_por_servicio = {}
    for ad in adicionales_asignados_lista:
        sid = int(ad.servicio_realizado_id)
        asignado_por_servicio[sid] = asignado_por_servicio.get(sid, Decimal(0)) + Decimal(ad.valor_cobrado or 0)

    for srv in servicios_qs:
        sid = int(srv.id)
        valor_adicionales_srv = Decimal(srv.valor_adicionales or 0)
        valor_producto_srv = Decimal(0)
        if srv.adicional_otro_producto_id:
            valor_producto_srv = Decimal(srv.adicional_otro_producto.precio_venta or 0) * Decimal(srv.adicional_otro_cantidad or 1)

        asignado_srv = asignado_por_servicio.get(sid, Decimal(0))
        restante_srv = valor_adicionales_srv - asignado_srv - valor_producto_srv
        if restante_srv <= 0:
            continue

        fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora).strftime('%Y-%m-%d')
        key = (fecha_srv, 'Otros adicionales sin detalle')
        if key not in otros_servicios_map:
            otros_servicios_map[key] = {
                'fecha': fecha_srv,
                'tipo_servicio': 'Otros adicionales sin detalle',
                'valor_original': Decimal(0),
                'valor_recibido': Decimal(0),
            }
        # Lo no asignado se considera ingreso del establecimiento.
        otros_servicios_map[key]['valor_original'] += restante_srv
        otros_servicios_map[key]['valor_recibido'] += restante_srv

    otros_servicios_detalle = [
        {
            'fecha': item['fecha'],
            'tipo_servicio': item['tipo_servicio'],
            'valor_original': float(item['valor_original']),
            'valor_recibido': float(item['valor_recibido']),
        }
        for item in sorted(otros_servicios_map.values(), key=lambda x: (x['fecha'], x['tipo_servicio']))
    ]

    if not otros_servicios_detalle and otros_servicios_no_producto > 0:
        otros_servicios_detalle.append(
            {
                'fecha': f'{fecha_inicio} a {fecha_fin}',
                'tipo_servicio': 'Resumen otros servicios',
                'valor_original': float(otros_servicios_no_producto),
                'valor_recibido': float(otros_servicios_no_producto),
            }
        )

    detalle_cobro_espacio = [
        {
            'estilista_id': item.get('estilista_id'),
            'estilista_nombre': item.get('estilista_nombre'),
            'tipo_cobro_espacio': item.get('tipo_cobro_espacio') or 'sin_cobro',
            'valor_cobro_espacio': float(item.get('valor_cobro_espacio') or 0),
            'base_cobro_espacio': float(item.get('base_cobro_espacio') or 0),
            'dias_cobrados_alquiler': int(item.get('dias_cobrados_alquiler') or 0),
            'total_dias_trabajados': int(item.get('total_dias_trabajados') or 0),
            'descuento_espacio': float(item.get('descuento_espacio') or 0),
            'valor_pagado': float(item.get('descuento_espacio') or 0),
        }
        for item in estilistas_data
    ]
    detalle_cobro_espacio = sorted(detalle_cobro_espacio, key=lambda x: x['descuento_espacio'], reverse=True)

    return {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'fecha_estado_pago': fecha_fin,
        'fecha_estado_pago_inicio': fecha_inicio,
        'fecha_estado_pago_fin': fecha_fin,
        'kpis': {
            'venta_neta_total': float(venta_neta_total),
            'total_ganancias_negocio': float(total_ganancias_negocio),
            'ingresos_productos': float(ingresos_productos),
            'ingresos_productos_totales': float(ingresos_productos_totales),
            'ingresos_productos_caja': float(ingresos_productos_caja),
            'ingresos_abonos_consumo_empleado': float(ingresos_abonos_consumo),
            'ingresos_productos_en_servicios': float(ingresos_productos_en_servicios),
            'ingresos_servicios': float(ingresos_servicios),
            'ingresos_servicios_totales': float(ingresos_servicios_total_cliente),
            'ingresos_servicios_no_producto': float(ingresos_servicios_no_producto),
            'costo_productos': float(costo_productos),
            'costo_productos_en_servicios': float(costo_productos_en_servicios),
            'reserva_reabastecimiento_productos': float(costo_productos_totales),
            'utilidad_productos': float(utilidad_productos),
            'utilidad_neta_productos': float(utilidad_productos_total),
            'otros_servicios_no_producto': float(otros_servicios_no_producto),
            'comision_producto_estilistas': float(comision_producto_estilistas_total),
            'comision_producto_estilistas_caja': float(comision_producto_estilistas),
            'comision_producto_estilistas_servicios': float(comision_producto_estilistas_en_servicios),
            'comision_servicios_establecimiento': float(comision_servicios_establecimiento),
            'ingresos_servicios_adicionales': float(total_servicios_adicionales_establecimiento),
            'ganancia_establecimiento_productos': float(ganancia_establecimiento_productos),
            'disponible_productos_despues_reabastecer': float(ganancia_establecimiento_productos),
            'ganancia_establecimiento_total': float(ganancia_establecimiento_total),
            'ganancia_establecimiento_bruta': float(ganancia_establecimiento_bruta),
            'pago_total_estilistas': float(total_pago_estilistas_positivo),
            'deudas_estilistas': float(total_deuda_estilistas),
            'deuda_consumo_empleado_total': float(deuda_consumo_empleado_total),
            'pago_total_estilistas_neto': float(total_pago_neto_estilistas),
            'pago_total_estilistas_neto_periodo': float(total_pago_neto_estilistas_periodo),
            'descuentos_espacio_estilistas': float(total_descuentos_espacio),
            'cantidad_ventas_productos': ventas_pagadas_qs.count(),
            'cantidad_abonos_consumo_empleado': abonos_consumo_qs.count(),
            'cantidad_servicios': servicios_qs.count(),
            'productos_bajo_stock': productos_bajo_stock_qs.count(),
        },
        'estilistas': estilistas_data,
        'productos_bajo_stock': [
            {
                'id': p.id,
                'nombre': p.nombre,
                'marca': p.marca,
                'precio_venta': float(p.precio_venta or 0),
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
        'cierre_medios': {
            'detalle': cierre_medios_detalle,
            'totales': {
                'ingresos': float(tot_ingresos_medios),
                'salidas': float(tot_salidas_medios),
                'saldo': float(tot_ingresos_medios - tot_salidas_medios),
            },
        },
        'detalle_ganancia_productos': detalle_ganancia_productos,
        'detalle_cobro_espacio': detalle_cobro_espacio,
        'productos_diario': productos_diario,
        'otros_servicios_detalle': otros_servicios_detalle,
        'detalle_servicios_reparto': detalle_servicios_reparto,
    }


def _recalcular_estado_deuda(deuda):
    """Normaliza saldo y estado según cargos/abonos acumulados."""
    saldo = Decimal(deuda.total_cargo or 0) - Decimal(deuda.total_abonado or 0)
    if saldo <= 0:
        deuda.saldo_pendiente = Decimal(0)
        deuda.estado = 'cancelado'
    elif Decimal(deuda.total_abonado or 0) > 0:
        deuda.saldo_pendiente = saldo
        deuda.estado = 'parcial'
    else:
        deuda.saldo_pendiente = saldo
        deuda.estado = 'pendiente'


def _sincronizar_deuda_desde_items(deuda):
    """Sincroniza total_cargo/estado según los items de consumo aún existentes."""
    if not deuda:
        return

    items_consumo_qs = deuda.ventas_items.filter(tipo_operacion='consumo_empleado')
    total_cargo_real = Decimal(items_consumo_qs.aggregate(total=Sum('total'))['total'] or 0)
    total_abonado = Decimal(deuda.total_abonado or 0)

    # Si ya no existen items de la factura, la deuda no debe seguir en cartera.
    # Si no tuvo abonos se elimina; si tuvo abonos se marca cancelada en cero para auditoria.
    if total_cargo_real <= 0:
        if total_abonado <= 0:
            deuda.delete()
            return
        deuda.total_cargo = Decimal(0)
        deuda.saldo_pendiente = Decimal(0)
        deuda.estado = 'cancelado'
        deuda.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado'])
        return

    deuda.total_cargo = total_cargo_real
    _recalcular_estado_deuda(deuda)
    deuda.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado'])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_consumo_empleado(request):
    """Resumen de deudas por consumo de empleado en un rango de fechas."""
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene acceso a consumo de empleado y cartera.')

    fecha_inicio, fecha_fin = _resolver_rango_fechas(request)
    estilista_id = (request.query_params.get('estilista_id') or '').strip()

    qs = DeudaConsumoEmpleado.objects.select_related('estilista').filter(
        Q(fecha_hora__date__gte=fecha_inicio, fecha_hora__date__lte=fecha_fin)
        | Q(abonos__isnull=False)
    ).annotate(abonos_count=Count('abonos', distinct=True)).distinct()

    if estilista_id:
        qs = qs.filter(estilista_id=int(estilista_id))

    # Limpia inconsistencias por facturas de consumo eliminadas.
    for deuda in list(qs):
        _sincronizar_deuda_desde_items(deuda)

    qs = DeudaConsumoEmpleado.objects.select_related('estilista').filter(
        Q(fecha_hora__date__gte=fecha_inicio, fecha_hora__date__lte=fecha_fin)
        | Q(abonos__isnull=False)
    ).annotate(abonos_count=Count('abonos', distinct=True)).distinct()
    if estilista_id:
        qs = qs.filter(estilista_id=int(estilista_id))

    # Cartera principal: mantener pendientes y también facturas con abonos
    # para que el usuario vea inmediatamente los pagos registrados en liquidación.
    qs_pendientes = []
    for deuda in qs:
        saldo = Decimal(deuda.saldo_pendiente or 0)
        tiene_abono = int(getattr(deuda, 'abonos_count', 0) or 0) > 0

        if saldo <= Decimal('0.5') and not tiene_abono:
            continue
        if not deuda.ventas_items.filter(tipo_operacion='consumo_empleado').exists():
            continue
        qs_pendientes.append(deuda)

    resumen_mapa = {}
    deudas_items = []
    deuda_item_map = {}
    for deuda in sorted(qs_pendientes, key=lambda x: x.fecha_hora or timezone.now(), reverse=True):
        est_id = int(deuda.estilista_id)
        if est_id not in resumen_mapa:
            resumen_mapa[est_id] = {
                'estilista_id': est_id,
                'estilista_nombre': deuda.estilista.nombre,
                'total_consumido': Decimal(0),
                'total_abonado': Decimal(0),
                'saldo_pendiente': Decimal(0),
                'facturas': 0,
            }

        resumen_mapa[est_id]['total_consumido'] += Decimal(deuda.total_cargo or 0)
        resumen_mapa[est_id]['total_abonado'] += Decimal(deuda.total_abonado or 0)
        resumen_mapa[est_id]['saldo_pendiente'] += Decimal(deuda.saldo_pendiente or 0)
        resumen_mapa[est_id]['facturas'] += 1

        deuda_item = {
            'deuda_id': deuda.id,
            'estilista_id': est_id,
            'estilista_nombre': deuda.estilista.nombre,
            'numero_factura': deuda.numero_factura,
            'fecha_hora': timezone.localtime(deuda.fecha_hora).strftime('%Y-%m-%d %H:%M:%S'),
            'total_cargo': float(deuda.total_cargo or 0),
            'total_abonado': float(deuda.total_abonado or 0),
            'saldo_pendiente': float(deuda.saldo_pendiente or 0),
            'estado': deuda.estado,
            'abonos': [],
        }
        deudas_items.append(deuda_item)
        deuda_item_map[int(deuda.id)] = deuda_item

    # Historial de abonos por deuda para vista de cartera y auditoria.
    deuda_ids = [int(d.id) for d in qs_pendientes]
    abono_map = {}
    abonos_historial = []
    if deuda_ids:
        abonos_qs = (
            AbonoDeudaEmpleado.objects
            .select_related('usuario', 'deuda')
            .filter(deuda_id__in=deuda_ids)
            .order_by('deuda_id', '-fecha_hora', '-id')
        )
        vistos = set()
        for ab in abonos_qs:
            if ab.deuda_id in vistos:
                pass
            else:
                abono_map[int(ab.deuda_id)] = ab
                vistos.add(ab.deuda_id)

            item_abono = {
                'abono_id': ab.id,
                'deuda_id': int(ab.deuda_id),
                'numero_factura': ab.deuda.numero_factura if ab.deuda_id else None,
                'estilista_id': int(ab.deuda.estilista_id) if ab.deuda_id and ab.deuda.estilista_id else None,
                'estilista_nombre': ab.deuda.estilista.nombre if ab.deuda_id and ab.deuda.estilista_id else None,
                'monto': float(ab.monto or 0),
                'medio_pago': ab.medio_pago,
                'fecha_hora': timezone.localtime(ab.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if ab.fecha_hora else None,
                'usuario_nombre': getattr(ab.usuario, 'nombre_completo', None) if ab.usuario_id else None,
                'notas': ab.notas,
            }

            abonos_historial.append(item_abono)
            deuda_item = deuda_item_map.get(int(ab.deuda_id))
            if deuda_item is not None:
                deuda_item['abonos'].append(item_abono)

    consumos_detalle = []
    for deuda in qs_pendientes:
        ultimo_abono = abono_map.get(int(deuda.id))
        items_qs = deuda.ventas_items.select_related('producto', 'estilista').filter(tipo_operacion='consumo_empleado').order_by('-fecha_hora', '-id')
        for venta in items_qs:
            consumos_detalle.append(
                {
                    'venta_id': venta.id,
                    'deuda_id': deuda.id,
                    'numero_factura': deuda.numero_factura,
                    'fecha_consumo': timezone.localtime(venta.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if venta.fecha_hora else None,
                    'estilista_id': deuda.estilista_id,
                    'estilista_nombre': deuda.estilista.nombre if deuda.estilista_id else None,
                    'producto_id': venta.producto_id,
                    'producto_nombre': venta.producto.nombre if venta.producto_id else None,
                    'cantidad': int(venta.cantidad or 0),
                    'precio_unitario': float(venta.precio_unitario or 0),
                    'valor_consumo': float(venta.total or 0),
                    'estado_pago': deuda.estado,
                    'pagado': deuda.estado == 'cancelado',
                    'total_abonado_factura': float(deuda.total_abonado or 0),
                    'saldo_factura': float(deuda.saldo_pendiente or 0),
                    'fecha_ultimo_abono': timezone.localtime(ultimo_abono.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if ultimo_abono and ultimo_abono.fecha_hora else None,
                    'medio_ultimo_abono': ultimo_abono.medio_pago if ultimo_abono else None,
                }
            )

    resumen = []
    for item in sorted(resumen_mapa.values(), key=lambda x: x['estilista_nombre'].lower()):
        saldo = Decimal(item['saldo_pendiente'])
        if saldo <= 0:
            estado = 'cancelado'
        elif Decimal(item['total_abonado']) > 0:
            estado = 'parcial'
        else:
            estado = 'pendiente'

        resumen.append(
            {
                'estilista_id': item['estilista_id'],
                'estilista_nombre': item['estilista_nombre'],
                'facturas': item['facturas'],
                'total_consumido': float(item['total_consumido']),
                'total_abonado': float(item['total_abonado']),
                'saldo_pendiente': float(item['saldo_pendiente']),
                'estado': estado,
            }
        )

    return Response(
        {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'resumen': resumen,
            'deudas': deudas_items,
            'consumos_detalle': consumos_detalle,
            'abonos_historial': abonos_historial,
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def abonar_consumo_empleado(request):
    """Registra un abono y lo distribuye en las deudas pendientes más antiguas."""
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene permiso para registrar abonos de cartera.')

    estilista_id = request.data.get('estilista_id')
    deuda_id = request.data.get('deuda_id')
    monto = request.data.get('monto')
    medio_pago = (request.data.get('medio_pago') or 'efectivo').strip().lower()
    notas = request.data.get('notas')
    fecha_raw = (request.data.get('fecha') or '').strip()

    if medio_pago not in {'nequi', 'daviplata', 'efectivo', 'otros'}:
        return Response({'error': 'Medio de pago inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    deuda_objetivo = None
    if deuda_id is not None and str(deuda_id).strip() != '':
        try:
            deuda_objetivo = DeudaConsumoEmpleado.objects.select_related('estilista').get(id=int(deuda_id))
            estilista = deuda_objetivo.estilista
        except Exception:
            return Response({'error': 'Factura de cartera no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
    else:
        try:
            estilista = Estilista.objects.get(id=int(estilista_id))
        except Exception:
            return Response({'error': 'Empleado no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        monto_decimal = Decimal(str(monto or 0))
    except Exception:
        return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    if monto_decimal <= 0:
        return Response({'error': 'El monto debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_abono_dt = None
    if fecha_raw:
        try:
            fecha_abono = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
            # Hora fija para evitar desplazamientos por zona horaria.
            fecha_abono_dt = datetime.combine(fecha_abono, datetime.min.time()).replace(hour=12)
            if timezone.is_naive(fecha_abono_dt):
                fecha_abono_dt = timezone.make_aware(fecha_abono_dt, timezone.get_current_timezone())
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        aplicaciones, restante = _aplicar_abonos_consumo_interno(
            estilista=estilista,
            monto_decimal=monto_decimal,
            medio_pago=medio_pago,
            usuario=request.user,
            notas=notas,
            fecha_abono_dt=fecha_abono_dt,
            deuda_objetivo=deuda_objetivo,
            deuda_ids=None,
        )
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'ok': True,
            'estilista_id': estilista.id,
            'estilista_nombre': estilista.nombre,
            'deuda_id': int(deuda_objetivo.id) if deuda_objetivo is not None else None,
            'monto_recibido': float(monto_decimal),
            'monto_aplicado': float(monto_decimal - restante),
            'monto_sobrante': float(restante),
            'medio_pago': medio_pago,
            'aplicaciones': aplicaciones,
        }
    )


def _aplicar_abonos_consumo_interno(
    *,
    estilista,
    monto_decimal,
    medio_pago,
    usuario,
    notas,
    fecha_abono_dt=None,
    deuda_objetivo=None,
    deuda_ids=None,
):
    """Aplica abonos de consumo a deudas pendientes en orden de antigüedad."""
    if deuda_objetivo is not None:
        if deuda_objetivo.estilista_id != estilista.id:
            raise ValueError('La factura no pertenece al empleado indicado.')
        if Decimal(deuda_objetivo.saldo_pendiente or 0) <= 0:
            raise ValueError('La factura seleccionada no tiene saldo pendiente.')
        deudas_pendientes = [deuda_objetivo]
    else:
        qs = DeudaConsumoEmpleado.objects.filter(
            estilista=estilista,
            saldo_pendiente__gt=0,
        ).order_by('fecha_hora', 'id')
        if deuda_ids:
            ids = [int(x) for x in deuda_ids if str(x).strip().isdigit()]
            if ids:
                qs = qs.filter(id__in=ids)
        deudas_pendientes = list(qs)

    if not deudas_pendientes:
        raise ValueError('El empleado no tiene deudas pendientes.')

    restante = Decimal(monto_decimal or 0)
    aplicaciones = []
    for deuda in deudas_pendientes:
        if restante <= 0:
            break

        saldo = Decimal(deuda.saldo_pendiente or 0)
        aplicado = saldo if restante >= saldo else restante
        if aplicado <= 0:
            continue

        create_data = {
            'deuda': deuda,
            'monto': aplicado,
            'medio_pago': medio_pago,
            'usuario': usuario,
            'notas': notas,
        }
        if fecha_abono_dt is not None:
            create_data['fecha_hora'] = fecha_abono_dt

        AbonoDeudaEmpleado.objects.create(**create_data)

        deuda.total_abonado = Decimal(deuda.total_abonado or 0) + aplicado
        _recalcular_estado_deuda(deuda)
        deuda.save(update_fields=['total_abonado', 'saldo_pendiente', 'estado'])

        aplicaciones.append(
            {
                'deuda_id': deuda.id,
                'numero_factura': deuda.numero_factura,
                'monto_aplicado': float(aplicado),
                'saldo_restante': float(deuda.saldo_pendiente),
                'estado': deuda.estado,
            }
        )

        restante -= aplicado

    return aplicaciones, restante


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def editar_abono_consumo_empleado(request, abono_id):
    """Permite corregir un abono registrado por error y recalcula la deuda asociada."""
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene permiso para editar abonos de cartera.')

    try:
        abono = AbonoDeudaEmpleado.objects.select_related('deuda').get(id=int(abono_id))
    except Exception:
        return Response({'error': 'Abono no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    monto_raw = request.data.get('monto', abono.monto)
    medio_pago = (request.data.get('medio_pago') or abono.medio_pago or 'efectivo').strip().lower()
    notas = request.data.get('notas', abono.notas)
    fecha_raw = (request.data.get('fecha') or '').strip()

    if medio_pago not in {'nequi', 'daviplata', 'efectivo', 'otros'}:
        return Response({'error': 'Medio de pago inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        monto_nuevo = Decimal(str(monto_raw or 0))
    except Exception:
        return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    if monto_nuevo <= 0:
        return Response({'error': 'El monto debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_nueva_dt = None
    if fecha_raw:
        try:
            fecha_nueva = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        # Usar una hora fija evita que el __date en BD cambie por conversión UTC.
        fecha_nueva_dt = datetime.combine(fecha_nueva, datetime.min.time()).replace(hour=12)
        if timezone.is_naive(fecha_nueva_dt):
            fecha_nueva_dt = timezone.make_aware(fecha_nueva_dt, timezone.get_current_timezone())

    with transaction.atomic():
        deuda = DeudaConsumoEmpleado.objects.select_for_update().get(id=abono.deuda_id)
        total_otros_abonos = Decimal(
            deuda.abonos.exclude(id=abono.id).aggregate(total=Sum('monto'))['total'] or 0
        )
        total_abonado_nuevo = total_otros_abonos + monto_nuevo
        total_cargo = Decimal(deuda.total_cargo or 0)

        if total_abonado_nuevo - total_cargo > Decimal('0.0001'):
            return Response(
                {
                    'error': 'El valor abonado supera el total de la factura.',
                    'maximo_permitido': float(max(total_cargo - total_otros_abonos, Decimal(0))),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        abono.monto = monto_nuevo
        abono.medio_pago = medio_pago
        abono.notas = notas
        if fecha_nueva_dt is not None:
            abono.fecha_hora = fecha_nueva_dt
            abono.save(update_fields=['monto', 'medio_pago', 'notas', 'fecha_hora'])
        else:
            abono.save(update_fields=['monto', 'medio_pago', 'notas'])

        deuda.total_abonado = total_abonado_nuevo
        _recalcular_estado_deuda(deuda)
        deuda.save(update_fields=['total_abonado', 'saldo_pendiente', 'estado'])

    fecha_abono_resp = None
    if abono.fecha_hora:
        try:
            fecha_abono_resp = timezone.localtime(abono.fecha_hora).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            fecha_abono_resp = abono.fecha_hora.strftime('%Y-%m-%d %H:%M:%S')

    return Response(
        {
            'ok': True,
            'abono': {
                'abono_id': abono.id,
                'deuda_id': abono.deuda_id,
                'numero_factura': deuda.numero_factura,
                'monto': float(abono.monto or 0),
                'medio_pago': abono.medio_pago,
                'notas': abono.notas,
                'fecha_hora': fecha_abono_resp,
            },
            'deuda': {
                'deuda_id': deuda.id,
                'total_cargo': float(deuda.total_cargo or 0),
                'total_abonado': float(deuda.total_abonado or 0),
                'saldo_pendiente': float(deuda.saldo_pendiente or 0),
                'estado': deuda.estado,
            },
        }
    )


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def estado_pago_estilista_dia(request):
    if request.method == 'GET':
        fecha_raw = (request.query_params.get('fecha') or timezone.localdate().strftime('%Y-%m-%d')).strip()
        fecha_inicio_raw = (request.query_params.get('fecha_inicio') or '').strip()
        fecha_fin_raw = (request.query_params.get('fecha_fin') or '').strip()
        estilista_id_raw = (request.query_params.get('estilista_id') or '').strip()

        # Modo rango: útil para cuadro de cuadre diario por fechas.
        if fecha_inicio_raw and fecha_fin_raw:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d').date()
                fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d').date()
            except Exception:
                return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

            if fecha_inicio > fecha_fin:
                return Response({'error': 'fecha_inicio no puede ser mayor que fecha_fin.'}, status=status.HTTP_400_BAD_REQUEST)

            qs = EstadoPagoEstilistaDia.objects.filter(fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
            if estilista_id_raw:
                try:
                    qs = qs.filter(estilista_id=int(estilista_id_raw))
                except Exception:
                    return Response({'error': 'estilista_id inválido.'}, status=status.HTTP_400_BAD_REQUEST)

            items = [
                {
                    'estilista_id': x.estilista_id,
                    'fecha': x.fecha.strftime('%Y-%m-%d'),
                    'estado': x.estado,
                    'pago_efectivo': float(x.pago_efectivo or 0),
                    'pago_nequi': float(x.pago_nequi or 0),
                    'pago_daviplata': float(x.pago_daviplata or 0),
                    'pago_otros': float(x.pago_otros or 0),
                    'abono_puesto': float(x.abono_puesto or 0),
                    'medio_abono_puesto': getattr(x, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                    'notas': x.notas,
                }
                for x in qs.order_by('fecha', 'estilista_id')
            ]

            return Response({'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'), 'fecha_fin': fecha_fin.strftime('%Y-%m-%d'), 'items': items})

        try:
            fecha = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except Exception:
            return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            items = [
                {
                    'estilista_id': x.estilista_id,
                    'fecha': fecha.strftime('%Y-%m-%d'),
                    'estado': x.estado,
                    'pago_efectivo': float(x.pago_efectivo or 0),
                    'pago_nequi': float(x.pago_nequi or 0),
                    'pago_daviplata': float(x.pago_daviplata or 0),
                    'pago_otros': float(x.pago_otros or 0),
                    'abono_puesto': float(x.abono_puesto or 0),
                    'medio_abono_puesto': getattr(x, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                    'notas': x.notas,
                }
                for x in EstadoPagoEstilistaDia.objects.filter(fecha=fecha)
            ]
        except (OperationalError, ProgrammingError):
            # Fallback: reconstruir estado del día usando el último historial por estilista.
            historial_qs = EstadoPagoEstilistaHistorial.objects.select_related('estilista').filter(
                fecha=fecha,
            ).order_by('estilista_id', '-fecha_cambio')
            items = []
            vistos = set()
            for h in historial_qs:
                if h.estilista_id in vistos:
                    continue
                items.append(
                    {
                        'estilista_id': h.estilista_id,
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'estado': h.estado_nuevo,
                        'pago_efectivo': 0,
                        'pago_nequi': 0,
                        'pago_daviplata': 0,
                        'pago_otros': 0,
                        'abono_puesto': float(getattr(h, 'abono_puesto', 0) or 0),
                        'medio_abono_puesto': getattr(h, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                        'notas': h.notas,
                    }
                )
                vistos.add(h.estilista_id)
        return Response({'fecha': fecha.strftime('%Y-%m-%d'), 'items': items})

    estilista_id = request.data.get('estilista_id')
    fecha_raw = request.data.get('fecha')
    fecha_inicio_raw = request.data.get('fecha_inicio')
    fecha_fin_raw = request.data.get('fecha_fin')
    estado = (request.data.get('estado') or '').strip().lower()
    notas = request.data.get('notas')
    pagos_detalle = request.data.get('pagos_detalle') or {}
    abono_puesto_raw = request.data.get('abono_puesto')
    medio_abono_puesto = (request.data.get('medio_abono_puesto') or 'efectivo').strip().lower()

    def _to_decimal_non_negative(value):
        try:
            dec = Decimal(str(value or 0))
        except Exception:
            return Decimal(0)
        if dec < 0:
            return Decimal(0)
        return dec

    pago_efectivo = _to_decimal_non_negative(pagos_detalle.get('efectivo'))
    pago_nequi = _to_decimal_non_negative(pagos_detalle.get('nequi'))
    pago_daviplata = _to_decimal_non_negative(pagos_detalle.get('daviplata'))
    pago_otros = _to_decimal_non_negative(pagos_detalle.get('otros'))
    total_pagado = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
    abono_operacion_puesto = abono_puesto
    abono_puesto = _to_decimal_non_negative(abono_puesto_raw)

    if medio_abono_puesto not in {'efectivo', 'nequi', 'daviplata', 'otros'}:
        medio_abono_puesto = 'efectivo'

    if not estilista_id or estado not in {'pendiente', 'cancelado'}:
        return Response(
            {'error': 'Debes enviar estilista_id y estado (pendiente|cancelado).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        if fecha_raw:
            fecha_inicio_dt = datetime.strptime(str(fecha_raw), '%Y-%m-%d').date()
            fecha_fin_dt = fecha_inicio_dt
        else:
            fecha_inicio_dt = datetime.strptime(str(fecha_inicio_raw), '%Y-%m-%d').date()
            fecha_fin_dt = datetime.strptime(str(fecha_fin_raw), '%Y-%m-%d').date()
    except Exception:
        return Response(
            {'error': 'Formato de fecha inválido. Usa fecha (YYYY-MM-DD) o fecha_inicio/fecha_fin (YYYY-MM-DD).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if fecha_inicio_dt > fecha_fin_dt:
        return Response({'error': 'fecha_inicio no puede ser mayor que fecha_fin.'}, status=status.HTTP_400_BAD_REQUEST)

    if (total_pagado > 0 or abono_puesto > 0) and fecha_inicio_dt != fecha_fin_dt:
        return Response(
            {'error': 'El detalle de pago por medio solo se puede registrar para un único día.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        estilista = Estilista.objects.get(id=int(estilista_id))
    except Exception:
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    usuario_obj = request.user if isinstance(request.user, Usuario) else None

    fechas_procesadas = 0
    cambios_registrados = 0
    historial_no_disponible = False
    tabla_diaria_no_disponible = False
    guardado_legacy_sql = False

    fecha_cursor = fecha_inicio_dt
    while fecha_cursor <= fecha_fin_dt:
        estado_anterior = 'pendiente'
        estado_guardado = estado

        if not tabla_diaria_no_disponible:
            try:
                actual = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha_cursor).first()
                estado_anterior = actual.estado if actual else 'pendiente'
            except (OperationalError, ProgrammingError):
                tabla_diaria_no_disponible = True

        if tabla_diaria_no_disponible:
            try:
                ultimo_hist = EstadoPagoEstilistaHistorial.objects.filter(
                    estilista=estilista,
                    fecha=fecha_cursor,
                ).order_by('-fecha_cambio').first()
                if ultimo_hist:
                    estado_anterior = ultimo_hist.estado_nuevo
            except Exception:
                estado_anterior = 'pendiente'

        if not tabla_diaria_no_disponible:
            try:
                # Calcular totales del día específico
                ganancias_totales_dia, descuento_dia, neto_dia = _calcular_totales_dia_estilista(estilista, fecha_cursor)
                valor_total_empleado_dia = max(Decimal(0), neto_dia)

                # El pago al empleado puede llegar al 100% de sus ganancias.
                if total_pagado > valor_total_empleado_dia:
                    return Response(
                        {
                            'error': (
                                f'La liquidación al empleado (${float(total_pagado):.2f}) '
                                f'no puede exceder el valor total ganado (${float(valor_total_empleado_dia):.2f}).'
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Actualizar tabla diaria: guarda pagos al empleado + abono y pendiente de puesto.
                _, descuento_dia, _ = _calcular_totales_dia_estilista(estilista, fecha_cursor)
                deuda_anterior_dia = Decimal(0)
                ultimo_estado_anterior = EstadoPagoEstilistaDia.objects.filter(
                    estilista=estilista,
                    fecha__lt=fecha_cursor,
                ).order_by('-fecha', '-actualizado_en').first()
                if ultimo_estado_anterior:
                    deuda_anterior_dia = Decimal(
                        getattr(ultimo_estado_anterior, 'saldo_puesto_pendiente', None)
                        or getattr(ultimo_estado_anterior, 'pendiente_puesto', 0)
                        or 0
                    )

                abono_puesto_dia = abono_puesto if estado in {'cancelado', 'debe'} else Decimal(0)
                pendiente_puesto_dia = max(deuda_anterior_dia + max(descuento_dia, Decimal(0)) - abono_puesto_dia, Decimal(0))
                pendiente_liquidacion_dia = max(valor_total_empleado_dia - total_pagado, Decimal(0))
                estado_guardado = 'pendiente' if pendiente_liquidacion_dia > 0 else ('debe' if pendiente_puesto_dia > 0 else 'cancelado')
                
                EstadoPagoEstilistaDia.objects.update_or_create(
                    estilista=estilista,
                    fecha=fecha_cursor,
                    defaults={
                        'estado': estado_guardado,
                        'ganancias_totales': valor_total_empleado_dia,
                        'descuento_puesto': descuento_dia,
                        'total_pagable': valor_total_empleado_dia,
                        'pago_efectivo': pago_efectivo,
                        'pago_nequi': pago_nequi,
                        'pago_daviplata': pago_daviplata,
                        'pago_otros': pago_otros,
                        'neto_dia': valor_total_empleado_dia,
                        'notas': notas,
                        'abono_puesto': abono_puesto_dia,
                        'medio_abono_puesto': medio_abono_puesto,
                        'saldo_puesto_pendiente': pendiente_puesto_dia,
                        'pendiente_puesto': pendiente_puesto_dia,
                    },
                )
            except (OperationalError, ProgrammingError):
                tabla_diaria_no_disponible = True

        # NOTA: El "deshacer" ya NO borra historial (auditoría se mantiene).
        # Solo se revierte el estado a pendiente en tabla diaria.

        if estado_anterior != estado and estado == 'cancelado':
            try:
                _, descuento_dia_hist, _ = _calcular_totales_dia_estilista(estilista, fecha_cursor)
                abono_aplicado_hist = abono_puesto if estado == 'cancelado' else Decimal(0)
                pendiente_puesto_hist = max(max(descuento_dia_hist, Decimal(0)) - abono_aplicado_hist, Decimal(0))
                try:
                    EstadoPagoEstilistaHistorial.objects.create(
                        estilista=estilista,
                        fecha=fecha_cursor,
                        estado_anterior=estado_anterior,
                        estado_nuevo=estado_guardado,
                        notas=notas,
                        usuario=usuario_obj,
                        monto_liquidado=total_pagado,
                        abono_puesto=abono_aplicado_hist,
                        medio_abono_puesto=medio_abono_puesto,
                        pendiente_puesto=pendiente_puesto_hist,
                    )
                except (OperationalError, ProgrammingError):
                    # Compatibilidad: si producción aún no tiene columnas nuevas,
                    # guardar historial con el esquema anterior.
                    _insertar_historial_legacy(
                        estilista_id=estilista.id,
                        fecha=fecha_cursor,
                        estado_anterior=estado_anterior,
                        estado_nuevo=estado,
                        notas=notas,
                        usuario_id=(usuario_obj.id if usuario_obj else None),
                        monto_liquidado=(total_pagado if estado == 'cancelado' else Decimal(0)),
                    )
                cambios_registrados += 1
            except (OperationalError, ProgrammingError):
                # No bloquear la operación diaria si falla la bitácora.
                historial_no_disponible = True

        fechas_procesadas += 1
        fecha_cursor += timedelta(days=1)

    return Response(
        {
            'estilista_id': estilista.id,
            'fecha_inicio': fecha_inicio_dt.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin_dt.strftime('%Y-%m-%d'),
            'estado': estado,
            'notas': notas,
            'fechas_procesadas': fechas_procesadas,
            'cambios_registrados': cambios_registrados,
            'historial_no_disponible': historial_no_disponible,
            'tabla_diaria_no_disponible': tabla_diaria_no_disponible,
            'pagos_detalle': {
                'efectivo': float(pago_efectivo),
                'nequi': float(pago_nequi),
                'daviplata': float(pago_daviplata),
                'otros': float(pago_otros),
                'total': float(total_pagado),
            },
            'abono_puesto': float(abono_puesto),
            'medio_abono_puesto': medio_abono_puesto,
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def liquidar_dia_v2(request):
    """
    NUEVO ENDPOINT SIMPLIFICADO - LIQUIDADOR CLARO Y CORRECTO
    
    POST /api/liquidar-dia-v2/
    
    Body:
    {
        "estilista_id": 5,
        "fecha": "2026-03-15",
        "pago_efectivo": 50000,
        "pago_nequi": 30000,
        "pago_daviplata": 0,
        "pago_otros": 0,
        "abono_puesto": 15000,
        "notas": "Liquidación del día"
    }
    
     LÓGICA:
     1. Calcula ganancias + descuento del día
     2. Valida reglas de negocio:
         - El valor a liquidar (pago al empleado) NO puede superar ganancias totales.
         - Se permite abono de puesto adelantado aunque no exista deuda previa.
     3. Guarda en tabla diaria
     4. Crea registro historial
     5. Retorna valores calculados
    """
    
    # ============ EXTRACCIÓN Y VALIDACIÓN ============
    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        fecha_str = request.data.get('fecha', '').strip()
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato fecha inválido'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Convertir a Decimal
    def _to_decimal(v):
        try:
            d = Decimal(str(v or 0))
            return max(d, Decimal(0))
        except:
            return Decimal(0)
    
    pago_efectivo = _to_decimal(request.data.get('pago_efectivo'))
    pago_nequi = _to_decimal(request.data.get('pago_nequi'))
    pago_daviplata = _to_decimal(request.data.get('pago_daviplata'))
    pago_otros = _to_decimal(request.data.get('pago_otros'))
    abono_puesto = _to_decimal(request.data.get('abono_puesto'))
    # El payload trae el abono de esta operación; luego se acumula con lo ya registrado en el día.
    abono_operacion_puesto = abono_puesto
    forzar_reemplazo_dia_raw = request.data.get('forzar_reemplazo_dia', False)
    if isinstance(forzar_reemplazo_dia_raw, str):
        forzar_reemplazo_dia = forzar_reemplazo_dia_raw.strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}
    else:
        forzar_reemplazo_dia = bool(forzar_reemplazo_dia_raw)
    medio_abono_puesto = (request.data.get('medio_abono_puesto') or 'efectivo').strip().lower()
    if medio_abono_puesto not in {'efectivo', 'nequi', 'daviplata', 'otros'}:
        medio_abono_puesto = 'efectivo'
    notas = request.data.get('notas', '').strip()[:255]
    
    total_pagado = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
    
    # ============ [1] CALCULAR LIQUIDACIÓN ============
    try:
        calc = calcular_liquidacion_dia_estilista(estilista, fecha)
    except (OperationalError, ProgrammingError) as e:
        return Response(
            {'error': f'No se pudo calcular la liquidación por un problema de base de datos: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        return Response(
            {'error': f'No se pudo calcular la liquidación: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    ganancias = calc['ganancias_totales']
    descuento = calc['descuento_puesto']
    pagable = calc['total_pagable']
    
    # ============ [2] VALIDAR REGLAS DE NEGOCIO ============
    # Deuda anterior de puesto (saldo arrastrado del último día liquidado)
    deuda_anterior_puesto = Decimal(0)
    try:
        ultimo_estado = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista,
            fecha__lt=fecha,
        ).order_by('-fecha').first()
        if ultimo_estado:
            deuda_anterior_puesto = Decimal(
                getattr(ultimo_estado, 'saldo_puesto_pendiente', None)
                or getattr(ultimo_estado, 'pendiente_puesto', 0)
                or 0
            )
    except (OperationalError, ProgrammingError):
        # Si la tabla diaria no está al día en producción, continuar sin romper.
        deuda_anterior_puesto = Decimal(0)

    # 1) Tope principal: valor a liquidar no puede superar el total ganado por el empleado.
    if total_pagado > pagable:
        return Response({
            'error': (
                f'El valor a liquidar (${float(total_pagado):.2f}) no puede superar '
                f'el valor total empleado (${float(pagable):.2f}).'
            ),
            'ganancias_totales': float(ganancias),
            'valor_liquidar': float(total_pagado),
        }, status=status.HTTP_400_BAD_REQUEST)

    # Se permite que el empleado pague abono de puesto adelantado.
    # Si no hay deuda suficiente para aplicarlo en el saldo, el excedente queda
    # como abono registrado del día (sin bloquear la liquidación).

    # En operación normal el abono se acumula por día; en modo corrección se reemplaza.
    abono_puesto_previo_dia = Decimal(0)
    if not forzar_reemplazo_dia:
        try:
            estado_existente_dia = EstadoPagoEstilistaDia.objects.filter(
                estilista=estilista,
                fecha=fecha,
            ).first()
            if estado_existente_dia:
                abono_puesto_previo_dia = Decimal(estado_existente_dia.abono_puesto or 0)
        except (OperationalError, ProgrammingError):
            abono_puesto_previo_dia = Decimal(0)

    abono_puesto = abono_operacion_puesto if forzar_reemplazo_dia else (abono_puesto_previo_dia + abono_operacion_puesto)
    
    # ============ [3] SALDO PENDIENTE ACUMULADO DE PUESTO ============
    deuda_total_puesto = deuda_anterior_puesto + descuento
    abono_aplicado_total_puesto = min(abono_puesto, deuda_total_puesto)
    saldo_puesto = max(deuda_total_puesto - abono_aplicado_total_puesto, Decimal(0))
    pendiente_liquidacion = max(pagable - total_pagado, Decimal(0))
    
    # ============ [4] GUARDAR ============
    tabla_diaria_no_disponible = False
    guardado_legacy_sql = False
    estado_resultante = 'pendiente'
    estado_anterior = 'pendiente'
    try:
        estado_diaria, _ = EstadoPagoEstilistaDia.objects.get_or_create(
            estilista=estilista,
            fecha=fecha,
        )
        estado_anterior = estado_diaria.estado
        
        # Actualizar todos los campos
        estado_diaria.ganancias_totales = ganancias
        estado_diaria.descuento_puesto = descuento
        estado_diaria.total_pagable = pagable
        estado_diaria.neto_dia = pagable  # compatibilidad legacy
        estado_diaria.pago_efectivo = pago_efectivo
        estado_diaria.pago_nequi = pago_nequi
        estado_diaria.pago_daviplata = pago_daviplata
        estado_diaria.pago_otros = pago_otros
        estado_diaria.abono_puesto = abono_puesto
        estado_diaria.medio_abono_puesto = medio_abono_puesto
        estado_diaria.saldo_puesto_pendiente = saldo_puesto
        estado_diaria.pendiente_puesto = saldo_puesto  # compatibilidad legacy
        estado_diaria.notas = notas
        estado_diaria.usuario_liquida = request.user
        
        # Estado del día:
        # - pendiente: aún falta liquidar al empleado
        # - debe: el empleado ya fue liquidado pero sigue debiendo puesto
        # - cancelado: empleado liquidado y sin deuda de puesto
        if pendiente_liquidacion > 0:
            estado_diaria.estado = 'pendiente'
        elif saldo_puesto > 0:
            estado_diaria.estado = 'debe'
        else:
            estado_diaria.estado = 'cancelado'
        
        estado_diaria.save()
        estado_resultante = estado_diaria.estado
        
    except (OperationalError, ProgrammingError):
        # Compatibilidad: intentar persistencia SQL en esquema legacy para no perder datos.
        tabla_diaria_no_disponible = True
        # Establecer estado segun el saldo del puesto
        if pendiente_liquidacion > 0:
            estado_resultante = 'pendiente'
        elif saldo_puesto > 0:
            estado_resultante = 'debe'
        else:
            estado_resultante = 'cancelado'
        try:
            with connection.cursor() as cursor:
                # 1) Intentar update de fila existente (set completo).
                try:
                    cursor.execute(
                        """
                        UPDATE estado_pago_estilista_dia
                        SET estado=%s,
                            pago_efectivo=%s,
                            pago_nequi=%s,
                            pago_daviplata=%s,
                            pago_otros=%s,
                            abono_puesto=%s,
                            medio_abono_puesto=%s,
                            pendiente_puesto=%s,
                            notas=%s,
                            actualizado_en=%s
                        WHERE estilista_id=%s AND fecha=%s
                        """,
                        [
                            estado_resultante,
                            pago_efectivo,
                            pago_nequi,
                            pago_daviplata,
                            pago_otros,
                            abono_puesto,
                            medio_abono_puesto,
                            saldo_puesto,
                            notas,
                            timezone.now(),
                            estilista.id,
                            fecha,
                        ],
                    )
                except Exception:
                    cursor.execute(
                        """
                        UPDATE estado_pago_estilista_dia
                        SET estado=%s,
                            pago_efectivo=%s,
                            pago_nequi=%s,
                            pago_daviplata=%s,
                            pago_otros=%s,
                            abono_puesto=%s,
                            medio_abono_puesto=%s,
                            saldo_puesto_pendiente=%s,
                            pendiente_puesto=%s,
                            notas=%s,
                            actualizado_en=%s
                        WHERE estilista_id=%s AND fecha=%s
                        """,
                        [
                            estado_resultante,
                            pago_efectivo,
                            pago_nequi,
                            pago_daviplata,
                            pago_otros,
                            abono_puesto,
                            medio_abono_puesto,
                            saldo_puesto,
                            saldo_puesto,
                            notas,
                            timezone.now(),
                            estilista.id,
                            fecha,
                        ],
                    )

                # 2) Si no existía, insertar.
                if cursor.rowcount == 0:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO estado_pago_estilista_dia
                            (estilista_id, fecha, estado, pago_efectivo, pago_nequi, pago_daviplata, pago_otros,
                             abono_puesto, medio_abono_puesto, pendiente_puesto, notas, actualizado_en)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            [
                                estilista.id,
                                fecha,
                                estado_resultante,
                                pago_efectivo,
                                pago_nequi,
                                pago_daviplata,
                                pago_otros,
                                abono_puesto,
                                medio_abono_puesto,
                                saldo_puesto,
                                notas,
                                timezone.now(),
                            ],
                        )
                    except Exception:
                        cursor.execute(
                            """
                            INSERT INTO estado_pago_estilista_dia
                            (estilista_id, fecha, estado, pago_efectivo, pago_nequi, pago_daviplata, pago_otros,
                             notas, actualizado_en)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            [
                                estilista.id,
                                fecha,
                                estado_resultante,
                                pago_efectivo,
                                pago_nequi,
                                pago_daviplata,
                                pago_otros,
                                notas,
                                timezone.now(),
                            ],
                        )
            guardado_legacy_sql = True
        except Exception as e:
            return Response(
                {'error': f'No se pudo guardar la liquidación en tabla diaria: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    except Exception as e:
        return Response({'error': f'Error procesando liquidación: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
    
    # ============ [5] HISTORIAL ============
    hubo_movimiento_liquidacion = (total_pagado > 0) or (abono_puesto > 0)
    try:
        if hubo_movimiento_liquidacion:
            EstadoPagoEstilistaHistorial.objects.create(
                estilista=estilista,
                fecha=fecha,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_resultante,
                notas=notas,
                usuario=request.user,
                monto_liquidado=total_pagado,
                abono_puesto=abono_operacion_puesto,
                medio_abono_puesto=medio_abono_puesto,
                pendiente_puesto=saldo_puesto,
            )
    except (OperationalError, ProgrammingError):
        # Historial en esquema legacy (sin columnas nuevas)
        try:
            if hubo_movimiento_liquidacion:
                _insertar_historial_legacy(
                    estilista_id=estilista.id,
                    fecha=fecha,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_resultante,
                    notas=notas,
                    usuario_id=(request.user.id if request.user else None),
                    monto_liquidado=total_pagado,
                )
        except Exception:
            pass
    except Exception:
        pass  # No bloquear

    _upsert_fact_liquidacion_dia(
        estilista=estilista,
        fecha=fecha,
        calc=calc,
        pago_efectivo=pago_efectivo,
        pago_nequi=pago_nequi,
        pago_daviplata=pago_daviplata,
        pago_otros=pago_otros,
        abono_puesto=abono_puesto,
        medio_abono_puesto=medio_abono_puesto,
        deuda_anterior=deuda_anterior_puesto,
        deuda_cierre=saldo_puesto,
        pendiente_pago=pendiente_liquidacion,
        estado_liquidacion=estado_resultante,
        forzar_reemplazo_dia=forzar_reemplazo_dia,
        usuario=request.user,
        notas=notas,
        origen='liquidar_dia_v2',
    )
    
    # ============ [6] RESPUESTA ============
    return Response({
        'success': True,
        'estilista': {'id': estilista.id, 'nombre': estilista.nombre},
        'fecha': fecha.strftime('%Y-%m-%d'),
        'liquidacion': {
            'ganancias_totales': float(ganancias),
            'descuento_puesto': float(descuento),
            'total_pagable': float(pagable),
            'pendiente_liquidacion': float(pendiente_liquidacion),
        },
        'pagos': {
            'efectivo': float(pago_efectivo),
            'nequi': float(pago_nequi),
            'daviplata': float(pago_daviplata),
            'otros': float(pago_otros),
            'total': float(total_pagado),
        },
        'puesto': {
            'descuento': float(descuento),
            'abono': float(abono_puesto),
            'abono_operacion': float(abono_operacion_puesto),
            'abono_previo_dia': float(abono_puesto_previo_dia),
            'medio_abono': medio_abono_puesto,
            'deuda_anterior': float(deuda_anterior_puesto),
            'deuda_total': float(deuda_total_puesto),
            'abono_aplicado': float(abono_aplicado_total_puesto),
            'saldo_pendiente': float(saldo_puesto),
        },
        'estado': estado_resultante,
        'tabla_diaria_no_disponible': tabla_diaria_no_disponible,
        'guardado_legacy_sql': guardado_legacy_sql,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def liquidar_operacion_integral(request):
    """Ejecuta en una sola transacción: cobro de consumo (opcional) + liquidación diaria."""
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene permiso para liquidar operaciones integrales.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except Exception:
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    consumo_monto = request.data.get('consumo_monto', 0)
    try:
        consumo_monto = Decimal(str(consumo_monto or 0))
    except Exception:
        return Response({'error': 'consumo_monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)
    consumo_monto = max(consumo_monto, Decimal(0))

    deuda_ids = request.data.get('deuda_ids') or []
    if not isinstance(deuda_ids, list):
        deuda_ids = []

    medio_cobro_consumo = (request.data.get('medio_cobro_consumo') or 'efectivo').strip().lower()
    if medio_cobro_consumo not in {'nequi', 'daviplata', 'efectivo', 'otros'}:
        return Response({'error': 'medio_cobro_consumo inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_raw = (request.data.get('fecha') or '').strip()
    fecha_abono_dt = None
    if fecha_raw:
        try:
            fecha_abono = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
            fecha_abono_dt = datetime.combine(fecha_abono, datetime.min.time()).replace(hour=12)
            if timezone.is_naive(fecha_abono_dt):
                fecha_abono_dt = timezone.make_aware(fecha_abono_dt, timezone.get_current_timezone())
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    consumo_aplicaciones = []
    consumo_sobrante = Decimal(0)

    try:
        with transaction.atomic():
            if consumo_monto > 0:
                consumo_aplicaciones, consumo_sobrante = _aplicar_abonos_consumo_interno(
                    estilista=estilista,
                    monto_decimal=consumo_monto,
                    medio_pago=medio_cobro_consumo,
                    usuario=request.user,
                    notas=f"Cobro consumo integrado liquidación {fecha_raw or timezone.localdate().strftime('%Y-%m-%d')}",
                    fecha_abono_dt=fecha_abono_dt,
                    deuda_objetivo=None,
                    deuda_ids=deuda_ids,
                )

            response_liq = liquidar_dia_v2(request)
            status_liq = int(getattr(response_liq, 'status_code', 500) or 500)
            if status_liq >= 400:
                data_liq = getattr(response_liq, 'data', None) or {}
                if isinstance(data_liq, dict):
                    msg = data_liq.get('error') or data_liq.get('detail') or 'No se pudo completar la liquidación.'
                else:
                    msg = 'No se pudo completar la liquidación.'
                raise ValueError(str(msg))

            payload = getattr(response_liq, 'data', {}) or {}
            payload['consumo_integrado'] = {
                'monto_solicitado': float(consumo_monto),
                'monto_aplicado': float(consumo_monto - consumo_sobrante),
                'monto_sobrante': float(consumo_sobrante),
                'medio_pago': medio_cobro_consumo,
                'aplicaciones': consumo_aplicaciones,
            }
            return Response(payload, status=status_liq)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'No se pudo completar la operación integral: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estado_pago_estilista_historial(request):
    fecha_inicio_raw = (request.query_params.get('fecha_inicio') or '').strip()
    fecha_fin_raw = (request.query_params.get('fecha_fin') or '').strip()
    estilista_id_raw = (request.query_params.get('estilista_id') or '').strip()
    limit_raw = (request.query_params.get('limit') or '100').strip()

    try:
        limit = max(1, min(int(limit_raw), 300))
    except Exception:
        limit = 100

    try:
        if fecha_inicio_raw and fecha_fin_raw:
            fecha_inicio = datetime.strptime(fecha_inicio_raw, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_raw, '%Y-%m-%d').date()
        else:
            hoy = timezone.localdate()
            fecha_inicio = hoy.replace(day=1)
            fecha_fin = hoy
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    if fecha_inicio > fecha_fin:
        return Response({'error': 'fecha_inicio no puede ser mayor que fecha_fin.'}, status=status.HTTP_400_BAD_REQUEST)

    # Limpieza puntual solicitada por negocio para eliminar dos registros incorrectos.
    # Se ejecuta con tolerancia de 1 segundo para evitar diferencias de milisegundos.
    marcas_erroneas = ['2026-03-25 00:41:27', '2026-03-25 00:11:54']
    for marca in marcas_erroneas:
        try:
            dt_local = timezone.make_aware(datetime.strptime(marca, '%Y-%m-%d %H:%M:%S'))
            dt_fin = dt_local + timedelta(seconds=1)
            try:
                EstadoPagoEstilistaHistorial.objects.filter(
                    fecha_cambio__gte=dt_local,
                    fecha_cambio__lt=dt_fin,
                ).delete()
            except (OperationalError, ProgrammingError):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM estado_pago_estilista_historial
                        WHERE fecha_cambio >= %s AND fecha_cambio < %s
                        """,
                        [dt_local, dt_fin],
                    )
        except Exception:
            continue

    try:
        qs = EstadoPagoEstilistaHistorial.objects.select_related('estilista', 'usuario').filter(
            fecha__gte=fecha_inicio,
            fecha__lte=fecha_fin,
        )
        if estilista_id_raw:
            qs = qs.filter(estilista_id=int(estilista_id_raw))

        registros = [
            {
                'id': x.id,
                'estilista_id': x.estilista_id,
                'estilista_nombre': x.estilista.nombre,
                'fecha': x.fecha.strftime('%Y-%m-%d'),
                'estado_anterior': x.estado_anterior,
                'estado_nuevo': x.estado_nuevo,
                'notas': x.notas,
                'usuario_id': x.usuario_id,
                'usuario_nombre': x.usuario.nombre_completo if x.usuario else 'Sistema',
                'monto_liquidado': float(x.monto_liquidado or 0),
                'abono_puesto': float(x.abono_puesto or 0),
                'medio_abono_puesto': getattr(x, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                'pendiente_puesto': float(x.pendiente_puesto or 0),
                'fecha_cambio': timezone.localtime(x.fecha_cambio).strftime('%Y-%m-%d %H:%M:%S'),
            }
            for x in qs[:limit]
        ]
    except (OperationalError, ProgrammingError):
        # Compatibilidad con esquema anterior sin abono_puesto/pendiente_puesto.
        try:
            registros = _listar_historial_legacy(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                estilista_id=estilista_id_raw or None,
                limit=limit,
            )
        except Exception:
            # Degradar sin romper frontend: retornar lista vacia con advertencia.
            registros = []
            return Response(
                {
                    'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'),
                    'fecha_fin': fecha_fin.strftime('%Y-%m-%d'),
                    'estilista_id': int(estilista_id_raw) if estilista_id_raw else None,
                    'items': registros,
                    'warning': 'Historial no disponible temporalmente. Verifica migraciones de backend.',
                }
            )

    return Response(
        {
            'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin.strftime('%Y-%m-%d'),
            'estilista_id': int(estilista_id_raw) if estilista_id_raw else None,
            'items': registros,
        }
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_estado_pago_historial(request, historial_id):
    # Administrador o gerente pueden eliminar para poder corregir liquidaciones mal registradas.
    if not _es_admin_o_gerente(request.user):
        return Response(
            {'error': 'Solo administrador o gerente pueden eliminar registros del historial.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        historial = EstadoPagoEstilistaHistorial.objects.filter(id=historial_id).first()
        if not historial:
            return Response({'error': 'Registro de historial no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        estilista_id = historial.estilista_id
        fecha = historial.fecha

        with transaction.atomic():
            eliminado_historial = EstadoPagoEstilistaHistorial.objects.filter(id=historial_id).delete()[0]
            eliminado_diaria = EstadoPagoEstilistaDia.objects.filter(
                estilista_id=estilista_id,
                fecha=fecha,
            ).delete()[0]

        return Response(
            {
                'success': True,
                'historial_id': historial_id,
                'estilista_id': estilista_id,
                'fecha': fecha.strftime('%Y-%m-%d') if hasattr(fecha, 'strftime') else str(fecha),
                'eliminado_historial': int(eliminado_historial),
                'eliminado_diaria': int(eliminado_diaria),
            }
        )
    except (OperationalError, ProgrammingError):
        # Compatibilidad con posibles desfaces de esquema.
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT estilista_id, fecha FROM estado_pago_estilista_historial WHERE id=%s",
                    [historial_id],
                )
                row = cursor.fetchone()
                if not row:
                    return Response({'error': 'Registro de historial no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

                estilista_id = row[0]
                fecha = row[1]

                cursor.execute("DELETE FROM estado_pago_estilista_historial WHERE id=%s", [historial_id])
                eliminado_historial = cursor.rowcount

                cursor.execute(
                    "DELETE FROM estado_pago_estilista_dia WHERE estilista_id=%s AND fecha=%s",
                    [estilista_id, fecha],
                )
                eliminado_diaria = cursor.rowcount

            return Response(
                {
                    'success': True,
                    'historial_id': historial_id,
                    'estilista_id': estilista_id,
                    'fecha': str(fecha),
                    'eliminado_historial': int(eliminado_historial),
                    'eliminado_diaria': int(eliminado_diaria),
                }
            )
        except Exception as e:
            return Response(
                {'error': f'No se pudo eliminar el registro del historial: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    except Exception as e:
        return Response(
            {'error': f'No se pudo eliminar el registro del historial: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def mover_fecha_estado_pago_dia(request, estado_id):
    if not _es_admin_o_gerente(request.user):
        return Response(
            {'error': 'Solo administrador o gerente pueden ajustar la fecha del pago de espacio.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    nueva_fecha_raw = (request.data.get('nueva_fecha') or '').strip()
    if not nueva_fecha_raw:
        return Response({'error': 'Debes enviar nueva_fecha (YYYY-MM-DD).'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        nueva_fecha = datetime.strptime(nueva_fecha_raw, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    monto_mover_raw = request.data.get('monto_mover', None)

    estado = EstadoPagoEstilistaDia.objects.select_related('estilista').filter(id=estado_id).first()
    if not estado:
        return Response({'error': 'Registro de pago diario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

    abono_origen = max(Decimal(estado.abono_puesto or 0), Decimal(0))
    if abono_origen <= 0:
        return Response({'error': 'Este registro no tiene abono de espacio para mover.'}, status=status.HTTP_400_BAD_REQUEST)

    if monto_mover_raw in (None, ''):
        monto_mover = abono_origen
    else:
        try:
            monto_mover = Decimal(str(monto_mover_raw))
        except Exception:
            return Response({'error': 'monto_mover inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto_mover <= 0:
            return Response({'error': 'monto_mover debe ser mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto_mover > abono_origen:
            return Response({'error': f'monto_mover no puede superar el abono disponible ({float(abono_origen):.2f}).'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_anterior = estado.fecha
    if fecha_anterior == nueva_fecha:
        return Response({'ok': True, 'estado_id': estado.id, 'fecha_anterior': str(fecha_anterior), 'fecha_nueva': str(nueva_fecha)})

    def _recalcular_estados_desde_fecha(estilista_obj, fecha_inicio):
        deuda_arrastre = Decimal(0)
        previo = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista_obj,
            fecha__lt=fecha_inicio,
        ).order_by('-fecha', '-actualizado_en').first()
        if previo:
            deuda_arrastre = max(
                Decimal(getattr(previo, 'saldo_puesto_pendiente', None) or getattr(previo, 'pendiente_puesto', 0) or 0),
                Decimal(0),
            )

        diarios = EstadoPagoEstilistaDia.objects.filter(
            estilista=estilista_obj,
            fecha__gte=fecha_inicio,
        ).order_by('fecha', 'id')

        for d in diarios:
            calc = calcular_liquidacion_dia_estilista(estilista_obj, d.fecha)
            ganancias = Decimal(calc.get('ganancias_totales') or 0)
            descuento = max(Decimal(calc.get('descuento_puesto') or 0), Decimal(0))
            total_pagable = max(Decimal(calc.get('total_pagable') or 0), Decimal(0))

            total_pagado = (
                Decimal(d.pago_efectivo or 0)
                + Decimal(d.pago_nequi or 0)
                + Decimal(d.pago_daviplata or 0)
                + Decimal(d.pago_otros or 0)
            )
            abono_dia = max(Decimal(d.abono_puesto or 0), Decimal(0))
            deuda_total = max(deuda_arrastre + descuento, Decimal(0))
            abono_aplicado = min(abono_dia, deuda_total)
            saldo_puesto = max(deuda_total - abono_aplicado, Decimal(0))

            pendiente_liquidacion = max(total_pagable - total_pagado, Decimal(0))
            if pendiente_liquidacion > 0:
                estado_calc = 'pendiente'
            elif saldo_puesto > 0:
                estado_calc = 'debe'
            else:
                estado_calc = 'cancelado'

            d.ganancias_totales = ganancias
            d.descuento_puesto = descuento
            d.total_pagable = total_pagable
            d.neto_dia = total_pagable
            d.saldo_puesto_pendiente = saldo_puesto
            d.pendiente_puesto = saldo_puesto
            d.estado = estado_calc
            d.save(
                update_fields=[
                    'ganancias_totales',
                    'descuento_puesto',
                    'total_pagable',
                    'neto_dia',
                    'saldo_puesto_pendiente',
                    'pendiente_puesto',
                    'estado',
                    'actualizado_en',
                ]
            )
            deuda_arrastre = saldo_puesto

    with transaction.atomic():
        destino = EstadoPagoEstilistaDia.objects.select_for_update().filter(
            estilista_id=estado.estilista_id,
            fecha=nueva_fecha,
        ).exclude(id=estado.id).first()

        if destino:
            destino.abono_puesto = Decimal(destino.abono_puesto or 0) + monto_mover
            if monto_mover > 0:
                destino.medio_abono_puesto = getattr(estado, 'medio_abono_puesto', destino.medio_abono_puesto)
            if estado.notas:
                notas_prev = (destino.notas or '').strip()
                destino.notas = f"{notas_prev} | ajuste fecha desde {fecha_anterior}: {estado.notas}" if notas_prev else f"ajuste fecha desde {fecha_anterior}: {estado.notas}"
            destino.usuario_liquida = request.user
            destino.save(
                update_fields=[
                    'abono_puesto',
                    'medio_abono_puesto',
                    'notas',
                    'usuario_liquida',
                    'actualizado_en',
                ]
            )

            estado.abono_puesto = max(abono_origen - monto_mover, Decimal(0))
            estado.usuario_liquida = request.user
            estado.save(update_fields=['abono_puesto', 'usuario_liquida', 'actualizado_en'])
            estado_result_id = destino.id
        else:
            destino = EstadoPagoEstilistaDia.objects.create(
                estilista_id=estado.estilista_id,
                fecha=nueva_fecha,
                estado='debe',
                pago_efectivo=Decimal(0),
                pago_nequi=Decimal(0),
                pago_daviplata=Decimal(0),
                pago_otros=Decimal(0),
                abono_puesto=monto_mover,
                medio_abono_puesto=getattr(estado, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                notas=f"Ajuste fecha desde {fecha_anterior}",
                usuario_liquida=request.user,
            )
            estado.abono_puesto = max(abono_origen - monto_mover, Decimal(0))
            estado.usuario_liquida = request.user
            estado.save(update_fields=['abono_puesto', 'usuario_liquida', 'actualizado_en'])
            estado_result_id = destino.id

        try:
            EstadoPagoEstilistaHistorial.objects.create(
                estilista_id=estado.estilista_id,
                fecha=nueva_fecha,
                estado_anterior='debe',
                estado_nuevo='debe',
                notas=f'Ajuste de fecha desde {fecha_anterior}',
                usuario=request.user,
                monto_liquidado=Decimal(0),
                abono_puesto=monto_mover,
                medio_abono_puesto=getattr(estado, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                pendiente_puesto=Decimal(0),
            )
        except Exception:
            pass

        fecha_recalculo = min(fecha_anterior, nueva_fecha)
        _recalcular_estados_desde_fecha(estado.estilista, fecha_recalculo)

    return Response(
        {
            'ok': True,
            'estado_id': estado_result_id,
            'estilista_id': estado.estilista_id,
            'estilista_nombre': estado.estilista.nombre if estado.estilista_id else None,
            'fecha_anterior': str(fecha_anterior),
            'fecha_nueva': str(nueva_fecha),
            'monto_movido': float(monto_mover),
        }
    )


@api_view(['GET'])
def bi_desglose_estilista_debug(request):
    """
    Endpoint PÚBLICO para debugging (sin autenticación requerida).
    Devuelve desglose completo del cálculo del BI para un estilista específico.
    
    Query params:
    - estilista_id: ID del estilista (requerido)
    - fecha_inicio: fecha inicio (YYYY-MM-DD)
    - fecha_fin: fecha fin (YYYY-MM-DD)
    
    **NOTA**: Este endpoint es solo para debugging temporal y debería desactivarse en producción.
    """
    from datetime import datetime, timedelta
    
    try:
        estilista_id = request.query_params.get('estilista_id')
        fecha_inicio_str = request.query_params.get('fecha_inicio', timezone.localdate().strftime('%Y-%m-%d'))
        fecha_fin_str = request.query_params.get('fecha_fin', timezone.localdate().strftime('%Y-%m-%d'))
        
        fecha_inicio_dt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        estilista = Estilista.objects.get(id=int(estilista_id))
    except Exception as e:
        return Response({'error': f'Parámetros inválidos: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Cargar datos
    servicios_est = ServicioRealizado.objects.select_related('estilista').filter(
        estilista=estilista,
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    adicionales_asignados_est = ServicioRealizadoAdicional.objects.select_related('servicio_realizado').filter(
        estilista=estilista,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    )
    ventas_est = VentaProducto.objects.select_related('producto', 'estilista').filter(
        estilista=estilista,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    
    # Resumen de servicios
    total_servicios_precio_cobrado = Decimal(servicios_est.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
    total_adicionales_est = Decimal(servicios_est.aggregate(total=Sum('valor_adicionales'))['total'] or 0)
    total_adicionales_asignados_est = Decimal(0)
    
    # Resumen de comisiones
    comision_ventas_producto_caja_est = Decimal(0)
    comision_por_dia = {}
    ventas_detalle = []
    for v in ventas_est:
        pct = Decimal(v.producto.comision_estilista or 0)
        valor_comision = (Decimal(v.total) * pct) / Decimal(100)
        comision_ventas_producto_caja_est += valor_comision
        fecha_v = _fecha_operativa_desde_dt(v.fecha_hora)
        comision_por_dia[fecha_v] = comision_por_dia.get(fecha_v, Decimal(0)) + valor_comision
        ventas_detalle.append({
            'fecha': fecha_v.strftime('%Y-%m-%d'),
            'producto': v.producto.nombre,
            'total_venta': float(Decimal(v.total)),
            'comision_pct': float(pct),
            'comision_valor': float(valor_comision),
        })

    # Servicios por día
    servicios_por_dia = {}
    for srv in servicios_est:
        fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
        servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + Decimal(srv.precio_cobrado or 0)
    for ad in adicionales_asignados_est:
        fecha_ad = _fecha_operativa_desde_dt(ad.servicio_realizado.fecha_hora)
        valor_ad = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct_est < 0:
            pct_est = Decimal(0)
        if pct_est > 100:
            pct_est = Decimal(100)
        valor_emp = valor_ad - ((valor_ad * pct_est) / Decimal(100))
        total_adicionales_asignados_est += valor_emp
        servicios_por_dia[fecha_ad] = servicios_por_dia.get(fecha_ad, Decimal(0)) + valor_emp

    ganancia_servicios_est = total_servicios_precio_cobrado + total_adicionales_asignados_est

    # Días trabajados
    dias_trabajados = set(servicios_por_dia.keys()) | set(comision_por_dia.keys())
    
    # Cargar estados
    try:
        estados_pago_map = {
            (ep.estilista_id, ep.fecha): ep.estado
            for ep in EstadoPagoEstilistaDia.objects.filter(
                estilista=estilista,
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            )
        }
    except (OperationalError, ProgrammingError):
        estados_pago_map = {}
    
    # Cálculo por día
    dias_desglose = []
    pago_neto_pendiente = Decimal(0)
    pago_neto_cancelado = Decimal(0)
    pago_neto_periodo = Decimal(0)
    dias_cancelados = 0
    
    for dia in sorted(dias_trabajados):
        base_servicio_dia = servicios_por_dia.get(dia, Decimal(0))
        comision_dia = comision_por_dia.get(dia, Decimal(0))
        
        descuento_dia = _descuento_puesto_dia(estilista, base_servicio_dia)
        
        neto_dia = max((base_servicio_dia + comision_dia) - descuento_dia, Decimal(0))
        estado_dia = estados_pago_map.get((estilista.id, dia), 'pendiente')
        
        pago_neto_periodo += neto_dia
        liquidado_empleado = estado_dia in {'cancelado', 'debe'}
        dias_desglose.append({
            'fecha': dia.strftime('%Y-%m-%d'),
            'base_servicio': float(base_servicio_dia),
            'descuento_espacio': float(descuento_dia),
            'comision_productos': float(comision_dia),
            'neto_dia': float(neto_dia),
            'estado': estado_dia,
            'incluido_en': 'cancelado' if liquidado_empleado else 'pendiente',
        })
        
        if liquidado_empleado:
            pago_neto_cancelado += neto_dia
            dias_cancelados += 1
        else:
            pago_neto_pendiente += neto_dia
    
    return Response({
        'estilista': {
            'id': estilista.id,
            'nombre': estilista.nombre,
            'tipo_cobro_espacio': estilista.tipo_cobro_espacio,
            'valor_cobro_espacio': float(estilista.valor_cobro_espacio or 0),
        },
        'periodo': {
            'fecha_inicio': fecha_inicio_dt.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin_dt.strftime('%Y-%m-%d'),
        },
        'servicios': {
            'total_precio_cobrado': float(total_servicios_precio_cobrado),
            'total_adicionales': float(total_adicionales_est),
            'total_adicionales_asignados': float(total_adicionales_asignados_est),
            'ganancia_servicios': float(ganancia_servicios_est),
        },
        'comisiones': {
            'total_comision': float(comision_ventas_producto_caja_est),
            'detalle_ventas': ventas_detalle,
        },
        'dias_trabajados': sorted([d.strftime('%Y-%m-%d') for d in dias_trabajados]),
        'desglose_por_dia': dias_desglose,
        'resumen': {
            'pago_neto_pendiente': float(pago_neto_pendiente),
            'pago_neto_cancelado': float(pago_neto_cancelado),
            'pago_neto_periodo': float(pago_neto_periodo),
            'generado_total_empleado': float(pago_neto_periodo),
            'pendiente_pago_empleado': float(pago_neto_pendiente),
            'dias_cancelados': dias_cancelados,
            'dias_pendientes': len(dias_trabajados) - dias_cancelados,
            'total_dias': len(dias_trabajados),
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_desglose_estilista(request):
    """
    Endpoint para debugging: Devuelve desglose completo del cálculo del BI para un estilista específico.
    
    Query params:
    - estilista_id: ID del estilista
    - fecha_inicio: fecha inicio (YYYY-MM-DD)
    - fecha_fin: fecha fin (YYYY-MM-DD)
    """
    from datetime import datetime, timedelta
    
    try:
        estilista_id = request.query_params.get('estilista_id')
        fecha_inicio_str = request.query_params.get('fecha_inicio', timezone.localdate().strftime('%Y-%m-%d'))
        fecha_fin_str = request.query_params.get('fecha_fin', timezone.localdate().strftime('%Y-%m-%d'))
        
        fecha_inicio_dt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        estilista = Estilista.objects.get(id=int(estilista_id))
    except Exception as e:
        return Response({'error': f'Parámetros inválidos: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Cargar datos
    servicios_est = ServicioRealizado.objects.select_related('estilista').filter(
        estilista=estilista,
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    adicionales_asignados_est = ServicioRealizadoAdicional.objects.select_related('servicio_realizado').filter(
        estilista=estilista,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    )
    ventas_est = VentaProducto.objects.select_related('producto', 'estilista').filter(
        estilista=estilista,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    
    # Resumen de servicios
    total_servicios_precio_cobrado = Decimal(servicios_est.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
    total_adicionales_est = Decimal(servicios_est.aggregate(total=Sum('valor_adicionales'))['total'] or 0)
    total_adicionales_asignados_est = Decimal(0)
    
    # Resumen de comisiones
    comision_ventas_producto_caja_est = Decimal(0)
    comision_por_dia = {}
    ventas_detalle = []
    for v in ventas_est:
        pct = Decimal(v.producto.comision_estilista or 0)
        valor_comision = (Decimal(v.total) * pct) / Decimal(100)
        comision_ventas_producto_caja_est += valor_comision
        fecha_v = _fecha_operativa_desde_dt(v.fecha_hora)
        comision_por_dia[fecha_v] = comision_por_dia.get(fecha_v, Decimal(0)) + valor_comision
        ventas_detalle.append({
            'fecha': fecha_v.strftime('%Y-%m-%d'),
            'producto': v.producto.nombre,
            'total_venta': float(Decimal(v.total)),
            'comision_pct': float(pct),
            'comision_valor': float(valor_comision),
        })

    # Servicios por día
    servicios_por_dia = {}
    for srv in servicios_est:
        fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
        servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + Decimal(srv.precio_cobrado or 0)
    for ad in adicionales_asignados_est:
        fecha_ad = _fecha_operativa_desde_dt(ad.servicio_realizado.fecha_hora)
        valor_ad = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct_est < 0:
            pct_est = Decimal(0)
        if pct_est > 100:
            pct_est = Decimal(100)
        valor_emp = valor_ad - ((valor_ad * pct_est) / Decimal(100))
        total_adicionales_asignados_est += valor_emp
        servicios_por_dia[fecha_ad] = servicios_por_dia.get(fecha_ad, Decimal(0)) + valor_emp

    ganancia_servicios_est = total_servicios_precio_cobrado + total_adicionales_asignados_est

    # Días trabajados
    dias_trabajados = set(servicios_por_dia.keys()) | set(comision_por_dia.keys())
    
    # Cargar estados
    try:
        estados_pago_map = {
            (ep.estilista_id, ep.fecha): ep.estado
            for ep in EstadoPagoEstilistaDia.objects.filter(
                estilista=estilista,
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            )
        }
    except (OperationalError, ProgrammingError):
        estados_pago_map = {}
    
    # Cálculo por día
    dias_desglose = []
    pago_neto_pendiente = Decimal(0)
    pago_neto_cancelado = Decimal(0)
    pago_neto_periodo = Decimal(0)
    dias_cancelados = 0
    
    for dia in sorted(dias_trabajados):
        base_servicio_dia = servicios_por_dia.get(dia, Decimal(0))
        comision_dia = comision_por_dia.get(dia, Decimal(0))
        
        descuento_dia = _descuento_puesto_dia(estilista, base_servicio_dia)
        
        neto_dia = max((base_servicio_dia + comision_dia) - descuento_dia, Decimal(0))
        estado_dia = estados_pago_map.get((estilista.id, dia), 'pendiente')
        
        pago_neto_periodo += neto_dia
        liquidado_empleado = estado_dia in {'cancelado', 'debe'}
        dias_desglose.append({
            'fecha': dia.strftime('%Y-%m-%d'),
            'base_servicio': float(base_servicio_dia),
            'descuento_espacio': float(descuento_dia),
            'comision_productos': float(comision_dia),
            'neto_dia': float(neto_dia),
            'estado': estado_dia,
            'incluido_en': 'cancelado' if liquidado_empleado else 'pendiente',
        })
        
        if liquidado_empleado:
            pago_neto_cancelado += neto_dia
            dias_cancelados += 1
        else:
            pago_neto_pendiente += neto_dia
    
    return Response({
        'estilista': {
            'id': estilista.id,
            'nombre': estilista.nombre,
            'tipo_cobro_espacio': estilista.tipo_cobro_espacio,
            'valor_cobro_espacio': float(estilista.valor_cobro_espacio or 0),
        },
        'periodo': {
            'fecha_inicio': fecha_inicio_dt.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin_dt.strftime('%Y-%m-%d'),
        },
        'servicios': {
            'total_precio_cobrado': float(total_servicios_precio_cobrado),
            'total_adicionales': float(total_adicionales_est),
            'total_adicionales_asignados': float(total_adicionales_asignados_est),
            'ganancia_servicios': float(ganancia_servicios_est),
        },
        'comisiones': {
            'total_comision': float(comision_ventas_producto_caja_est),
            'detalle_ventas': ventas_detalle,
        },
        'dias_trabajados': sorted([d.strftime('%Y-%m-%d') for d in dias_trabajados]),
        'desglose_por_dia': dias_desglose,
        'resumen': {
            'pago_neto_pendiente': float(pago_neto_pendiente),
            'pago_neto_cancelado': float(pago_neto_cancelado),
            'pago_neto_periodo': float(pago_neto_periodo),
            'dias_cancelados': dias_cancelados,
            'dias_pendientes': len(dias_trabajados) - dias_cancelados,
            'total_dias': len(dias_trabajados),
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_ajuste_diario_unificado(request):
    """Tabla unificada por día y empleado para ajustes operativos en una sola vista."""
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene acceso al módulo unificado de ajustes.')

    fecha_inicio, fecha_fin = _resolver_rango_fechas(request)
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    if fecha_inicio_dt > fecha_fin_dt:
        return Response({'error': 'fecha_inicio no puede ser mayor que fecha_fin.'}, status=status.HTTP_400_BAD_REQUEST)

    estilistas = list(Estilista.objects.filter(activo=True).order_by('nombre'))
    estilista_ids = [int(e.id) for e in estilistas]

    estados_map = {}
    try:
        estados_qs = EstadoPagoEstilistaDia.objects.filter(
            estilista_id__in=estilista_ids,
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
        )
        for ep in estados_qs:
            estados_map[(int(ep.estilista_id), ep.fecha)] = ep
    except (OperationalError, ProgrammingError):
        estados_map = {}

    usar_fact = _usar_fact_liquidacion_en_reportes()
    facts_map = {}
    if usar_fact:
        try:
            facts_qs = FactLiquidacionEstilistaDia.objects.filter(
                estilista_id__in=estilista_ids,
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
                vigente=True,
            )
            for fact in facts_qs:
                facts_map[(int(fact.estilista_id), fact.fecha)] = fact
        except Exception:
            facts_map = {}

    consumo_por_est_dia = defaultdict(Decimal)
    try:
        abonos_qs = AbonoDeudaEmpleado.objects.select_related('deuda').filter(
            deuda__estilista_id__in=estilista_ids,
        )
        for ab in abonos_qs:
            fecha_op = _fecha_operativa_desde_dt(ab.fecha_hora)
            if not fecha_op or fecha_op < fecha_inicio_dt or fecha_op > fecha_fin_dt:
                continue
            est_id = int(getattr(getattr(ab, 'deuda', None), 'estilista_id', 0) or 0)
            if not est_id:
                continue
            consumo_por_est_dia[(est_id, fecha_op)] += Decimal(ab.monto or 0)
    except Exception:
        consumo_por_est_dia = defaultdict(Decimal)

    dias_con_movimiento = defaultdict(set)

    servicios_mov_qs = ServicioRealizado.objects.filter(
        estado='finalizado',
        estilista_id__in=estilista_ids,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    ).values_list('estilista_id', 'fecha_hora')
    for est_id, dt in servicios_mov_qs:
        f = _fecha_operativa_desde_dt(dt)
        if f:
            dias_con_movimiento[int(est_id)].add(f)

    adic_mov_qs = ServicioRealizadoAdicional.objects.filter(
        estilista_id__in=estilista_ids,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    ).values_list('estilista_id', 'servicio_realizado__fecha_hora')
    for est_id, dt in adic_mov_qs:
        f = _fecha_operativa_desde_dt(dt)
        if f:
            dias_con_movimiento[int(est_id)].add(f)

    ventas_mov_qs = VentaProducto.objects.filter(
        tipo_operacion='venta',
        estilista_id__in=estilista_ids,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    ).values_list('estilista_id', 'fecha_hora')
    for est_id, dt in ventas_mov_qs:
        f = _fecha_operativa_desde_dt(dt)
        if f:
            dias_con_movimiento[int(est_id)].add(f)

    for (est_id, fecha_dia), ep in estados_map.items():
        dias_con_movimiento[int(est_id)].add(fecha_dia)

    for (est_id, fecha_dia), _monto in consumo_por_est_dia.items():
        dias_con_movimiento[int(est_id)].add(fecha_dia)

    items = []
    for est in estilistas:
        est_id = int(est.id)
        for dia in sorted(list(dias_con_movimiento.get(est_id, set())), reverse=True):
            calc = calcular_liquidacion_dia_estilista(est, dia)
            ep = estados_map.get((est_id, dia))
            fact = facts_map.get((est_id, dia)) if usar_fact else None

            pago_efectivo = Decimal((fact.pago_efectivo if fact else (ep.pago_efectivo if ep else 0)) or 0)
            pago_nequi = Decimal((fact.pago_nequi if fact else (ep.pago_nequi if ep else 0)) or 0)
            pago_daviplata = Decimal((fact.pago_daviplata if fact else (ep.pago_daviplata if ep else 0)) or 0)
            pago_otros = Decimal((fact.pago_otros if fact else (ep.pago_otros if ep else 0)) or 0)
            abono_puesto = Decimal((fact.abono_puesto_dia if fact else (ep.abono_puesto if ep else 0)) or 0)
            medio_abono = (getattr(fact, 'medio_abono_puesto', None) or (getattr(ep, 'medio_abono_puesto', None) if ep else None) or 'efectivo')
            pagado_total = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
            generado = Decimal((
                max(Decimal(fact.ganancias_totales or 0) - Decimal(fact.descuento_puesto_dia or 0), Decimal(0))
                if fact else calc.get('total_pagable')
            ) or 0)
            descuento_puesto = Decimal((fact.descuento_puesto_dia if fact else calc.get('descuento_puesto')) or 0)
            deuda_puesto = Decimal((fact.deuda_puesto_cierre if fact else (getattr(ep, 'saldo_puesto_pendiente', 0) if ep else 0)) or 0)
            estado_item = (fact.estado_liquidacion if fact else (ep.estado if ep else 'pendiente'))
            cobro_consumo = Decimal((fact.cobro_consumo_dia if fact else consumo_por_est_dia.get((est_id, dia), Decimal(0))) or 0)

            items.append(
                {
                    'estilista_id': est_id,
                    'estilista_nombre': est.nombre,
                    'fecha': dia.strftime('%Y-%m-%d'),
                    'estado': estado_item,
                    'generado_total': float(generado),
                    'descuento_puesto': float(descuento_puesto),
                    'pago_efectivo': float(pago_efectivo),
                    'pago_nequi': float(pago_nequi),
                    'pago_daviplata': float(pago_daviplata),
                    'pago_otros': float(pago_otros),
                    'pagado_total': float(pagado_total),
                    'pendiente_pago_empleado': float(max(generado - pagado_total, Decimal(0))),
                    'abono_puesto': float(abono_puesto),
                    'medio_abono_puesto': medio_abono,
                    'cobro_consumo_dia': float(cobro_consumo),
                    'deuda_puesto_pendiente': float(deuda_puesto),
                }
            )

    items.sort(key=lambda x: (x.get('fecha') or '', x.get('estilista_nombre') or ''), reverse=True)
    return Response(
        {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'items': items,
            'total_filas': len(items),
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_resumen(request):
    """Vista API que retorna datos de BI como JSON"""
    data = _calcular_datos_bi(request)
    if _es_recepcion(request.user):
        data = _sanitizar_bi_para_recepcion(data)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_cierre_caja(request):
    """Resumen y detalle operativo de cierre de caja para el rango seleccionado."""
    fecha_inicio, fecha_fin = _resolver_rango_fechas(request)
    medio_pago = (request.query_params.get('medio_pago') or '').strip().lower()

    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        fecha_fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha invalido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    data_bi = _calcular_datos_bi(request)
    kpis = data_bi.get('kpis', {})

    ventas_qs = VentaProducto.objects.select_related('producto', 'estilista').filter(
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    ventas_pagadas_qs = ventas_qs.exclude(tipo_operacion='consumo_empleado')
    ventas_consumo_qs = ventas_qs.filter(tipo_operacion='consumo_empleado')

    servicios_qs = ServicioRealizado.objects.select_related(
        'servicio',
        'estilista',
        'cliente',
        'adicional_otro_producto',
        'adicional_otro_estilista',
    ).filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )

    adicionales_qs = ServicioRealizadoAdicional.objects.select_related(
        'servicio_realizado',
        'servicio_realizado__servicio',
        'estilista',
    ).filter(
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    )

    if medio_pago and medio_pago != 'todos':
        ventas_qs = ventas_qs.filter(medio_pago=medio_pago)
        ventas_pagadas_qs = ventas_pagadas_qs.filter(medio_pago=medio_pago)
        ventas_consumo_qs = ventas_consumo_qs.filter(medio_pago=medio_pago)
        servicios_qs = servicios_qs.filter(medio_pago=medio_pago)
        adicionales_qs = adicionales_qs.filter(servicio_realizado__medio_pago=medio_pago)

    abonos_consumo_qs = AbonoDeudaEmpleado.objects.select_related('deuda', 'deuda__estilista')
    if medio_pago and medio_pago != 'todos':
        abonos_consumo_qs = abonos_consumo_qs.filter(medio_pago=medio_pago)

    abonos_consumo_lista = []
    for ab in abonos_consumo_qs:
        fecha_operativa_ab = _fecha_operativa_desde_dt(ab.fecha_hora)
        if not fecha_operativa_ab:
            continue
        if fecha_inicio_dt <= fecha_operativa_ab <= fecha_fin_dt:
            abonos_consumo_lista.append(ab)

    abonos_por_deuda = {}
    for ab in abonos_consumo_lista:
        did = int(ab.deuda_id)
        abonos_por_deuda[did] = abonos_por_deuda.get(did, Decimal(0)) + Decimal(ab.monto or 0)

    # Detalle de productos vendidos en operacion diaria:
    # 1) venta directa de producto
    # 2) producto adicional dentro de servicio
    detalle_productos = []
    ventas_productos_total = Decimal(0)
    costo_productos_total = Decimal(0)
    comision_productos_total = Decimal(0)
    ventas_productos_directos_total = Decimal(0)
    consumo_empleado_abonado_total = Decimal(0)

    for venta in ventas_pagadas_qs.order_by('-fecha_hora'):
        valor_venta = Decimal(venta.total or 0)
        costo_unitario = Decimal(venta.producto.precio_compra or 0)
        valor_compra = costo_unitario * Decimal(venta.cantidad or 0)
        comision_empleado = Decimal(0)
        if venta.estilista_id:
            pct = Decimal(venta.producto.comision_estilista or 0)
            if pct < 0:
                pct = Decimal(0)
            if pct > 100:
                pct = Decimal(100)
            comision_empleado = (valor_venta * pct) / Decimal(100)

        ganancia = valor_venta - valor_compra - comision_empleado

        ventas_productos_total += valor_venta
        costo_productos_total += valor_compra
        comision_productos_total += comision_empleado
        ventas_productos_directos_total += valor_venta

        detalle_productos.append(
            {
                'fecha_hora': timezone.localtime(venta.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if venta.fecha_hora else None,
                'fecha': _fecha_operativa_desde_dt(venta.fecha_hora).strftime('%Y-%m-%d') if venta.fecha_hora else None,
                'origen': 'venta_producto',
                'numero_factura': venta.numero_factura,
                'medio_pago': venta.medio_pago,
                'estilista_nombre': venta.estilista.nombre if venta.estilista_id else '',
                'descripcion': venta.producto.nombre,
                'cantidad': int(venta.cantidad or 0),
                'valor_venta': float(valor_venta),
                'valor_compra': float(valor_compra),
                'con_comision_empleado': bool(comision_empleado > 0),
                'comision_empleado': float(comision_empleado),
                'ganancia_neta': float(ganancia),
            }
        )

    # Consumo empleado: en cierre de caja se reconoce por fecha de ABONO,
    # no por fecha de creación de la factura de consumo.
    for ab in sorted(abonos_consumo_lista, key=lambda x: (x.fecha_hora or datetime.min, x.id or 0), reverse=True):
        try:
            deuda = getattr(ab, 'deuda', None)
            if not deuda:
                continue

            valor_venta = Decimal(ab.monto or 0)
            if valor_venta <= 0:
                continue

            total_credito_deuda = Decimal(deuda.total_cargo or 0)
            costo_total_deuda = Decimal(0)
            items_consumo = list(
                deuda.ventas_items.select_related('producto').filter(tipo_operacion='consumo_empleado')
            )
            productos_consumo = []
            for item in items_consumo:
                costo_total_deuda += Decimal(item.producto.precio_compra or 0) * Decimal(item.cantidad or 0)
                nombre_prod = (item.producto.nombre or '').strip() if item.producto_id else ''
                if not nombre_prod:
                    continue
                qty = int(item.cantidad or 0)
                productos_consumo.append(f"{nombre_prod} x{qty}" if qty > 1 else nombre_prod)

            descripcion_abono = (
                f"Abono consumo empleado - {', '.join(productos_consumo)}"
                if productos_consumo
                else f"Abono consumo empleado ({deuda.numero_factura or deuda.id})"
            )

            factor_pago = (valor_venta / total_credito_deuda) if total_credito_deuda > 0 else Decimal(0)
            if factor_pago < 0:
                factor_pago = Decimal(0)
            if factor_pago > 1:
                factor_pago = Decimal(1)

            valor_compra = costo_total_deuda * factor_pago
            ganancia = valor_venta - valor_compra

            ventas_productos_total += valor_venta
            costo_productos_total += valor_compra
            consumo_empleado_abonado_total += valor_venta

            detalle_productos.append(
                {
                    'abono_id': int(ab.id),
                    'fecha_hora': timezone.localtime(ab.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if ab.fecha_hora else None,
                    'fecha': _fecha_operativa_desde_dt(ab.fecha_hora).strftime('%Y-%m-%d') if ab.fecha_hora else None,
                    'origen': 'consumo_empleado_abono',
                    'numero_factura': deuda.numero_factura,
                    'medio_pago': ab.medio_pago,
                    'estilista_nombre': deuda.estilista.nombre if deuda.estilista_id else '',
                    'descripcion': descripcion_abono,
                    'cantidad': 1,
                    'valor_venta': float(valor_venta),
                    'valor_compra': float(valor_compra),
                    'con_comision_empleado': False,
                    'comision_empleado': 0.0,
                    'ganancia_neta': float(ganancia),
                }
            )
        except Exception:
            # Evita error 500 por una deuda/abono inconsistente.
            continue

    for srv in servicios_qs.order_by('-fecha_hora'):
        if not srv.adicional_otro_producto_id:
            continue

        qty = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        precio_compra = Decimal(srv.adicional_otro_producto.precio_compra or 0)
        valor_venta = precio_venta * qty
        valor_compra = precio_compra * qty
        comision_empleado = Decimal(0)
        if srv.adicional_otro_estilista_id:
            pct = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
            if pct < 0:
                pct = Decimal(0)
            if pct > 100:
                pct = Decimal(100)
            comision_empleado = (valor_venta * pct) / Decimal(100)

        ganancia = valor_venta - valor_compra - comision_empleado

        ventas_productos_total += valor_venta
        costo_productos_total += valor_compra
        comision_productos_total += comision_empleado

        detalle_productos.append(
            {
                'fecha_hora': timezone.localtime(srv.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if srv.fecha_hora else None,
                'fecha': _fecha_operativa_desde_dt(srv.fecha_hora).strftime('%Y-%m-%d') if srv.fecha_hora else None,
                'origen': 'adicional_producto_servicio',
                'numero_factura': srv.numero_factura,
                'medio_pago': srv.medio_pago,
                'estilista_nombre': srv.adicional_otro_estilista.nombre if srv.adicional_otro_estilista_id else (srv.estilista.nombre if srv.estilista_id else ''),
                'descripcion': f"{srv.adicional_otro_producto.nombre} (servicio: {srv.servicio.nombre if srv.servicio_id else '-'})",
                'cantidad': int(qty),
                'valor_venta': float(valor_venta),
                'valor_compra': float(valor_compra),
                'con_comision_empleado': bool(comision_empleado > 0),
                'comision_empleado': float(comision_empleado),
                'ganancia_neta': float(ganancia),
            }
        )

    detalle_productos.sort(key=lambda x: x.get('fecha_hora') or '', reverse=True)

    # Detalle de ingresos por espacio (abonos realizados por empleados al espacio).
    detalle_espacio = []
    ingresos_espacios = Decimal(0)
    try:
        estado_pago_qs = EstadoPagoEstilistaDia.objects.select_related('estilista').filter(
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
        ).order_by('-fecha', 'estilista__nombre')

        for ep in estado_pago_qs:
            # El ingreso por espacio es el abono_puesto (lo que el empleado pagó al espacio)
            valor_recibido = Decimal(ep.abono_puesto or 0)

            if valor_recibido <= 0:
                continue

            ingresos_espacios += valor_recibido
            detalle_espacio.append(
                {
                    'estado_pago_id': ep.id,
                    'fecha': ep.fecha.strftime('%Y-%m-%d'),
                    'estilista_id': ep.estilista_id,
                    'estilista_nombre': ep.estilista.nombre if ep.estilista_id else '',
                    'medio_pago': getattr(ep, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                    'valor_pagado': float(valor_recibido),
                }
            )
    except (OperationalError, ProgrammingError):
        detalle_espacio = []
        ingresos_espacios = Decimal(0)

    # Fallback: si la tabla diaria no trae abonos, intentar reconstruir desde historial
    # (último registro por estilista/fecha para evitar doble conteo por múltiples cambios).
    if ingresos_espacios <= 0 and len(detalle_espacio) == 0:
        try:
            historial_qs = EstadoPagoEstilistaHistorial.objects.select_related('estilista').filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            ).order_by('estilista_id', 'fecha', '-fecha_cambio')

            vistos_hist = set()
            for h in historial_qs:
                key = (int(h.estilista_id or 0), h.fecha)
                if key in vistos_hist:
                    continue
                vistos_hist.add(key)

                valor_recibido = Decimal(getattr(h, 'abono_puesto', 0) or 0)
                if valor_recibido <= 0:
                    continue

                ingresos_espacios += valor_recibido
                detalle_espacio.append(
                    {
                        'fecha': h.fecha.strftime('%Y-%m-%d') if h.fecha else None,
                        'estilista_id': h.estilista_id,
                        'estilista_nombre': h.estilista.nombre if h.estilista_id else '',
                        'medio_pago': getattr(h, 'medio_abono_puesto', 'efectivo') or 'efectivo',
                        'valor_pagado': float(valor_recibido),
                    }
                )

            detalle_espacio.sort(key=lambda x: (x.get('fecha') or '', x.get('estilista_nombre') or ''), reverse=True)
        except Exception:
            pass

    # Detalle de servicios que dejan ganancia al establecimiento.
    adicionales_por_servicio = {}
    adicionales_nombres_por_servicio = {}
    for ad in adicionales_qs:
        sid = int(ad.servicio_realizado_id)
        valor = Decimal(ad.valor_cobrado or 0)
        pct = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        if pct < 0:
            pct = Decimal(0)
        if pct > 100:
            pct = Decimal(100)

        valor_est = (valor * pct) / Decimal(100)

        if sid not in adicionales_por_servicio:
            adicionales_por_servicio[sid] = {
                'bruto': Decimal(0),
                'establecimiento': Decimal(0),
                'cantidad': 0,
            }
            adicionales_nombres_por_servicio[sid] = []

        adicionales_por_servicio[sid]['bruto'] += valor
        adicionales_por_servicio[sid]['establecimiento'] += valor_est
        adicionales_por_servicio[sid]['cantidad'] += 1
        
        nombres_adicionales = []
        if ad.servicio_id:
            nombres_adicionales.append(ad.servicio.nombre)
        if nombres_adicionales:
            nombre = ' + '.join(nombres_adicionales)
            if nombre not in adicionales_nombres_por_servicio[sid]:
                adicionales_nombres_por_servicio[sid].append(nombre)

    detalle_servicios_establecimiento = []
    ingresos_servicios_establecimiento = Decimal(0)

    for srv in servicios_qs.order_by('-fecha_hora'):
        sid = int(srv.id)
        ad_info = adicionales_por_servicio.get(sid, {'bruto': Decimal(0), 'establecimiento': Decimal(0), 'cantidad': 0})
        ad_nombres = list(adicionales_nombres_por_servicio.get(sid, []))

        valor_producto_adicional = Decimal(0)
        if srv.adicional_otro_producto_id:
            valor_producto_adicional = Decimal(srv.adicional_otro_producto.precio_venta or 0) * Decimal(srv.adicional_otro_cantidad or 1)

        valor_adicionales_total = Decimal(srv.valor_adicionales or 0)
        valor_adicionales_desglosados = Decimal(ad_info.get('bruto', 0) or 0)
        remanente_adicional_no_producto = valor_adicionales_total - valor_adicionales_desglosados - valor_producto_adicional
        if remanente_adicional_no_producto < 0:
            remanente_adicional_no_producto = Decimal(0)

        # Fallback para registros legacy: shampoo/guantes pueden venir solo en flags
        # y no en la tabla de adicionales asignados.
        if remanente_adicional_no_producto > 0 and getattr(srv, 'adicional_shampoo', False):
            ad_nombres.append('Shampoo')
        if remanente_adicional_no_producto > 0 and getattr(srv, 'adicional_guantes', False):
            ad_nombres.append('Guantes')

        adicionales_servicio_no_producto = Decimal(srv.valor_adicionales or 0) - valor_producto_adicional
        if adicionales_servicio_no_producto < 0:
            adicionales_servicio_no_producto = Decimal(0)

        valor_servicio = Decimal(srv.precio_cobrado or 0) + adicionales_servicio_no_producto
        # En este detalle solo se reporta ganancia de servicios (sin productos).
        ganancia_est = (
            _monto_establecimiento_resuelto(srv)
            + Decimal(ad_info['establecimiento'] or 0)
            + remanente_adicional_no_producto
        )

        if ganancia_est <= 0:
            continue

        ingresos_servicios_establecimiento += ganancia_est
        
        # Construir nombre del servicio
        tipo_servicio = srv.servicio.nombre if srv.servicio_id else '-'
        if ad_nombres:
            tipo_servicio = f"{tipo_servicio} + {', '.join(ad_nombres)}"
        
        detalle_servicios_establecimiento.append(
            {
                'fecha_hora': timezone.localtime(srv.fecha_hora).strftime('%Y-%m-%d %H:%M:%S') if srv.fecha_hora else None,
                'fecha': _fecha_operativa_desde_dt(srv.fecha_hora).strftime('%Y-%m-%d') if srv.fecha_hora else None,
                'numero_factura': srv.numero_factura,
                'tipo_servicio': tipo_servicio,
                'medio_pago': srv.medio_pago,
                'estilista_nombre': srv.estilista.nombre if srv.estilista_id else '',
                'valor_servicio': float(valor_servicio),
                'ganancia_establecimiento': float(ganancia_est),
            }
        )

    # Tarjetas de cierre de caja según reglas de negocio solicitadas:
    # Ingresos Totales = servicios base + servicios adicionales + productos + consumo empleado.
    servicios_base_total = Decimal(servicios_qs.aggregate(total=Sum('precio_cobrado'))['total'] or 0)
    servicios_adicionales_total = Decimal(servicios_qs.aggregate(total=Sum('valor_adicionales'))['total'] or 0)
    total_ingresos = (
        servicios_base_total
        + servicios_adicionales_total
        + ventas_productos_directos_total
        + consumo_empleado_abonado_total
    )

    # Ganancia Total = servicios establecimiento + productos + espacios.
    medios_totales = data_bi.get('cierre_medios', {}).get('totales', {})
    liquidacion_empleados = Decimal(str(medios_totales.get('salidas', 0) or 0))

    # Mantener coherencia semántica: esta tarjeta debe ser la misma ganancia
    # que se muestra en el detalle de servicios del establecimiento.
    ingresos_servicios_tarjeta = ingresos_servicios_establecimiento
    ingresos_productos_tarjeta = ventas_productos_total - comision_productos_total
    if ingresos_productos_tarjeta < 0:
        ingresos_productos_tarjeta = Decimal(0)
    ingresos_espacios_tarjeta = ingresos_espacios

    suma_componentes = ingresos_servicios_tarjeta + ingresos_productos_tarjeta + ingresos_espacios_tarjeta
    ganancia_total = suma_componentes

    return Response(
        {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'medio_pago': medio_pago or 'todos',
            'resumen': {
                'total_ingresos': float(total_ingresos),
                'liquidacion_empleados': float(liquidacion_empleados),
                'ganancia_total': float(ganancia_total),
                'ingresos_servicios_establecimiento': float(ingresos_servicios_tarjeta),
                'ingresos_productos_utilidad': float(ingresos_productos_tarjeta),
                'ingresos_espacios': float(ingresos_espacios_tarjeta),
                'suma_componentes_ganancia': float(suma_componentes),
                'diferencia_cuadre': float(ganancia_total - suma_componentes),
            },
            'medios': {
                'detalle': data_bi.get('cierre_medios', {}).get('detalle', []),
                'totales': data_bi.get('cierre_medios', {}).get('totales', {}),
            },
            'productos': {
                'ingresos_venta': float(ventas_productos_total),
                'ingresos_venta_neto_comision': float(max(ventas_productos_total - comision_productos_total, Decimal(0))),
                'total_abonos_consumo_dia': float(consumo_empleado_abonado_total),
                'valor_compra': float(costo_productos_total),
                'comision_empleado_total': float(comision_productos_total),
                'ganancia_neta': float(ventas_productos_total - costo_productos_total - comision_productos_total),
                'detalle': detalle_productos,
            },
            'espacios': {
                'total_recibido': float(ingresos_espacios),
                'detalle': detalle_espacio,
            },
            'servicios_establecimiento': {
                'total_ganancia': float(ingresos_servicios_establecimiento),
                'detalle': detalle_servicios_establecimiento,
            },
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_export_csv(request):
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene permiso para exportar BI completo.')

    try:
        data = _calcular_datos_bi(request)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="reporte_bi_{data["fecha_inicio"]}_{data["fecha_fin"]}.csv"'

        writer = csv.writer(response)
        kpis = data.get('kpis', {})
        venta_neta_total = Decimal(str(kpis.get('venta_neta_total', 0) or 0))
        ganancia_establecimiento_total = Decimal(str(kpis.get('ganancia_establecimiento_total', 0) or 0))
        pago_total_estilistas = Decimal(str(kpis.get('pago_total_estilistas', 0) or 0))
        margen_establecimiento_pct = float((ganancia_establecimiento_total / venta_neta_total) * 100) if venta_neta_total > 0 else 0.0
        participacion_estilistas_pct = float((pago_total_estilistas / venta_neta_total) * 100) if venta_neta_total > 0 else 0.0

        # Encabezado
        writer.writerow(['INFORME GERENCIAL - REPORTE BI'])
        writer.writerow(['Período', f"{data['fecha_inicio']} a {data['fecha_fin']}"])
        writer.writerow(['Generado', timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])

        # Resumen Ejecutivo
        writer.writerow(['=== RESUMEN EJECUTIVO ==='])
        writer.writerow(['Venta Neta Total', f"${float(venta_neta_total):,.2f}"])
        writer.writerow(['Ganancia Establecimiento', f"${float(ganancia_establecimiento_total):,.2f}"])
        writer.writerow(['Margen Establecimiento (%)', f"{margen_establecimiento_pct:.2f}%"])
        writer.writerow(['Pago Total Estilistas', f"${float(pago_total_estilistas):,.2f}"])
        writer.writerow(['Participación Estilistas (%)', f"{participacion_estilistas_pct:.2f}%"])
        writer.writerow(['Ingresos por Servicios Adicionales', f"${float(kpis.get('ingresos_servicios_adicionales', 0)):,.2f}"])
        writer.writerow([])

        # KPIs Clave
        writer.writerow(['=== KPIs CLAVE ==='])
        writer.writerow(['Concepto', 'Valor'])
        for k, v in kpis.items():
            writer.writerow([k, f"${float(v):,.2f}" if isinstance(v, (int, float, Decimal)) else v])
        writer.writerow([])

        # Liquidación por Estilista
        writer.writerow(['=== LIQUIDACION POR ESTILISTA ==='])
        writer.writerow([
            'Estilista',
            'Facturación Servicios',
            'Servicios Adicionales',
            'Base para Pagar',
            'Comisión Producto',
            'Cobro Espacio',
            'Neto a Pagar'
        ])
        for est in data.get('estilistas', []):
            writer.writerow([
                est.get('estilista_nombre', '-'),
                f"${float(est.get('facturacion_servicios', 0)):,.2f}",
                f"${float(est.get('valor_servicios_adicionales', 0)):,.2f}",
                f"${float(est.get('ganancias_servicios', 0)):,.2f}",
                f"${float(est.get('comision_ventas_producto', 0)):,.2f}",
                f"${float(est.get('descuento_espacio', 0)):,.2f}",
                f"${float(est.get('pago_neto_estilista', 0)):,.2f}",
            ])
        writer.writerow([])

        # Top Productos
        writer.writerow(['=== TOP PRODUCTOS ==='])
        writer.writerow(['Producto', 'Cantidad', 'Total Venta'])
        for item in data.get('top_ventas_productos', [])[:15]:
            writer.writerow([
                item.get('producto_nombre', '-'),
                item.get('cantidad', 0),
                f"${float(item.get('total', 0)):,.2f}",
            ])
        writer.writerow([])

        # Productos Bajo Stock
        writer.writerow(['=== PRODUCTOS BAJO STOCK ==='])
        writer.writerow(['Producto', 'Marca', 'Stock Actual', 'Stock Mínimo', 'Precio'])
        for p in data.get('productos_bajo_stock', []):
            writer.writerow([
                p.get('nombre', '-'),
                p.get('marca', '-'),
                p.get('stock', 0),
                p.get('stock_minimo', 0),
                f"${float(p.get('precio_venta', 0)):,.2f}",
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
    if _es_recepcion(request.user):
        raise PermissionDenied('Recepción no tiene permiso para exportar BI completo.')

    try:
        data = _calcular_datos_bi(request)
    except Exception as e:
        return Response(
            {'error': f'Error obteniendo datos para PDF: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except Exception:
        return Response(
            {'error': 'La exportación PDF requiere instalar reportlab.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        story = []
        
        kpis = data.get('kpis', {})
        venta_neta_total = Decimal(str(kpis.get('venta_neta_total', 0) or 0))
        ganancia_establecimiento_total = Decimal(str(kpis.get('ganancia_establecimiento_total', 0) or 0))
        pago_total_estilistas = Decimal(str(kpis.get('pago_total_estilistas', 0) or 0))
        margen_establecimiento_pct = float((ganancia_establecimiento_total / venta_neta_total) * 100) if venta_neta_total > 0 else 0.0
        participacion_estilistas_pct = float((pago_total_estilistas / venta_neta_total) * 100) if venta_neta_total > 0 else 0.0

        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#007bff'),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#007bff'),
            spaceAfter=10,
            spaceBefore=10,
        )

        # Título
        story.append(Paragraph('Informe Gerencial - Reporte BI', title_style))
        story.append(Paragraph(f'Período: {data["fecha_inicio"]} a {data["fecha_fin"]} | Generado: {timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # Resumen Ejecutivo - Tabla con métricas principales
        story.append(Paragraph('Resumen Ejecutivo', heading_style))
        resumen_data = [
            ['Venta Neta Total', f"${float(venta_neta_total):,.2f}"],
            ['Ganancia Establecimiento', f"${float(ganancia_establecimiento_total):,.2f}"],
            ['Margen Establecimiento (%)', f"{margen_establecimiento_pct:.2f}%"],
            ['Pago Total Estilistas', f"${float(pago_total_estilistas):,.2f}"],
            ['Participación Estilistas (%)', f"{participacion_estilistas_pct:.2f}%"],
            ['Ingresos Servicios Adicionales', f"${float(kpis.get('ingresos_servicios_adicionales', 0)):,.2f}"],
        ]
        resumen_table = Table(resumen_data, colWidths=[3.5*inch, 2.5*inch])
        resumen_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ]))
        story.append(resumen_table)
        story.append(Spacer(1, 0.25*inch))

        # Liquidación por Estilista
        story.append(Paragraph('Liquidación por Estilista', heading_style))
        liquidacion_data = [[
            'Estilista', 'Facturación', 'Adicionales', 'Base Pago', 'Comisión', 'Cobro Espacio', 'Neto a Pagar'
        ]]
        for est in data.get('estilistas', []):
            liquidacion_data.append([
                est.get('estilista_nombre', '-'),
                f"${float(est.get('facturacion_servicios', 0)):,.0f}",
                f"${float(est.get('valor_servicios_adicionales', 0)):,.0f}",
                f"${float(est.get('ganancias_servicios', 0)):,.0f}",
                f"${float(est.get('comision_ventas_producto', 0)):,.0f}",
                f"${float(est.get('descuento_espacio', 0)):,.0f}",
                f"${float(est.get('pago_neto_estilista', 0)):,.0f}",
            ])
        
        liquidacion_table = Table(liquidacion_data, colWidths=[1.2*inch, 0.95*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1*inch, 1.05*inch])
        liquidacion_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(liquidacion_table)
        story.append(Spacer(1, 0.25*inch))

        # Top Productos
        story.append(Paragraph('Top Productos', heading_style))
        productos_data = [['Producto', 'Cantidad', 'Total Venta']]
        for item in data.get('top_ventas_productos', [])[:12]:
            productos_data.append([
                item.get('producto_nombre', '-'),
                str(item.get('cantidad', 0)),
                f"${float(item.get('total', 0)):,.0f}",
            ])
        
        productos_table = Table(productos_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        productos_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(productos_table)

        # Construir PDF
        doc.build(story)
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
    comision_servicios_est = sum((_monto_establecimiento_resuelto(srv) for srv in servicios), Decimal(0))

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
