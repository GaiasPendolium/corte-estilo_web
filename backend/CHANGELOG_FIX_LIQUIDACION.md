# 🐛 Fix: Liquidación de Estilista mostrando $0 (22 de marzo de 2026)

## Problema Reportado
- En el menú de reportes de "Liquidación por estilista", el campo **"Neto pendiente"** mostraba **$0** incluso cuando había servicios
- Ejemplo: Angel mostraba "Base para pagar: $10.000" pero "Neto pendiente: $0"
- El problema ocurría cuando el usuario cambiaba el estado a "Cancelado" y después lo revirtía a "Pendiente"

## Raíz del Problema
En la función `_calcular_datos_bi()` del backend ([views.py línea 595](backend/api/views.py#L595)):

**Líneas 620-628** filtraban servicios y ventas con **STRINGS**:
```python
servicios_qs = ServicioRealizado.objects.filter(
    fecha_hora__date__gte=fecha_inicio,  # ← STRING (ej: '2026-03-01')
    fecha_hora__date__lte=fecha_fin,      # ← STRING
)
```

**Línea 691** filtraba estados de pago con **datetime.date**:
```python
EstadoPagoEstilistaDia.objects.filter(
    fecha__gte=fecha_inicio_dt,  # ← datetime.date
    fecha__lte=fecha_fin_dt       # ← datetime.date
)
```

Esta **inconsistencia de tipos de datos** causaba que:
1. Los servicios se filtraban con strings
2. Los estados de pago se filtraban con datetime.date
3. En ciertos casos (especialmente con timezones o conversiones), podían no alinearse correctamente
4. Resultado: `pago_neto_pendiente` = $0 porque los estados no coincidían con los servicios

## Solución Implementada
**Cambio en [views.py línea 620-628](backend/api/views.py#L620-L628):**

```python
# ✅ DESPUÉS (Fix)
servicios_qs = ServicioRealizado.objects.filter(
    estado='finalizado',
    fecha_hora__date__gte=fecha_inicio_dt,  # ← Ahora datetime.date
    fecha_hora__date__lte=fecha_fin_dt,     # ← Ahora datetime.date
)
ventas_qs = VentaProducto.objects.filter(
    fecha_hora__date__gte=fecha_inicio_dt,  # ← Ahora datetime.date
    fecha_hora__date__lte=fecha_fin_dt,     # ← Ahora datetime.date
)
```

Esto asegura que **ambos filtros usen el mismo tipo de datos** (datetime.date), garantizando que:
- Los servicios se filtren correctamente
- Los estados de pago se alineen con los servicios
- El cálculo de `pago_neto_pendiente` sea consistente

## Archivos Modificados
- `backend/api/views.py` - Línea 620-628

## Verificación
✅ Test creado: `backend/test_fecha_fix.py` - Valida consistencia de tipos de fecha

## Impacto
- **Criticidad:** Alta (afecta reportes de pago a estilistas)
- **Alcance:** Endpoint API `/api/reportes/bi-resumen/`
- **Backward compatible:** Sí
- **Requiere migración:** No
