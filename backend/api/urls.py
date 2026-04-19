from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    UsuarioViewSet, EstilistaViewSet, ServicioViewSet, ClienteViewSet,
    ProductoViewSet, ServicioRealizadoViewSet, VentaProductoViewSet,
    MovimientoInventarioViewSet, estadisticas_generales,
    reporte_ventas, reporte_servicios, bi_resumen, bi_export_csv,
    bi_export_pdf, bi_resumen_diario, estado_pago_estilista_dia,
    estado_pago_estilista_historial, bi_desglose_estilista, bi_desglose_estilista_debug,
    reporte_consumo_empleado, abonar_consumo_empleado, editar_abono_consumo_empleado, reporte_cierre_caja,
    liquidar_dia_v2, liquidar_operacion_integral, cargar_deuda_puesto_dia, eliminar_estado_pago_historial, mover_fecha_estado_pago_dia, qz_certificate, qz_sign,
    reporte_ajuste_diario_unificado
)

# Crear router para los viewsets
router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet, basename='usuario')
router.register(r'estilistas', EstilistaViewSet, basename='estilista')
router.register(r'servicios', ServicioViewSet, basename='servicio')
router.register(r'clientes', ClienteViewSet, basename='cliente')
router.register(r'productos', ProductoViewSet, basename='producto')
router.register(r'servicios-realizados', ServicioRealizadoViewSet, basename='servicio-realizado')
router.register(r'ventas', VentaProductoViewSet, basename='venta')
router.register(r'movimientos-inventario', MovimientoInventarioViewSet, basename='movimiento-inventario')

urlpatterns = [
    # Autenticación JWT
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # QZ Tray signing
    path('qz/certificate/', qz_certificate, name='qz-certificate'),
    path('qz/sign/', qz_sign, name='qz-sign'),
    
    # Reportes y estadísticas
    path('reportes/estadisticas/', estadisticas_generales, name='estadisticas-generales'),
    path('reportes/ventas/', reporte_ventas, name='reporte-ventas'),
    path('reportes/servicios/', reporte_servicios, name='reporte-servicios'),
    path('reportes/bi/', bi_resumen, name='reporte-bi'),
    path('reportes/bi/export/', bi_export_csv, name='reporte-bi-export'),
    path('reportes/bi/export-pdf/', bi_export_pdf, name='reporte-bi-export-pdf'),
    path('reportes/bi/resumen-diario/', bi_resumen_diario, name='reporte-bi-resumen-diario'),
    path('reportes/bi/desglose/', bi_desglose_estilista, name='reporte-bi-desglose-estilista'),
    path('reportes/bi/desglose-debug/', bi_desglose_estilista_debug, name='reporte-bi-desglose-debug'),
    path('reportes/estilistas/estado-pago-dia/', estado_pago_estilista_dia, name='reporte-estilista-estado-pago-dia'),
    path('reportes/estilistas/estado-pago-historial/', estado_pago_estilista_historial, name='reporte-estilista-estado-pago-historial'),
    path('reportes/estilistas/estado-pago-historial/<int:historial_id>/', eliminar_estado_pago_historial, name='reporte-estilista-estado-pago-historial-eliminar'),
    path('reportes/estilistas/estado-pago-dia/<int:estado_id>/mover-fecha/', mover_fecha_estado_pago_dia, name='reporte-estilista-estado-pago-dia-mover-fecha'),
    path('reportes/estilistas/liquidar-dia-v2/', liquidar_dia_v2, name='reportes-estilista-liquidar-dia-v2'),
    path('reportes/estilistas/liquidar-operacion-integral/', liquidar_operacion_integral, name='reportes-estilista-liquidar-operacion-integral'),
    path('reportes/estilistas/cargar-deuda-puesto/', cargar_deuda_puesto_dia, name='reportes-estilista-cargar-deuda-puesto'),
    path('reportes/consumo-empleado/deudas/', reporte_consumo_empleado, name='reporte-consumo-empleado-deudas'),
    path('reportes/consumo-empleado/abonar/', abonar_consumo_empleado, name='reporte-consumo-empleado-abonar'),
    path('reportes/consumo-empleado/abonos/<int:abono_id>/', editar_abono_consumo_empleado, name='reporte-consumo-empleado-abono-editar'),
    path('reportes/ajuste-diario/', reporte_ajuste_diario_unificado, name='reporte-ajuste-diario-unificado'),
    path('reportes/cierre-caja/', reporte_cierre_caja, name='reporte-cierre-caja'),
    
    # Incluir todas las rutas del router
    path('', include(router.urls)),
]
