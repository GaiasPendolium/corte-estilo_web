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
from datetime import datetime, timedelta, date
from decimal import Decimal
from collections import defaultdict
import base64
import csv
import io
import json
import logging
import os
import uuid
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from .models import (
    Usuario, Estilista, Servicio, Cliente, Producto,
    ServicioRealizado, VentaProducto, MovimientoInventario, EstadoPagoEstilistaDia,
    DeudaConsumoEmpleado, AbonoDeudaEmpleado, ServicioRealizadoAdicional,
    EstadoPagoEstilistaHistorial, FactLiquidacionEstilistaDia, SaldoDeudaPuesto,
    Credito, AbonoCredito, CreditoHistorial, PersonaCredito,
    DeudaEntreEmpleados, AbonoDeudaEntreEmpleados,
)
from .serializers import (
    UsuarioSerializer, EstilistaSerializer, ServicioSerializer, ClienteSerializer,
    ProductoSerializer, ServicioRealizadoSerializer, VentaProductoSerializer,
    MovimientoInventarioSerializer, ReporteVentasSerializer,
    ReporteServiciosSerializer, EstadisticasGeneralesSerializer,
    CreditoListSerializer, CreditoDetailSerializer, CreditoCreateSerializer,
    CreditoUpdateSerializer, AbonoCreditoSerializer, EstilistaResumenCreditosSerializer,
    ResumenCreditosSerializer, CreditoHistorialSerializer,
    PersonaCreditoSerializer, PersonaCreditoResumenSerializer,
    DeudaEntreEmpleadosSerializer, AbonoDeudaEntreEmpleadosSerializer,
)
from .serializers import _recalcular_cadena_abonos


logger = logging.getLogger(__name__)


def _tiene_permiso_ui(user, menu_key, action='view', submenu_key=None):
    """
    Valida `permisos_ui` (el mismo JSON que ya existe en Usuario y que el
    frontend usa via hasMenuPermission/hasSubmenuPermission en
    frontend/src/utils/permissions.js) tambien del lado del servidor. No es un
    sistema de permisos nuevo: lee la misma fuente de datos, con la misma
    forma de claves (menu -> accion, o menu -> submenus -> submenu -> accion).

    Administrador/Gerente siempre tienen acceso completo, igual que en el
    frontend (getDefaultPermissionsForRole).
    """
    rol_user = (getattr(user, 'rol', '') or '').strip().lower()
    if rol_user in {'administrador', 'gerente'}:
        return True

    permisos = getattr(user, 'permisos_ui', None) or {}
    menu = permisos.get(menu_key) or {}

    if submenu_key:
        if not menu.get('view'):
            return False
        submenu = (menu.get('submenus') or {}).get(submenu_key) or {}
        return bool(submenu.get(action))

    return bool(menu.get(action))


def _requerir_permiso_ui(user, menu_key, action='view', submenu_key=None, mensaje=None):
    """Lanza PermissionDenied si el usuario no tiene el permiso_ui indicado.

    Reemplaza los checks hardcodeados por rol para que lo que el
    administrador/gerente habilite en Usuarios sea lo que efectivamente
    decide qué puede hacer cada usuario, en vez del rol.
    """
    if not _tiene_permiso_ui(user, menu_key, action, submenu_key):
        raise PermissionDenied(mensaje or 'No tienes permiso para realizar esta acción.')


def _qz_allowed_origins():
    raw = os.environ.get('QZ_ALLOWED_ORIGINS', '').strip()
    if not raw:
        return []
    return [item.strip().rstrip('/') for item in raw.split(',') if item.strip()]


def _qz_origin_is_local(origin):
    if not origin:
        return False

    local_prefixes = (
        'http://localhost',
        'https://localhost',
        'http://127.0.0.1',
        'https://127.0.0.1',
    )
    return origin.startswith(local_prefixes)


def _qz_check_origin(request):
    allowed = _qz_allowed_origins()
    if not allowed:
        return None

    origin = (request.headers.get('Origin') or '').strip().rstrip('/')
    if origin in allowed or _qz_origin_is_local(origin):
        return None

    detail = origin or 'sin Origin'
    return HttpResponse(
        f'Origin no autorizado para firma QZ: {detail}. Agrega este dominio a QZ_ALLOWED_ORIGINS en Railway.',
        status=403,
        content_type='text/plain; charset=utf-8'
    )


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
        logger.exception('Error firmando solicitud QZ')
        return HttpResponse('No se pudo firmar la solicitud', status=500, content_type='text/plain; charset=utf-8')


def _sanitizar_bi_para_recepcion(data):
    """Oculta datos de módulos restringidos cuando el usuario no tiene permiso de ver 'agotarse'."""
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
    monto_estilista = Decimal(getattr(srv, 'monto_estilista', 0) or 0)
    monto_establecimiento = Decimal(srv.monto_establecimiento or 0)
    nombre_servicio = str(getattr(getattr(srv, 'servicio', None), 'nombre', '') or '').lower()

    if 'shampoo' in nombre_servicio:
        return Decimal(0)

    # Si ya existe reparto guardado en la factura (monto del estilista o establecimiento),
    # usar ese valor como fuente de verdad para no volver al total cobrado.
    if monto_estilista > 0 or monto_establecimiento > 0:
        if monto_estilista < 0:
            return Decimal(0)
        if monto_estilista > neto:
            return neto
        return monto_estilista

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
    monto_estilista = Decimal(getattr(srv, 'monto_estilista', 0) or 0)
    monto_establecimiento = Decimal(srv.monto_establecimiento or 0)
    nombre_servicio = str(getattr(getattr(srv, 'servicio', None), 'nombre', '') or '').lower()

    if 'shampoo' in nombre_servicio:
        return neto

    # Si la factura ya trae reparto persistido, respetarlo para mantener consistencia
    # entre histórico y cálculos de liquidación.
    if monto_estilista > 0 or monto_establecimiento > 0:
        if monto_establecimiento < 0:
            return Decimal(0)
        if monto_establecimiento > neto:
            return neto
        return monto_establecimiento

    if tipo_reparto in {'porcentaje', 'monto'}:
        if monto_establecimiento < 0:
            return Decimal(0)
        if monto_establecimiento > neto:
            return neto
        return monto_establecimiento

    return Decimal(0)


def _aplicar_abonos_vale_interno(
    *,
    estilista,
    monto_decimal,
    usuario,
    notas,
    origen_liquidacion_fecha=None,
):
    """
    Aplica el descuento de Vale (deuda entre empleados) a las deudas
    pendientes del empleado como deudor, en orden de antigüedad (FIFO) --
    mismo patrón que `_aplicar_abonos_consumo_interno`, pero contra
    `DeudaEntreEmpleados` en vez de `DeudaConsumoEmpleado`. Cada aplicación
    crea un `AbonoDeudaEntreEmpleados` (así queda saldada la deuda con el
    compañero) y decrementa el saldo consolidado `SaldoDeudaPuesto.saldo_vale`.
    """
    deudas_pendientes = list(
        DeudaEntreEmpleados.objects.filter(
            deudor=estilista,
            estado='pendiente',
        ).order_by('fecha_creacion', 'id')
    )

    if not deudas_pendientes:
        return [], Decimal(monto_decimal or 0)

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
            'usuario': usuario,
            'notas': notas,
        }
        if origen_liquidacion_fecha is not None:
            create_data['origen_liquidacion_fecha'] = origen_liquidacion_fecha

        AbonoDeudaEntreEmpleados.objects.create(**create_data)

        deuda.monto_abonado = Decimal(deuda.monto_abonado or 0) + aplicado
        deuda.saldo_pendiente = max(Decimal(deuda.monto or 0) - deuda.monto_abonado, Decimal(0))
        deuda.estado = 'pagado' if deuda.saldo_pendiente <= 0 else 'pendiente'
        deuda.save(update_fields=['monto_abonado', 'saldo_pendiente', 'estado'])

        aplicaciones.append(
            {
                'deuda_id': deuda.id,
                'acreedor_nombre': deuda.acreedor.nombre,
                'monto_aplicado': float(aplicado),
                'saldo_restante': float(deuda.saldo_pendiente),
                'estado': deuda.estado,
            }
        )

        restante -= aplicado

    total_aplicado = Decimal(monto_decimal or 0) - restante
    if total_aplicado > 0:
        try:
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj.saldo_vale = max(Decimal(saldo_obj.saldo_vale or 0) - total_aplicado, Decimal(0))
            saldo_obj.save()
        except Exception:
            pass

    return aplicaciones, restante


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


def _campos_liquidacion_v3_dia(estado_dia):
    """
    Campos de solo lectura del régimen "solo efectivo" para un
    EstadoPagoEstilistaDia, usados por el GET de estado_pago_estilista_dia
    (consumidos por la UI de liquidación, Fase 6).
    """
    return {
        'motor_calculo': getattr(estado_dia, 'motor_calculo', 'v2_mixed') or 'v2_mixed',
        'ganancia_efectivo_dia': float(getattr(estado_dia, 'ganancia_efectivo_dia', 0) or 0),
        'ganancia_electronica_dia': float(getattr(estado_dia, 'ganancia_electronica_dia', 0) or 0),
        'ganancia_electronica_nequi': float(getattr(estado_dia, 'ganancia_electronica_nequi', 0) or 0),
        'ganancia_electronica_daviplata': float(getattr(estado_dia, 'ganancia_electronica_daviplata', 0) or 0),
        'ganancia_electronica_otros': float(getattr(estado_dia, 'ganancia_electronica_otros', 0) or 0),
        'comision_producto_dia': float(getattr(estado_dia, 'comision_producto_dia', 0) or 0),
        'reparto_establecimiento_electronico_pendiente': float(getattr(estado_dia, 'reparto_establecimiento_electronico_pendiente', 0) or 0),
        'descuento_consumo_dia': float(getattr(estado_dia, 'descuento_consumo_dia', 0) or 0),
        'saltar_descuento_consumo': bool(getattr(estado_dia, 'saltar_descuento_consumo', False)),
        'total_deducciones_dia': float(getattr(estado_dia, 'total_deducciones_dia', 0) or 0),
        'monto_transferir_empleado': float(getattr(estado_dia, 'monto_transferir_empleado', 0) or 0),
        'monto_transferir_recibido': float(getattr(estado_dia, 'monto_transferir_recibido', 0) or 0),
        'pendiente_transferencia_empleado': float(getattr(estado_dia, 'pendiente_transferencia_empleado', 0) or 0),
        'monto_pagar_establecimiento': float(getattr(estado_dia, 'monto_pagar_establecimiento', 0) or 0),
        'monto_pagar_entregado': float(getattr(estado_dia, 'monto_pagar_entregado', 0) or 0),
        'pendiente_pago_empleado_efectivo': float(getattr(estado_dia, 'pendiente_pago_empleado_efectivo', 0) or 0),
    }


def _normalizar_medio_pago_efectivo_electronico(medio_pago):
    """
    Normaliza medio_pago a uno de: 'efectivo', 'nequi', 'daviplata', 'otros'.
    Nulo/desconocido se trata como 'efectivo' -- decision conservadora para no
    inflar "ganancia electronica" con datos incompletos (ver plan de la fase
    de liquidacion "solo efectivo").
    """
    medio = str(medio_pago or '').strip().lower()
    if medio in {'nequi', 'daviplata', 'otros'}:
        return medio
    return 'efectivo'


def calcular_liquidacion_dia_estilista(estilista, fecha_dia, aplica_comision_ventas=True):
    """
    Dispatcher: decide el motor de calculo segun la fecha (ver
    `_usa_motor_cash_only`). Fechas anteriores a LIQUIDACION_CASH_ONLY_DESDE
    usan el motor legacy intacto (Nequi/Daviplata eran ingreso del negocio);
    fechas desde el corte usan el motor "solo efectivo".
    """
    if _usa_motor_cash_only(fecha_dia):
        return _calcular_liquidacion_dia_estilista_v3(estilista, fecha_dia, aplica_comision_ventas)
    return _calcular_liquidacion_dia_estilista_v2_legacy(estilista, fecha_dia, aplica_comision_ventas)


def _calcular_liquidacion_dia_estilista_v3(estilista, fecha_dia, aplica_comision_ventas=True):
    """
    Motor de liquidacion para el regimen "solo efectivo": el negocio ya no
    recibe Nequi/Daviplata/transferencias en su cuenta -- ese dinero lo recibe
    directo el empleado. Este motor separa la ganancia del empleado en
    efectivo (dinero real en caja) vs electronica (informativa, ya en manos
    del empleado), y calcula cuanto del % de establecimiento quedo pendiente
    de recuperar por haberse pagado electronico.
    """
    ganancia_efectivo = Decimal(0)
    ganancia_electronica = Decimal(0)
    ganancia_nequi = Decimal(0)
    ganancia_daviplata = Decimal(0)
    ganancia_otros = Decimal(0)
    reparto_establecimiento_electronico = Decimal(0)

    servicios_dia = ServicioRealizado.objects.select_related('servicio', 'estilista').filter(
        estado='finalizado',
        estilista=estilista,
        fecha_hora__date=fecha_dia,
    )
    for srv in servicios_dia:
        monto_emp = _monto_estilista_resuelto(srv)
        medio = _normalizar_medio_pago_efectivo_electronico(srv.medio_pago)
        if medio == 'efectivo':
            ganancia_efectivo += monto_emp
        else:
            ganancia_electronica += monto_emp
            reparto_establecimiento_electronico += _monto_establecimiento_resuelto(srv)
            if medio == 'nequi':
                ganancia_nequi += monto_emp
            elif medio == 'daviplata':
                ganancia_daviplata += monto_emp
            else:
                ganancia_otros += monto_emp

    adicionales_dia = ServicioRealizadoAdicional.objects.select_related('servicio_realizado').filter(
        estilista=estilista,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date=fecha_dia,
    )
    for ad in adicionales_dia:
        valor_cobrado = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        pct_est = max(Decimal(0), min(Decimal(100), pct_est))
        monto_emp = valor_cobrado - (valor_cobrado * pct_est / Decimal(100))
        monto_est = valor_cobrado - monto_emp
        medio = _normalizar_medio_pago_efectivo_electronico(ad.servicio_realizado.medio_pago)
        if medio == 'efectivo':
            ganancia_efectivo += monto_emp
        else:
            ganancia_electronica += monto_emp
            reparto_establecimiento_electronico += monto_est
            if medio == 'nequi':
                ganancia_nequi += monto_emp
            elif medio == 'daviplata':
                ganancia_daviplata += monto_emp
            else:
                ganancia_otros += monto_emp

    # Comision por venta de producto en caja + producto adicional en servicio:
    # formula identica al motor legacy (no cambia con este requerimiento). Esta
    # plata siempre entro a caja del negocio al vender el producto -- nunca fue
    # efectivo fisico en mano del empleado -- asi que no se bucketiza por medio
    # de pago del servicio.
    ventas_dia = VentaProducto.objects.select_related('producto').filter(
        estilista=estilista,
        tipo_operacion='venta',
        fecha_hora__date=fecha_dia,
    )
    comisiones_ventas_caja = Decimal(0)
    for venta in ventas_dia:
        monto_venta = Decimal(venta.total or 0)
        pct_comision = Decimal(venta.producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_caja += (monto_venta * pct_comision) / Decimal(100)

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

    comision_producto_dia = comisiones_ventas_caja + comisiones_ventas_servicios
    if not aplica_comision_ventas:
        comision_producto_dia = Decimal(0)

    ganancias_totales = ganancia_efectivo + ganancia_electronica + comision_producto_dia

    # Descuento de puesto: misma formula que el motor legacy, sobre la base de
    # ganancias por servicio del empleado (efectivo + electronico), sin
    # comisiones de producto.
    base_puesto = ganancia_efectivo + ganancia_electronica
    descuento_puesto = _descuento_puesto_dia(estilista, base_puesto)
    total_pagable = max(ganancias_totales - descuento_puesto, Decimal(0))

    return {
        # Claves nuevas del regimen "solo efectivo"
        'ganancia_efectivo_dia': ganancia_efectivo,
        'ganancia_electronica_dia': ganancia_electronica,
        'ganancia_electronica_nequi': ganancia_nequi,
        'ganancia_electronica_daviplata': ganancia_daviplata,
        'ganancia_electronica_otros': ganancia_otros,
        'reparto_establecimiento_electronico_pendiente': reparto_establecimiento_electronico,
        'comision_producto_dia': comision_producto_dia,
        # Claves compartidas con el motor legacy, para no romper codigo que
        # aun no conoce el regimen "solo efectivo" (ej. _upsert_fact_liquidacion_dia).
        'servicios_base': ganancia_efectivo + ganancia_electronica,
        'comisiones_adicionales': Decimal(0),
        'ganancias_totales': ganancias_totales,
        'comisiones_ventas_caja': comisiones_ventas_caja,
        'comisiones_ventas_servicios': comisiones_ventas_servicios,
        'comisiones_ventas': comision_producto_dia,
        'aplica_comision_ventas': bool(aplica_comision_ventas),
        'descuento_puesto': descuento_puesto,
        'total_pagable': total_pagable,
        'motor_calculo': 'v3_efectivo',
    }


def _calcular_liquidacion_dia_estilista_v2_legacy(estilista, fecha_dia, aplica_comision_ventas=True):
    """
    LIQUIDADOR SIMPLIFICADO Y CLARO (motor legacy, vigente para fechas
    anteriores a LIQUIDACION_CASH_ONLY_DESDE -- Nequi/Daviplata eran ingreso
    del negocio):

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
    if not aplica_comision_ventas:
        comisiones_ventas = Decimal(0)
    
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
        'aplica_comision_ventas': bool(aplica_comision_ventas),
        'descuento_puesto': descuento_puesto,
        'total_pagable': total_pagable,
        'motor_calculo': 'v2_mixed',
    }


def _precargar_datos_liquidacion_rango(estilista_ids, fecha_inicio_dt, fecha_fin_dt):
    """
    Trae en bloque (4 queries totales, sin importar cuantos estilistas/dias haya)
    todo lo que `calcular_liquidacion_dia_estilista` necesita, agrupado por
    (estilista_id, fecha_operativa). Evita el N+1 de llamar esa funcion una vez
    por cada combinacion estilista/dia (que antes disparaba 4 queries cada vez).
    """
    servicios_por_dia = defaultdict(list)
    servicios_qs = ServicioRealizado.objects.select_related('servicio', 'estilista').filter(
        estado='finalizado',
        estilista_id__in=estilista_ids,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    for srv in servicios_qs:
        f = _fecha_operativa_desde_dt(srv.fecha_hora)
        if f:
            servicios_por_dia[(int(srv.estilista_id), f)].append(srv)

    adicionales_por_dia = defaultdict(list)
    adicionales_qs = ServicioRealizadoAdicional.objects.filter(
        estilista_id__in=estilista_ids,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date__gte=fecha_inicio_dt,
        servicio_realizado__fecha_hora__date__lte=fecha_fin_dt,
    ).select_related('servicio_realizado')
    for ad in adicionales_qs:
        f = _fecha_operativa_desde_dt(ad.servicio_realizado.fecha_hora)
        if f:
            adicionales_por_dia[(int(ad.estilista_id), f)].append(ad)

    ventas_por_dia = defaultdict(list)
    ventas_qs = VentaProducto.objects.select_related('producto').filter(
        tipo_operacion='venta',
        estilista_id__in=estilista_ids,
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    for venta in ventas_qs:
        f = _fecha_operativa_desde_dt(venta.fecha_hora)
        if f:
            ventas_por_dia[(int(venta.estilista_id), f)].append(venta)

    servicios_producto_adicional_por_dia = defaultdict(list)
    prod_ad_qs = ServicioRealizado.objects.select_related('adicional_otro_producto').filter(
        estado='finalizado',
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
        adicional_otro_producto__isnull=False,
        adicional_otro_estilista_id__in=estilista_ids,
    )
    for srv in prod_ad_qs:
        f = _fecha_operativa_desde_dt(srv.fecha_hora)
        if f:
            servicios_producto_adicional_por_dia[(int(srv.adicional_otro_estilista_id), f)].append(srv)

    return {
        'servicios': servicios_por_dia,
        'adicionales': adicionales_por_dia,
        'ventas': ventas_por_dia,
        'servicios_producto_adicional': servicios_producto_adicional_por_dia,
    }


def _calcular_liquidacion_dia_estilista_bulk(datos_precargados, estilista, fecha_dia, aplica_comision_ventas=True):
    """
    Dispatcher bulk: mismo criterio que `calcular_liquidacion_dia_estilista`
    (decide por la fecha del dia, no por la fecha actual).
    """
    if _usa_motor_cash_only(fecha_dia):
        return _calcular_liquidacion_dia_estilista_bulk_v3(datos_precargados, estilista, fecha_dia, aplica_comision_ventas)
    return _calcular_liquidacion_dia_estilista_bulk_v2_legacy(datos_precargados, estilista, fecha_dia, aplica_comision_ventas)


def _calcular_liquidacion_dia_estilista_bulk_v3(datos_precargados, estilista, fecha_dia, aplica_comision_ventas=True):
    """
    Misma formula que `_calcular_liquidacion_dia_estilista_v3`, pero usando
    datos precargados en bloque (ver `_precargar_datos_liquidacion_rango`).
    """
    key = (int(estilista.id), fecha_dia)

    ganancia_efectivo = Decimal(0)
    ganancia_electronica = Decimal(0)
    ganancia_nequi = Decimal(0)
    ganancia_daviplata = Decimal(0)
    ganancia_otros = Decimal(0)
    reparto_establecimiento_electronico = Decimal(0)

    for srv in datos_precargados['servicios'].get(key, []):
        monto_emp = _monto_estilista_resuelto(srv)
        medio = _normalizar_medio_pago_efectivo_electronico(srv.medio_pago)
        if medio == 'efectivo':
            ganancia_efectivo += monto_emp
        else:
            ganancia_electronica += monto_emp
            reparto_establecimiento_electronico += _monto_establecimiento_resuelto(srv)
            if medio == 'nequi':
                ganancia_nequi += monto_emp
            elif medio == 'daviplata':
                ganancia_daviplata += monto_emp
            else:
                ganancia_otros += monto_emp

    for ad in datos_precargados['adicionales'].get(key, []):
        valor_cobrado = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        pct_est = max(Decimal(0), min(Decimal(100), pct_est))
        monto_emp = valor_cobrado - (valor_cobrado * pct_est / Decimal(100))
        monto_est = valor_cobrado - monto_emp
        medio = _normalizar_medio_pago_efectivo_electronico(ad.servicio_realizado.medio_pago)
        if medio == 'efectivo':
            ganancia_efectivo += monto_emp
        else:
            ganancia_electronica += monto_emp
            reparto_establecimiento_electronico += monto_est
            if medio == 'nequi':
                ganancia_nequi += monto_emp
            elif medio == 'daviplata':
                ganancia_daviplata += monto_emp
            else:
                ganancia_otros += monto_emp

    comisiones_ventas_caja = Decimal(0)
    for venta in datos_precargados['ventas'].get(key, []):
        monto_venta = Decimal(venta.total or 0)
        pct_comision = Decimal(venta.producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_caja += (monto_venta * pct_comision) / Decimal(100)

    comisiones_ventas_servicios = Decimal(0)
    for srv in datos_precargados['servicios_producto_adicional'].get(key, []):
        cantidad = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        monto_venta = precio_venta * cantidad
        pct_comision = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_servicios += (monto_venta * pct_comision) / Decimal(100)

    comision_producto_dia = comisiones_ventas_caja + comisiones_ventas_servicios
    if not aplica_comision_ventas:
        comision_producto_dia = Decimal(0)

    ganancias_totales = ganancia_efectivo + ganancia_electronica + comision_producto_dia
    base_puesto = ganancia_efectivo + ganancia_electronica
    descuento_puesto = _descuento_puesto_dia(estilista, base_puesto)
    total_pagable = max(ganancias_totales - descuento_puesto, Decimal(0))

    return {
        'ganancia_efectivo_dia': ganancia_efectivo,
        'ganancia_electronica_dia': ganancia_electronica,
        'ganancia_electronica_nequi': ganancia_nequi,
        'ganancia_electronica_daviplata': ganancia_daviplata,
        'ganancia_electronica_otros': ganancia_otros,
        'reparto_establecimiento_electronico_pendiente': reparto_establecimiento_electronico,
        'comision_producto_dia': comision_producto_dia,
        'servicios_base': ganancia_efectivo + ganancia_electronica,
        'comisiones_adicionales': Decimal(0),
        'ganancias_totales': ganancias_totales,
        'comisiones_ventas_caja': comisiones_ventas_caja,
        'comisiones_ventas_servicios': comisiones_ventas_servicios,
        'comisiones_ventas': comision_producto_dia,
        'aplica_comision_ventas': bool(aplica_comision_ventas),
        'descuento_puesto': descuento_puesto,
        'total_pagable': total_pagable,
        'motor_calculo': 'v3_efectivo',
    }


def _calcular_liquidacion_dia_estilista_bulk_v2_legacy(datos_precargados, estilista, fecha_dia, aplica_comision_ventas=True):
    """
    Misma formula que `_calcular_liquidacion_dia_estilista_v2_legacy`, pero
    usando datos precargados en bloque (ver `_precargar_datos_liquidacion_rango`)
    en vez de lanzar 4 queries nuevas por cada combinacion estilista/dia.
    """
    key = (int(estilista.id), fecha_dia)

    servicios_base = Decimal(0)
    for srv in datos_precargados['servicios'].get(key, []):
        servicios_base += _monto_estilista_resuelto(srv)

    comisiones_adicionales = Decimal(0)
    for ad in datos_precargados['adicionales'].get(key, []):
        valor_cobrado = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        pct_est = max(Decimal(0), min(Decimal(100), pct_est))
        monto_estilista = valor_cobrado - (valor_cobrado * pct_est / Decimal(100))
        comisiones_adicionales += monto_estilista

    comisiones_ventas_caja = Decimal(0)
    for venta in datos_precargados['ventas'].get(key, []):
        monto_venta = Decimal(venta.total or 0)
        pct_comision = Decimal(venta.producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_caja += (monto_venta * pct_comision) / Decimal(100)

    comisiones_ventas_servicios = Decimal(0)
    for srv in datos_precargados['servicios_producto_adicional'].get(key, []):
        cantidad = Decimal(srv.adicional_otro_cantidad or 1)
        precio_venta = Decimal(srv.adicional_otro_producto.precio_venta or 0)
        monto_venta = precio_venta * cantidad
        pct_comision = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
        pct_comision = max(Decimal(0), min(Decimal(100), pct_comision))
        comisiones_ventas_servicios += (monto_venta * pct_comision) / Decimal(100)

    comisiones_ventas = comisiones_ventas_caja + comisiones_ventas_servicios
    if not aplica_comision_ventas:
        comisiones_ventas = Decimal(0)

    ganancias_totales = servicios_base + comisiones_adicionales + comisiones_ventas
    base_puesto = servicios_base + comisiones_adicionales
    descuento_puesto = _descuento_puesto_dia(estilista, base_puesto)
    total_pagable = max(ganancias_totales - descuento_puesto, Decimal(0))

    return {
        'ganancias_totales': ganancias_totales,
        'servicios_base': servicios_base,
        'comisiones_adicionales': comisiones_adicionales,
        'comisiones_ventas_caja': comisiones_ventas_caja,
        'comisiones_ventas_servicios': comisiones_ventas_servicios,
        'comisiones_ventas': comisiones_ventas,
        'aplica_comision_ventas': bool(aplica_comision_ventas),
        'descuento_puesto': descuento_puesto,
        'total_pagable': total_pagable,
        'motor_calculo': 'v2_mixed',
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


def _fecha_corte_liquidacion_cash_only():
    """
    Fecha desde la cual el negocio dejo de recibir Nequi/Daviplata/transferencias
    en su propia cuenta (solo efectivo en caja). Se configura por variable de
    entorno para poder activarla en Railway sin un nuevo deploy, o en el
    archivo .env en desarrollo local. Se lee con decouple.config (no con
    os.environ directamente) porque python-decouple NO copia el contenido de
    .env a os.environ -- solo os.environ.get() nunca veria un valor puesto
    unicamente en .env. Si no esta configurada, ninguna fecha usa el motor
    nuevo -- el sistema sigue funcionando exactamente igual que antes.
    """
    from decouple import config as _decouple_config
    raw = str(_decouple_config('LIQUIDACION_CASH_ONLY_DESDE', default='')).strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except Exception:
        logger.warning('LIQUIDACION_CASH_ONLY_DESDE tiene un formato invalido (usa YYYY-MM-DD): %r', raw)
        return None


def _usa_motor_cash_only(fecha_dia):
    """
    Decide si una fecha usa el motor de liquidacion "solo efectivo" (v3) o el
    motor legacy (v2, donde Nequi/Daviplata entraban a caja del negocio).
    Se decide SIEMPRE por la fecha del registro/operacion, nunca por la fecha
    en que se ejecuta el calculo o el reporte -- asi un reporte que cruce la
    fecha de corte suma correctamente ambos regimenes sin reinterpretar el
    historico.
    """
    corte = _fecha_corte_liquidacion_cash_only()
    if corte is None:
        return False
    if isinstance(fecha_dia, datetime):
        fecha_dia = timezone.localtime(fecha_dia).date() if timezone.is_aware(fecha_dia) else fecha_dia.date()
    elif not isinstance(fecha_dia, date):
        fecha_dia = datetime.strptime(str(fecha_dia), '%Y-%m-%d').date()
    return fecha_dia >= corte


def _to_bool_flag(value, default=True):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {'1', 'true', 'si', 'sí', 'yes'}:
        return True
    if raw in {'0', 'false', 'no'}:
        return False
    return bool(default)


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
    aplica_comision_ventas,
    deuda_anterior,
    deuda_cierre,
    pendiente_pago,
    estado_liquidacion,
    forzar_reemplazo_dia,
    usuario,
    notas,
    origen='liquidar_dia_v2',
    saltar_descuento_consumo=False,
    descuento_consumo_dia=0,
    descuento_vale_dia=0,
    total_deducciones_dia=0,
    monto_transferir_empleado=0,
    monto_transferir_recibido=0,
    monto_pagar_establecimiento=0,
    monto_pagar_entregado=0,
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
            fact.aplica_comision_ventas = bool(aplica_comision_ventas)
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
            fact.saltar_descuento_consumo = bool(saltar_descuento_consumo)
            fact.descuento_vale_dia = Decimal(descuento_vale_dia or 0)
            fact.estado_liquidacion = estado_liquidacion
            fact.forzar_reemplazo_dia = bool(forzar_reemplazo_dia)
            fact.usuario_liquida = usuario if getattr(usuario, 'is_authenticated', False) else None
            fact.notas = notas

            # Régimen "solo efectivo" -- en filas legacy (calc sin estas claves)
            # todo queda en 0, que es el valor correcto para esas fechas.
            fact.ganancia_efectivo = Decimal(calc.get('ganancia_efectivo_dia') or 0)
            fact.ganancia_electronica = Decimal(calc.get('ganancia_electronica_dia') or 0)
            fact.ganancia_electronica_nequi = Decimal(calc.get('ganancia_electronica_nequi') or 0)
            fact.ganancia_electronica_daviplata = Decimal(calc.get('ganancia_electronica_daviplata') or 0)
            fact.ganancia_electronica_otros = Decimal(calc.get('ganancia_electronica_otros') or 0)
            fact.reparto_establecimiento_electronico_pendiente = Decimal(calc.get('reparto_establecimiento_electronico_pendiente') or 0)
            fact.total_deducciones_dia = Decimal(total_deducciones_dia or 0)
            fact.monto_transferir_empleado = Decimal(monto_transferir_empleado or 0)
            fact.monto_transferir_recibido = Decimal(monto_transferir_recibido or 0)
            fact.monto_pagar_establecimiento = Decimal(monto_pagar_establecimiento or 0)
            fact.monto_pagar_entregado = Decimal(monto_pagar_entregado or 0)

            fact.payload_fuente = {
                'ganancias_totales': float(Decimal(calc.get('ganancias_totales') or 0)),
                'descuento_puesto': float(Decimal(calc.get('descuento_puesto') or 0)),
                'total_pagable': float(Decimal(calc.get('total_pagable') or 0)),
                'comisiones_ventas_caja': float(comision_caja),
                'comisiones_ventas_servicios': float(comision_servicios),
                'comisiones_ventas': float(comisiones_totales),
                'aplica_comision_ventas': bool(aplica_comision_ventas),
                'motor_calculo': calc.get('motor_calculo') or 'v2_mixed',
                'descuento_consumo_dia': float(Decimal(descuento_consumo_dia or 0)),
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

    def _validar_edicion_permisos_ui(self, request):
        if 'permisos_ui' not in request.data:
            return
        rol_user = (getattr(request.user, 'rol', '') or '').strip().lower()
        if rol_user != 'administrador':
            raise PermissionDenied('Solo administrador puede modificar permisos por menú.')

    def create(self, request, *args, **kwargs):
        self._validar_edicion_permisos_ui(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._validar_edicion_permisos_ui(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._validar_edicion_permisos_ui(request)
        return super().partial_update(request, *args, **kwargs)
    
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
        _requerir_permiso_ui(request.user, 'productos', 'create', 'servicios', 'No tienes permiso para crear servicios del catálogo.')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'edit', 'servicios', 'No tienes permiso para editar servicios del catálogo.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'edit', 'servicios', 'No tienes permiso para editar servicios del catálogo.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'delete', 'servicios', 'No tienes permiso para eliminar servicios del catálogo.')
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
        _requerir_permiso_ui(request.user, 'productos', 'create', 'inventario', 'No tienes permiso para crear productos.')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'edit', 'inventario', 'No tienes permiso para editar productos.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'edit', 'inventario', 'No tienes permiso para editar productos.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'productos', 'delete', 'inventario', 'No tienes permiso para eliminar productos.')
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
        _requerir_permiso_ui(request.user, 'ventas', 'edit', 'servicios', 'No tienes permiso para editar servicios facturados.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'ventas', 'edit', 'servicios', 'No tienes permiso para editar servicios facturados.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'ventas', 'delete', 'servicios', 'No tienes permiso para eliminar servicios facturados.')
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
        _requerir_permiso_ui(request.user, 'ventas', 'edit', 'ventas', 'No tienes permiso para editar facturas de venta.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'ventas', 'edit', 'ventas', 'No tienes permiso para editar facturas de venta.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _requerir_permiso_ui(request.user, 'ventas', 'delete', 'ventas', 'No tienes permiso para eliminar facturas de venta.')
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
                    # Mantener sincronizado el saldo consolidado (fuente de verdad que
                    # usa Ajuste Diario para el total "Consumo empleado"). Antes solo se
                    # incrementaba en la carga manual de cargos (crear_cargo_manual_empleado),
                    # no aqui, en el flujo normal de venta de consumo — por eso el total
                    # mostrado quedaba por debajo de la suma real de facturas pendientes.
                    saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista_id=int(estilista))
                    saldo_obj.saldo_consumo = max(Decimal(saldo_obj.saldo_consumo or 0) + total_transaccion, Decimal(0))
                    saldo_obj.save()

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
        _requerir_permiso_ui(request.user, 'ventas', 'delete', 'ventas', 'No tienes permiso para cancelar facturas de venta.')

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
        _requerir_permiso_ui(request.user, 'ventas', 'edit', 'ventas', 'No tienes permiso para editar facturas de venta.')

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
                saldo_anterior_deuda = Decimal(deuda_obj.saldo_pendiente or 0)
                deuda_obj.total_cargo = total_transaccion
                deuda_obj.fecha_hora = fecha_referencia
                _recalcular_estado_deuda(deuda_obj)
                deuda_obj.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado', 'fecha_hora'])
                _ajustar_saldo_consumo_consolidado(
                    deuda_obj.estilista_id, saldo_anterior_deuda, Decimal(deuda_obj.saldo_pendiente or 0)
                )

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

    fact_aplica_map = {}
    try:
        fact_aplica_qs = FactLiquidacionEstilistaDia.objects.filter(
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
            vigente=True,
        ).only('estilista_id', 'fecha', 'aplica_comision_ventas')
        for fact_ap in fact_aplica_qs:
            fact_aplica_map[(int(fact_ap.estilista_id), fact_ap.fecha)] = bool(getattr(fact_ap, 'aplica_comision_ventas', True))
    except Exception:
        fact_aplica_map = {}

    def _aplica_comision_ventas_dia(estilista_id, fecha_operativa):
        if not estilista_id or not fecha_operativa:
            return True
        return fact_aplica_map.get((int(estilista_id), fecha_operativa), True)

    ventas_qs = VentaProducto.objects.select_related('producto', 'estilista').filter(
        fecha_hora__date__gte=fecha_inicio_dt,
        fecha_hora__date__lte=fecha_fin_dt,
    )
    ventas_pagadas_qs = ventas_qs.exclude(tipo_operacion='consumo_empleado')
    servicios_qs = ServicioRealizado.objects.select_related(
        'servicio', 'estilista', 'adicional_otro_producto', 'adicional_otro_estilista'
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

    ingresos_abonos_consumo = sum((Decimal(ab.monto or 0) for ab in abonos_consumo_lista), Decimal(0))
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
            fecha_v = _fecha_operativa_desde_dt(venta.fecha_hora)
            if not _aplica_comision_ventas_dia(venta.estilista_id, fecha_v):
                continue
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
                fecha_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
                if not _aplica_comision_ventas_dia(srv.adicional_otro_estilista_id, fecha_srv):
                    continue
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
            fecha_v = _fecha_operativa_desde_dt(v.fecha_hora)
            if not _aplica_comision_ventas_dia(estilista.id, fecha_v):
                continue
            pct = Decimal(v.producto.comision_estilista or 0)
            valor_comision = (Decimal(v.total) * pct) / Decimal(100)
            comision_ventas_producto_caja_est += valor_comision
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
                descuento_dia = Decimal(fact_dia.descuento_puesto_dia or descuento_dia)
                ganancias_dia = Decimal(fact_dia.ganancias_totales or ganancias_dia)
                if getattr(fact_dia, 'origen_calculo', '') == 'engine_v3_efectivo':
                    # Régimen "solo efectivo": los campos legacy pago_efectivo/
                    # nequi/daviplata/otros quedan en 0 a propósito (ver
                    # _liquidar_dia_v3_core) -- el efectivo que de verdad se le
                    # entregó al empleado ese día vive en estos otros campos.
                    pago_empleado_dia = max(
                        Decimal(getattr(fact_dia, 'monto_pagar_entregado', 0) or 0)
                        - Decimal(getattr(fact_dia, 'monto_transferir_recibido', 0) or 0),
                        Decimal(0),
                    )
                else:
                    pago_empleado_dia = (
                        Decimal(fact_dia.pago_efectivo or 0)
                        + Decimal(fact_dia.pago_nequi or 0)
                        + Decimal(fact_dia.pago_daviplata or 0)
                        + Decimal(fact_dia.pago_otros or 0)
                    )
                abono_puesto_dia = Decimal(fact_dia.abono_puesto_dia or 0)
                estado_dia = fact_dia.estado_liquidacion
            elif estado_dia_obj:
                if getattr(estado_dia_obj, 'motor_calculo', '') == 'v3_efectivo':
                    pago_empleado_dia = max(
                        Decimal(getattr(estado_dia_obj, 'monto_pagar_entregado', 0) or 0)
                        - Decimal(getattr(estado_dia_obj, 'monto_transferir_recibido', 0) or 0),
                        Decimal(0),
                    )
                else:
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
        # Deuda total acumulada: leer directamente de SaldoDeudaPuesto (fuente de verdad).
        # Este valor se actualiza en cada operación (carga, cancelación, liquidación)
        # y no depende del filtro de fechas del UI.
        deuda_total_acumulada = Decimal(0)
        deuda_consumo_acumulada = Decimal(0)
        try:
            saldo_obj = SaldoDeudaPuesto.objects.filter(estilista=estilista).first()
            if saldo_obj:
                deuda_total_acumulada = max(Decimal(saldo_obj.saldo or 0), Decimal(0))
                deuda_consumo_acumulada = max(Decimal(saldo_obj.saldo_consumo or 0), Decimal(0))
        except Exception:
            deuda_total_acumulada = Decimal(0)
            deuda_consumo_acumulada = Decimal(0)

        deuda_puesto_historial = deuda_total_acumulada
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
                'deuda_consumo_acumulada': float(deuda_consumo_acumulada),
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
    # Régimen "solo efectivo": lo que un servicio cobrado electrónico ya no
    # entra a la caja del negocio (lo recibe el empleado directo) se separa
    # aquí -- informativo, nunca se suma a ingresos_por_medio ni a los
    # totales de caja. Se decide por la fecha de CADA registro, nunca por un
    # flag global, para no reinterpretar el histórico.
    ingresos_informativos_electronicos_empleado = Decimal(0)

    for v in ventas_pagadas_qs:
        # La venta de producto siempre entra a caja del negocio (no cambió
        # con el régimen "solo efectivo" -- solo cambió el pago de servicios).
        medio_v = (v.medio_pago or 'otros').strip().lower()
        if medio_v not in ingresos_por_medio:
            medio_v = 'otros'
        ingresos_por_medio[medio_v] += Decimal(v.total or 0)

    for ab in abonos_consumo_lista:
        medio_ab = (ab.medio_pago or 'otros').strip().lower()
        if medio_ab not in ingresos_por_medio:
            medio_ab = 'otros'
        ingresos_por_medio[medio_ab] += Decimal(ab.monto or 0)

    for srv in servicios_qs:
        medio_srv = (srv.medio_pago or 'otros').strip().lower()
        if medio_srv not in ingresos_por_medio:
            medio_srv = 'otros'
        monto_srv = Decimal(srv.precio_cobrado or 0) + Decimal(srv.valor_adicionales or 0)
        fecha_op_srv = _fecha_operativa_desde_dt(srv.fecha_hora)
        # El monto completo (sin importar el medio) SIEMPRE cuenta como
        # ingreso del salón por ese medio de pago -- aunque el dinero lo haya
        # recibido el empleado directo y no la caja física, sigue siendo
        # ingreso generado por el negocio con ESE medio. `ingresos_informativos_
        # electronicos_empleado` se conserva aparte solo como dato informativo
        # (cuánto de lo electrónico lo recibió el empleado y no la caja),
        # nunca se resta de ingresos_por_medio.
        ingresos_por_medio[medio_srv] += monto_srv
        if medio_srv != 'efectivo' and fecha_op_srv and _usa_motor_cash_only(fecha_op_srv):
            ingresos_informativos_electronicos_empleado += monto_srv

    try:
        if usar_fact:
            facts_medios_qs = FactLiquidacionEstilistaDia.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
                vigente=True,
            )
            for fact in facts_medios_qs:
                if _usa_motor_cash_only(fact.fecha):
                    # v3: lo unico que realmente sale de caja del negocio es
                    # el efectivo entregado al empleado (nunca electronico,
                    # el negocio ya no tiene esas cuentas). El efectivo que el
                    # empleado transfiere de vuelta NO se suma aquí como
                    # ingreso -- ya está contado en el ingreso del servicio
                    # por su propio medio (nequi/daviplata/otros) más arriba;
                    # sumarlo aquí también lo contaría dos veces. Ese
                    # movimiento queda solo como informativo en
                    # `transferencias_empleados_recibidas`.
                    salidas_por_medio['efectivo'] += Decimal(getattr(fact, 'monto_pagar_entregado', 0) or 0)
                else:
                    salidas_por_medio['efectivo'] += Decimal(fact.pago_efectivo or 0)
                    salidas_por_medio['nequi'] += Decimal(fact.pago_nequi or 0)
                    salidas_por_medio['daviplata'] += Decimal(fact.pago_daviplata or 0)
                    salidas_por_medio['otros'] += Decimal(fact.pago_otros or 0)
                # El pago de espacio (abono_puesto) recibido ese día es un
                # ingreso real de caja, sin importar el régimen -- faltaba
                # contarlo aquí (solo se contaba en la tarjeta "Espacios").
                abono_puesto_fact = Decimal(getattr(fact, 'abono_puesto_dia', 0) or 0)
                if abono_puesto_fact > 0:
                    medio_abono_fact = str(getattr(fact, 'medio_abono_puesto', 'efectivo') or 'efectivo').strip().lower()
                    if medio_abono_fact not in ingresos_por_medio:
                        medio_abono_fact = 'otros'
                    ingresos_por_medio[medio_abono_fact] += abono_puesto_fact
        else:
            estados_pago_qs = EstadoPagoEstilistaDia.objects.filter(
                fecha__gte=fecha_inicio_dt,
                fecha__lte=fecha_fin_dt,
            )
            for ep in estados_pago_qs:
                if _usa_motor_cash_only(ep.fecha):
                    # No se suma aquí `monto_transferir_recibido` como
                    # ingreso -- ya está contado en el ingreso del servicio
                    # por su propio medio más arriba (ver comentario análogo
                    # en la rama `usar_fact`).
                    salidas_por_medio['efectivo'] += Decimal(getattr(ep, 'monto_pagar_entregado', 0) or 0)
                else:
                    salidas_por_medio['efectivo'] += Decimal(ep.pago_efectivo or 0)
                    salidas_por_medio['nequi'] += Decimal(ep.pago_nequi or 0)
                    salidas_por_medio['daviplata'] += Decimal(ep.pago_daviplata or 0)
                    salidas_por_medio['otros'] += Decimal(ep.pago_otros or 0)
                # Ingreso por espacio = cobro normal del día (si no se saltó
                # ese día) + cualquier abono extra voluntario a deuda vieja --
                # antes solo se contaba el abono extra (mismo gap que existía
                # en el propio loop de espacios de reporte_cierre_caja).
                descuento_dia_aplicado_ep = Decimal(0) if getattr(ep, 'skip_descuento_puesto', False) else Decimal(ep.descuento_puesto or 0)
                abono_puesto_ep = descuento_dia_aplicado_ep + Decimal(getattr(ep, 'abono_puesto', 0) or 0)
                if abono_puesto_ep > 0:
                    medio_abono_ep = str(getattr(ep, 'medio_abono_puesto', 'efectivo') or 'efectivo').strip().lower()
                    if medio_abono_ep not in ingresos_por_medio:
                        medio_abono_ep = 'otros'
                    ingresos_por_medio[medio_abono_ep] += abono_puesto_ep
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
    for ab in abonos_consumo_lista:
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
            'cantidad_abonos_consumo_empleado': len(abonos_consumo_lista),
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
            # Régimen "solo efectivo": servicios pagados electrónico donde ese
            # dinero nunca entró a caja del negocio (lo recibió el empleado
            # directo). Informativo -- no forma parte de ingresos/salidas/saldo.
            'ingresos_informativos_electronicos_empleado': float(ingresos_informativos_electronicos_empleado),
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


def _ajustar_saldo_consumo_consolidado(estilista_id, saldo_anterior, saldo_nuevo):
    """
    Ajusta SaldoDeudaPuesto.saldo_consumo (el total consolidado que usa Ajuste
    Diario) por el delta cuando el saldo_pendiente de una DeudaConsumoEmpleado
    cambia FUERA del flujo normal de creacion/abono (edicion o eliminacion de
    factura de consumo, que recalculan saldo_pendiente directamente).
    """
    if not estilista_id:
        return
    delta = Decimal(saldo_nuevo or 0) - Decimal(saldo_anterior or 0)
    if delta == 0:
        return
    saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista_id=estilista_id)
    saldo_obj.saldo_consumo = max(Decimal(saldo_obj.saldo_consumo or 0) + delta, Decimal(0))
    saldo_obj.save()


def _sincronizar_deuda_desde_items(deuda):
    """Sincroniza total_cargo/estado según los items de consumo aún existentes."""
    if not deuda:
        return

    # Los cargos manuales (CARGO-*) no tienen items de venta por diseño; no sincronizar.
    if str(deuda.numero_factura or '').startswith('CARGO-'):
        return

    estilista_id = deuda.estilista_id
    saldo_anterior = Decimal(deuda.saldo_pendiente or 0)

    items_consumo_qs = deuda.ventas_items.filter(tipo_operacion='consumo_empleado')
    total_cargo_real = Decimal(items_consumo_qs.aggregate(total=Sum('total'))['total'] or 0)
    total_abonado = Decimal(deuda.total_abonado or 0)

    # Si ya no existen items de la factura, la deuda no debe seguir en cartera.
    # Si no tuvo abonos se elimina; si tuvo abonos se marca cancelada en cero para auditoria.
    if total_cargo_real <= 0:
        if total_abonado <= 0:
            deuda.delete()
            _ajustar_saldo_consumo_consolidado(estilista_id, saldo_anterior, Decimal(0))
            return
        deuda.total_cargo = Decimal(0)
        deuda.saldo_pendiente = Decimal(0)
        deuda.estado = 'cancelado'
        deuda.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado'])
        _ajustar_saldo_consumo_consolidado(estilista_id, saldo_anterior, Decimal(0))
        return

    deuda.total_cargo = total_cargo_real
    _recalcular_estado_deuda(deuda)
    deuda.save(update_fields=['total_cargo', 'saldo_pendiente', 'estado'])
    _ajustar_saldo_consumo_consolidado(estilista_id, saldo_anterior, Decimal(deuda.saldo_pendiente or 0))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_cargo_manual_empleado(request):
    """Crea un cargo manual de consumo para un empleado sin afectar inventario."""
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'cartera', 'No tienes permiso para crear cargos manuales.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except Exception:
        return Response({'error': 'Empleado no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        monto = Decimal(str(request.data.get('monto') or 0))
    except Exception:
        return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    if monto <= 0:
        return Response({'error': 'El monto debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)

    motivo = (request.data.get('motivo') or '').strip()
    if not motivo:
        return Response({'error': 'El motivo del cargo es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_raw = (request.data.get('fecha') or '').strip()
    ahora = timezone.now()
    if fecha_raw:
        try:
            fecha_dt = datetime.strptime(fecha_raw, '%Y-%m-%d')
            fecha_dt = fecha_dt.replace(hour=12, minute=0, second=0)
            if timezone.is_naive(fecha_dt):
                fecha_dt = timezone.make_aware(fecha_dt, timezone.get_current_timezone())
            ahora = fecha_dt
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    timestamp_str = timezone.localtime(ahora).strftime('%Y%m%d%H%M%S')
    numero_factura = f"CARGO-{estilista_id}-{timestamp_str}"
    intentos = 0
    while DeudaConsumoEmpleado.objects.filter(numero_factura=numero_factura).exists():
        intentos += 1
        numero_factura = f"CARGO-{estilista_id}-{timestamp_str}-{intentos}"

    try:
        with transaction.atomic():
            deuda = DeudaConsumoEmpleado.objects.create(
                estilista=estilista,
                numero_factura=numero_factura,
                total_cargo=monto,
                total_abonado=Decimal(0),
                saldo_pendiente=monto,
                estado='pendiente',
                fecha_hora=ahora,
                usuario=request.user,
                notas=motivo,
            )
            # Incrementa saldo_consumo consolidado
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj.saldo_consumo = max(Decimal(saldo_obj.saldo_consumo or 0) + monto, Decimal(0))
            saldo_obj.save()
    except Exception as e:
        logger.exception('Error creando cargo manual empleado')
        return Response({'error': f'No se pudo crear el cargo: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            'ok': True,
            'deuda_id': deuda.id,
            'numero_factura': deuda.numero_factura,
            'monto': float(monto),
            'estilista_nombre': estilista.nombre,
            'motivo': motivo,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_consumo_empleado(request):
    """Resumen de deudas por consumo de empleado en un rango de fechas."""
    _requerir_permiso_ui(request.user, 'reportes', 'view', 'cartera', 'No tienes acceso a consumo de empleado y cartera.')

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
        total_cargo = Decimal(deuda.total_cargo or 0)
        total_abonado_real = Decimal(deuda.abonos.aggregate(total=Sum('monto'))['total'] or 0)
        saldo = max(total_cargo - total_abonado_real, Decimal(0))

        estado_real = 'pendiente'
        if saldo <= 0:
            estado_real = 'cancelado'
        elif total_abonado_real > 0:
            estado_real = 'parcial'

        # Normaliza datos persistidos para evitar que la UI muestre saldos en 0 incorrectos.
        total_abonado_db = Decimal(deuda.total_abonado or 0)
        saldo_db = Decimal(deuda.saldo_pendiente or 0)
        if (
            abs(total_abonado_db - total_abonado_real) > Decimal('0.009')
            or abs(saldo_db - saldo) > Decimal('0.009')
            or str(deuda.estado or '') != estado_real
        ):
            deuda.total_abonado = total_abonado_real
            deuda.saldo_pendiente = saldo
            deuda.estado = estado_real
            deuda.save(update_fields=['total_abonado', 'saldo_pendiente', 'estado'])

        tiene_abono = int(getattr(deuda, 'abonos_count', 0) or 0) > 0

        if saldo <= Decimal('0.5') and not tiene_abono:
            continue
        # Allow manual charges (CARGO-*) even without linked product items
        es_cargo_manual = str(deuda.numero_factura or '').startswith('CARGO-')
        if not es_cargo_manual and not deuda.ventas_items.filter(tipo_operacion='consumo_empleado').exists():
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
            'notas': deuda.notas or '',
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
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'cartera', 'No tienes permiso para registrar abonos de cartera.')

    estilista_id = request.data.get('estilista_id')
    deuda_id = request.data.get('deuda_id')
    monto = request.data.get('monto')
    medio_pago = (request.data.get('medio_pago') or 'efectivo').strip().lower()
    notas = request.data.get('notas')
    fecha_raw = (request.data.get('fecha') or '').strip()

    if medio_pago not in {'nequi', 'daviplata', 'efectivo', 'otros'}:
        return Response({'error': 'Medio de pago inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    fecha_efectiva = timezone.localdate()
    if fecha_raw:
        try:
            fecha_efectiva = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except Exception:
            fecha_efectiva = timezone.localdate()
    if medio_pago != 'efectivo' and _usa_motor_cash_only(fecha_efectiva):
        return Response(
            {'error': 'Desde el régimen de solo efectivo, los abonos de cartera solo pueden ser en efectivo.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

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
    origen_liquidacion_fecha=None,
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
        if origen_liquidacion_fecha is not None:
            create_data['origen_liquidacion_fecha'] = origen_liquidacion_fecha

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

    # Decrementar saldo_consumo consolidado por el total efectivamente aplicado
    total_aplicado = Decimal(monto_decimal or 0) - restante
    if total_aplicado > 0:
        try:
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj.saldo_consumo = max(Decimal(saldo_obj.saldo_consumo or 0) - total_aplicado, Decimal(0))
            saldo_obj.save()
        except Exception:
            pass

    return aplicaciones, restante


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def editar_abono_consumo_empleado(request, abono_id):
    """Permite corregir un abono registrado por error y recalcula la deuda asociada."""
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'cartera', 'No tienes permiso para editar abonos de cartera.')

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
                    'aplica_comision_ventas': True,
                    'notas': x.notas,
                    **_campos_liquidacion_v3_dia(x),
                }
                for x in qs.order_by('fecha', 'estilista_id')
            ]

            if items:
                fact_map = {
                    (int(f.estilista_id), f.fecha): f
                    for f in FactLiquidacionEstilistaDia.objects.filter(
                        vigente=True,
                        fecha__gte=fecha_inicio,
                        fecha__lte=fecha_fin,
                    )
                }
                for item in items:
                    key = (int(item['estilista_id']), datetime.strptime(item['fecha'], '%Y-%m-%d').date())
                    fact = fact_map.get(key)
                    if fact:
                        item['aplica_comision_ventas'] = bool(getattr(fact, 'aplica_comision_ventas', True))

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
                    'aplica_comision_ventas': True,
                    'notas': x.notas,
                    **_campos_liquidacion_v3_dia(x),
                }
                for x in EstadoPagoEstilistaDia.objects.filter(fecha=fecha)
            ]

            if items:
                fact_map = {
                    int(f.estilista_id): f
                    for f in FactLiquidacionEstilistaDia.objects.filter(vigente=True, fecha=fecha)
                }
                for item in items:
                    fact = fact_map.get(int(item['estilista_id']))
                    if fact:
                        item['aplica_comision_ventas'] = bool(getattr(fact, 'aplica_comision_ventas', True))
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
                        'aplica_comision_ventas': True,
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


def _liquidar_dia_v2_core(request):
    """
    Dispatcher: decide el motor de liquidacion segun la fecha del body (ver
    `_usa_motor_cash_only`). No cambia la ruta de API ni el contrato basico
    de la respuesta -- las claves nuevas del regimen "solo efectivo" se
    agregan sin quitar las que ya lee el frontend actual.
    """
    fecha_dia = None
    try:
        fecha_str = (request.data.get('fecha') or '').strip()
        fecha_dia = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except Exception:
        fecha_dia = None

    if fecha_dia is not None and _usa_motor_cash_only(fecha_dia):
        return _liquidar_dia_v3_core(request)
    return _liquidar_dia_v2_core_legacy(request)


def _calcular_preview_liquidacion_v3(estilista, fecha, data):
    """
    Cálculo puro (sin escribir nada en la base de datos) del régimen "solo
    efectivo" para un estilista+fecha, a partir de un dict-like `data`
    (request.data en el POST de liquidar, o los query params del GET de
    vista previa). Lo usan tanto `_liquidar_dia_v3_core` (que después SÍ
    persiste) como `liquidacion_recibo_imprimible` (que solo muestra el
    resultado antes de confirmar) -- así ambos siempre calculan exactamente
    lo mismo, sin que puedan divergir.

    No aplica el abono de consumo (FIFO) ni guarda nada -- eso lo hace quien
    llama, solo si de verdad va a confirmar la liquidación.
    """
    def _to_decimal(v):
        try:
            d = Decimal(str(v if v is not None else 0))
            return max(d, Decimal(0))
        except Exception:
            return Decimal(0)

    aplica_comision_ventas = _to_bool_flag(data.get('aplica_comision_ventas'), default=True)
    skip_descuento_puesto = _to_bool_flag(data.get('skip_descuento_puesto'), default=False)
    saltar_descuento_consumo = _to_bool_flag(data.get('saltar_descuento_consumo'), default=False)
    puesto_modo = str(data.get('puesto_modo') or 'fijo').strip().lower()
    if puesto_modo not in {'fijo', 'porcentaje'}:
        puesto_modo = 'fijo'
    puesto_porcentaje = _to_decimal(data.get('puesto_porcentaje'))
    if puesto_porcentaje > Decimal(100):
        puesto_porcentaje = Decimal(100)
    forzar_reemplazo_dia = _to_bool_flag(data.get('forzar_reemplazo_dia'), default=False)
    abono_puesto_extra = _to_decimal(data.get('abono_puesto'))
    consumo_monto_solicitado = _to_decimal(data.get('consumo_monto'))
    deuda_ids_consumo = data.get('deuda_ids') or []
    if not isinstance(deuda_ids_consumo, list):
        deuda_ids_consumo = []
    notas = str(data.get('notas') or '').strip()[:255]

    calc = calcular_liquidacion_dia_estilista(estilista, fecha, aplica_comision_ventas=aplica_comision_ventas)

    ganancia_efectivo = calc['ganancia_efectivo_dia']
    ganancia_electronica = calc['ganancia_electronica_dia']
    comision_producto_dia = calc['comision_producto_dia']
    reparto_pendiente = calc['reparto_establecimiento_electronico_pendiente']

    descuento_puesto_calculado = calc['descuento_puesto']
    if puesto_modo == 'porcentaje':
        base_pct = ganancia_efectivo + ganancia_electronica
        descuento_puesto_calculado = max((base_pct * puesto_porcentaje) / Decimal(100), Decimal(0))
    descuento_puesto_aplicado_hoy = Decimal(0) if skip_descuento_puesto else descuento_puesto_calculado

    saldo_obj_consumo, _created_saldo = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
    saldo_consumo_antes = Decimal(saldo_obj_consumo.saldo_consumo or 0)
    if saltar_descuento_consumo:
        monto_a_aplicar_consumo = Decimal(0)
    else:
        monto_a_aplicar_consumo = min(max(consumo_monto_solicitado, Decimal(0)), saldo_consumo_antes)

    # Vale (deuda entre empleados): a diferencia de puesto/consumo no hay un
    # monto parcial a elegir -- si no se salta, se intenta descontar TODO lo
    # pendiente de una vez (mismo criterio que ya usa el motor para las
    # demás deducciones: se aplican a valor pleno, el faltante se convierte
    # en transferencia). `saldo_obj_consumo` ya sirvió para get_or_create
    # el registro de SaldoDeudaPuesto; se reutiliza el mismo objeto.
    skip_descuento_vale = _to_bool_flag(data.get('skip_descuento_vale'), default=False)
    saldo_vale_antes = Decimal(saldo_obj_consumo.saldo_vale or 0)
    monto_a_aplicar_vale = Decimal(0) if skip_descuento_vale else saldo_vale_antes

    deuda_anterior_puesto = Decimal(0)
    ultimo_estado = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha__lt=fecha).order_by('-fecha').first()
    if ultimo_estado:
        deuda_anterior_puesto = Decimal(ultimo_estado.saldo_puesto_pendiente or 0)

    if skip_descuento_puesto:
        deuda_total_puesto = deuda_anterior_puesto + descuento_puesto_calculado
    else:
        deuda_total_puesto = deuda_anterior_puesto

    # Abono voluntario a la deuda de puesto acumulada de días anteriores (el
    # empleado decide pagar de más hoy, además del cobro normal del día).
    # Se topa a lo realmente adeudado y se descuenta del efectivo disponible
    # igual que cualquier otra deducción -- mismo tratamiento que ya tiene el
    # abono de consumo (`monto_a_aplicar_consumo`) unas líneas arriba.
    abono_puesto_extra_aplicado = min(max(abono_puesto_extra, Decimal(0)), deuda_total_puesto)

    disponible = ganancia_efectivo + comision_producto_dia
    total_deducciones_dia = (
        descuento_puesto_aplicado_hoy + monto_a_aplicar_consumo + monto_a_aplicar_vale
        + reparto_pendiente + abono_puesto_extra_aplicado
    )
    saldo_neto = disponible - total_deducciones_dia

    if saldo_neto < 0:
        monto_transferir_empleado = -saldo_neto
        monto_pagar_establecimiento = Decimal(0)
    else:
        monto_transferir_empleado = Decimal(0)
        monto_pagar_establecimiento = saldo_neto

    monto_transferir_recibido = min(
        _to_decimal(data.get('monto_transferir_recibido', monto_transferir_empleado)),
        monto_transferir_empleado,
    )
    monto_pagar_entregado = min(
        _to_decimal(data.get('monto_pagar_entregado', monto_pagar_establecimiento)),
        monto_pagar_establecimiento,
    )

    abono_puesto_previo_dia = Decimal(0)
    if not forzar_reemplazo_dia:
        estado_existente_dia = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
        if estado_existente_dia:
            abono_puesto_previo_dia = Decimal(estado_existente_dia.abono_puesto or 0)
    abono_puesto_total = abono_puesto_extra_aplicado if forzar_reemplazo_dia else (abono_puesto_previo_dia + abono_puesto_extra_aplicado)

    abono_aplicado_total_puesto = min(abono_puesto_total, deuda_total_puesto)
    saldo_puesto_cierre = max(deuda_total_puesto - abono_aplicado_total_puesto, Decimal(0))

    # Estimado de cierre de consumo para la vista previa (sin aplicar el FIFO
    # de verdad todavía) -- el total que queda es matemáticamente el mismo,
    # el FIFO solo decide CUÁLES facturas se pagan primero.
    saldo_consumo_estimado_cierre = max(saldo_consumo_antes - monto_a_aplicar_consumo, Decimal(0))

    return {
        'calc': calc,
        'ganancia_efectivo': ganancia_efectivo,
        'ganancia_electronica': ganancia_electronica,
        'comision_producto_dia': comision_producto_dia,
        'reparto_pendiente': reparto_pendiente,
        'descuento_puesto_calculado': descuento_puesto_calculado,
        'descuento_puesto_aplicado_hoy': descuento_puesto_aplicado_hoy,
        'aplica_comision_ventas': aplica_comision_ventas,
        'skip_descuento_puesto': skip_descuento_puesto,
        'saltar_descuento_consumo': saltar_descuento_consumo,
        'puesto_modo': puesto_modo,
        'puesto_porcentaje': puesto_porcentaje,
        'forzar_reemplazo_dia': forzar_reemplazo_dia,
        'abono_puesto_extra': abono_puesto_extra_aplicado,
        'abono_puesto_extra_solicitado': abono_puesto_extra,
        'consumo_monto_solicitado': consumo_monto_solicitado,
        'deuda_ids_consumo': deuda_ids_consumo,
        'notas': notas,
        'saldo_obj_consumo': saldo_obj_consumo,
        'saldo_consumo_antes': saldo_consumo_antes,
        'monto_a_aplicar_consumo': monto_a_aplicar_consumo,
        'saldo_consumo_estimado_cierre': saldo_consumo_estimado_cierre,
        'skip_descuento_vale': skip_descuento_vale,
        'saldo_vale_antes': saldo_vale_antes,
        'monto_a_aplicar_vale': monto_a_aplicar_vale,
        'saldo_vale_estimado_cierre': max(saldo_vale_antes - monto_a_aplicar_vale, Decimal(0)),
        'disponible': disponible,
        'total_deducciones_dia': total_deducciones_dia,
        'monto_transferir_empleado': monto_transferir_empleado,
        'monto_transferir_recibido': monto_transferir_recibido,
        'monto_pagar_establecimiento': monto_pagar_establecimiento,
        'monto_pagar_entregado': monto_pagar_entregado,
        'deuda_anterior_puesto': deuda_anterior_puesto,
        'deuda_total_puesto': deuda_total_puesto,
        'abono_puesto_previo_dia': abono_puesto_previo_dia,
        'abono_puesto_total': abono_puesto_total,
        'abono_aplicado_total_puesto': abono_aplicado_total_puesto,
        'saldo_puesto_cierre': saldo_puesto_cierre,
    }


def _liquidar_dia_v3_core(request):
    """
    Motor de liquidacion para el regimen "solo efectivo": el negocio ya no
    recibe Nequi/Daviplata/transferencias en su cuenta -- solo efectivo. Del
    efectivo ganado (mas la comision de producto, que tampoco es efectivo
    fisico en mano del empleado pero ya entro a caja) se descuentan puesto,
    consumo y el % de establecimiento pendiente por pagos electronicos. Si el
    efectivo no alcanza, el faltante es lo que el empleado debe transferir;
    si sobra, es lo que el negocio le debe entregar en efectivo.

    Reutiliza TAL CUAL la logica de arrastre de deuda de puesto y el motor
    FIFO de deuda de consumo (`_aplicar_abonos_consumo_interno`) -- solo
    cambia que dispara cada deduccion y con que medio de pago (siempre
    efectivo, porque el negocio ya no tiene cuentas electronicas propias).
    """
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

    medio_abono_puesto = (request.data.get('medio_abono_puesto') or 'efectivo').strip().lower()
    if medio_abono_puesto != 'efectivo':
        return Response(
            {'error': 'Desde el régimen de solo efectivo, los abonos de puesto solo pueden ser en efectivo.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        prev = _calcular_preview_liquidacion_v3(estilista, fecha, request.data)
    except Exception as e:
        return Response({'error': f'No se pudo calcular la liquidación: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    calc = prev['calc']
    ganancia_efectivo = prev['ganancia_efectivo']
    ganancia_electronica = prev['ganancia_electronica']
    comision_producto_dia = prev['comision_producto_dia']
    reparto_pendiente = prev['reparto_pendiente']
    descuento_puesto_calculado = prev['descuento_puesto_calculado']
    descuento_puesto_aplicado_hoy = prev['descuento_puesto_aplicado_hoy']
    saltar_descuento_consumo = prev['saltar_descuento_consumo']
    skip_descuento_puesto = prev['skip_descuento_puesto']
    aplica_comision_ventas = prev['aplica_comision_ventas']
    puesto_modo = prev['puesto_modo']
    puesto_porcentaje = prev['puesto_porcentaje']
    forzar_reemplazo_dia = prev['forzar_reemplazo_dia']
    abono_puesto_extra = prev['abono_puesto_extra']
    consumo_monto_solicitado = prev['consumo_monto_solicitado']
    deuda_ids_consumo = prev['deuda_ids_consumo']
    notas = prev['notas']
    saldo_obj_consumo = prev['saldo_obj_consumo']
    saldo_consumo_antes = prev['saldo_consumo_antes']
    monto_a_aplicar_consumo = prev['monto_a_aplicar_consumo']
    skip_descuento_vale = prev['skip_descuento_vale']
    saldo_vale_antes = prev['saldo_vale_antes']
    monto_a_aplicar_vale = prev['monto_a_aplicar_vale']
    monto_transferir_empleado = prev['monto_transferir_empleado']
    monto_transferir_recibido = prev['monto_transferir_recibido']
    monto_pagar_establecimiento = prev['monto_pagar_establecimiento']
    monto_pagar_entregado = prev['monto_pagar_entregado']
    deuda_anterior_puesto = prev['deuda_anterior_puesto']
    deuda_total_puesto = prev['deuda_total_puesto']
    abono_puesto_previo_dia = prev['abono_puesto_previo_dia']
    abono_puesto_total = prev['abono_puesto_total']
    abono_aplicado_total_puesto = prev['abono_aplicado_total_puesto']
    saldo_puesto_cierre = prev['saldo_puesto_cierre']
    total_deducciones_dia = prev['total_deducciones_dia']
    disponible = prev['disponible']

    # ---- aplicar el abono real de consumo (motor FIFO existente, intacto) ----
    aplicaciones_consumo = []
    sobrante_consumo = Decimal(0)
    if monto_a_aplicar_consumo > 0:
        try:
            with transaction.atomic():
                aplicaciones_consumo, sobrante_consumo = _aplicar_abonos_consumo_interno(
                    estilista=estilista,
                    monto_decimal=monto_a_aplicar_consumo,
                    medio_pago='efectivo',
                    usuario=request.user,
                    notas=notas or f'Liquidación (solo efectivo) {fecha}',
                    deuda_ids=deuda_ids_consumo,
                    origen_liquidacion_fecha=fecha,
                )
        except Exception as e:
            return Response({'error': f'No se pudo aplicar el abono de consumo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    # ---- aplicar el descuento real de Vale (motor FIFO análogo al de consumo) ----
    aplicaciones_vale = []
    sobrante_vale = Decimal(0)
    if monto_a_aplicar_vale > 0:
        try:
            with transaction.atomic():
                aplicaciones_vale, sobrante_vale = _aplicar_abonos_vale_interno(
                    estilista=estilista,
                    monto_decimal=monto_a_aplicar_vale,
                    usuario=request.user,
                    notas=notas or f'Liquidación (solo efectivo) {fecha}',
                    origen_liquidacion_fecha=fecha,
                )
        except Exception as e:
            return Response({'error': f'No se pudo aplicar el descuento de Vale: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

    saldo_obj_consumo.refresh_from_db()
    saldo_consumo_cierre = Decimal(saldo_obj_consumo.saldo_consumo or 0)
    saldo_vale_cierre = Decimal(saldo_obj_consumo.saldo_vale or 0)

    pendiente_transferencia_empleado = max(monto_transferir_empleado - monto_transferir_recibido, Decimal(0))
    pendiente_pago_empleado_efectivo = max(monto_pagar_establecimiento - monto_pagar_entregado, Decimal(0))

    if pendiente_transferencia_empleado > 0 or pendiente_pago_empleado_efectivo > 0:
        estado_resultante = 'pendiente'
    elif saldo_puesto_cierre > 0 or saldo_consumo_cierre > 0 or saldo_vale_cierre > 0:
        estado_resultante = 'debe'
    else:
        estado_resultante = 'cancelado'

    estado_diaria, _created_dia = EstadoPagoEstilistaDia.objects.get_or_create(estilista=estilista, fecha=fecha)
    estado_anterior = estado_diaria.estado

    estado_diaria.ganancias_totales = calc['ganancias_totales']
    estado_diaria.descuento_puesto = descuento_puesto_calculado
    estado_diaria.total_pagable = calc['total_pagable']
    estado_diaria.neto_dia = calc['total_pagable']
    # Los campos legacy pago_efectivo/nequi/daviplata/otros ya no representan
    # "lo que pago el negocio" en este regimen -- quedan en 0 para no
    # confundir reportes que aun no migraron (Fase 4 los reinterpreta).
    estado_diaria.pago_efectivo = Decimal(0)
    estado_diaria.pago_nequi = Decimal(0)
    estado_diaria.pago_daviplata = Decimal(0)
    estado_diaria.pago_otros = Decimal(0)
    estado_diaria.abono_puesto = abono_puesto_total
    estado_diaria.medio_abono_puesto = 'efectivo'
    estado_diaria.saldo_puesto_pendiente = saldo_puesto_cierre
    estado_diaria.pendiente_puesto = saldo_puesto_cierre
    estado_diaria.skip_descuento_puesto = skip_descuento_puesto
    estado_diaria.saltar_descuento_consumo = saltar_descuento_consumo
    estado_diaria.skip_descuento_vale = skip_descuento_vale
    estado_diaria.descuento_vale_dia = monto_a_aplicar_vale
    estado_diaria.ganancia_efectivo_dia = ganancia_efectivo
    estado_diaria.ganancia_electronica_dia = ganancia_electronica
    estado_diaria.ganancia_electronica_nequi = calc['ganancia_electronica_nequi']
    estado_diaria.ganancia_electronica_daviplata = calc['ganancia_electronica_daviplata']
    estado_diaria.ganancia_electronica_otros = calc['ganancia_electronica_otros']
    estado_diaria.comision_producto_dia = comision_producto_dia
    estado_diaria.reparto_establecimiento_electronico_pendiente = reparto_pendiente
    estado_diaria.descuento_consumo_dia = monto_a_aplicar_consumo
    estado_diaria.total_deducciones_dia = total_deducciones_dia
    estado_diaria.monto_transferir_empleado = monto_transferir_empleado
    estado_diaria.monto_transferir_recibido = monto_transferir_recibido
    estado_diaria.monto_pagar_establecimiento = monto_pagar_establecimiento
    estado_diaria.monto_pagar_entregado = monto_pagar_entregado
    estado_diaria.motor_calculo = 'v3_efectivo'
    estado_diaria.notas = notas
    estado_diaria.usuario_liquida = request.user
    estado_diaria.estado = estado_resultante
    estado_diaria.save()

    try:
        hay_mas_reciente = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha__gt=fecha).exists()
        if not hay_mas_reciente:
            saldo_obj_puesto, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj_puesto.saldo = max(saldo_puesto_cierre, Decimal(0))
            saldo_obj_puesto.save()
    except Exception:
        pass

    hubo_movimiento = (
        monto_transferir_recibido > 0 or monto_pagar_entregado > 0
        or abono_puesto_extra > 0 or monto_a_aplicar_consumo > 0 or monto_a_aplicar_vale > 0
    )
    if hubo_movimiento:
        try:
            EstadoPagoEstilistaHistorial.objects.create(
                estilista=estilista,
                fecha=fecha,
                estado_anterior=estado_anterior,
                estado_nuevo=estado_resultante,
                notas=notas,
                usuario=request.user,
                monto_liquidado=monto_transferir_recibido + monto_pagar_entregado,
                abono_puesto=abono_puesto_extra,
                medio_abono_puesto='efectivo',
                pendiente_puesto=saldo_puesto_cierre,
                descuento_consumo_dia=monto_a_aplicar_consumo,
                descuento_vale_dia=monto_a_aplicar_vale,
                monto_transferir_empleado=monto_transferir_empleado,
                monto_pagar_establecimiento=monto_pagar_establecimiento,
                motor_calculo='v3_efectivo',
            )
        except Exception:
            pass

    _upsert_fact_liquidacion_dia(
        estilista=estilista,
        fecha=fecha,
        calc=calc,
        pago_efectivo=Decimal(0),
        pago_nequi=Decimal(0),
        pago_daviplata=Decimal(0),
        pago_otros=Decimal(0),
        abono_puesto=abono_puesto_total,
        medio_abono_puesto='efectivo',
        aplica_comision_ventas=aplica_comision_ventas,
        deuda_anterior=deuda_anterior_puesto,
        deuda_cierre=saldo_puesto_cierre,
        pendiente_pago=pendiente_pago_empleado_efectivo,
        estado_liquidacion=estado_resultante,
        forzar_reemplazo_dia=forzar_reemplazo_dia,
        usuario=request.user,
        notas=notas,
        origen='engine_v3_efectivo',
        saltar_descuento_consumo=saltar_descuento_consumo,
        descuento_consumo_dia=monto_a_aplicar_consumo,
        descuento_vale_dia=monto_a_aplicar_vale,
        total_deducciones_dia=total_deducciones_dia,
        monto_transferir_empleado=monto_transferir_empleado,
        monto_transferir_recibido=monto_transferir_recibido,
        monto_pagar_establecimiento=monto_pagar_establecimiento,
        monto_pagar_entregado=monto_pagar_entregado,
    )

    return Response({
        'success': True,
        'motor_calculo': 'v3_efectivo',
        'estilista': {'id': estilista.id, 'nombre': estilista.nombre},
        'fecha': fecha.strftime('%Y-%m-%d'),
        'liquidacion': {
            'ganancias_totales': float(calc['ganancias_totales']),
            'descuento_puesto': float(descuento_puesto_calculado),
            'total_pagable': float(calc['total_pagable']),
            'pendiente_liquidacion': float(pendiente_pago_empleado_efectivo),
            'aplica_comision_ventas': bool(aplica_comision_ventas),
        },
        'pagos': {
            'efectivo': float(ganancia_efectivo),
            'nequi': float(calc['ganancia_electronica_nequi']),
            'daviplata': float(calc['ganancia_electronica_daviplata']),
            'otros': float(calc['ganancia_electronica_otros']),
            'total': float(ganancia_efectivo + ganancia_electronica),
        },
        'puesto': {
            'descuento': float(descuento_puesto_calculado),
            'abono': float(abono_puesto_total),
            'abono_operacion': float(abono_puesto_extra),
            'abono_previo_dia': float(abono_puesto_previo_dia),
            'medio_abono': 'efectivo',
            'modo_cobro': puesto_modo,
            'porcentaje_cobro': float(puesto_porcentaje),
            'deuda_anterior': float(deuda_anterior_puesto),
            'deuda_total': float(deuda_total_puesto),
            'abono_aplicado': float(abono_aplicado_total_puesto),
            'saldo_pendiente': float(saldo_puesto_cierre),
        },
        'efectivo': {
            'ganado_efectivo': float(ganancia_efectivo),
            'ganado_electronico': float(ganancia_electronica),
            'ganado_electronico_detalle': {
                'nequi': float(calc['ganancia_electronica_nequi']),
                'daviplata': float(calc['ganancia_electronica_daviplata']),
                'otros': float(calc['ganancia_electronica_otros']),
            },
            'comision_producto': float(comision_producto_dia),
            'disponible_para_deducciones': float(disponible),
        },
        'deducciones': {
            'puesto': {
                'aplicado_hoy': float(descuento_puesto_aplicado_hoy),
                'diferido': bool(skip_descuento_puesto),
                'monto_calculado': float(descuento_puesto_calculado),
            },
            'consumo': {
                'aplicado_hoy': float(monto_a_aplicar_consumo),
                'diferido': bool(saltar_descuento_consumo),
                'saldo_antes': float(saldo_consumo_antes),
                'saldo_despues': float(saldo_consumo_cierre),
            },
            'vale': {
                'aplicado_hoy': float(monto_a_aplicar_vale),
                'diferido': bool(skip_descuento_vale),
                'saldo_antes': float(saldo_vale_antes),
                'saldo_despues': float(saldo_vale_cierre),
            },
            'total': float(total_deducciones_dia),
        },
        'liquidacion_efectivo': {
            'monto_transferir_empleado': float(monto_transferir_empleado),
            'monto_transferir_recibido': float(monto_transferir_recibido),
            'pendiente_transferencia_empleado': float(pendiente_transferencia_empleado),
            'monto_pagar_establecimiento': float(monto_pagar_establecimiento),
            'monto_pagar_entregado': float(monto_pagar_entregado),
            'pendiente_pago_empleado_efectivo': float(pendiente_pago_empleado_efectivo),
        },
        'reparto_establecimiento_electronico_pendiente': float(reparto_pendiente),
        'deuda_consumo': {
            'anterior': float(saldo_consumo_antes),
            'abono_aplicado': float(monto_a_aplicar_consumo),
            'sobrante': float(sobrante_consumo),
            'cierre': float(saldo_consumo_cierre),
            'aplicaciones': aplicaciones_consumo,
        },
        'deuda_vale': {
            'anterior': float(saldo_vale_antes),
            'abono_aplicado': float(monto_a_aplicar_vale),
            'sobrante': float(sobrante_vale),
            'cierre': float(saldo_vale_cierre),
            'aplicaciones': aplicaciones_vale,
        },
        'estado': estado_resultante,
        'tabla_diaria_no_disponible': False,
        'guardado_legacy_sql': False,
    })


def _liquidar_dia_v2_core_legacy(request):
    """
    LIQUIDADOR SIMPLIFICADO Y CLARO (motor legacy, vigente para fechas
    anteriores a LIQUIDACION_CASH_ONLY_DESDE -- Nequi/Daviplata eran ingreso
    del negocio).

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
    puesto_modo = str(request.data.get('puesto_modo') or 'fijo').strip().lower()
    if puesto_modo not in {'fijo', 'porcentaje'}:
        puesto_modo = 'fijo'
    puesto_porcentaje = _to_decimal(request.data.get('puesto_porcentaje'))
    if puesto_porcentaje > Decimal(100):
        puesto_porcentaje = Decimal(100)
    forzar_reemplazo_dia_raw = request.data.get('forzar_reemplazo_dia', False)
    if isinstance(forzar_reemplazo_dia_raw, str):
        forzar_reemplazo_dia = forzar_reemplazo_dia_raw.strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}
    else:
        forzar_reemplazo_dia = bool(forzar_reemplazo_dia_raw)
    skip_descuento_puesto_raw = request.data.get('skip_descuento_puesto', False)
    if isinstance(skip_descuento_puesto_raw, str):
        skip_descuento_puesto = skip_descuento_puesto_raw.strip().lower() in {'1', 'true', 'si', 'sí', 'yes'}
    else:
        skip_descuento_puesto = bool(skip_descuento_puesto_raw)
    # DEBUG: Log para verificar que se recibe correctamente
    logger = logging.getLogger(__name__)
    logger.info(f"skip_descuento_puesto: {skip_descuento_puesto} (raw: {skip_descuento_puesto_raw})")

    medio_abono_puesto = (request.data.get('medio_abono_puesto') or 'efectivo').strip().lower()
    aplica_comision_ventas = _to_bool_flag(request.data.get('aplica_comision_ventas'), default=True)
    if medio_abono_puesto not in {'efectivo', 'nequi', 'daviplata', 'otros'}:
        medio_abono_puesto = 'efectivo'
    notas = request.data.get('notas', '').strip()[:255]

    total_pagado = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
    
    # ============ [1] CALCULAR LIQUIDACIÓN ============
    try:
        calc = calcular_liquidacion_dia_estilista(estilista, fecha, aplica_comision_ventas=aplica_comision_ventas)
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
    if puesto_modo == 'porcentaje':
        descuento_override = max((ganancias * puesto_porcentaje) / Decimal(100), Decimal(0))
        calc['descuento_puesto'] = descuento_override
        calc['total_pagable'] = max(ganancias - descuento_override, Decimal(0))
    descuento = calc['descuento_puesto']
    pagable = calc['total_pagable']

    # ============ LÓGICA SKIP_DESCUENTO_PUESTO ============
    # Si skip_descuento_puesto es True, NO descontar puesto del pago.
    # El empleado recibe el 100% ganado, y el descuento se suma a la deuda.
    if skip_descuento_puesto:
        pagable = ganancias  # Pago sin descuento
        abono_operacion_puesto = Decimal(0)  # NO permitir abono ese día
    
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
        logger = logging.getLogger(__name__)
        logger.error(f"ERROR VALIDACIÓN: total_pagado={float(total_pagado):.2f} > pagable={float(pagable):.2f}")
        logger.error(f"ganancias={float(ganancias):.2f}, descuento={float(descuento):.2f}, skip_descuento_puesto={skip_descuento_puesto}")
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
    # Si skip=True (dejar pendiente): el descuento NO se cobró hoy → se suma como nueva deuda.
    # Si skip=False (cobrar hoy): el descuento ya fue cobrado vía reducción del pago
    #   (pagable = ganancias - descuento), por lo que NO genera deuda nueva.
    if skip_descuento_puesto:
        deuda_total_puesto = deuda_anterior_puesto + descuento
    else:
        deuda_total_puesto = deuda_anterior_puesto
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
        estado_diaria.skip_descuento_puesto = skip_descuento_puesto
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

        # Sincronizar saldo consolidado con el resultado de esta liquidación.
        # _liquidar_dia_v2_core calcula saldo_puesto correctamente usando la cadena de días,
        # así que ese valor es autoritativo. Lo usamos si este día es el más reciente.
        try:
            hay_mas_reciente = EstadoPagoEstilistaDia.objects.filter(
                estilista=estilista,
                fecha__gt=estado_diaria.fecha,
            ).exists()
            if not hay_mas_reciente:
                saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
                saldo_obj.saldo = max(saldo_puesto, Decimal(0))
                saldo_obj.save()
        except Exception:
            pass

    except (OperationalError, ProgrammingError) as e:
        # Compatibilidad: intentar persistencia SQL en esquema legacy para no perder datos.
        logger.error(f"Error saving EstadoPagoEstilistaDia (ORM): {str(e)}")
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
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'estado_pago_estilista_dia'
                    """
                )
                columnas_disponibles = {row[0] for row in cursor.fetchall()}
                if 'skip_descuento_puesto' not in columnas_disponibles:
                    logger.warning('Tabla legacy sin columna skip_descuento_puesto; se guardará sin ese campo.')

                columnas_update = [
                    ('estado', estado_resultante),
                    ('pago_efectivo', pago_efectivo),
                    ('pago_nequi', pago_nequi),
                    ('pago_daviplata', pago_daviplata),
                    ('pago_otros', pago_otros),
                    ('abono_puesto', abono_puesto),
                ]
                if 'medio_abono_puesto' in columnas_disponibles:
                    columnas_update.append(('medio_abono_puesto', medio_abono_puesto))
                if 'saldo_puesto_pendiente' in columnas_disponibles:
                    columnas_update.append(('saldo_puesto_pendiente', saldo_puesto))
                if 'pendiente_puesto' in columnas_disponibles:
                    columnas_update.append(('pendiente_puesto', saldo_puesto))
                if 'skip_descuento_puesto' in columnas_disponibles:
                    columnas_update.append(('skip_descuento_puesto', skip_descuento_puesto))
                if 'notas' in columnas_disponibles:
                    columnas_update.append(('notas', notas))
                if 'actualizado_en' in columnas_disponibles:
                    columnas_update.append(('actualizado_en', timezone.now()))

                set_clause = ',\n                            '.join(
                    f"{columna}=%s" for columna, _ in columnas_update
                )
                cursor.execute(
                    f"""
                        UPDATE estado_pago_estilista_dia
                        SET {set_clause}
                        WHERE estilista_id=%s AND fecha=%s
                    """,
                    [valor for _, valor in columnas_update] + [estilista.id, fecha],
                )

                # 2) Si no existía, insertar.
                if cursor.rowcount == 0:
                    columnas_insert = [
                        ('estilista_id', estilista.id),
                        ('fecha', fecha),
                        ('estado', estado_resultante),
                        ('pago_efectivo', pago_efectivo),
                        ('pago_nequi', pago_nequi),
                        ('pago_daviplata', pago_daviplata),
                        ('pago_otros', pago_otros),
                    ]
                    if 'abono_puesto' in columnas_disponibles:
                        columnas_insert.append(('abono_puesto', abono_puesto))
                    if 'medio_abono_puesto' in columnas_disponibles:
                        columnas_insert.append(('medio_abono_puesto', medio_abono_puesto))
                    if 'saldo_puesto_pendiente' in columnas_disponibles:
                        columnas_insert.append(('saldo_puesto_pendiente', saldo_puesto))
                    if 'pendiente_puesto' in columnas_disponibles:
                        columnas_insert.append(('pendiente_puesto', saldo_puesto))
                    if 'skip_descuento_puesto' in columnas_disponibles:
                        columnas_insert.append(('skip_descuento_puesto', skip_descuento_puesto))
                    if 'notas' in columnas_disponibles:
                        columnas_insert.append(('notas', notas))
                    if 'actualizado_en' in columnas_disponibles:
                        columnas_insert.append(('actualizado_en', timezone.now()))

                    columnas_sql = ', '.join(columna for columna, _ in columnas_insert)
                    valores_sql = ', '.join(['%s'] * len(columnas_insert))
                    cursor.execute(
                        f"""
                            INSERT INTO estado_pago_estilista_dia ({columnas_sql})
                            VALUES ({valores_sql})
                        """,
                        [valor for _, valor in columnas_insert],
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
        aplica_comision_ventas=aplica_comision_ventas,
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
            'aplica_comision_ventas': bool(aplica_comision_ventas),
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
            'modo_cobro': puesto_modo,
            'porcentaje_cobro': float(puesto_porcentaje),
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
def liquidar_dia_v2(request):
    return _liquidar_dia_v2_core(request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def liquidar_operacion_integral(request):
    """Ejecuta en una sola transacción: cobro de consumo (opcional) + liquidación diaria."""
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion', 'No tienes permiso para liquidar operaciones integrales.')

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
    fecha_dia = None
    if fecha_raw:
        try:
            fecha_abono = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
            fecha_dia = fecha_abono
            fecha_abono_dt = datetime.combine(fecha_abono, datetime.min.time()).replace(hour=12)
            if timezone.is_naive(fecha_abono_dt):
                fecha_abono_dt = timezone.make_aware(fecha_abono_dt, timezone.get_current_timezone())
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    # Desde el régimen "solo efectivo", el motor de liquidación v3 aplica el
    # cobro de consumo internamente (usa consumo_monto/deuda_ids del mismo
    # body) -- no se pre-aplica aquí para no descontarlo dos veces. Además,
    # el negocio ya no tiene cuentas electrónicas para recibir ese cobro.
    usa_motor_v3 = fecha_dia is not None and _usa_motor_cash_only(fecha_dia)
    if usa_motor_v3 and medio_cobro_consumo != 'efectivo':
        return Response(
            {'error': 'Desde el régimen de solo efectivo, el cobro de consumo solo puede ser en efectivo.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    consumo_aplicaciones = []
    consumo_sobrante = Decimal(0)
    consumo_aplicado = Decimal(0)

    try:
        if not usa_motor_v3:
            # Motor legacy: el core de liquidación no toca deuda de consumo,
            # así que se aplica aparte antes de liquidar.
            try:
                with transaction.atomic():
                    if consumo_monto > 0:
                        consumo_aplicaciones, consumo_sobrante = _aplicar_abonos_consumo_interno(
                            estilista=estilista,
                            monto_decimal=consumo_monto,
                            medio_pago=medio_cobro_consumo,
                            usuario=request.user,
                            notas=f"Cobro consumo integrado liquidación {fecha_raw or timezone.localtime().strftime('%Y-%m-%d')}",
                            fecha_abono_dt=fecha_abono_dt,
                            deuda_objetivo=None,
                            deuda_ids=deuda_ids,
                        )
            except Exception as e_consumo:
                logger.warning(f"Advertencia en cobro consumo integrado: {str(e_consumo)}")
                consumo_aplicaciones = []
                consumo_sobrante = Decimal(0)
            consumo_aplicado = consumo_monto - consumo_sobrante

        # Ejecutar liquidación (v3 aplica el consumo internamente leyendo
        # consumo_monto/deuda_ids del mismo request.data).
        response_liq = _liquidar_dia_v2_core(request)
        status_liq = int(getattr(response_liq, 'status_code', 500) or 500)
        if status_liq >= 400:
            data_liq = getattr(response_liq, 'data', None) or {}
            if isinstance(data_liq, dict):
                msg = data_liq.get('error') or data_liq.get('detail') or 'No se pudo completar la liquidación.'
            else:
                msg = 'No se pudo completar la liquidación.'
            return Response({'error': str(msg)}, status=status_liq)

        payload = getattr(response_liq, 'data', {}) or {}

        if usa_motor_v3:
            deuda_consumo_payload = payload.get('deuda_consumo') or {}
            consumo_aplicaciones = deuda_consumo_payload.get('aplicaciones') or []
            consumo_sobrante = Decimal(str(deuda_consumo_payload.get('sobrante') or 0))
            consumo_aplicado = Decimal(str(deuda_consumo_payload.get('abono_aplicado') or 0))

        payload['consumo_integrado'] = {
            'monto_solicitado': float(consumo_monto),
            'monto_aplicado': float(consumo_aplicado),
            'monto_sobrante': float(consumo_sobrante),
            'medio_pago': medio_cobro_consumo,
            'aplicaciones': consumo_aplicaciones,
        }
        return Response(payload, status=status_liq)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Error en liquidar_operacion_integral")
        return Response({'error': f'No se pudo completar la operación integral: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def liquidacion_recibo_imprimible(request):
    """
    Payload de solo lectura para imprimir el recibo de liquidación de un
    empleado en una fecha: detalle de servicios del día, subtotal efectivo,
    subtotal electrónico, comisión de producto, deducciones aplicadas y el
    resultado final (transferencia del empleado o pago del establecimiento).

    GET /api/reportes/estilistas/liquidacion-recibo/?estilista_id=5&fecha=2026-07-30

    Si el día ya fue liquidado, usa los valores guardados en
    EstadoPagoEstilistaDia (auditable, no cambia si se recalcula el día).
    Si aún no se liquida, calcula una vista previa "en vivo" (no persiste
    nada) para que el empleado pueda revisar antes de confirmar.
    """
    _requerir_permiso_ui(request.user, 'reportes', 'view', 'liquidacion', 'No tienes permiso para ver el recibo de liquidación.')

    try:
        estilista_id = int(request.query_params.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except Exception:
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        fecha_str = (request.query_params.get('fecha') or '').strip()
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    estado_dia = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
    es_preview = estado_dia is None
    motor_v3 = _usa_motor_cash_only(fecha)

    # Los toggles que el usuario esté eligiendo en pantalla (aún sin
    # confirmar) se leen de los query params, para que la vista previa
    # refleje EXACTAMENTE lo que se liquidaría si confirma ahora mismo.
    qp = request.query_params
    aplica_comision_ventas_preview = _to_bool_flag(qp.get('aplica_comision_ventas'), default=True)
    calc = calcular_liquidacion_dia_estilista(estilista, fecha, aplica_comision_ventas=aplica_comision_ventas_preview)

    # ---- Detalle de servicios del día (para el recibo itemizado) ----
    servicios_dia = ServicioRealizado.objects.select_related('servicio').filter(
        estado='finalizado',
        estilista=estilista,
        fecha_hora__date=fecha,
    ).order_by('fecha_hora')

    items = []
    for srv in servicios_dia:
        monto_emp = _monto_estilista_resuelto(srv)
        monto_est = _monto_establecimiento_resuelto(srv)
        items.append({
            'servicio_nombre': srv.servicio.nombre if srv.servicio_id else 'Servicio',
            'numero_factura': srv.numero_factura,
            'precio_cobrado': float(srv.precio_cobrado or 0),
            'medio_pago': srv.medio_pago or 'efectivo',
            'monto_empleado': float(monto_emp),
            'monto_establecimiento': float(monto_est),
        })

    adicionales_dia = ServicioRealizadoAdicional.objects.filter(
        estilista=estilista,
        servicio_realizado__estado='finalizado',
        servicio_realizado__fecha_hora__date=fecha,
    ).select_related('servicio', 'servicio_realizado')
    for ad in adicionales_dia:
        valor_cobrado = Decimal(ad.valor_cobrado or 0)
        pct_est = Decimal(ad.porcentaje_establecimiento or 0) if ad.aplica_porcentaje_establecimiento else Decimal(0)
        pct_est = max(Decimal(0), min(Decimal(100), pct_est))
        monto_emp = valor_cobrado - (valor_cobrado * pct_est / Decimal(100))
        items.append({
            'servicio_nombre': f"{ad.servicio.nombre if ad.servicio_id else 'Adicional'} (adicional)",
            'numero_factura': ad.servicio_realizado.numero_factura if ad.servicio_realizado_id else None,
            'precio_cobrado': float(valor_cobrado),
            'medio_pago': ad.servicio_realizado.medio_pago if ad.servicio_realizado_id else 'efectivo',
            'monto_empleado': float(monto_emp),
            'monto_establecimiento': float(valor_cobrado - monto_emp),
        })

    if motor_v3:
        if estado_dia is not None:
            resultado = {
                'ganancia_efectivo_dia': float(estado_dia.ganancia_efectivo_dia or 0),
                'ganancia_electronica_dia': float(estado_dia.ganancia_electronica_dia or 0),
                'ganancia_electronica_nequi': float(estado_dia.ganancia_electronica_nequi or 0),
                'ganancia_electronica_daviplata': float(estado_dia.ganancia_electronica_daviplata or 0),
                'ganancia_electronica_otros': float(estado_dia.ganancia_electronica_otros or 0),
                'comision_producto_dia': float(estado_dia.comision_producto_dia or 0),
                'reparto_establecimiento_electronico_pendiente': float(estado_dia.reparto_establecimiento_electronico_pendiente or 0),
                'descuento_puesto': float(estado_dia.descuento_puesto or 0),
                'saltar_descuento_puesto': bool(estado_dia.skip_descuento_puesto),
                'descuento_consumo_dia': float(estado_dia.descuento_consumo_dia or 0),
                'saltar_descuento_consumo': bool(estado_dia.saltar_descuento_consumo),
                'descuento_vale_dia': float(estado_dia.descuento_vale_dia or 0),
                'saltar_descuento_vale': bool(estado_dia.skip_descuento_vale),
                'total_deducciones_dia': float(estado_dia.total_deducciones_dia or 0),
                'monto_transferir_empleado': float(estado_dia.monto_transferir_empleado or 0),
                'monto_pagar_establecimiento': float(estado_dia.monto_pagar_establecimiento or 0),
                'deuda_anterior_puesto': float(getattr(estado_dia, 'saldo_puesto_pendiente', 0) or 0),
                'saldo_puesto_pendiente': float(estado_dia.saldo_puesto_pendiente or 0),
                'saldo_consumo_pendiente': float(SaldoDeudaPuesto.objects.filter(estilista=estilista).values_list('saldo_consumo', flat=True).first() or 0),
                'saldo_vale_pendiente': float(SaldoDeudaPuesto.objects.filter(estilista=estilista).values_list('saldo_vale', flat=True).first() or 0),
                'estado': estado_dia.estado,
            }
        else:
            # Vista previa en vivo -- usa el MISMO cálculo puro que usaría
            # _liquidar_dia_v3_core si se confirmara ahora mismo, con los
            # toggles que el usuario esté eligiendo en pantalla (query params).
            prev = _calcular_preview_liquidacion_v3(estilista, fecha, qp)
            resultado = {
                'ganancia_efectivo_dia': float(prev['ganancia_efectivo']),
                'ganancia_electronica_dia': float(prev['ganancia_electronica']),
                'ganancia_electronica_nequi': float(calc.get('ganancia_electronica_nequi') or 0),
                'ganancia_electronica_daviplata': float(calc.get('ganancia_electronica_daviplata') or 0),
                'ganancia_electronica_otros': float(calc.get('ganancia_electronica_otros') or 0),
                'comision_producto_dia': float(prev['comision_producto_dia']),
                'reparto_establecimiento_electronico_pendiente': float(prev['reparto_pendiente']),
                'descuento_puesto': float(prev['descuento_puesto_calculado']),
                'saltar_descuento_puesto': bool(prev['skip_descuento_puesto']),
                'descuento_consumo_dia': float(prev['monto_a_aplicar_consumo']),
                'saltar_descuento_consumo': bool(prev['saltar_descuento_consumo']),
                'descuento_vale_dia': float(prev['monto_a_aplicar_vale']),
                'saltar_descuento_vale': bool(prev['skip_descuento_vale']),
                'total_deducciones_dia': float(prev['total_deducciones_dia']),
                'monto_transferir_empleado': float(prev['monto_transferir_empleado']),
                'monto_pagar_establecimiento': float(prev['monto_pagar_establecimiento']),
                'deuda_anterior_puesto': float(prev['deuda_anterior_puesto']),
                'saldo_puesto_pendiente': float(prev['saldo_puesto_cierre']),
                'saldo_consumo_pendiente': float(prev['saldo_consumo_antes']),
                'saldo_consumo_pendiente_despues': float(prev['saldo_consumo_estimado_cierre']),
                'saldo_vale_pendiente': float(prev['saldo_vale_antes']),
                'saldo_vale_pendiente_despues': float(prev['saldo_vale_estimado_cierre']),
                'puesto_modo': prev['puesto_modo'],
                'puesto_porcentaje': float(prev['puesto_porcentaje']),
                'estado': 'preview',
            }
    else:
        resultado = None

    return Response({
        'estilista': {'id': estilista.id, 'nombre': estilista.nombre},
        'fecha': fecha.strftime('%Y-%m-%d'),
        'motor_calculo': 'v3_efectivo' if motor_v3 else 'v2_mixed',
        'es_preview': es_preview,
        'items': items,
        'resultado': resultado,
        'legacy': None if motor_v3 else {
            'ganancias_totales': float(calc.get('ganancias_totales') or 0),
            'descuento_puesto': float(calc.get('descuento_puesto') or 0),
            'total_pagable': float(calc.get('total_pagable') or 0),
            'pago_efectivo': float(estado_dia.pago_efectivo or 0) if estado_dia else 0.0,
            'pago_nequi': float(estado_dia.pago_nequi or 0) if estado_dia else 0.0,
            'pago_daviplata': float(estado_dia.pago_daviplata or 0) if estado_dia else 0.0,
            'pago_otros': float(estado_dia.pago_otros or 0) if estado_dia else 0.0,
            'estado': estado_dia.estado if estado_dia else 'preview',
        },
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_liquidacion_dia_v3(request, estilista_id, fecha):
    """
    Deshace una liquidación (régimen "solo efectivo") mal hecha para que se
    pueda volver a liquidar ese día. Revierte TODO lo que la liquidación
    escribió, no solo el registro visible:

    - Los abonos de consumo aplicados automáticamente ese día (motor FIFO):
      se borran y su monto se devuelve a las deudas de consumo originales
      (y al saldo consolidado).
    - El registro diario (EstadoPagoEstilistaDia) y su historial de
      movimientos de esa fecha.
    - El "fact" consolidado usado por los reportes (FactLiquidacionEstilistaDia).
    - El saldo de puesto consolidado (SaldoDeudaPuesto.saldo) se recalcula
      contra el día anterior más reciente que siga liquidado.

    Por seguridad, no se permite eliminar un día si el empleado ya tiene una
    liquidación más reciente registrada (evitaría "mover" retroactivamente lo
    que esos días posteriores ya dieron por hecho) -- en ese caso hay que
    eliminar primero las liquidaciones más recientes.

    DELETE /api/reportes/estilistas/liquidacion-dia/<estilista_id>/<fecha>/eliminar/
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion', 'No tienes permiso para eliminar una liquidación.')

    try:
        estilista = Estilista.objects.get(id=int(estilista_id))
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        fecha_dt = datetime.strptime(str(fecha), '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    estado_dia = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha_dt).first()
    if not estado_dia:
        return Response({'error': 'No hay ninguna liquidación registrada para ese día.'}, status=status.HTTP_404_NOT_FOUND)

    if estado_dia.motor_calculo != 'v3_efectivo':
        return Response(
            {'error': 'Esta liquidación no usa el régimen "solo efectivo"; elimínala desde el histórico clásico.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha__gt=fecha_dt).exists():
        return Response(
            {'error': 'No se puede eliminar: este empleado ya tiene una liquidación más reciente. Elimina primero las liquidaciones posteriores.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            # ---- revertir abonos de consumo que esta liquidación aplicó ----
            abonos_a_revertir = AbonoDeudaEmpleado.objects.select_related('deuda').filter(
                deuda__estilista=estilista,
                origen_liquidacion_fecha=fecha_dt,
            )
            total_revertido_consumo = Decimal(0)
            deudas_tocadas = {}
            for abono in abonos_a_revertir:
                deuda = deudas_tocadas.get(abono.deuda_id) or abono.deuda
                deuda.total_abonado = max(Decimal(deuda.total_abonado or 0) - Decimal(abono.monto or 0), Decimal(0))
                _recalcular_estado_deuda(deuda)
                deudas_tocadas[abono.deuda_id] = deuda
                total_revertido_consumo += Decimal(abono.monto or 0)
            for deuda in deudas_tocadas.values():
                deuda.save(update_fields=['total_abonado', 'saldo_pendiente', 'estado'])
            cantidad_abonos_revertidos = abonos_a_revertir.count()
            abonos_a_revertir.delete()

            if total_revertido_consumo > 0:
                saldo_obj_consumo, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
                saldo_obj_consumo.saldo_consumo = Decimal(saldo_obj_consumo.saldo_consumo or 0) + total_revertido_consumo
                saldo_obj_consumo.save()

            # ---- revertir abonos de Vale que esta liquidación aplicó ----
            abonos_vale_a_revertir = AbonoDeudaEntreEmpleados.objects.select_related('deuda').filter(
                deuda__deudor=estilista,
                origen_liquidacion_fecha=fecha_dt,
            )
            total_revertido_vale = Decimal(0)
            deudas_vale_tocadas = {}
            for abono in abonos_vale_a_revertir:
                deuda = deudas_vale_tocadas.get(abono.deuda_id) or abono.deuda
                deuda.monto_abonado = max(Decimal(deuda.monto_abonado or 0) - Decimal(abono.monto or 0), Decimal(0))
                deuda.saldo_pendiente = max(Decimal(deuda.monto or 0) - deuda.monto_abonado, Decimal(0))
                deuda.estado = 'pagado' if deuda.saldo_pendiente <= 0 else 'pendiente'
                deudas_vale_tocadas[abono.deuda_id] = deuda
                total_revertido_vale += Decimal(abono.monto or 0)
            for deuda in deudas_vale_tocadas.values():
                deuda.save(update_fields=['monto_abonado', 'saldo_pendiente', 'estado'])
            cantidad_abonos_vale_revertidos = abonos_vale_a_revertir.count()
            abonos_vale_a_revertir.delete()

            if total_revertido_vale > 0:
                saldo_obj_vale, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
                saldo_obj_vale.saldo_vale = Decimal(saldo_obj_vale.saldo_vale or 0) + total_revertido_vale
                saldo_obj_vale.save()

            # ---- borrar el registro diario, su historial y el fact de reportes ----
            EstadoPagoEstilistaHistorial.objects.filter(estilista=estilista, fecha=fecha_dt).delete()
            FactLiquidacionEstilistaDia.objects.filter(estilista=estilista, fecha=fecha_dt).delete()
            estado_dia.delete()

            # ---- recalcular el saldo de puesto consolidado contra el día anterior ----
            saldo_obj_puesto, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            estado_previo = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha__lt=fecha_dt).order_by('-fecha').first()
            saldo_obj_puesto.saldo = max(Decimal(estado_previo.saldo_puesto_pendiente or 0), Decimal(0)) if estado_previo else Decimal(0)
            saldo_obj_puesto.save()
    except Exception as e:
        return Response({'error': f'No se pudo eliminar la liquidación: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'success': True,
        'estilista_id': estilista.id,
        'fecha': fecha_dt.strftime('%Y-%m-%d'),
        'abonos_consumo_revertidos': cantidad_abonos_revertidos,
        'monto_consumo_revertido': float(total_revertido_consumo),
        'abonos_vale_revertidos': cantidad_abonos_vale_revertidos,
        'monto_vale_revertido': float(total_revertido_vale),
        'mensaje': 'Liquidación eliminada. El día queda disponible para volver a liquidarse.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cargar_deuda_puesto_dia(request):
    """
    Carga manual de deuda de puesto para un día específico.

    POST /api/reportes/estilistas/cargar-deuda-puesto/

    Body:
    {
        "estilista_id": 5,
        "fecha": "2026-04-15",
        "monto_deuda": 45000,
        "notas": "No laboró este día"
    }

    Lógica:
    1. Validar que la fecha NO tenga liquidación previa
    2. Obtener o crear EstadoPagoEstilistaDia
    3. Sumar monto_deuda a saldo_puesto_pendiente
    4. Crear registro en historial
    5. Retornar estado actualizado
    """

    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'ajuste', 'No tienes permiso para cargar deuda de puesto.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        fecha_str = request.data.get('fecha', '').strip()
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    def _to_decimal(v):
        try:
            d = Decimal(str(v or 0))
            return max(d, Decimal(0))
        except:
            return Decimal(0)

    monto_deuda = _to_decimal(request.data.get('monto_deuda'))
    if monto_deuda <= Decimal(0):
        return Response({'error': 'El monto de deuda debe ser mayor a 0.'}, status=status.HTTP_400_BAD_REQUEST)

    notas = request.data.get('notas', '').strip()[:255]

    try:
        with transaction.atomic():
            # Obtener o crear registro (sin restricción por fecha o liquidación previa)
            estado_diaria, creado = EstadoPagoEstilistaDia.objects.get_or_create(
                estilista=estilista,
                fecha=fecha,
            )

            estado_anterior = estado_diaria.estado
            saldo_anterior = estado_diaria.saldo_puesto_pendiente

            # For new records on non-service days, include prior accumulated debt so
            # saldo_puesto_pendiente is always the full running total (prior + new charge).
            if creado:
                estado_previo = EstadoPagoEstilistaDia.objects.filter(
                    estilista=estilista,
                    fecha__lt=fecha,
                ).order_by('-fecha').first()
                deuda_previa = max(
                    Decimal(getattr(estado_previo, 'saldo_puesto_pendiente', 0) or 0),
                    Decimal(0)
                ) if estado_previo else Decimal(0)
                estado_diaria.saldo_puesto_pendiente = deuda_previa + monto_deuda
            else:
                # Existing record: add on top of whatever was already stored for this day
                estado_diaria.saldo_puesto_pendiente = estado_diaria.saldo_puesto_pendiente + monto_deuda

            # Actualizar estado a 'debe' si hay deuda
            if estado_diaria.saldo_puesto_pendiente > Decimal(0):
                estado_diaria.estado = 'debe'
            else:
                estado_diaria.estado = 'cancelado'

            # Agregar nota
            notas_actual = str(estado_diaria.notas or '')
            if notas:
                notas_actual = f"{notas_actual} | Carga manual: {notas}".lstrip('| ')
            estado_diaria.notas = notas_actual[:255]
            estado_diaria.usuario_liquida = request.user

            estado_diaria.save()

            # Actualizar saldo consolidado (fuente de verdad)
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj.saldo = max(Decimal(saldo_obj.saldo or 0) + monto_deuda, Decimal(0))
            saldo_obj.save()

            # Crear registro en historial
            try:
                EstadoPagoEstilistaHistorial.objects.create(
                    estilista=estilista,
                    fecha=fecha,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_diaria.estado,
                    usuario=request.user,
                    notas=f'Carga manual de deuda: ${float(monto_deuda):,.2f}. {notas}',
                    monto_liquidado=Decimal(0),
                    abono_puesto_dia=Decimal(0),
                )
            except Exception:
                pass  # Continuar si no se puede crear historial

            return Response({
                'success': True,
                'mensaje': f'Deuda de ${float(monto_deuda):,.2f} cargada correctamente.',
                'estilista_id': estilista.id,
                'estilista_nombre': estilista.nombre,
                'fecha': fecha.strftime('%Y-%m-%d'),
                'monto_cargado': float(monto_deuda),
                'saldo_anterior': float(saldo_anterior),
                'saldo_nuevo': float(estado_diaria.saldo_puesto_pendiente),
                'estado': estado_diaria.estado,
            }, status=status.HTTP_200_OK)

    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': f'No se pudo cargar la deuda: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancelar_deuda_puesto_dias(request):
    """
    Cancela (pone a cero) la deuda de puesto de días específicos.

    POST /api/reportes/estilistas/cancelar-deuda-puesto-dias/

    Body:
    {
        "estilista_id": 5,
        "fechas": ["2026-04-10", "2026-04-11"]
    }
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'ajuste', 'No tienes permiso para cancelar deuda de puesto.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas_raw = request.data.get('fechas', [])
    if not fechas_raw or not isinstance(fechas_raw, list):
        return Response({'error': 'Se requiere una lista de fechas.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas = []
    for f in fechas_raw:
        try:
            fechas.append(datetime.strptime(str(f).strip(), '%Y-%m-%d').date())
        except Exception:
            return Response({'error': f'Fecha inválida: {f}'}, status=status.HTTP_400_BAD_REQUEST)

    cancelados = []
    try:
        with transaction.atomic():
            # Calcular primero la contribución de cada día para decrementar el saldo consolidado.
            # La contribución = saldo[día] - saldo[día_anterior] (lo que ese día sumó a la deuda).
            total_a_restar = Decimal(0)
            for fecha in sorted(fechas):
                estado = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
                if not estado:
                    continue
                saldo_dia = max(Decimal(estado.saldo_puesto_pendiente or 0), Decimal(0))
                prev_estado = EstadoPagoEstilistaDia.objects.filter(
                    estilista=estilista, fecha__lt=fecha,
                ).order_by('-fecha').first()
                saldo_prev = max(Decimal(getattr(prev_estado, 'saldo_puesto_pendiente', 0) or 0), Decimal(0)) if prev_estado else Decimal(0)
                contribucion = max(saldo_dia - saldo_prev, Decimal(0))
                total_a_restar += contribucion

            # Decrementar saldo consolidado
            if total_a_restar > Decimal(0):
                saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
                saldo_obj.saldo = max(Decimal(saldo_obj.saldo or 0) - total_a_restar, Decimal(0))
                saldo_obj.save()

            for fecha in fechas:
                estado = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
                if not estado:
                    continue
                saldo_anterior = float(estado.saldo_puesto_pendiente or 0)
                estado.saldo_puesto_pendiente = Decimal(0)
                if estado.estado == 'debe':
                    estado.estado = 'cancelado'
                estado.save()

                fact = FactLiquidacionEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
                if fact:
                    fact.deuda_puesto_cierre = Decimal(0)
                    fact.save()

                try:
                    EstadoPagoEstilistaHistorial.objects.create(
                        estilista=estilista,
                        fecha=fecha,
                        estado_anterior='debe',
                        estado_nuevo='cancelado',
                        usuario=request.user,
                        notas=f'Deuda de puesto cancelada manualmente (anterior: ${saldo_anterior:,.2f}).',
                        monto_liquidado=Decimal(0),
                        abono_puesto_dia=Decimal(0),
                    )
                except Exception:
                    pass

                cancelados.append({'fecha': fecha.strftime('%Y-%m-%d'), 'saldo_anterior': saldo_anterior})

        return Response({
            'success': True,
            'mensaje': f'{len(cancelados)} día(s) de deuda de puesto cancelado(s).',
            'cancelados': cancelados,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': f'No se pudo cancelar la deuda: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def abonar_deuda_puesto_dias(request):
    """
    Abona (o liquida completo si no se envia monto) deuda de puesto de dias
    especificos, aplicando el abono de la fecha MAS ANTIGUA a la MAS RECIENTE
    entre los dias seleccionados, cubriendo cada uno hasta donde alcance.

    NO usa _liquidar_dia_v2_core: esa funcion esta pensada para procesar "el dia
    de hoy" contra el saldo heredado del dia anterior, y al forzar el reemplazo
    de un dia pasado termina descartando lo que ese dia aportaba y sobrescribe el
    pago al empleado a 0. Esta funcion recalcula la cadena completa de deuda por
    dia (mismo criterio que el reporte de Ajuste Diario: descuento diferido con
    skip_descuento_puesto=True, o incremento detectado por carga manual) y la
    vuelve a guardar de forma consistente, sin tocar pago_efectivo/pago_nequi/
    pago_daviplata/pago_otros ni facturas de consumo interno en ningun momento.

    POST /api/reportes/estilistas/abonar-deuda-puesto-dias/
    Body: {"estilista_id": 5, "fechas": ["2026-06-07", "2026-06-30"], "monto": 29000}
    Si "monto" se omite o es 0 o negativo, liquida completo cada dia seleccionado.
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'ajuste', 'No tienes permiso para abonar deuda de puesto.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas_raw = request.data.get('fechas', [])
    if not fechas_raw or not isinstance(fechas_raw, list):
        return Response({'error': 'Se requiere una lista de fechas.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas_seleccionadas = set()
    for f in fechas_raw:
        try:
            fechas_seleccionadas.add(datetime.strptime(str(f).strip(), '%Y-%m-%d').date())
        except Exception:
            return Response({'error': f'Fecha inválida: {f}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        monto_raw = request.data.get('monto', 0)
        monto_abono = max(Decimal(str(monto_raw or 0)), Decimal(0))
    except Exception:
        return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            registros = list(
                EstadoPagoEstilistaDia.objects.filter(estilista=estilista).order_by('fecha')
            )

            # 1) Reconstruir la cola FIFO real de deuda pendiente por dia, con el
            # mismo criterio que reporte_ajuste_diario_unificado: un dia aporta
            # deuda nueva si (a) tiene skip_descuento_puesto=True con descuento>0,
            # o (b) su saldo acumulado subio respecto al dia anterior sin ser por
            # ese motivo (carga manual). Los abonos historicos de cada dia ya
            # consumen la cola en orden, igual que en el reporte.
            pendientes_fifo = []  # [[fecha, monto_propio_restante], ...]
            saldo_crudo_anterior = Decimal(0)
            for ep in registros:
                skip_desc = bool(ep.skip_descuento_puesto)
                descuento = max(Decimal(ep.descuento_puesto or 0), Decimal(0))
                saldo_crudo_dia = max(Decimal(ep.saldo_puesto_pendiente or 0), Decimal(0))

                if descuento > 0 and skip_desc:
                    pendientes_fifo.append([ep.fecha, descuento])
                else:
                    delta_manual = saldo_crudo_dia - saldo_crudo_anterior
                    if delta_manual > 0:
                        pendientes_fifo.append([ep.fecha, delta_manual])

                saldo_crudo_anterior = saldo_crudo_dia

                abono_dia = max(Decimal(ep.abono_puesto or 0), Decimal(0))
                while abono_dia > 0 and pendientes_fifo:
                    f0, s0 = pendientes_fifo[0]
                    aplicar = min(s0, abono_dia)
                    s0 -= aplicar
                    abono_dia -= aplicar
                    if s0 <= 0:
                        pendientes_fifo.pop(0)
                    else:
                        pendientes_fifo[0][1] = s0

            pendientes_por_fecha = {}
            for f, s in pendientes_fifo:
                pendientes_por_fecha[f] = pendientes_por_fecha.get(f, Decimal(0)) + max(s, Decimal(0))

            # 2) Aplicar el NUEVO abono solo a las fechas seleccionadas, de la mas
            # antigua a la mas reciente entre ellas.
            fechas_ordenadas = sorted(fechas_seleccionadas)
            restante = monto_abono if monto_abono > 0 else None  # None = liquidar completo
            aplicado_por_fecha = {}
            total_aplicado = Decimal(0)
            for f in fechas_ordenadas:
                pendiente_dia = pendientes_por_fecha.get(f, Decimal(0))
                if pendiente_dia <= 0:
                    continue
                if restante is not None:
                    if restante <= 0:
                        break
                    aplicar = min(pendiente_dia, restante)
                    restante -= aplicar
                else:
                    aplicar = pendiente_dia
                if aplicar <= 0:
                    continue
                aplicado_por_fecha[f] = aplicar
                pendientes_por_fecha[f] = pendiente_dia - aplicar
                total_aplicado += aplicar

            if total_aplicado <= 0:
                return Response(
                    {'error': 'No hay deuda pendiente en los días seleccionados o el monto no alcanza para cubrir nada.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 3) Reconstruir el saldo acumulado dia a dia con la deuda YA reducida
            # por el nuevo abono, y guardar solo los registros que cambiaron.
            fechas_con_aporte = sorted(pendientes_por_fecha.keys())
            acumulado = Decimal(0)
            saldo_final_por_fecha = {}
            for f in fechas_con_aporte:
                acumulado += max(pendientes_por_fecha.get(f, Decimal(0)), Decimal(0))
                saldo_final_por_fecha[f] = acumulado

            saldo_vigente = Decimal(0)
            actualizados = 0
            for ep in registros:
                if ep.fecha in saldo_final_por_fecha:
                    saldo_vigente = saldo_final_por_fecha[ep.fecha]

                if Decimal(ep.saldo_puesto_pendiente or 0) == saldo_vigente and ep.fecha not in aplicado_por_fecha:
                    continue

                ep.saldo_puesto_pendiente = saldo_vigente
                ep.pendiente_puesto = saldo_vigente
                # No se toca pago_efectivo/pago_nequi/pago_daviplata/pago_otros ni
                # nada de consumo interno. El estado 'pendiente' (pago al empleado
                # sin liquidar) tampoco se toca; solo se alterna entre 'debe' y
                # 'cancelado' segun el nuevo saldo de puesto.
                if ep.estado != 'pendiente':
                    ep.estado = 'debe' if saldo_vigente > 0 else 'cancelado'
                if ep.fecha in aplicado_por_fecha:
                    notas_actual = str(ep.notas or '')
                    nota_extra = f'Abono deuda de puesto ${aplicado_por_fecha[ep.fecha]:,.2f} desde Ajuste Diario.'
                    ep.notas = f'{notas_actual} | {nota_extra}'.strip(' |')[:255]
                ep.save()
                actualizados += 1

            # 4) Sincronizar el saldo consolidado (fuente de verdad).
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=estilista)
            saldo_obj.saldo = max(Decimal(saldo_obj.saldo or 0) - total_aplicado, Decimal(0))
            saldo_obj.save()

        return Response({
            'success': True,
            'mensaje': f'Abono aplicado: ${total_aplicado:,.2f} en {len(aplicado_por_fecha)} día(s).',
            'total_aplicado': float(total_aplicado),
            'aplicado_por_fecha': {f.strftime('%Y-%m-%d'): float(v) for f, v in aplicado_por_fecha.items()},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': f'No se pudo abonar la deuda de puesto: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def liquidar_pago_empleado_dias(request):
    """
    Marca como liquidado (pagado) el pago al empleado de uno o mas dias especificos,
    SIN tocar deuda de puesto (abono_puesto/saldo_puesto_pendiente/skip_descuento_puesto)
    ni facturas de consumo interno del empleado. Pensado para el caso donde ya se
    liquido al empleado en la caja pero nunca se guardo el registro en el sistema.

    POST /api/reportes/estilistas/liquidar-pago-empleado-dias/

    Body:
    {
        "estilista_id": 5,
        "fechas": ["2026-06-19", "2026-06-20"]
    }
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion', 'No tienes permiso para liquidar pagos de empleado.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas_raw = request.data.get('fechas', [])
    if not fechas_raw or not isinstance(fechas_raw, list):
        return Response({'error': 'Se requiere una lista de fechas.'}, status=status.HTTP_400_BAD_REQUEST)

    fechas = []
    for f in fechas_raw:
        try:
            fechas.append(datetime.strptime(str(f).strip(), '%Y-%m-%d').date())
        except Exception:
            return Response({'error': f'Fecha inválida: {f}'}, status=status.HTTP_400_BAD_REQUEST)

    actualizados = []
    total_aplicado = Decimal(0)
    try:
        with transaction.atomic():
            for fecha in sorted(fechas):
                ep = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
                fact = FactLiquidacionEstilistaDia.objects.filter(estilista=estilista, fecha=fecha, vigente=True).first()
                aplica_comision_ventas = bool(getattr(fact, 'aplica_comision_ventas', True)) if fact else True

                calc = calcular_liquidacion_dia_estilista(estilista, fecha, aplica_comision_ventas=aplica_comision_ventas)
                generado = Decimal(calc.get('total_pagable') or 0)

                pago_efectivo = Decimal(ep.pago_efectivo or 0) if ep else Decimal(0)
                pago_nequi = Decimal(ep.pago_nequi or 0) if ep else Decimal(0)
                pago_daviplata = Decimal(ep.pago_daviplata or 0) if ep else Decimal(0)
                pago_otros = Decimal(ep.pago_otros or 0) if ep else Decimal(0)
                pagado_total = pago_efectivo + pago_nequi + pago_daviplata + pago_otros

                gap = max(generado - pagado_total, Decimal(0))
                if gap <= 0:
                    continue

                if ep is None:
                    # Dia sin registro previo: se crea uno nuevo, pero la deuda de puesto
                    # DEBE arrancar en lo que traiga el dia anterior mas reciente (arrastre),
                    # nunca en 0 — si el empleado ya tenia deuda acumulada, forzar 0 aqui
                    # "resetea" la cadena y hace que el dia siguiente con registro propio
                    # se vea como si esa deuda completa fuera nueva otra vez.
                    ep_previo = EstadoPagoEstilistaDia.objects.filter(
                        estilista=estilista, fecha__lt=fecha
                    ).order_by('-fecha').first()
                    saldo_arrastrado = max(
                        Decimal(getattr(ep_previo, 'saldo_puesto_pendiente', None) or getattr(ep_previo, 'pendiente_puesto', 0) or 0),
                        Decimal(0),
                    ) if ep_previo else Decimal(0)
                    ep = EstadoPagoEstilistaDia(
                        estilista=estilista,
                        fecha=fecha,
                        saldo_puesto_pendiente=saldo_arrastrado,
                        pendiente_puesto=saldo_arrastrado,
                        abono_puesto=Decimal(0),
                    )

                ep.ganancias_totales = Decimal(calc.get('ganancias_totales') or 0)
                ep.descuento_puesto = Decimal(calc.get('descuento_puesto') or 0)
                ep.total_pagable = generado
                ep.neto_dia = generado
                # Solo se toca el pago al empleado; abono_puesto/saldo_puesto_pendiente/
                # skip_descuento_puesto quedan exactamente como estaban (o como el
                # arrastre correcto, si el registro se acaba de crear arriba).
                ep.pago_efectivo = pago_efectivo + gap
                saldo_puesto_actual = Decimal(ep.saldo_puesto_pendiente or 0)
                ep.estado = 'debe' if saldo_puesto_actual > 0 else 'cancelado'
                notas_actual = str(ep.notas or '')
                nota_extra = f'Pago liquidado desde Ajuste Diario (${gap:,.2f}).'
                ep.notas = f'{notas_actual} | {nota_extra}'.strip(' |')[:255]
                ep.usuario_liquida = request.user
                ep.save()

                if fact is not None:
                    fact.pago_efectivo = Decimal(fact.pago_efectivo or 0) + gap
                    fact.pago_total_empleado = Decimal(fact.pago_total_empleado or 0) + gap
                    fact.estado_liquidacion = ep.estado
                    fact.save()

                total_aplicado += gap
                actualizados.append({'fecha': fecha.strftime('%Y-%m-%d'), 'monto_aplicado': float(gap)})

        return Response({
            'success': True,
            'mensaje': f'{len(actualizados)} día(s) liquidado(s).',
            'actualizados': actualizados,
            'total_aplicado': float(total_aplicado),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': f'No se pudo liquidar el pago: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirmar_transferencia_pendiente_dia(request):
    """
    Confirma que una transferencia/pago pendiente de un día ya liquidado
    (régimen "solo efectivo", v3) efectivamente se recibió/entregó, para que
    el día deje de quedar como "Pendiente" para siempre.

    Cubre los dos sentidos posibles del día:
    - El empleado debía transferir dinero al negocio (monto_transferir_empleado)
      y ahora se confirma que lo hizo -- se acredita a monto_transferir_recibido.
    - El negocio debía entregarle efectivo al empleado (monto_pagar_establecimiento)
      y ahora se confirma que se le entregó -- se acredita a monto_pagar_entregado.

    POST /api/reportes/estilistas/confirmar-transferencia-dia/

    Body:
    {
        "estilista_id": 5,
        "fecha": "2026-08-02",
        "tipo": "transferencia_empleado" | "pago_establecimiento",
        "monto": 55000  // opcional; si se omite, confirma el pendiente completo
    }
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion', 'No tienes permiso para confirmar pagos pendientes de liquidación.')

    try:
        estilista_id = int(request.data.get('estilista_id') or 0)
        estilista = Estilista.objects.get(id=estilista_id, activo=True)
    except (ValueError, Estilista.DoesNotExist):
        return Response({'error': 'Estilista no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        fecha = datetime.strptime(str(request.data.get('fecha') or '').strip(), '%Y-%m-%d').date()
    except Exception:
        return Response({'error': 'Formato de fecha inválido. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    tipo = str(request.data.get('tipo') or '').strip().lower()
    if tipo not in {'transferencia_empleado', 'pago_establecimiento'}:
        return Response({'error': "tipo debe ser 'transferencia_empleado' o 'pago_establecimiento'."}, status=status.HTTP_400_BAD_REQUEST)

    def _to_decimal(v):
        try:
            d = Decimal(str(v if v is not None else 0))
            return max(d, Decimal(0))
        except Exception:
            return Decimal(0)

    ep = EstadoPagoEstilistaDia.objects.filter(estilista=estilista, fecha=fecha).first()
    if ep is None:
        return Response({'error': 'No existe una liquidación registrada para ese día.'}, status=status.HTTP_404_NOT_FOUND)

    if getattr(ep, 'motor_calculo', '') != 'v3_efectivo':
        return Response({'error': 'Este día no usa el régimen de liquidación "solo efectivo".'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            estado_anterior = ep.estado

            if tipo == 'transferencia_empleado':
                pendiente_actual = max(Decimal(ep.monto_transferir_empleado or 0) - Decimal(ep.monto_transferir_recibido or 0), Decimal(0))
                if pendiente_actual <= 0:
                    return Response({'error': 'No hay transferencia pendiente del empleado para este día.'}, status=status.HTTP_400_BAD_REQUEST)
                monto_confirmar = _to_decimal(request.data.get('monto', pendiente_actual))
                if monto_confirmar <= 0:
                    return Response({'error': 'El monto a confirmar debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
                monto_confirmar = min(monto_confirmar, pendiente_actual)
                ep.monto_transferir_recibido = Decimal(ep.monto_transferir_recibido or 0) + monto_confirmar
            else:
                pendiente_actual = max(Decimal(ep.monto_pagar_establecimiento or 0) - Decimal(ep.monto_pagar_entregado or 0), Decimal(0))
                if pendiente_actual <= 0:
                    return Response({'error': 'No hay pago pendiente del establecimiento para este día.'}, status=status.HTTP_400_BAD_REQUEST)
                monto_confirmar = _to_decimal(request.data.get('monto', pendiente_actual))
                if monto_confirmar <= 0:
                    return Response({'error': 'El monto a confirmar debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
                monto_confirmar = min(monto_confirmar, pendiente_actual)
                ep.monto_pagar_entregado = Decimal(ep.monto_pagar_entregado or 0) + monto_confirmar

            pendiente_transferencia = max(Decimal(ep.monto_transferir_empleado or 0) - Decimal(ep.monto_transferir_recibido or 0), Decimal(0))
            pendiente_pago = max(Decimal(ep.monto_pagar_establecimiento or 0) - Decimal(ep.monto_pagar_entregado or 0), Decimal(0))
            saldo_puesto_actual = Decimal(ep.saldo_puesto_pendiente or 0)
            saldo_obj_consumo = SaldoDeudaPuesto.objects.filter(estilista=estilista).first()
            saldo_consumo_actual = Decimal(getattr(saldo_obj_consumo, 'saldo_consumo', 0) or 0)

            if pendiente_transferencia > 0 or pendiente_pago > 0:
                estado_resultante = 'pendiente'
            elif saldo_puesto_actual > 0 or saldo_consumo_actual > 0:
                estado_resultante = 'debe'
            else:
                estado_resultante = 'cancelado'

            ep.estado = estado_resultante
            notas_actual = str(ep.notas or '')
            tipo_legible = 'transferencia del empleado' if tipo == 'transferencia_empleado' else 'pago del establecimiento'
            nota_extra = f'Confirmado {tipo_legible} (${monto_confirmar:,.2f}).'
            ep.notas = f'{notas_actual} | {nota_extra}'.strip(' |')[:255]
            ep.usuario_liquida = request.user
            ep.save()

            fact = FactLiquidacionEstilistaDia.objects.filter(estilista=estilista, fecha=fecha, vigente=True).first()
            if fact is not None:
                fact.monto_transferir_recibido = ep.monto_transferir_recibido
                fact.monto_pagar_entregado = ep.monto_pagar_entregado
                fact.estado_liquidacion = estado_resultante
                fact.save()

            try:
                EstadoPagoEstilistaHistorial.objects.create(
                    estilista=estilista,
                    fecha=fecha,
                    estado_anterior=estado_anterior,
                    estado_nuevo=estado_resultante,
                    notas=nota_extra,
                    usuario=request.user,
                    monto_liquidado=monto_confirmar,
                    pendiente_puesto=saldo_puesto_actual,
                    monto_transferir_empleado=Decimal(ep.monto_transferir_empleado or 0),
                    monto_pagar_establecimiento=Decimal(ep.monto_pagar_establecimiento or 0),
                    motor_calculo='v3_efectivo',
                )
            except Exception:
                pass

        return Response({
            'success': True,
            'estilista_id': estilista.id,
            'fecha': fecha.strftime('%Y-%m-%d'),
            'tipo': tipo,
            'monto_confirmado': float(monto_confirmar),
            'estado': ep.estado,
            'monto_transferir_empleado': float(ep.monto_transferir_empleado or 0),
            'monto_transferir_recibido': float(ep.monto_transferir_recibido or 0),
            'pendiente_transferencia_empleado': float(pendiente_transferencia),
            'monto_pagar_establecimiento': float(ep.monto_pagar_establecimiento or 0),
            'monto_pagar_entregado': float(ep.monto_pagar_entregado or 0),
            'pendiente_pago_empleado_efectivo': float(pendiente_pago),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': f'No se pudo confirmar el pago pendiente: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancelar_facturas_deuda_empleado(request):
    """
    Cancela (estado='cancelado', saldo=0) facturas de deuda de consumo de empleado.

    POST /api/reportes/consumo-empleado/cancelar-facturas/

    Body:
    {
        "deuda_ids": [12, 34, 56]
    }
    """
    _requerir_permiso_ui(request.user, 'reportes', 'delete', 'cartera', 'No tienes permiso para cancelar facturas de deuda.')

    deuda_ids_raw = request.data.get('deuda_ids', [])
    if not deuda_ids_raw or not isinstance(deuda_ids_raw, list):
        return Response({'error': 'Se requiere una lista de deuda_ids.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        deuda_ids = [int(x) for x in deuda_ids_raw]
    except (ValueError, TypeError):
        return Response({'error': 'deuda_ids debe contener números enteros.'}, status=status.HTTP_400_BAD_REQUEST)

    canceladas = []
    try:
        with transaction.atomic():
            deudas = DeudaConsumoEmpleado.objects.filter(id__in=deuda_ids).select_related('estilista')
            saldo_restar_por_emp = {}
            for deuda in deudas:
                if deuda.estado == 'cancelado':
                    continue
                saldo_anterior = Decimal(str(deuda.saldo_pendiente or 0))
                deuda.estado = 'cancelado'
                deuda.saldo_pendiente = Decimal(0)
                deuda.save()
                canceladas.append({'deuda_id': deuda.id, 'numero_factura': deuda.numero_factura, 'saldo_anterior': float(saldo_anterior)})
                emp_id = int(deuda.estilista_id)
                saldo_restar_por_emp[emp_id] = saldo_restar_por_emp.get(emp_id, Decimal(0)) + saldo_anterior

            # Decrementar saldo_consumo consolidado por empleado
            for emp_id, total_restar in saldo_restar_por_emp.items():
                try:
                    saldo_obj = SaldoDeudaPuesto.objects.get(estilista_id=emp_id)
                    saldo_obj.saldo_consumo = max(Decimal(saldo_obj.saldo_consumo or 0) - total_restar, Decimal(0))
                    saldo_obj.save()
                except SaldoDeudaPuesto.DoesNotExist:
                    pass

        return Response({
            'success': True,
            'mensaje': f'{len(canceladas)} factura(s) cancelada(s).',
            'canceladas': canceladas,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': f'No se pudo cancelar las facturas: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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

        registros_x = list(qs[:limit])

        # El historial es una bitácora de auditoría (nunca cambia una vez
        # creada) -- para saber si HOY sigue habiendo algo pendiente por
        # confirmar (transferencia del empleado o pago del negocio) hay que
        # mirar el estado VIGENTE de EstadoPagoEstilistaDia, no el snapshot
        # congelado del momento en que se liquidó.
        pares = {(x.estilista_id, x.fecha) for x in registros_x}
        estado_actual_map = {}
        if pares:
            estilista_ids = {p[0] for p in pares}
            fechas = {p[1] for p in pares}
            for ep in EstadoPagoEstilistaDia.objects.filter(estilista_id__in=estilista_ids, fecha__in=fechas):
                estado_actual_map[(ep.estilista_id, ep.fecha)] = ep

        registros = []
        for x in registros_x:
            ep_actual = estado_actual_map.get((x.estilista_id, x.fecha))
            if ep_actual is not None and getattr(ep_actual, 'motor_calculo', '') == 'v3_efectivo':
                pendiente_transferencia_actual = float(max(
                    Decimal(ep_actual.monto_transferir_empleado or 0) - Decimal(ep_actual.monto_transferir_recibido or 0),
                    Decimal(0),
                ))
                pendiente_pago_actual = float(max(
                    Decimal(ep_actual.monto_pagar_establecimiento or 0) - Decimal(ep_actual.monto_pagar_entregado or 0),
                    Decimal(0),
                ))
                estado_actual = ep_actual.estado
            else:
                pendiente_transferencia_actual = 0.0
                pendiente_pago_actual = 0.0
                estado_actual = x.estado_nuevo

            registros.append({
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
                'motor_calculo': getattr(x, 'motor_calculo', 'v2_mixed') or 'v2_mixed',
                'monto_transferir_empleado': float(getattr(x, 'monto_transferir_empleado', 0) or 0),
                'monto_pagar_establecimiento': float(getattr(x, 'monto_pagar_establecimiento', 0) or 0),
                # Estado VIGENTE (no el snapshot histórico) -- para decidir si
                # todavía se puede confirmar una transferencia/pago pendiente.
                'estado_actual': estado_actual,
                'pendiente_transferencia_empleado_actual': pendiente_transferencia_actual,
                'pendiente_pago_empleado_actual': pendiente_pago_actual,
            })
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
    # Permiso de edición de liquidación: quien puede corregir/liquidar también puede
    # eliminar un registro de historial mal guardado.
    if not _tiene_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion'):
        return Response(
            {'error': 'No tienes permiso para eliminar registros del historial.'},
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
    if not _tiene_permiso_ui(request.user, 'reportes', 'edit', 'liquidacion'):
        return Response(
            {'error': 'No tienes permiso para ajustar la fecha del pago de espacio.'},
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
    servicios_est = ServicioRealizado.objects.select_related('estilista', 'servicio').filter(
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
        # En liquidación del empleado la base del día debe excluir la porción del establecimiento.
        base_empleado_srv = _monto_estilista_resuelto(srv)
        servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + base_empleado_srv
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
    servicios_est = ServicioRealizado.objects.select_related('estilista', 'servicio').filter(
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
        # Debe coincidir con Histórico de ventas: base empleado = suma de monto_estilista.
        base_empleado_srv = Decimal(getattr(srv, 'monto_estilista', 0) or 0)
        if base_empleado_srv <= 0:
            base_empleado_srv = _monto_estilista_resuelto(srv)
        servicios_por_dia[fecha_srv] = servicios_por_dia.get(fecha_srv, Decimal(0)) + base_empleado_srv
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
        # No sumar aquí a la base diaria para evitar doble conteo respecto a monto_estilista.

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


def _calcular_ajuste_diario_items(request):
    """
    Lógica compartida de `reporte_ajuste_diario_unificado`, extraída para
    poder llamarse como función Python normal (ej. desde
    `reporte_cierre_caja`) sin pasar por la maquinaria de despacho de vistas
    de DRF -- llamar directamente a una función decorada con `@api_view`
    pasándole un `rest_framework.request.Request` ya envuelto revienta con
    `AssertionError: The request argument must be an instance of
    django.http.HttpRequest` (el decorador CSRF interno de DRF espera un
    HttpRequest crudo, no uno ya envuelto). Devuelve el dict plano, sin
    envolver en Response -- eso lo hace el view público más abajo.
    """
    _requerir_permiso_ui(request.user, 'reportes', 'view', 'ajuste', 'No tienes acceso al módulo unificado de ajustes.')

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

    facts_map_aplica = {}
    try:
        facts_qs_aplica = FactLiquidacionEstilistaDia.objects.filter(
            estilista_id__in=estilista_ids,
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
            vigente=True,
        )
        for fact in facts_qs_aplica:
            facts_map_aplica[(int(fact.estilista_id), fact.fecha)] = fact
    except Exception:
        facts_map_aplica = {}

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

    def _deuda_arrastre_previa(est_id):
        if usar_fact:
            try:
                fact_prev = FactLiquidacionEstilistaDia.objects.filter(
                    estilista_id=est_id,
                    fecha__lt=fecha_inicio_dt,
                    vigente=True,
                ).order_by('-fecha', '-version').first()
                if fact_prev is not None:
                    return max(Decimal(getattr(fact_prev, 'deuda_puesto_cierre', 0) or 0), Decimal(0))
            except Exception:
                pass

        try:
            ep_prev = EstadoPagoEstilistaDia.objects.filter(
                estilista_id=est_id,
                fecha__lt=fecha_inicio_dt,
            ).order_by('-fecha', '-actualizado_en').first()
            if ep_prev is not None:
                return max(
                    Decimal(getattr(ep_prev, 'saldo_puesto_pendiente', None) or getattr(ep_prev, 'pendiente_puesto', 0) or 0),
                    Decimal(0),
                )
        except Exception:
            pass

        return Decimal(0)

    # Saldo actual por empleado desde la tabla consolidada (fuente de verdad)
    saldo_puesto_actual_map = {}
    saldo_consumo_actual_map = {}
    try:
        for sdp in SaldoDeudaPuesto.objects.filter(estilista_id__in=estilista_ids):
            saldo_puesto_actual_map[int(sdp.estilista_id)] = max(Decimal(str(sdp.saldo or 0)), Decimal(0))
            saldo_consumo_actual_map[int(sdp.estilista_id)] = max(Decimal(str(sdp.saldo_consumo or 0)), Decimal(0))
    except Exception:
        saldo_puesto_actual_map = {}
        saldo_consumo_actual_map = {}

    # Precarga en bloque (4 queries totales) + memo cache: evita repetir 4 queries
    # por cada combinacion estilista/dia (antes se llamaba calcular_liquidacion_dia_estilista
    # hasta 4 veces por dia -2 en este loop, 2 en el loop de items de abajo- y cada llamada
    # hacia 4 queries propias; con muchos estilistas/dias esto disparaba miles de queries
    # y era la causa principal de que "Reportes" tardara tanto en cargar).
    datos_precargados = _precargar_datos_liquidacion_rango(estilista_ids, fecha_inicio_dt, fecha_fin_dt)
    calc_cache = {}

    def _calc_memo(est, dia, aplica_comision_ventas):
        cache_key = (int(est.id), dia, bool(aplica_comision_ventas))
        if cache_key not in calc_cache:
            calc_cache[cache_key] = _calcular_liquidacion_dia_estilista_bulk(
                datos_precargados, est, dia, aplica_comision_ventas
            )
        return calc_cache[cache_key]

    fifo_por_estilista = {}
    for est in estilistas:
        est_id = int(est.id)
        dias_est = sorted(list(dias_con_movimiento.get(est_id, set())))
        if not dias_est:
            fifo_por_estilista[est_id] = {
                'arrastre_inicial': Decimal(0),
                'arrastre_final': Decimal(0),
                'pendiente_por_fecha': {},
                'aplicado_por_fecha': {},
            }
            continue

        arrastre = _deuda_arrastre_previa(est_id)
        arrastre_inicial = Decimal(arrastre)
        pendientes_fifo = []
        aplicado_por_fecha = defaultdict(Decimal)
        # Saldo acumulado "crudo" tal como queda guardado en
        # EstadoPagoEstilistaDia.saldo_puesto_pendiente (siempre es un total corrido,
        # nunca un valor propio del dia). Se usa solo para DETECTAR cargas manuales de
        # deuda (ver cargar_deuda_puesto_dia) que no generan descuento_puesto/skip_desc:
        # un incremento neto en este saldo que el flujo normal no explica. Ese incremento
        # se encola en la MISMA cola FIFO de abajo para que quede correctamente "envejecido"
        # por los abonos que lleguen despues (si no, cada dia mostraria el acumulado
        # completo y liquidar un solo dia cancelaria de golpe deuda de otros dias).
        saldo_crudo_anterior = arrastre_inicial

        for dia in dias_est:
            ep = estados_map.get((est_id, dia))
            fact = facts_map.get((est_id, dia)) if usar_fact else None
            fact_aplica = facts_map_aplica.get((est_id, dia))

            calc_con_comision = _calc_memo(est, dia, True)
            calc_sin_comision = _calc_memo(est, dia, False)
            aplica_comision_ventas = bool(getattr(fact_aplica, 'aplica_comision_ventas', True)) if fact_aplica else True
            descuento_puesto = Decimal((
                fact.descuento_puesto_dia if fact else (calc_con_comision.get('descuento_puesto') if aplica_comision_ventas else calc_sin_comision.get('descuento_puesto'))
            ) or 0)
            descuento_puesto = max(descuento_puesto, Decimal(0))

            # Si ese día se eligió "cobrar hoy" (skip=False), el descuento ya fue cobrado
            # vía reducción del pago → no genera nueva entrada en la cola FIFO de deudas.
            skip_desc = bool(getattr(ep, 'skip_descuento_puesto', False)) if ep else False
            if descuento_puesto > 0 and skip_desc:
                pendientes_fifo.append([dia, descuento_puesto])
            elif ep is not None:
                saldo_crudo_dia = max(
                    Decimal(getattr(ep, 'saldo_puesto_pendiente', None) or getattr(ep, 'pendiente_puesto', 0) or 0),
                    Decimal(0),
                )
                delta_manual = saldo_crudo_dia - saldo_crudo_anterior
                if delta_manual > 0:
                    pendientes_fifo.append([dia, delta_manual])

            # Mantener el baseline al dia (independiente de la rama de arriba) para
            # que el proximo dia calcule su delta manual contra el valor correcto.
            if ep is not None:
                saldo_crudo_anterior = max(
                    Decimal(getattr(ep, 'saldo_puesto_pendiente', None) or getattr(ep, 'pendiente_puesto', 0) or 0),
                    Decimal(0),
                )

            abono_puesto = Decimal((fact.abono_puesto_dia if fact else (ep.abono_puesto if ep else 0)) or 0)
            abono_restante = max(abono_puesto, Decimal(0))

            aplicado_arrastre = min(arrastre, abono_restante)
            arrastre = max(arrastre - aplicado_arrastre, Decimal(0))
            abono_restante -= aplicado_arrastre
            aplicado_por_fecha[dia] += aplicado_arrastre

            while abono_restante > 0 and pendientes_fifo:
                fecha_deuda, saldo_deuda = pendientes_fifo[0]
                aplicar = min(saldo_deuda, abono_restante)
                saldo_deuda -= aplicar
                abono_restante -= aplicar
                aplicado_por_fecha[dia] += aplicar

                if saldo_deuda <= 0:
                    pendientes_fifo.pop(0)
                else:
                    pendientes_fifo[0][1] = saldo_deuda

        pendiente_por_fecha = defaultdict(Decimal)
        for fecha_pendiente, saldo_pendiente in pendientes_fifo:
            pendiente_por_fecha[fecha_pendiente] += max(Decimal(saldo_pendiente or 0), Decimal(0))

        fifo_por_estilista[est_id] = {
            'arrastre_inicial': arrastre_inicial,
            'arrastre_final': arrastre,
            'pendiente_por_fecha': pendiente_por_fecha,
            'aplicado_por_fecha': aplicado_por_fecha,
        }

    solo_deuda_abierta_raw = (request.query_params.get('solo_deuda_abierta') or '').strip().lower()
    solo_deuda_abierta = solo_deuda_abierta_raw in {'1', 'true', 'si', 'sí', 'yes'}

    items = []
    for est in estilistas:
        est_id = int(est.id)
        fifo_est = fifo_por_estilista.get(est_id, {})
        pendiente_por_fecha = fifo_est.get('pendiente_por_fecha', {})
        aplicado_por_fecha = fifo_est.get('aplicado_por_fecha', {})

        for dia in sorted(list(dias_con_movimiento.get(est_id, set())), reverse=True):
            calc_con_comision = _calc_memo(est, dia, True)
            calc_sin_comision = _calc_memo(est, dia, False)
            ep = estados_map.get((est_id, dia))
            fact = facts_map.get((est_id, dia)) if usar_fact else None
            fact_aplica = facts_map_aplica.get((est_id, dia))

            pago_efectivo = Decimal((fact.pago_efectivo if fact else (ep.pago_efectivo if ep else 0)) or 0)
            pago_nequi = Decimal((fact.pago_nequi if fact else (ep.pago_nequi if ep else 0)) or 0)
            pago_daviplata = Decimal((fact.pago_daviplata if fact else (ep.pago_daviplata if ep else 0)) or 0)
            pago_otros = Decimal((fact.pago_otros if fact else (ep.pago_otros if ep else 0)) or 0)
            abono_puesto = Decimal((fact.abono_puesto_dia if fact else (ep.abono_puesto if ep else 0)) or 0)
            medio_abono = (getattr(fact, 'medio_abono_puesto', None) or (getattr(ep, 'medio_abono_puesto', None) if ep else None) or 'efectivo')
            aplica_comision_ventas = bool(getattr(fact_aplica, 'aplica_comision_ventas', True)) if fact_aplica else True
            pagado_total = pago_efectivo + pago_nequi + pago_daviplata + pago_otros
            generado_con_comision = Decimal(calc_con_comision.get('total_pagable') or 0)
            generado_sin_comision = Decimal(calc_sin_comision.get('total_pagable') or 0)
            generado = Decimal((
                max(Decimal(fact.ganancias_totales or 0) - Decimal(fact.descuento_puesto_dia or 0), Decimal(0))
                if fact else (generado_con_comision if aplica_comision_ventas else generado_sin_comision)
            ) or 0)
            descuento_puesto = Decimal((
                fact.descuento_puesto_dia if fact else (calc_con_comision.get('descuento_puesto') if aplica_comision_ventas else calc_sin_comision.get('descuento_puesto'))
            ) or 0)
            descuento_puesto = max(descuento_puesto, Decimal(0))
            deuda_puesto = Decimal((fact.deuda_puesto_cierre if fact else (getattr(ep, 'saldo_puesto_pendiente', 0) if ep else 0)) or 0)
            estado_item = (fact.estado_liquidacion if fact else (ep.estado if ep else 'pendiente'))
            cobro_consumo = Decimal((fact.cobro_consumo_dia if fact else consumo_por_est_dia.get((est_id, dia), Decimal(0))) or 0)

            pendiente_empleado = max(generado - pagado_total, Decimal(0))
            es_v3 = _usa_motor_cash_only(dia)
            if es_v3 and ep is not None:
                # Régimen "solo efectivo": el negocio solo paga en efectivo
                # (monto_pagar_entregado) -- pago_efectivo/nequi/daviplata/otros
                # quedan en 0 por diseño (ver EstadoPagoEstilistaDia), así que
                # "pagado_total"/"pendiente_empleado" deben leerse de los
                # campos nuevos en vez de la fórmula legacy.
                pagado_total = Decimal(getattr(ep, 'monto_pagar_entregado', 0) or 0)
                pendiente_empleado = Decimal(getattr(ep, 'pendiente_pago_empleado_efectivo', 0) or 0)
            # pendiente_por_fecha ya incluye tanto el descuento diferido normal
            # (skip_descuento_puesto=True) como la deuda cargada manualmente (detectada
            # como incremento del saldo acumulado en el loop de arriba), ambos envejecidos
            # correctamente por la misma cola FIFO — por eso cada dia refleja solo lo que
            # aporto ESE dia y no el acumulado completo del empleado.
            deuda_puesto_dia_pendiente = max(Decimal(pendiente_por_fecha.get(dia, Decimal(0)) or 0), Decimal(0))
            abono_puesto_aplicado_fifo = max(Decimal(aplicado_por_fecha.get(dia, Decimal(0)) or 0), Decimal(0))

            if solo_deuda_abierta and pendiente_empleado <= 0 and deuda_puesto_dia_pendiente <= 0 and cobro_consumo <= 0:
                continue

            items.append(
                {
                    'estilista_id': est_id,
                    'estilista_nombre': est.nombre,
                    'fecha': dia.strftime('%Y-%m-%d'),
                    'estado': estado_item,
                    'generado_total': float(generado),
                    'generado_total_con_comision': float(generado_con_comision),
                    'generado_total_sin_comision': float(generado_sin_comision),
                    'descuento_puesto': float(descuento_puesto),
                    'pago_efectivo': float(pago_efectivo),
                    'pago_nequi': float(pago_nequi),
                    'pago_daviplata': float(pago_daviplata),
                    'pago_otros': float(pago_otros),
                    'pagado_total': float(pagado_total),
                    'pendiente_pago_empleado': float(pendiente_empleado),
                    'abono_puesto': float(abono_puesto),
                    'abono_puesto_aplicado_fifo': float(abono_puesto_aplicado_fifo),
                    'medio_abono_puesto': medio_abono,
                    'aplica_comision_ventas': aplica_comision_ventas,
                    'cobro_consumo_dia': float(cobro_consumo),
                    'deuda_puesto_pendiente': float(deuda_puesto),
                    'deuda_puesto_dia_pendiente': float(deuda_puesto_dia_pendiente),
                    'deuda_puesto_dia_cancelada': float(deuda_puesto_dia_pendiente) <= 0.005,
                    'deuda_puesto_arrastre_inicial': float(max(Decimal(fifo_est.get('arrastre_inicial', 0) or 0), Decimal(0))),
                    'deuda_puesto_arrastre_actual': float(max(Decimal(fifo_est.get('arrastre_final', 0) or 0), Decimal(0))),
                    'saldo_puesto_total': float(saldo_puesto_actual_map.get(est_id, Decimal(0))),
                    'saldo_consumo_total': float(saldo_consumo_actual_map.get(est_id, Decimal(0))),
                    **(_campos_liquidacion_v3_dia(ep) if ep is not None else {}),
                }
            )

    items.sort(key=lambda x: (x.get('fecha') or '', x.get('estilista_nombre') or ''), reverse=True)
    return {
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'items': items,
        'total_filas': len(items),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def reporte_ajuste_diario_unificado(request):
    """Tabla unificada por día y empleado para ajustes operativos en una sola vista."""
    return Response(_calcular_ajuste_diario_items(request))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bi_resumen(request):
    """Vista API que retorna datos de BI como JSON"""
    data = _calcular_datos_bi(request)
    if not _tiene_permiso_ui(request.user, 'reportes', 'view', 'agotarse'):
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

    fact_aplica_map = {}
    try:
        fact_aplica_qs = FactLiquidacionEstilistaDia.objects.filter(
            fecha__gte=fecha_inicio_dt,
            fecha__lte=fecha_fin_dt,
            vigente=True,
        ).only('estilista_id', 'fecha', 'aplica_comision_ventas')
        for fact_ap in fact_aplica_qs:
            fact_aplica_map[(int(fact_ap.estilista_id), fact_ap.fecha)] = bool(getattr(fact_ap, 'aplica_comision_ventas', True))
    except Exception:
        fact_aplica_map = {}

    def _aplica_comision_ventas_dia(estilista_id, fecha_operativa):
        if not estilista_id or not fecha_operativa:
            return True
        return fact_aplica_map.get((int(estilista_id), fecha_operativa), True)

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
            fecha_op = _fecha_operativa_desde_dt(venta.fecha_hora)
            if _aplica_comision_ventas_dia(venta.estilista_id, fecha_op):
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
            fecha_op = _fecha_operativa_desde_dt(srv.fecha_hora)
            if _aplica_comision_ventas_dia(srv.adicional_otro_estilista_id, fecha_op):
                pct = Decimal(srv.adicional_otro_producto.comision_estilista or 0)
                if pct < 0:
                    pct = Decimal(0)
                if pct > 100:
                    pct = Decimal(100)
                comision_empleado = (valor_venta * pct) / Decimal(100)

        ganancia = valor_venta - valor_compra - comision_empleado

        # Cierre de caja = contabilidad de TODO lo que factura el salón, sin
        # importar si el cliente pagó en efectivo (va a la caja) o
        # electrónico (va directo a la cuenta del empleado) -- es ingreso
        # del negocio de todas formas, solo cambia quién lo tiene en la mano
        # en este momento. Por eso se cuenta siempre, sin filtrar por medio.
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
            # El ingreso por espacio tiene dos partes: el cobro normal del
            # día (descuento_puesto, si no se saltó ese día) y cualquier
            # abono extra voluntario a la deuda acumulada (abono_puesto).
            # Antes solo se contaba el abono extra -- por eso "Espacios"
            # aparecía en $0 aunque sí se hubiera cobrado puesto ese día.
            descuento_dia_aplicado = Decimal(0) if getattr(ep, 'skip_descuento_puesto', False) else Decimal(ep.descuento_puesto or 0)
            valor_recibido = descuento_dia_aplicado + Decimal(ep.abono_puesto or 0)

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
    # ganancias_empleados_servicios_total: TODO lo que ganaron los empleados
    # en servicios (efectivo o electrónico, cobrado o no) -- es su ganancia
    # real, sin importar el medio de pago ni si ya se las entregaron. Para
    # la tarjeta "Ganancias de empleados".
    ganancias_empleados_servicios_total = Decimal(0)

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

        # Ganancia del empleado en este servicio: se cuenta SIEMPRE (efectivo
        # o electrónico), porque representa lo que ganó, no lo que ya cobró.
        ad_empleado = valor_adicionales_desglosados - Decimal(ad_info['establecimiento'] or 0)
        if ad_empleado < 0:
            ad_empleado = Decimal(0)
        ganancias_empleados_servicios_total += _monto_estilista_resuelto(srv) + ad_empleado

        fecha_op_est = _fecha_operativa_desde_dt(srv.fecha_hora)
        medio_est = (srv.medio_pago or 'efectivo').strip().lower()
        es_electronico_v3 = bool(
            medio_est != 'efectivo' and fecha_op_est and _usa_motor_cash_only(fecha_op_est)
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
                'fecha': fecha_op_est.strftime('%Y-%m-%d') if fecha_op_est else None,
                'numero_factura': srv.numero_factura,
                'tipo_servicio': tipo_servicio,
                'medio_pago': srv.medio_pago,
                'estilista_nombre': srv.estilista.nombre if srv.estilista_id else '',
                'valor_servicio': float(valor_servicio),
                'ganancia_establecimiento': float(ganancia_est),
                # Régimen "solo efectivo": si este % de establecimiento ya
                # está en caja (pago en efectivo) o sigue pendiente de
                # recuperar porque el cliente pagó electrónico directo al
                # empleado (se suma a lo que ese empleado debe transferir
                # al liquidar -- ver Fase 3).
                'recuperado_en_efectivo': not es_electronico_v3,
                'pendiente_electronico': float(ganancia_est) if es_electronico_v3 else 0.0,
            }
        )

    # Cálculo de salidas/entradas de caja por movimientos de liquidación
    # (efectivo entregado al empleado, o transferido de vuelta por él) --
    # se calcula ANTES de las tarjetas de resumen porque "Total ingresos"
    # también necesita `total_transferencias_recibidas` (ver abajo).
    salidas_por_medio_ajuste = {
        'efectivo': Decimal(0),
        'nequi': Decimal(0),
        'daviplata': Decimal(0),
        'otros': Decimal(0),
    }
    ajuste_items = []
    total_transferencias_recibidas = Decimal(0)
    try:
        ajuste_items = _calcular_ajuste_diario_items(request).get('items', []) or []
        for item in ajuste_items:
            if item.get('motor_calculo') == 'v3_efectivo':
                # Régimen "solo efectivo": lo único que sale de caja es el
                # efectivo entregado al empleado. Lo que el empleado
                # transfiere de vuelta (cuando su efectivo no alcanzó) NO se
                # resta aquí de las salidas (se contaría dos veces con el
                # ingreso del servicio, ya contado por su propio medio) ni se
                # suma a ningún ingreso -- queda solo como dato informativo en
                # `transferencias_empleados_recibidas`, fuera de los totales.
                salidas_por_medio_ajuste['efectivo'] += Decimal(str(item.get('monto_pagar_entregado', 0) or 0))
                total_transferencias_recibidas += Decimal(str(item.get('monto_transferir_recibido', 0) or 0))
            else:
                salidas_por_medio_ajuste['efectivo'] += Decimal(str(item.get('pago_efectivo', 0) or 0))
                salidas_por_medio_ajuste['nequi'] += Decimal(str(item.get('pago_nequi', 0) or 0))
                salidas_por_medio_ajuste['daviplata'] += Decimal(str(item.get('pago_daviplata', 0) or 0))
                salidas_por_medio_ajuste['otros'] += Decimal(str(item.get('pago_otros', 0) or 0))
    except Exception:
        pass

    # Tarjetas de cierre de caja -- CONTABILIDAD del negocio: se cuenta TODO
    # lo que el salón factura, sin importar si el cliente pagó en efectivo
    # (va a la caja) o electrónico (va directo a la cuenta del empleado). Es
    # ingreso del negocio de todas formas -- el medio de pago solo cambia
    # quién tiene el dinero en la mano en este momento, no si es o no
    # ingreso. (El desglose por medio de pago, más abajo, sigue mostrando
    # ESE detalle por separado).
    servicios_base_total = Decimal(0)
    servicios_adicionales_total = Decimal(0)
    for srv in servicios_qs:
        servicios_base_total += Decimal(srv.precio_cobrado or 0)
        servicios_adicionales_total += Decimal(srv.valor_adicionales or 0)
    servicios_bruto_total = servicios_base_total + servicios_adicionales_total

    # "Total ingresos": TODO lo que genera el salón -- servicios (precio
    # completo) + productos (venta completa) + espacios, sin importar el
    # medio de pago ni quién tiene el dinero ahora mismo.
    total_ingresos = servicios_bruto_total + ventas_productos_total + ingresos_espacios

    # "Desglose de ingresos": estas 3 tarjetas NO son un reparto de
    # "Total ingresos" (son magnitudes distintas, cada una responde una
    # pregunta distinta) --
    # - Servicios: SOLO lo que se queda el establecimiento por servicios
    #   (su % o los ítems 100% del negocio, como shampoo) -- coincide con la
    #   pestaña de detalle "Servicios" de más abajo.
    # - Productos: el valor bruto de TODO lo vendido (venta directa +
    #   producto dentro de un servicio + abonos de consumo empleado).
    # - Espacios: lo cobrado por uso de espacio (cobro normal del día +
    #   abonos extra a deuda vieja).
    ingresos_servicios_tarjeta = ingresos_servicios_establecimiento
    ingresos_productos_tarjeta = ventas_productos_total
    ingresos_espacios_tarjeta = ingresos_espacios

    # "Ganancias de empleados": lo que ganaron en TOTAL por servicios más su
    # comisión de productos -- su ganancia real, sin importar si el cobro fue
    # en efectivo o electrónico, ni si ya se les entregó ese dinero. No es un
    # movimiento de caja, es informativo de cuánto les corresponde.
    ganancias_empleados_resumen = ganancias_empleados_servicios_total + comision_productos_total
    if ganancias_empleados_resumen < 0:
        ganancias_empleados_resumen = Decimal(0)

    # "Ganancia neta": lo que se queda el establecimiento -- su parte de
    # servicios (todos, sin importar medio de pago), más la utilidad neta de
    # productos (venta - costo - comisión), más los pagos de espacio. Es la
    # ganancia real del negocio, gane el negocio ya haya recuperado ese
    # dinero en la caja o siga en la cuenta personal del empleado hasta que
    # liquide.
    ganancia_producto_neta = ventas_productos_total - costo_productos_total - comision_productos_total
    if ganancia_producto_neta < 0:
        ganancia_producto_neta = Decimal(0)
    ganancia_total = ingresos_servicios_establecimiento + ganancia_producto_neta + ingresos_espacios

    suma_componentes = ingresos_servicios_tarjeta + ganancia_producto_neta + ingresos_espacios_tarjeta

    detalle_medios_bi = data_bi.get('cierre_medios', {}).get('detalle', []) or []
    ingresos_informativos_electronicos = Decimal(str(data_bi.get('cierre_medios', {}).get('ingresos_informativos_electronicos_empleado', 0) or 0))
    medios_orden = ['efectivo', 'nequi', 'daviplata', 'otros']
    ingresos_por_medio = {m: Decimal(0) for m in medios_orden}
    salidas_por_medio_bi = {m: Decimal(0) for m in medios_orden}

    for item in detalle_medios_bi:
        medio_item = str(item.get('medio_pago') or 'otros').strip().lower()
        if medio_item not in ingresos_por_medio:
            medio_item = 'otros'
        ingresos_por_medio[medio_item] += Decimal(str(item.get('ingresos', 0) or 0))
        salidas_por_medio_bi[medio_item] += Decimal(str(item.get('salidas', 0) or 0))

    salidas_final_por_medio = salidas_por_medio_ajuste if ajuste_items else salidas_por_medio_bi

    # Si se solicita un medio específico, el detalle conserva el formato completo
    # pero con valores solo para ese medio para evitar descuadres visuales.
    if medio_pago and medio_pago != 'todos' and medio_pago in ingresos_por_medio:
        for m in medios_orden:
            if m != medio_pago:
                ingresos_por_medio[m] = Decimal(0)
                salidas_final_por_medio[m] = Decimal(0)

    detalle_medios_serializado = []
    for m in medios_orden:
        ingreso_m = ingresos_por_medio.get(m, Decimal(0))
        salida_m = salidas_final_por_medio.get(m, Decimal(0))
        detalle_medios_serializado.append(
            {
                'medio_pago': m,
                'ingresos': float(ingreso_m),
                'salidas': float(salida_m),
                'saldo': float(ingreso_m - salida_m),
            }
        )

    total_ingresos_medios = sum(ingresos_por_medio.values(), Decimal(0))
    total_salidas_medios = sum(salidas_final_por_medio.values(), Decimal(0))

    return Response(
        {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'medio_pago': medio_pago or 'todos',
            'resumen': {
                'total_ingresos': float(total_ingresos),
                'liquidacion_empleados': float(ganancias_empleados_resumen),
                'ganancia_total': float(ganancia_total),
                'ingresos_servicios_establecimiento': float(ingresos_servicios_tarjeta),
                'ingresos_productos_utilidad': float(ingresos_productos_tarjeta),
                'ingresos_espacios': float(ingresos_espacios_tarjeta),
                'suma_componentes_ganancia': float(suma_componentes),
                'diferencia_cuadre': float(ganancia_total - suma_componentes),
                # Informativo, NO sumado a total_ingresos/ganancia_total (ver
                # comentario junto a total_transferencias_recibidas más
                # arriba): dinero que empleados transfirieron de vuelta al
                # negocio porque su efectivo del día no alcanzó para cubrir
                # sus deducciones (puesto/consumo/% establecimiento
                # electrónico mezclados, sin desglose por concepto).
                'transferencias_empleados_recibidas': float(total_transferencias_recibidas),
            },
            'medios': {
                'detalle': detalle_medios_serializado,
                'totales': {
                    'ingresos': float(total_ingresos_medios),
                    'salidas': float(total_salidas_medios),
                    'saldo': float(total_ingresos_medios - total_salidas_medios),
                },
                'ingresos_informativos_electronicos_empleado': float(ingresos_informativos_electronicos),
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
    _requerir_permiso_ui(request.user, 'reportes', 'export_excel', 'cierre', 'No tienes permiso para exportar BI completo.')

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
    _requerir_permiso_ui(request.user, 'reportes', 'export_pdf', 'cierre', 'No tienes permiso para exportar BI completo.')

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


# ============================================================================
# VIEWSETS PARA EL MÓDULO DE CRÉDITOS
# ============================================================================

class PersonaCreditoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para personas externas (no empleados) que pueden tener un
    crédito. Usa los mismos permisos del menú 'creditos' que CreditoViewSet
    -- no es un módulo aparte, es parte del flujo de dar de alta un titular
    de crédito que no es empleado.
    """

    queryset = PersonaCredito.objects.all()
    serializer_class = PersonaCreditoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['activo']
    search_fields = ['nombre', 'telefono', 'documento']
    ordering_fields = ['nombre', 'fecha_registro']
    ordering = ['nombre']

    def get_queryset(self):
        if not _tiene_permiso_ui(self.request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        if not _tiene_permiso_ui(request.user, 'creditos', 'create'):
            raise PermissionDenied('No tienes permiso para crear personas con crédito.')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not _tiene_permiso_ui(request.user, 'creditos', 'edit'):
            raise PermissionDenied('No tienes permiso para editar personas con crédito.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not _tiene_permiso_ui(request.user, 'creditos', 'edit'):
            raise PermissionDenied('No tienes permiso para editar personas con crédito.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not _tiene_permiso_ui(request.user, 'creditos', 'delete'):
            raise PermissionDenied('No tienes permiso para eliminar personas con crédito.')
        instance = self.get_object()
        if instance.creditos.exists():
            return Response(
                {'error': 'No se puede eliminar: esta persona ya tiene créditos registrados. Desactívala en su lugar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class CreditoViewSet(viewsets.ModelViewSet):
    """ViewSet para gestionar créditos a empleados o a personas externas"""

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['estilista', 'persona_credito', 'estado']
    search_fields = ['estilista__nombre', 'persona_credito__nombre', 'observaciones']
    ordering_fields = ['fecha_inicio', 'fecha_vencimiento', 'saldo_actual']
    ordering = ['-fecha_creacion']

    def get_queryset(self):
        """Filtrar créditos con opciones avanzadas"""
        if not _tiene_permiso_ui(self.request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')

        queryset = Credito.objects.select_related(
            'estilista', 'persona_credito', 'usuario_creador', 'usuario_editor'
        ).prefetch_related('abonos').all()

        fecha_inicio = self.request.query_params.get('fecha_inicio_desde')
        if fecha_inicio:
            queryset = queryset.filter(fecha_inicio__gte=fecha_inicio)

        fecha_vencimiento = self.request.query_params.get('fecha_vencimiento_hasta')
        if fecha_vencimiento:
            queryset = queryset.filter(fecha_vencimiento__lte=fecha_vencimiento)

        return queryset

    def get_serializer_class(self):
        """Usar serializer adecuado según la acción"""
        if self.action == 'retrieve':
            return CreditoDetailSerializer
        elif self.action == 'create':
            return CreditoCreateSerializer
        elif self.action in ('update', 'partial_update'):
            return CreditoUpdateSerializer
        return CreditoListSerializer

    def _verificar_permiso(self, action_key):
        if not _tiene_permiso_ui(self.request.user, 'creditos', action_key):
            raise PermissionDenied('No tienes permiso para esta acción sobre Créditos.')

    def create(self, request, *args, **kwargs):
        self._verificar_permiso('create')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._verificar_permiso('edit')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._verificar_permiso('edit')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._verificar_permiso('delete')
        instance = self.get_object()
        if instance.abonos.exists():
            return Response(
                {'error': 'No se puede eliminar un crédito que ya tiene abonos registrados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        estilista = instance.estilista
        persona_credito = instance.persona_credito
        CreditoHistorial.objects.create(
            credito=None,
            estilista=estilista,
            persona_credito=persona_credito,
            accion='credito_eliminado',
            detalle=f"Crédito #{instance.id} eliminado (valor total ${instance.valor_total}), sin abonos registrados.",
            usuario=request.user,
        )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        """Crear crédito y registrar auditoría"""
        serializer.context['request'] = self.request
        credito = serializer.save()
        CreditoHistorial.objects.create(
            credito=credito,
            estilista=credito.estilista,
            persona_credito=credito.persona_credito,
            accion='credito_creado',
            detalle=(
                f"Crédito creado: prestado ${credito.valor_prestado}, "
                f"interés {credito.porcentaje_interes}%, total ${credito.valor_total}, "
                f"vence {credito.fecha_vencimiento}."
            ),
            usuario=self.request.user,
        )

    def perform_update(self, serializer):
        """Editar crédito y registrar auditoría"""
        serializer.context['request'] = self.request
        credito = serializer.save()
        accion = 'credito_cancelado' if credito.estado == 'cancelado' else 'credito_editado'
        CreditoHistorial.objects.create(
            credito=credito,
            estilista=credito.estilista,
            persona_credito=credito.persona_credito,
            accion=accion,
            detalle=f"Crédito actualizado. Estado: {credito.estado}, saldo actual: ${credito.saldo_actual}.",
            usuario=self.request.user,
        )

    @action(detail=False, methods=['get'])
    def resumen(self, request):
        """Obtener resumen general de créditos"""
        if not _tiene_permiso_ui(request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')

        creditos = Credito.objects.all()

        total_prestado = creditos.aggregate(Sum('valor_prestado'))['valor_prestado__sum'] or 0
        total_abonado = sum((c.valor_total - c.saldo_actual for c in creditos), Decimal(0))
        saldo_pendiente = creditos.aggregate(Sum('saldo_actual'))['saldo_actual__sum'] or 0
        creditos_activos = creditos.exclude(estado='cancelado').count()
        creditos_cancelados = creditos.filter(estado='cancelado').count()
        empleados_con_creditos = (
            creditos.exclude(estilista__isnull=True).values('estilista').distinct().count()
            + creditos.exclude(persona_credito__isnull=True).values('persona_credito').distinct().count()
        )

        data = {
            'total_prestado': total_prestado,
            'total_abonado': total_abonado,
            'saldo_pendiente': saldo_pendiente,
            'creditos_activos': creditos_activos,
            'creditos_cancelados': creditos_cancelados,
            'empleados_con_creditos': empleados_con_creditos
        }

        serializer = ResumenCreditosSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='por-titular')
    def por_titular(self, request):
        """
        Resumen de créditos por titular: empleados activos + personas externas
        con crédito, en una sola lista combinada (cada item trae 'tipo':
        'empleado'|'persona'). Se listan TODOS los empleados/personas activos,
        no solo los que ya tienen algún crédito -- si no, nunca se podría
        elegir a alguien para otorgarle su primer crédito.
        """
        if not _tiene_permiso_ui(request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')

        estilistas = Estilista.objects.filter(activo=True).order_by('nombre').prefetch_related('creditos')
        personas = PersonaCredito.objects.filter(activo=True).order_by('nombre').prefetch_related('creditos')

        data_empleados = EstilistaResumenCreditosSerializer(estilistas, many=True).data
        data_personas = PersonaCreditoResumenSerializer(personas, many=True).data

        resultado = [{'tipo': 'empleado', **item} for item in data_empleados]
        resultado += [{'tipo': 'persona', **item} for item in data_personas]
        return Response(resultado)

    @action(detail=False, methods=['get'])
    def historial(self, request):
        """Bitácora de auditoría de créditos, opcionalmente filtrada por estilista_id o persona_credito_id"""
        if not _tiene_permiso_ui(request.user, 'creditos', 'view', 'reportes'):
            raise PermissionDenied('No tienes permiso para ver el historial de auditoría de Créditos.')

        qs = CreditoHistorial.objects.select_related('estilista', 'persona_credito', 'usuario', 'credito').all()
        estilista_id = request.query_params.get('estilista_id')
        if estilista_id:
            qs = qs.filter(estilista_id=estilista_id)
        persona_credito_id = request.query_params.get('persona_credito_id')
        if persona_credito_id:
            qs = qs.filter(persona_credito_id=persona_credito_id)

        serializer = CreditoHistorialSerializer(qs[:300], many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='exportar-excel')
    def exportar_excel(self, request):
        """Exporta créditos a CSV (compatible con Excel), opcionalmente filtrado por estilista_id o persona_credito_id"""
        if not _tiene_permiso_ui(request.user, 'creditos', 'export_excel', 'reportes'):
            raise PermissionDenied('No tienes permiso para exportar Créditos a Excel.')

        estilista_id = request.query_params.get('estilista_id')
        persona_credito_id = request.query_params.get('persona_credito_id')
        creditos = Credito.objects.select_related('estilista', 'persona_credito')
        if estilista_id:
            creditos = creditos.filter(estilista_id=estilista_id)
        if persona_credito_id:
            creditos = creditos.filter(persona_credito_id=persona_credito_id)

        hoy = timezone.localdate()
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="creditos_{hoy}.csv"'
        writer = csv.writer(response)
        writer.writerow(['REPORTE DE CRÉDITOS'])
        writer.writerow(['Generado', timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow([
            'Titular', 'Fecha inicio', 'Valor prestado', 'Interés %', 'Valor interés',
            'Valor total', 'Total abonado', 'Saldo pendiente', 'Fecha vencimiento', 'Estado',
        ])
        for c in creditos.order_by('-fecha_creacion'):
            estado = 'vencido' if c.estado == 'activo' and c.saldo_actual > 0 and c.fecha_vencimiento < hoy else c.estado
            writer.writerow([
                c.titular_nombre,
                c.fecha_inicio.strftime('%Y-%m-%d'),
                f"${float(c.valor_prestado):,.2f}",
                f"{c.porcentaje_interes}%",
                f"${float(c.valor_interes):,.2f}",
                f"${float(c.valor_total):,.2f}",
                f"${float(c.valor_total - c.saldo_actual):,.2f}",
                f"${float(c.saldo_actual):,.2f}",
                c.fecha_vencimiento.strftime('%Y-%m-%d'),
                estado,
            ])
        return response

    @action(detail=False, methods=['get'], url_path='exportar-pdf')
    def exportar_pdf(self, request):
        """Exporta créditos a PDF, opcionalmente filtrado por estilista_id"""
        if not _tiene_permiso_ui(request.user, 'creditos', 'export_pdf', 'reportes'):
            raise PermissionDenied('No tienes permiso para exportar Créditos a PDF.')

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.enums import TA_CENTER
        except Exception:
            return Response(
                {'error': 'La exportación PDF requiere instalar reportlab.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        estilista_id = request.query_params.get('estilista_id')
        persona_credito_id = request.query_params.get('persona_credito_id')
        creditos = Credito.objects.select_related('estilista', 'persona_credito')
        if estilista_id:
            creditos = creditos.filter(estilista_id=estilista_id)
        if persona_credito_id:
            creditos = creditos.filter(persona_credito_id=persona_credito_id)
        creditos = list(creditos.order_by('-fecha_creacion'))

        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CreditoTitle', parent=styles['Heading1'], fontSize=16,
                alignment=TA_CENTER, textColor=colors.HexColor('#5b21b6'),
            )
            hoy = timezone.localdate()
            story = [
                Paragraph('Reporte de Créditos', title_style),
                Paragraph(f'Generado: {timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal']),
                Spacer(1, 0.25 * inch),
            ]
            data = [['Titular', 'Prestado', 'Interés', 'Total', 'Abonado', 'Saldo', 'Vence', 'Estado']]
            for c in creditos:
                estado = 'Vencido' if c.estado == 'activo' and c.saldo_actual > 0 and c.fecha_vencimiento < hoy else c.estado.capitalize()
                data.append([
                    c.titular_nombre,
                    f"${float(c.valor_prestado):,.0f}",
                    f"{c.porcentaje_interes}%",
                    f"${float(c.valor_total):,.0f}",
                    f"${float(c.valor_total - c.saldo_actual):,.0f}",
                    f"${float(c.saldo_actual):,.0f}",
                    c.fecha_vencimiento.strftime('%Y-%m-%d'),
                    estado,
                ])
            tabla = Table(data, repeatRows=1)
            tabla.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5b21b6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f3ff')]),
            ]))
            story.append(tabla)
            doc.build(story)
            buffer.seek(0)
        except Exception as e:
            return Response(
                {'error': f'Error generando PDF: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="creditos_{timezone.localdate()}.pdf"'
        return response


class AbonoCreditoViewSet(viewsets.ModelViewSet):
    """ViewSet para registrar, editar y eliminar abonos a créditos"""

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['credito', 'credito__estilista']
    search_fields = ['observaciones']
    ordering_fields = ['fecha']
    ordering = ['-fecha']
    serializer_class = AbonoCreditoSerializer

    def get_queryset(self):
        """Filtrar abonos con opciones avanzadas"""
        if not _tiene_permiso_ui(self.request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')

        queryset = AbonoCredito.objects.select_related('credito', 'credito__estilista', 'usuario').all()

        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            queryset = queryset.filter(fecha__gte=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            queryset = queryset.filter(fecha__lte=fecha_hasta)

        return queryset

    def _verificar_permiso(self, action_key):
        if not _tiene_permiso_ui(self.request.user, 'creditos', action_key, 'abonos'):
            raise PermissionDenied('No tienes permiso para esta acción sobre abonos de Créditos.')

    def create(self, request, *args, **kwargs):
        self._verificar_permiso('create')
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._verificar_permiso('edit')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._verificar_permiso('edit')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._verificar_permiso('delete')
        instance = self.get_object()
        credito = instance.credito
        detalle = f"Abono de ${instance.valor_abono} del {instance.fecha} eliminado."
        instance.delete()
        _recalcular_cadena_abonos(credito)
        CreditoHistorial.objects.create(
            credito=credito,
            estilista=credito.estilista,
            persona_credito=credito.persona_credito,
            accion='abono_eliminado',
            detalle=detalle,
            usuario=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_create(self, serializer):
        """Registrar abono, asignar usuario actual y auditar"""
        abono = serializer.save(usuario=self.request.user)
        CreditoHistorial.objects.create(
            credito=abono.credito,
            estilista=abono.credito.estilista,
            persona_credito=abono.credito.persona_credito,
            accion='abono_creado',
            detalle=f"Abono de ${abono.valor_abono} registrado. Saldo restante: ${abono.saldo_restante}.",
            usuario=self.request.user,
        )

    def perform_update(self, serializer):
        """Editar abono y auditar"""
        abono = serializer.save()
        CreditoHistorial.objects.create(
            credito=abono.credito,
            estilista=abono.credito.estilista,
            persona_credito=abono.credito.persona_credito,
            accion='abono_editado',
            detalle=f"Abono editado a ${abono.valor_abono}. Saldo restante: ${abono.saldo_restante}.",
            usuario=self.request.user,
        )

    @action(detail=False, methods=['get'])
    def por_credito(self, request):
        """Obtener abonos de un crédito específico"""
        if not _tiene_permiso_ui(request.user, 'creditos', 'view'):
            raise PermissionDenied('No tienes permiso para ver el módulo de Créditos.')

        credito_id = request.query_params.get('credito_id')
        if not credito_id:
            return Response(
                {'error': 'Parámetro credito_id es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            credito = Credito.objects.get(id=credito_id)
            abonos = credito.abonos.all()
            serializer = AbonoCreditoSerializer(abonos, many=True)
            return Response(serializer.data)
        except Credito.DoesNotExist:
            return Response(
                {'error': 'Crédito no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


# ============================================================================
# VIEWSETS: VALE (deuda entre empleados por servicios cobrados en conjunto)
# ============================================================================

class DeudaEntreEmpleadosViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vales: deuda de un empleado hacia un compañero cuando cobró
    electrónicamente el total de una visita con varios servicios de varios
    empleados. Se registran manualmente (ver `registrar_deuda_vale`) y se
    descuentan automáticamente en la liquidación del deudor (ver
    `_aplicar_abonos_vale_interno`), o se pueden saldar a mano registrando
    un abono (AbonoDeudaEntreEmpleadosViewSet).
    """

    queryset = DeudaEntreEmpleados.objects.select_related(
        'deudor', 'acreedor', 'servicio_realizado__servicio'
    ).prefetch_related('abonos').all()
    serializer_class = DeudaEntreEmpleadosSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['deudor', 'acreedor', 'estado']
    ordering_fields = ['fecha_creacion']
    ordering = ['-fecha_creacion']

    def get_queryset(self):
        if not _tiene_permiso_ui(self.request.user, 'reportes', 'view', 'entre_empleados'):
            raise PermissionDenied('No tienes permiso para ver la cuenta entre empleados.')
        return super().get_queryset()


class AbonoDeudaEntreEmpleadosViewSet(viewsets.ModelViewSet):
    """Registrar cuándo un empleado le transfirió a otro su parte de un cobro conjunto."""

    queryset = AbonoDeudaEntreEmpleados.objects.select_related('deuda', 'usuario').all()
    serializer_class = AbonoDeudaEntreEmpleadosSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['deuda']
    ordering_fields = ['fecha']
    ordering = ['-fecha']

    def get_queryset(self):
        if not _tiene_permiso_ui(self.request.user, 'reportes', 'view', 'entre_empleados'):
            raise PermissionDenied('No tienes permiso para ver la cuenta entre empleados.')
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        if not _tiene_permiso_ui(request.user, 'reportes', 'edit', 'entre_empleados'):
            raise PermissionDenied('No tienes permiso para registrar abonos entre empleados.')
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def registrar_deuda_vale(request):
    """
    Registra manualmente un Vale: un empleado (deudor) cobró
    electrónicamente el total de una visita con varios servicios de varios
    empleados (cada uno facturado por separado, uno en medio electrónico y
    los demás en efectivo aunque no haya entrado efectivo físico), y le
    queda debiendo a un compañero (acreedor) la parte que le corresponde.
    Se descuenta automáticamente en la próxima liquidación del deudor (con
    opción de saltar el día, igual que el cobro de puesto).

    POST /api/reportes/estilistas/registrar-deuda-vale/
    Body: { deudor_id, acreedor_id, monto, fecha (opcional), notas (opcional) }
    """
    _requerir_permiso_ui(request.user, 'reportes', 'edit', 'entre_empleados', 'No tienes permiso para registrar un Vale.')

    try:
        deudor = Estilista.objects.get(id=int(request.data.get('deudor_id') or 0), activo=True)
    except Exception:
        return Response({'error': 'Empleado deudor no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        acreedor = Estilista.objects.get(id=int(request.data.get('acreedor_id') or 0), activo=True)
    except Exception:
        return Response({'error': 'Empleado acreedor no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

    if deudor.id == acreedor.id:
        return Response({'error': 'El deudor y el acreedor no pueden ser el mismo empleado.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        monto = Decimal(str(request.data.get('monto') or 0))
    except Exception:
        return Response({'error': 'Monto inválido.'}, status=status.HTTP_400_BAD_REQUEST)
    if monto <= 0:
        return Response({'error': 'El monto debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)

    notas = (request.data.get('notas') or '').strip()[:255]

    fecha_raw = (request.data.get('fecha') or '').strip()
    fecha = timezone.localdate()
    if fecha_raw:
        try:
            fecha = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except Exception:
            return Response({'error': 'Fecha inválida. Usa YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            deuda = DeudaEntreEmpleados.objects.create(
                deudor=deudor,
                acreedor=acreedor,
                servicio_realizado=None,
                monto=monto,
                monto_abonado=Decimal(0),
                saldo_pendiente=monto,
                estado='pendiente',
                fecha=fecha,
                notas=notas,
            )
            saldo_obj, _ = SaldoDeudaPuesto.objects.get_or_create(estilista=deudor)
            saldo_obj.saldo_vale = max(Decimal(saldo_obj.saldo_vale or 0) + monto, Decimal(0))
            saldo_obj.save()
    except Exception as e:
        logger.exception('Error registrando Vale')
        return Response({'error': f'No se pudo registrar el Vale: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            'ok': True,
            'deuda_id': deuda.id,
            'deudor_nombre': deudor.nombre,
            'acreedor_nombre': acreedor.nombre,
            'monto': float(monto),
            'fecha': fecha.strftime('%Y-%m-%d'),
        },
        status=status.HTTP_201_CREATED,
    )
