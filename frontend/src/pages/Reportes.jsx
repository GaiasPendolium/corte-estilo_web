import { useCallback, useEffect, useMemo, useState } from 'react';
import { format } from 'date-fns';
import { reportesService } from '../services/api';
import { toast } from 'react-toastify';
import useAuthStore from '../store/authStore';

const today = new Date();
const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

const MODULOS = [
  { key: 'cierre', label: '1. Cierre de Caja' },
  { key: 'liquidacion', label: '2. Liquidacion Empleado' },
  { key: 'cartera', label: '3. Cartera Empleado' },
  { key: 'agotarse', label: '4. Productos Agotarse' },
];

const MEDIOS_PAGO = [
  { value: 'todos', label: 'Todos los medios' },
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const MEDIOS_PAGO_OPERACION = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const moneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const formatMoney = (value) => `$${moneyFormatter.format(Number(value || 0))}`;

const KpiCard = ({ title, value, hint, tone = 'slate' }) => {
  const tones = {
    slate: 'from-slate-900 to-slate-700 text-white',
    emerald: 'from-emerald-600 to-teal-500 text-white',
    sky: 'from-sky-600 to-blue-600 text-white',
    amber: 'from-amber-500 to-orange-500 text-white',
  };

  return (
    <div className={`rounded-2xl bg-gradient-to-br ${tones[tone]} p-5 shadow-lg`}>
      <p className="text-sm opacity-85">{title}</p>
      <p className="mt-2 text-2xl font-black">{value}</p>
      <p className="mt-2 text-xs opacity-85">{hint}</p>
    </div>
  );
};

const NumericPad = ({ visible, value, onChange, onClose }) => {
  if (!visible) return null;

  const append = (token) => {
    const current = String(value || '');
    if (token === 'DEL') {
      onChange(current.slice(0, -1));
      return;
    }
    if (token === 'C') {
      onChange('');
      return;
    }
    if (token === '00') {
      onChange(`${current}00`);
      return;
    }
    onChange(`${current}${token}`);
  };

  return (
    <div className="fixed bottom-4 right-4 z-[80] w-[280px] rounded-2xl border border-slate-300 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-100 px-4 py-2 rounded-t-2xl">
        <span className="text-sm font-semibold text-slate-700">Teclado numérico</span>
        <button type="button" className="btn-secondary !px-3 !py-1" onClick={onClose}>Cerrar</button>
      </div>
      <div className="p-3">
        <div className="mb-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-right text-lg font-bold text-slate-900 min-h-[44px]">
          {value || '0'}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '00', 'DEL'].map((k) => (
            <button key={k} type="button" className="btn-secondary !py-3" onClick={() => append(k)}>
              {k}
            </button>
          ))}
        </div>
        <button type="button" className="btn-danger !w-full !py-3 mt-2" onClick={() => append('C')}>Limpiar</button>
      </div>
    </div>
  );
};

const Reportes = () => {
  const { user } = useAuthStore();
  const esAdministrador = String(user?.rol || '').toLowerCase() === 'administrador';
  const esRecepcion = String(user?.rol || '').toLowerCase() === 'recepcion';
  const [moduloActivo, setModuloActivo] = useState('cierre');
  const [periodo, setPeriodo] = useState('mes');
  const [fechaInicio, setFechaInicio] = useState(format(firstDay, 'yyyy-MM-dd'));
  const [fechaFin, setFechaFin] = useState(format(today, 'yyyy-MM-dd'));
  const [medioPago, setMedioPago] = useState('todos');

  const [loading, setLoading] = useState(true);
  const [cierreCaja, setCierreCaja] = useState(null);
  const [biData, setBiData] = useState(null);
  const [carteraData, setCarteraData] = useState({ resumen: [], deudas: [], abonos_historial: [] });
  const [abonoPorDeuda, setAbonoPorDeuda] = useState({});
  const [medioAbonoPorDeuda, setMedioAbonoPorDeuda] = useState({});
  const [savingAbonoByDeuda, setSavingAbonoByDeuda] = useState({});
  const [editMontoByAbono, setEditMontoByAbono] = useState({});
  const [editMedioByAbono, setEditMedioByAbono] = useState({});
  const [editNotasByAbono, setEditNotasByAbono] = useState({});
  const [savingEditByAbono, setSavingEditByAbono] = useState({});
  const [deudaActivaHistorial, setDeudaActivaHistorial] = useState(null);
  const [pagosPorEstilista, setPagosPorEstilista] = useState({});
  const [estadoDiaPorEstilista, setEstadoDiaPorEstilista] = useState({});
  const [abonoPuestoPorEstilista, setAbonoPuestoPorEstilista] = useState({});
  const [medioAbonoPuestoPorEstilista, setMedioAbonoPuestoPorEstilista] = useState({});
  const [cobroConsumoPorEstilista, setCobroConsumoPorEstilista] = useState({});
  const [medioCobroConsumoPorEstilista, setMedioCobroConsumoPorEstilista] = useState({});
  const [savingEstadoByEstilista, setSavingEstadoByEstilista] = useState({});
  const [numericPadTarget, setNumericPadTarget] = useState(null);
  const [historialEstados, setHistorialEstados] = useState([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);

  const modulosVisibles = useMemo(() => {
    if (!esRecepcion) return MODULOS;
    return MODULOS.filter((mod) => mod.key === 'cierre' || mod.key === 'liquidacion');
  }, [esRecepcion]);

  useEffect(() => {
    if (modulosVisibles.some((mod) => mod.key === moduloActivo)) return;
    setModuloActivo(modulosVisibles[0]?.key || 'cierre');
  }, [modulosVisibles, moduloActivo]);

  const paramsBase = useMemo(
    () => ({
      periodo,
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      ...(medioPago !== 'todos' ? { medio_pago: medioPago } : {}),
    }),
    [periodo, fechaInicio, fechaFin, medioPago]
  );

  const cargarTodo = useCallback(async () => {
    try {
      setLoading(true);
      const [cierreResp, biResp] = await Promise.all([
        reportesService.getCierreCaja(paramsBase),
        reportesService.getBIResumen(paramsBase),
      ]);

      let carteraResp = null;
      if (!esRecepcion) {
        carteraResp = await reportesService.getConsumoEmpleadoDeudas({
          periodo,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
        });
      }

      setCierreCaja(cierreResp || null);
      setBiData(biResp || null);
      setCarteraData({
        resumen: carteraResp?.resumen || [],
        deudas: carteraResp?.deudas || [],
        abonos_historial: carteraResp?.abonos_historial || [],
      });

      try {
        setLoadingHistorial(true);
        const hist = await reportesService.getEstadoPagoHistorial({
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
          limit: 200,
        });
        setHistorialEstados(hist?.items || []);
      } catch (err) {
        setHistorialEstados([]);
      } finally {
        setLoadingHistorial(false);
      }

      if (fechaInicio === fechaFin) {
        try {
          const estadoDia = await reportesService.getEstadoPagoEstilistaDia(fechaInicio);
          const mapPagos = {};
          const mapEstado = {};
          (estadoDia?.items || []).forEach((x) => {
            mapPagos[x.estilista_id] = {
              efectivo: String(Number(x.pago_efectivo || 0) || ''),
              nequi: String(Number(x.pago_nequi || 0) || ''),
              daviplata: String(Number(x.pago_daviplata || 0) || ''),
              otros: String(Number(x.pago_otros || 0) || ''),
            };
            mapEstado[x.estilista_id] = x.estado || 'pendiente';
          });
          setPagosPorEstilista(mapPagos);
          setEstadoDiaPorEstilista(mapEstado);
          setAbonoPuestoPorEstilista(
            Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, String(Number(x.abono_puesto || 0) || '')]))
          );
          setMedioAbonoPuestoPorEstilista(
            Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, x.medio_abono_puesto || 'efectivo']))
          );
          setCobroConsumoPorEstilista({});
          setMedioCobroConsumoPorEstilista({});
        } catch (err) {
          setPagosPorEstilista({});
          setEstadoDiaPorEstilista({});
          setAbonoPuestoPorEstilista({});
          setMedioAbonoPuestoPorEstilista({});
          setCobroConsumoPorEstilista({});
          setMedioCobroConsumoPorEstilista({});
        }
      } else {
        setPagosPorEstilista({});
        setEstadoDiaPorEstilista({});
        setAbonoPuestoPorEstilista({});
        setMedioAbonoPuestoPorEstilista({});
        setCobroConsumoPorEstilista({});
        setMedioCobroConsumoPorEstilista({});
      }
    } catch (error) {
      toast.error('No se pudieron cargar los reportes');
      setCierreCaja(null);
      setBiData(null);
      setCarteraData({ resumen: [], deudas: [], abonos_historial: [] });
    } finally {
      setLoading(false);
    }
  }, [paramsBase, periodo, fechaInicio, fechaFin, esRecepcion]);

  useEffect(() => {
    cargarTodo();
  }, [cargarTodo]);

  const aplicarRangoRapido = (tipo) => {
    const base = new Date();
    if (tipo === 'hoy') {
      const value = format(base, 'yyyy-MM-dd');
      setFechaInicio(value);
      setFechaFin(value);
      setPeriodo('personalizado');
      return;
    }
    if (tipo === 'ayer') {
      const ayer = new Date(base);
      ayer.setDate(base.getDate() - 1);
      const value = format(ayer, 'yyyy-MM-dd');
      setFechaInicio(value);
      setFechaFin(value);
      setPeriodo('personalizado');
      return;
    }
    if (tipo === '7dias') {
      const inicio = new Date(base);
      inicio.setDate(base.getDate() - 6);
      setFechaInicio(format(inicio, 'yyyy-MM-dd'));
      setFechaFin(format(base, 'yyyy-MM-dd'));
      setPeriodo('personalizado');
      return;
    }

    const inicioMes = new Date(base.getFullYear(), base.getMonth(), 1);
    setFechaInicio(format(inicioMes, 'yyyy-MM-dd'));
    setFechaFin(format(base, 'yyyy-MM-dd'));
    setPeriodo('mes');
  };

  const resumen = cierreCaja?.resumen || {};
  const medios = cierreCaja?.medios?.detalle || [];
  const productos = cierreCaja?.productos || { detalle: [] };
  const espacios = cierreCaja?.espacios || { detalle: [] };
  const serviciosEst = cierreCaja?.servicios_establecimiento || { detalle: [] };
  const ingresoServiciosTarjeta = Number(
    serviciosEst?.total_ganancia ?? resumen?.ingresos_servicios_establecimiento ?? 0
  );
  const ingresoProductosTarjeta = Number(productos?.ingresos_venta_neto_comision ?? productos?.ingresos_venta ?? 0);
  const ingresoEspaciosTarjeta = Number(resumen?.ingresos_espacios ?? espacios?.total_recibido ?? 0);
  const gananciaTotalTarjeta = ingresoServiciosTarjeta + ingresoProductosTarjeta + ingresoEspaciosTarjeta;
  const liquidacionPagadoCaja = Number(resumen?.liquidacion_empleados ?? 0);

  const liquidacionTotal = (biData?.estilistas || []).reduce((sum, item) => {
    const valorTotalEmpleado = Number((item.valor_total_empleado ?? item.facturacion_servicios ?? item.ganancias_servicios) || 0);
    const comisionesEmpleado = Number(item.comision_ventas_producto || 0);
    return sum + valorTotalEmpleado + comisionesEmpleado;
  }, 0);
  const liquidacionPendiente = Math.max(liquidacionTotal - liquidacionPagadoCaja, 0);

  const actualizarPagoMedio = (estilistaId, medio, valor) => {
    const limpio = String(valor || '').replace(/[^\d.]/g, '');
    setPagosPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: {
        efectivo: prev[estilistaId]?.efectivo || '',
        nequi: prev[estilistaId]?.nequi || '',
        daviplata: prev[estilistaId]?.daviplata || '',
        otros: prev[estilistaId]?.otros || '',
        [medio]: limpio,
      },
    }));
  };

  const totalPagoMedios = (estilistaId) => {
    const pagos = pagosPorEstilista[estilistaId] || {};
    return ['efectivo', 'nequi', 'daviplata', 'otros']
      .map((k) => Number(pagos[k] || 0))
      .reduce((acc, val) => acc + (Number.isFinite(val) ? val : 0), 0);
  };

  const getNumericPadValue = () => {
    if (!numericPadTarget?.estilistaId || !numericPadTarget?.field) return '';
    const estId = numericPadTarget.estilistaId;
    const field = numericPadTarget.field;
    if (['efectivo', 'nequi', 'daviplata', 'otros'].includes(field)) {
      return pagosPorEstilista[estId]?.[field] || '';
    }
    if (field === 'abono_puesto') return abonoPuestoPorEstilista[estId] || '';
    if (field === 'cobro_consumo') return cobroConsumoPorEstilista[estId] || '';
    return '';
  };

  const setNumericPadValue = (nextValue) => {
    if (!numericPadTarget?.estilistaId || !numericPadTarget?.field) return;
    const estId = numericPadTarget.estilistaId;
    const field = numericPadTarget.field;
    const limpio = String(nextValue || '').replace(/[^\d.]/g, '');

    if (['efectivo', 'nequi', 'daviplata', 'otros'].includes(field)) {
      setPagosPorEstilista((prev) => ({
        ...prev,
        [estId]: {
          efectivo: prev[estId]?.efectivo || '',
          nequi: prev[estId]?.nequi || '',
          daviplata: prev[estId]?.daviplata || '',
          otros: prev[estId]?.otros || '',
          [field]: limpio,
        },
      }));
      return;
    }

    if (field === 'abono_puesto') {
      setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: limpio }));
      return;
    }

    if (field === 'cobro_consumo') {
      setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: limpio }));
    }
  };

  const cobrarConsumoEnDeudas = async ({ estilistaId, monto, medioPago, fecha }) => {
    const deudas = (carteraData?.deudas || [])
      .filter((d) => Number(d.estilista_id) === Number(estilistaId) && Number(d.saldo_pendiente || 0) > 0)
      .sort((a, b) => String(a.fecha_hora || '').localeCompare(String(b.fecha_hora || '')));

    let restante = Number(monto || 0);
    let cobrado = 0;

    for (const deuda of deudas) {
      if (restante <= 0) break;
      const saldo = Number(deuda.saldo_pendiente || 0);
      if (saldo <= 0) continue;
      const abono = Math.min(restante, saldo);
      await reportesService.abonarConsumoEmpleado({
        estilista_id: estilistaId,
        deuda_id: deuda.deuda_id,
        monto: abono,
        medio_pago: medioPago,
        notas: `Cobro consumo integrado en liquidacion ${fecha}`,
      });
      cobrado += abono;
      restante -= abono;
    }

    return { cobrado, restante };
  };

  const resumenPorEstilista = useMemo(() => {
    const mapa = {};
    (carteraData?.resumen || []).forEach((item) => {
      mapa[item.estilista_id] = item;
    });
    return mapa;
  }, [carteraData]);

  const deudaSeleccionada = useMemo(
    () => (carteraData?.deudas || []).find((d) => Number(d.deuda_id) === Number(deudaActivaHistorial)) || null,
    [carteraData, deudaActivaHistorial]
  );

  const abonarFacturaCartera = async (deuda) => {
    const deudaId = Number(deuda?.deuda_id || 0);
    const monto = Number(abonoPorDeuda[deudaId] || 0);
    const medio = medioAbonoPorDeuda[deudaId] || 'efectivo';

    if (!deudaId) {
      toast.error('Factura inválida.');
      return;
    }
    if (!Number.isFinite(monto) || monto <= 0) {
      toast.error('Ingresa un valor de abono mayor a 0.');
      return;
    }

    setSavingAbonoByDeuda((prev) => ({ ...prev, [deudaId]: true }));
    try {
      await reportesService.abonarConsumoEmpleado({
        estilista_id: deuda.estilista_id,
        deuda_id: deudaId,
        monto,
        medio_pago: medio,
        notas: `Abono cartera factura ${deuda.numero_factura || deudaId}`,
      });
      toast.success('Abono registrado correctamente.');
      setAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: '' }));
      await cargarTodo();
      setDeudaActivaHistorial(deudaId);
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo registrar el abono.';
      toast.error(msg);
    } finally {
      setSavingAbonoByDeuda((prev) => ({ ...prev, [deudaId]: false }));
    }
  };

  const editarAbonoCartera = async (abono, deuda) => {
    const abonoId = Number(abono?.abono_id || 0);
    const monto = Number(editMontoByAbono[abonoId] || 0);
    const medio = editMedioByAbono[abonoId] || abono.medio_pago || 'efectivo';
    const notas = editNotasByAbono[abonoId] ?? (abono.notas || '');
    if (!abonoId) {
      toast.error('Abono inválido.');
      return;
    }
    if (!Number.isFinite(monto) || monto <= 0) {
      toast.error('El nuevo valor del abono debe ser mayor a 0.');
      return;
    }

    setSavingEditByAbono((prev) => ({ ...prev, [abonoId]: true }));
    try {
      await reportesService.editarAbonoConsumoEmpleado({
        abono_id: abonoId,
        monto,
        medio_pago: medio,
        notas,
      });
      toast.success('Abono actualizado.');
      await cargarTodo();
      setDeudaActivaHistorial(deuda?.deuda_id || null);
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo editar el abono.';
      toast.error(msg);
    } finally {
      setSavingEditByAbono((prev) => ({ ...prev, [abonoId]: false }));
    }
  };

const aplicarEstadoLiquidacion = async (fila) => {
  const estilistaId = fila.estilista_id;
  const esDiaUnico = fechaInicio === fechaFin;
  
  if (!esDiaUnico) {
    toast.warning('⚠️ Para liquidación debes seleccionar UN SOLO DÍA');
    return;
  }
  
  const pago_efectivo = Number(pagosPorEstilista[estilistaId]?.efectivo || 0);
  const pago_nequi = Number(pagosPorEstilista[estilistaId]?.nequi || 0);
  const pago_daviplata = Number(pagosPorEstilista[estilistaId]?.daviplata || 0);
  const pago_otros = Number(pagosPorEstilista[estilistaId]?.otros || 0);
  const abono_puesto = Number(abonoPuestoPorEstilista[estilistaId] || 0);
  const medio_abono_puesto = medioAbonoPuestoPorEstilista[estilistaId] || 'efectivo';
  const saldoConsumoEmpleado = Number(resumenPorEstilista[estilistaId]?.saldo_pendiente || 0);
  const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[estilistaId] || 0);
  const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(saldoConsumoEmpleado, 0));
  const medioCobroConsumo = medioCobroConsumoPorEstilista[estilistaId] || 'efectivo';
  
  setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: true }));
  
  try {
    let resumenCobro = null;
    if (cobroConsumoAplicado > 0) {
      resumenCobro = await cobrarConsumoEnDeudas({
        estilistaId,
        monto: cobroConsumoAplicado,
        medioPago: medioCobroConsumo,
        fecha: fechaInicio,
      });
    }

    const resultado = await reportesService.liquidarDiaV2({
      estilista_id: estilistaId,
      fecha: fechaInicio,
      pago_efectivo,
      pago_nequi,
      pago_daviplata,
      pago_otros,
      abono_puesto,
      medio_abono_puesto,
      notas: `Liquidación ${fechaInicio}`,
    });
    const g = resultado.liquidacion.ganancias_totales;
    const d = resultado.liquidacion.descuento_puesto;
    const d_ant = resultado.puesto.deuda_anterior;
    const d_tot = resultado.puesto.deuda_total;
    const p = resultado.pagos.total;
    const s = resultado.puesto.saldo_pendiente;
    
    const msgDeuda = d_ant > 0 ? ` (${formatMoney(d_ant)} anterior + ${formatMoney(d)} hoy)` : '';
    const msgConsumo = resumenCobro && resumenCobro.cobrado > 0
      ? ` - Consumo cobrado ${formatMoney(resumenCobro.cobrado)}`
      : '';
    toast.success(`✓ ${resultado.estilista.nombre}: Gan ${formatMoney(g)} - Puesto ${formatMoney(d_tot)}${msgDeuda}${msgConsumo} - Pagado ${formatMoney(p)} - Saldo ${formatMoney(s)}`);
    
    // Actualizar estado localmente de inmediato para UI responsiva
    setEstadoDiaPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: resultado.estado,
    }));
    
    await cargarTodo();
  } catch (error) {
    const msg = error?.response?.data?.error || error?.message || 'No se pudo procesar la liquidación.';
    toast.error(`❌ ${msg}`);
  } finally {
    setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: false }));
  }
};

  const eliminarRegistroHistorial = async (registro) => {
    if (!esAdministrador) {
      toast.error('Solo el administrador puede eliminar registros del historial');
      return;
    }

    const ok = window.confirm(
      `Se eliminará el historial de ${registro.estilista_nombre || 'empleado'} del día ${registro.fecha || '-'} y su registro diario asociado. ¿Deseas continuar?`
    );
    if (!ok) return;

    try {
      await reportesService.deleteEstadoPagoHistorial(registro.id);
      toast.success('Registro eliminado correctamente');
      await cargarTodo();
    } catch (err) {
      const msg = err?.response?.data?.error || 'No se pudo eliminar el registro del historial';
      toast.error(msg);
    }
  };

  const renderModuloCierreCaja = () => (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <KpiCard title="Ingresos Totales" value={formatMoney(resumen.total_ingresos)} hint="Total ingresos recibidos del periodo" tone="slate" />
        <div className="rounded-2xl bg-gradient-to-br from-sky-600 to-blue-600 text-white p-5 shadow-lg">
          <p className="text-sm opacity-85">Liquidacion Empleado</p>
          <p className="mt-2 text-lg font-black">Total: {formatMoney(liquidacionTotal)}</p>
          <p className="mt-1 text-sm opacity-90">Pagado en caja: {formatMoney(liquidacionPagadoCaja)}</p>
          <p className="mt-1 text-sm opacity-90">Pendiente: {formatMoney(liquidacionPendiente)}</p>
        </div>
        <KpiCard title="Ganancia Total" value={formatMoney(gananciaTotalTarjeta)} hint="Ingreso por Servicios + Ingreso por Productos + Ingreso por Espacios" tone="emerald" />
        <KpiCard title="Ingreso por Servicios" value={formatMoney(ingresoServiciosTarjeta)} hint="Ganancia del establecimiento en servicios y adicionales" tone="slate" />
        <KpiCard title="Ingreso por Productos" value={formatMoney(ingresoProductosTarjeta)} hint="Valor de productos menos comision de empleado" tone="amber" />
        <KpiCard title="Ingreso por Espacios" value={formatMoney(resumen.ingresos_espacios)} hint="Pagos recibidos por espacio" tone="sky" />
      </div>

      <div className="card border border-indigo-200 bg-indigo-50">
        <h2 className="card-header">Cuadre por medio de pago</h2>
        <p className="text-sm text-slate-600">Saldo por medio = ingresos del medio - liquidaciones del medio.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Medio</th>
                <th className="px-4 py-3 text-left">Ingresos</th>
                <th className="px-4 py-3 text-left">Liquidacion</th>
                <th className="px-4 py-3 text-left">Ganancia</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {medios.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={4}>No hay movimientos para el rango seleccionado.</td>
                </tr>
              )}
              {medios.map((m) => (
                <tr key={m.medio_pago}>
                  <td className="table-cell capitalize font-medium">{m.medio_pago || '-'}</td>
                  <td className="table-cell">{formatMoney(m.ingresos)}</td>
                  <td className="table-cell">{formatMoney(m.salidas)}</td>
                  <td className={`table-cell font-semibold ${Number(m.saldo || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                    {formatMoney(m.saldo)}
                  </td>
                </tr>
              ))}
              {medios.length > 0 && (
                <tr className="bg-indigo-100 font-semibold">
                  <td className="table-cell">TOTAL</td>
                  <td className="table-cell">{formatMoney(medios.reduce((sum, m) => sum + Number(m.ingresos || 0), 0))}</td>
                  <td className="table-cell">{formatMoney(medios.reduce((sum, m) => sum + Number(m.salidas || 0), 0))}</td>
                  <td className="table-cell text-indigo-900">{formatMoney(medios.reduce((sum, m) => sum + Number(m.saldo || 0), 0))}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card border border-emerald-200 bg-emerald-50">
        <h2 className="card-header">Detalle de productos vendidos</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-emerald-200 bg-white p-4">
            <p className="text-sm text-slate-500">Ingresos de productos</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{formatMoney(productos.ingresos_venta)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-4">
            <p className="text-sm text-slate-500">Valor de compra</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{formatMoney(productos.valor_compra)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-4">
            <p className="text-sm text-slate-500">Ganancia neta</p>
            <p className="text-2xl font-bold text-emerald-700 mt-1">{formatMoney(productos.ganancia_neta)}</p>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Fecha</th>
                <th className="px-4 py-3 text-left">Origen</th>
                <th className="px-4 py-3 text-left">Descripcion</th>
                <th className="px-4 py-3 text-left">Cantidad</th>
                <th className="px-4 py-3 text-left">Valor venta</th>
                <th className="px-4 py-3 text-left">Valor compra</th>
                <th className="px-4 py-3 text-left">Comision empleado</th>
                <th className="px-4 py-3 text-left">Ganancia neta</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {(productos.detalle || []).length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={8}>No hay detalle de productos en el rango seleccionado.</td>
                </tr>
              )}
              {(productos.detalle || []).map((item, idx) => (
                <tr key={`${item.fecha_hora || item.fecha || 'x'}-${idx}`}>
                  <td className="table-cell">{item.fecha_hora || item.fecha || '-'}</td>
                  <td className="table-cell">
                    {item.origen === 'adicional_producto_servicio'
                      ? 'Servicio adicional producto'
                      : item.origen === 'consumo_empleado'
                        ? 'Consumo empleado'
                        : 'Venta producto'}
                  </td>
                  <td className="table-cell">{item.descripcion || '-'}</td>
                  <td className="table-cell">{item.cantidad || 0}</td>
                  <td className="table-cell">{formatMoney(item.valor_venta)}</td>
                  <td className="table-cell">{formatMoney(item.valor_compra)}</td>
                  <td className="table-cell">
                    {Number(item.comision_empleado || 0) > 0
                      ? `Si (${formatMoney(item.comision_empleado)})`
                      : 'No ($0)'}
                  </td>
                  <td className={`table-cell font-semibold ${Number(item.ganancia_neta || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                    {formatMoney(item.ganancia_neta)}
                  </td>
                </tr>
              ))}
              {(productos.detalle || []).length > 0 && (
                <tr className="bg-emerald-100 font-semibold">
                  <td className="table-cell" colSpan={3}>TOTAL</td>
                  <td className="table-cell">{(productos.detalle || []).reduce((sum, item) => sum + Number(item.cantidad || 0), 0)}</td>
                  <td className="table-cell">{formatMoney((productos.detalle || []).reduce((sum, item) => sum + Number(item.valor_venta || 0), 0))}</td>
                  <td className="table-cell">{formatMoney((productos.detalle || []).reduce((sum, item) => sum + Number(item.valor_compra || 0), 0))}</td>
                  <td className="table-cell">{formatMoney((productos.detalle || []).reduce((sum, item) => sum + Number(item.comision_empleado || 0), 0))}</td>
                  <td className="table-cell">{formatMoney((productos.detalle || []).reduce((sum, item) => sum + Number(item.ganancia_neta || 0), 0))}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card border border-cyan-200 bg-cyan-50">
          <h2 className="card-header">Detalle valor recibido por espacio</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-4 py-3 text-left">Fecha</th>
                  <th className="px-4 py-3 text-left">Empleado</th>
                  <th className="px-4 py-3 text-left">Valor pagado</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {(espacios.detalle || []).length === 0 && (
                  <tr>
                    <td className="table-cell text-slate-500" colSpan={3}>No hay pagos por espacio registrados en el rango.</td>
                  </tr>
                )}
                {(espacios.detalle || []).map((item, idx) => (
                  <tr key={`${item.fecha || 'x'}-${item.estilista_id || idx}-${idx}`}>
                    <td className="table-cell">{item.fecha || '-'}</td>
                    <td className="table-cell">{item.estilista_nombre || '-'}</td>
                    <td className="table-cell font-semibold text-cyan-700">{formatMoney(item.valor_pagado)}</td>
                  </tr>
                ))}
                {(espacios.detalle || []).length > 0 && (
                  <tr className="bg-cyan-100 font-semibold">
                    <td className="table-cell" colSpan={2}>TOTAL</td>
                    <td className="table-cell text-cyan-800">{formatMoney((espacios.detalle || []).reduce((sum, item) => sum + Number(item.valor_pagado || 0), 0))}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card border border-violet-200 bg-violet-50">
          <h2 className="card-header">Detalle servicios (ganancia establecimiento)</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-4 py-3 text-left">Fecha</th>
                  <th className="px-4 py-3 text-left">Tipo servicio</th>
                  <th className="px-4 py-3 text-left">Valor servicio</th>
                  <th className="px-4 py-3 text-left">Ganancia establecimiento</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {(serviciosEst.detalle || []).length === 0 && (
                  <tr>
                    <td className="table-cell text-slate-500" colSpan={4}>No hay servicios con ganancia para establecimiento en el rango.</td>
                  </tr>
                )}
                {(serviciosEst.detalle || []).map((item, idx) => (
                  <tr key={`${item.fecha_hora || item.fecha || 'x'}-${item.numero_factura || idx}-${idx}`}>
                    <td className="table-cell">{item.fecha_hora || item.fecha || '-'}</td>
                    <td className="table-cell">{item.tipo_servicio || '-'}</td>
                    <td className="table-cell">{formatMoney(item.valor_servicio)}</td>
                    <td className="table-cell font-semibold text-violet-700">{formatMoney(item.ganancia_establecimiento)}</td>
                  </tr>
                ))}
                {(serviciosEst.detalle || []).length > 0 && (
                  <tr className="bg-violet-100 font-semibold">
                    <td className="table-cell" colSpan={2}>TOTAL</td>
                    <td className="table-cell">{formatMoney((serviciosEst.detalle || []).reduce((sum, item) => sum + Number(item.valor_servicio || 0), 0))}</td>
                    <td className="table-cell text-violet-800">{formatMoney((serviciosEst.detalle || []).reduce((sum, item) => sum + Number(item.ganancia_establecimiento || 0), 0))}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );

  const renderModuloLiquidacion = () => (
    <div className="space-y-6">
      <div className="card">
        <h2 className="card-header">Liquidacion Empleado</h2>
        <p className="text-sm text-slate-600">
          Liquidacion integrada: puedes cobrar consumo y liquidar al empleado en una sola accion.
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Para registrar pagos por medio o abono de puesto, usa un unico dia (fecha inicio = fecha fin).
        </p>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Empleado</th>
                <th className="px-4 py-3 text-left">Valor total empleado</th>
                <th className="px-4 py-3 text-left">Comisiones</th>
                <th className="px-4 py-3 text-left">Valor a liquidar</th>
                <th className="px-4 py-3 text-left">Consumo pendiente</th>
                <th className="px-4 py-3 text-left">Cobro consumo</th>
                <th className="px-4 py-3 text-left">Medio cobro consumo</th>
                <th className="px-4 py-3 text-left">Puesto</th>
                <th className="px-4 py-3 text-left">Pago efectivo</th>
                <th className="px-4 py-3 text-left">Pago Nequi</th>
                <th className="px-4 py-3 text-left">Pago Daviplata</th>
                <th className="px-4 py-3 text-left">Pago otros</th>
                <th className="px-4 py-3 text-left">Abono puesto</th>
                <th className="px-4 py-3 text-left">Medio abono puesto</th>
                <th className="px-4 py-3 text-left">Neto estimado</th>
                <th className="px-4 py-3 text-left">Acciones</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {(biData?.estilistas || []).length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={17}>No hay liquidacion para el rango seleccionado.</td>
                </tr>
              )}
              {(biData?.estilistas || []).map((item) => {
                const deudaPuestoHistorica = Number(item.deuda_puesto_historica || 0);
                const valorTotalEmpleado = Number((item.valor_total_empleado ?? item.facturacion_servicios ?? item.ganancias_servicios) || 0);
                const comisionesEmpleado = Number(item.comision_ventas_producto || 0);
                const tipoCobro = item.tipo_cobro_espacio || 'sin_cobro';
                const valorCobroCfg = Number(item.valor_cobro_espacio || 0);
                const descuentoBackend = Math.max(Number(item.debe_puesto_periodo ?? item.descuento_espacio ?? item.total_deducciones ?? 0), 0);
                const descuentoVisible = descuentoBackend;
                const gananciasTotales = valorTotalEmpleado + comisionesEmpleado;
                const abonoPuestoDigitado = Number(abonoPuestoPorEstilista[item.estilista_id] || 0);
                const deudaAcumulada = Number(item.deuda_total_acumulada || 0);
                const pagadoEmpleadoPeriodo = Number(item.pagado_empleado_periodo || 0);
                const descripcionCobroPuesto = tipoCobro === 'costo_fijo_neto'
                  ? `Cobro fijo: ${formatMoney(descuentoVisible || valorCobroCfg)}`
                  : tipoCobro === 'porcentaje_neto'
                    ? `Cobro porcentaje: (${formatMoney(descuentoVisible)}) ${valorCobroCfg}%`
                    : 'Sin cobro de puesto';
                // Para UN DÍA: confiar SOLO en estadoDiaPorEstilista (del endpoint específico del día)
                // Para RANGO: usar el estado del BI basado en múltiples días
                const estadoActual = (fechaInicio === fechaFin)
                  ? (estadoDiaPorEstilista[item.estilista_id] || 'pendiente')
                  : (item.estado_pago_rango || item.estado_pago_dia || 'pendiente');
                const valorALiquidarBase = Math.max(gananciasTotales - pagadoEmpleadoPeriodo, 0);
                const valorALiquidarVisible = estadoActual === 'cancelado' ? 0 : valorALiquidarBase;
                const consumoPendiente = Number(resumenPorEstilista[item.estilista_id]?.saldo_pendiente || 0);
                const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[item.estilista_id] || 0);
                const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(consumoPendiente, 0));
                const netoEstimado = Math.max(gananciasTotales - cobroConsumoAplicado, 0);
                const saldoNeto = Math.max(netoEstimado - totalPagoMedios(item.estilista_id), 0);
                const descuentoPuestoValidado = descuentoVisible;
                const descuentoPuestoTotalVisible = deudaAcumulada;
                const inputsHabilitados = estadoActual !== 'cancelado';
                return (
                  <tr key={item.estilista_id}>
                    <td className="table-cell font-medium">{item.estilista_nombre}</td>
                    <td className="table-cell">{formatMoney(valorTotalEmpleado)}</td>
                    <td className="table-cell">{formatMoney(comisionesEmpleado)}</td>
                    <td className={`table-cell font-semibold ${valorALiquidarVisible >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {formatMoney(valorALiquidarVisible)}
                    </td>
                    <td className="table-cell text-rose-700 font-semibold">{formatMoney(consumoPendiente)}</td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (cobroConsumoPorEstilista[item.estilista_id] || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'cobro_consumo' })}
                        onChange={(e) =>
                          setCobroConsumoPorEstilista((prev) => ({
                            ...prev,
                            [item.estilista_id]: String(e.target.value || '').replace(/[^\d.]/g, ''),
                          }))
                        }
                      />
                      <div className="text-xs text-slate-500 mt-1">Aplicado: {formatMoney(cobroConsumoAplicado)}</div>
                    </td>
                    <td className="table-cell">
                      <select
                        className="input-field !py-2 !min-h-0 min-w-[130px]"
                        value={medioCobroConsumoPorEstilista[item.estilista_id] || 'efectivo'}
                        onChange={(e) =>
                          setMedioCobroConsumoPorEstilista((prev) => ({
                            ...prev,
                            [item.estilista_id]: e.target.value,
                          }))
                        }
                      >
                        {MEDIOS_PAGO_OPERACION.map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="table-cell">
                      <div>Debe hoy: {formatMoney(descuentoPuestoValidado)}</div>
                      <div className="text-[11px] leading-tight text-slate-500">{descripcionCobroPuesto}</div>
                      <div className="text-[11px] leading-tight text-amber-600">
                        Deuda acumulada: {formatMoney(descuentoPuestoTotalVisible)}
                      </div>
                      <div className="text-[11px] leading-tight text-slate-500">
                        Pagado al empleado: {formatMoney(pagadoEmpleadoPeriodo)}
                      </div>
                    </td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (pagosPorEstilista[item.estilista_id]?.efectivo || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'efectivo' })}
                        onChange={(e) => actualizarPagoMedio(item.estilista_id, 'efectivo', e.target.value)}
                      />
                    </td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (pagosPorEstilista[item.estilista_id]?.nequi || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'nequi' })}
                        onChange={(e) => actualizarPagoMedio(item.estilista_id, 'nequi', e.target.value)}
                      />
                    </td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (pagosPorEstilista[item.estilista_id]?.daviplata || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'daviplata' })}
                        onChange={(e) => actualizarPagoMedio(item.estilista_id, 'daviplata', e.target.value)}
                      />
                    </td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (pagosPorEstilista[item.estilista_id]?.otros || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'otros' })}
                        onChange={(e) => actualizarPagoMedio(item.estilista_id, 'otros', e.target.value)}
                      />
                      <div className="text-xs text-slate-500 mt-1">Total: {formatMoney(inputsHabilitados ? totalPagoMedios(item.estilista_id) : 0)}</div>
                    </td>
                    <td className="table-cell">
                      <input
                        className="input-field !py-2 !min-h-0 min-w-[120px]"
                        type="number"
                        min="0"
                        step="1"
                        value={inputsHabilitados ? (abonoPuestoPorEstilista[item.estilista_id] || '') : ''}
                        onFocus={() => setNumericPadTarget({ estilistaId: item.estilista_id, field: 'abono_puesto' })}
                        onChange={(e) =>
                          setAbonoPuestoPorEstilista((prev) => ({
                            ...prev,
                            [item.estilista_id]: String(e.target.value || '').replace(/[^\d.]/g, ''),
                          }))
                        }
                      />
                    </td>
                    <td className="table-cell">
                      <select
                        className="input-field !py-2 !min-h-0 min-w-[130px]"
                        value={medioAbonoPuestoPorEstilista[item.estilista_id] || 'efectivo'}
                        onChange={(e) =>
                          setMedioAbonoPuestoPorEstilista((prev) => ({
                            ...prev,
                            [item.estilista_id]: e.target.value,
                          }))
                        }
                      >
                        {MEDIOS_PAGO_OPERACION.map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </td>
                    <td className="table-cell">
                      <div className="font-semibold text-emerald-700">{formatMoney(netoEstimado)}</div>
                      <div className="text-xs text-slate-500">Pago: {formatMoney(totalPagoMedios(item.estilista_id))}</div>
                      <div className="text-xs text-amber-600">Pendiente: {formatMoney(saldoNeto)}</div>
                    </td>
                    <td className="table-cell">
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="btn-primary !px-3 !py-2"
                          onClick={() => aplicarEstadoLiquidacion(item)}
                          disabled={!!savingEstadoByEstilista[item.estilista_id]}
                        >
                          Liquidar
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <NumericPad
        visible={!!numericPadTarget}
        value={getNumericPadValue()}
        onChange={setNumericPadValue}
        onClose={() => setNumericPadTarget(null)}
      />

      <div className="card">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="card-header mb-0">Historial de Liquidacion</h3>
            <p className="text-sm text-slate-600">Fecha del dia liquidado, fecha hora del proceso, empleado, estado, valor liquidado, pendiente puesto y usuario que liquido.</p>
          </div>
          <button className="btn-secondary" onClick={cargarTodo} disabled={loadingHistorial}>
            {loadingHistorial ? 'Cargando...' : 'Actualizar historial'}
          </button>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Fecha liquidada</th>
                <th className="px-4 py-3 text-left">Fecha hora</th>
                <th className="px-4 py-3 text-left">Empleado</th>
                <th className="px-4 py-3 text-left">Estado</th>
                <th className="px-4 py-3 text-left">Valor liquidado</th>
                <th className="px-4 py-3 text-left">Abono puesto</th>
                <th className="px-4 py-3 text-left">Pendiente puesto</th>
                <th className="px-4 py-3 text-left">Usuario</th>
                {esAdministrador && <th className="px-4 py-3 text-left">Acciones</th>}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {historialEstados.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={esAdministrador ? 9 : 8}>No hay liquidaciones registradas en el rango.</td>
                </tr>
              )}
              {historialEstados.map((h) => {
                const pendientePuesto = Number(h.pendiente_puesto || 0);
                const estadoNuevo = String(h.estado_nuevo || '').toLowerCase();
                const estadoHist = estadoNuevo === 'cancelado' ? 'cancelado' : estadoNuevo === 'debe' ? 'debe' : 'pendiente';
                const estadoHistLabel = estadoHist === 'cancelado' ? 'Liquidado' : estadoHist === 'debe' ? 'Debe' : 'Pendiente';
                const estadoHistClass = estadoHist === 'debe'
                  ? 'bg-rose-100 text-rose-800'
                  : (estadoHist === 'cancelado' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800');
                return (
                  <tr key={h.id}>
                    <td className="table-cell">{h.fecha || '-'}</td>
                    <td className="table-cell">{h.fecha_cambio || '-'}</td>
                    <td className="table-cell font-medium">{h.estilista_nombre || '-'}</td>
                    <td className="table-cell">
                      <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${estadoHistClass}`}>
                        {estadoHistLabel}
                      </span>
                    </td>
                    <td className={`table-cell font-semibold ${Number(h.monto_liquidado || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {formatMoney(h.monto_liquidado)}
                    </td>
                    <td className="table-cell text-sky-700 font-semibold">{formatMoney(h.abono_puesto)}</td>
                    <td className="table-cell text-amber-700 font-semibold">{formatMoney(pendientePuesto)}</td>
                    <td className="table-cell">{h.usuario_nombre || 'Sistema'}</td>
                    {esAdministrador && (
                      <td className="table-cell">
                        <button
                          className="btn-secondary !px-3 !py-1.5 !text-xs"
                          onClick={() => eliminarRegistroHistorial(h)}
                          title="Eliminar historial y registro diario"
                        >
                          Eliminar
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  const renderModuloCartera = () => (
    <div className="space-y-6">
      <div className="card border border-amber-200 bg-amber-50">
        <h2 className="card-header">Cartera Empleado</h2>
        <p className="text-sm text-slate-600">Vista por factura con abonos y saldo pendiente. Selecciona una fila para ver su histórico.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Empleado</th>
                <th className="px-4 py-3 text-left">Fecha</th>
                <th className="px-4 py-3 text-left">Factura</th>
                <th className="px-4 py-3 text-left">Valor total</th>
                <th className="px-4 py-3 text-left">Valor abonado</th>
                <th className="px-4 py-3 text-left">Saldo pendiente</th>
                <th className="px-4 py-3 text-left">Total empleado</th>
                <th className="px-4 py-3 text-left">Abonar</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {(carteraData.deudas || []).length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={8}>No hay cartera en el rango seleccionado.</td>
                </tr>
              )}
              {(carteraData.deudas || []).map((deuda) => {
                const deudaId = Number(deuda.deuda_id);
                const resumenEmpleado = resumenPorEstilista[deuda.estilista_id] || {};
                const saving = !!savingAbonoByDeuda[deudaId];
                return (
                  <tr
                    key={deudaId}
                    className={`cursor-pointer ${Number(deudaActivaHistorial) === deudaId ? 'bg-amber-100' : ''}`}
                    onClick={() => setDeudaActivaHistorial(deudaId)}
                  >
                    <td className="table-cell font-medium">{deuda.estilista_nombre || '-'}</td>
                    <td className="table-cell">{(deuda.fecha_hora || '').slice(0, 10) || '-'}</td>
                    <td className="table-cell font-semibold">{deuda.numero_factura || '-'}</td>
                    <td className="table-cell">{formatMoney(deuda.total_cargo)}</td>
                    <td className="table-cell text-sky-700 font-semibold">{formatMoney(deuda.total_abonado)}</td>
                    <td className="table-cell text-rose-700 font-semibold">{formatMoney(deuda.saldo_pendiente)}</td>
                    <td className="table-cell">
                      <div className="text-xs text-slate-700">Saldo: <b>{formatMoney(resumenEmpleado.saldo_pendiente)}</b></div>
                      <div className="text-xs text-slate-500">Facturas: {resumenEmpleado.facturas || 0}</div>
                    </td>
                    <td className="table-cell" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        <select
                          className="input-field !py-2 !w-28"
                          value={medioAbonoPorDeuda[deudaId] || 'efectivo'}
                          onChange={(e) => setMedioAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        <input
                          type="number"
                          min="0"
                          step="100"
                          className="input-field !py-2 !w-28"
                          placeholder="Valor"
                          value={abonoPorDeuda[deudaId] || ''}
                          onChange={(e) => setAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: e.target.value }))}
                        />
                        <button
                          className="btn-primary !px-3 !py-2"
                          onClick={() => abonarFacturaCartera(deuda)}
                          disabled={saving}
                        >
                          {saving ? 'Abonando...' : 'Abonar'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card border border-sky-200 bg-sky-50">
        <h2 className="card-header">Historico de abonos de la deuda seleccionada</h2>
        <p className="text-sm text-slate-600">
          {deudaSeleccionada
            ? `Factura ${deudaSeleccionada.numero_factura || '-'} - ${deudaSeleccionada.estilista_nombre || '-'}`
            : 'Selecciona una factura en la tabla superior para ver su histórico.'}
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Fecha</th>
                <th className="px-4 py-3 text-left">Medio</th>
                <th className="px-4 py-3 text-left">Valor abonado</th>
                <th className="px-4 py-3 text-left">Editar datos del abono</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {!deudaSeleccionada && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={4}>Sin deuda seleccionada.</td>
                </tr>
              )}
              {deudaSeleccionada && (deudaSeleccionada.abonos || []).length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={4}>Esta factura no tiene abonos registrados.</td>
                </tr>
              )}
              {deudaSeleccionada && (deudaSeleccionada.abonos || []).map((abono) => {
                const abonoId = Number(abono.abono_id);
                const savingEdit = !!savingEditByAbono[abonoId];
                const editValue = editMontoByAbono[abonoId] ?? String(Number(abono.monto || 0));
                const editMedio = editMedioByAbono[abonoId] ?? (abono.medio_pago || 'efectivo');
                const editNotas = editNotasByAbono[abonoId] ?? (abono.notas || '');
                return (
                  <tr key={abonoId}>
                    <td className="table-cell">{abono.fecha_hora || '-'}</td>
                    <td className="table-cell capitalize">{abono.medio_pago || '-'}</td>
                    <td className="table-cell text-sky-700 font-semibold">{formatMoney(abono.monto)}</td>
                    <td className="table-cell">
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          type="number"
                          min="0"
                          step="100"
                          className="input-field !py-2 !w-28"
                          value={editValue}
                          onChange={(e) => setEditMontoByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        />
                        <select
                          className="input-field !py-2 !w-28"
                          value={editMedio}
                          onChange={(e) => setEditMedioByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        <input
                          type="text"
                          className="input-field !py-2 min-w-[220px]"
                          placeholder="Notas"
                          value={editNotas}
                          onChange={(e) => setEditNotasByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        />
                        <button
                          className="btn-secondary !px-3 !py-2"
                          onClick={() => editarAbonoCartera(abono, deudaSeleccionada)}
                          disabled={savingEdit}
                        >
                          {savingEdit ? 'Guardando...' : 'Guardar'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  const renderModuloAgotarse = () => (
    <div className="card">
      <h2 className="card-header">Productos por Agotarse</h2>
      <p className="text-sm text-slate-600">Listado de productos con stock igual o menor al minimo configurado.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="table-header">
            <tr>
              <th className="px-4 py-3 text-left">Marca</th>
              <th className="px-4 py-3 text-left">Producto</th>
              <th className="px-4 py-3 text-left">Stock</th>
              <th className="px-4 py-3 text-left">Stock minimo</th>
              <th className="px-4 py-3 text-left">Precio venta</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {(biData?.productos_bajo_stock || []).length === 0 && (
              <tr>
                <td className="table-cell text-slate-500" colSpan={5}>No hay productos en riesgo para el rango seleccionado.</td>
              </tr>
            )}
            {(biData?.productos_bajo_stock || []).map((item) => (
              <tr key={item.id}>
                <td className="table-cell">{item.marca || '-'}</td>
                <td className="table-cell font-medium">{item.nombre}</td>
                <td className="table-cell">{item.stock}</td>
                <td className="table-cell">{item.stock_minimo}</td>
                <td className="table-cell">{formatMoney(item.precio_venta)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="space-y-6 fade-in">
      <section className="rounded-[28px] bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_34%),linear-gradient(135deg,#0f172a_0%,#111827_35%,#1f2937_100%)] p-6 text-white shadow-2xl">
        <h1 className="text-3xl font-black tracking-tight">Reportes</h1>
        <p className="text-slate-300 mt-2">Estructura modular para cierre y control operativo.</p>
      </section>

      <div className="card">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Periodo</label>
            <select className="input-field" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
              <option value="semana">Semana</option>
              <option value="mes">Mes</option>
              <option value="personalizado">Personalizado</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Fecha inicio</label>
            <input type="date" className="input-field" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Fecha fin</label>
            <input type="date" className="input-field" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Medio de pago</label>
            <select className="input-field" value={medioPago} onChange={(e) => setMedioPago(e.target.value)}>
              {MEDIOS_PAGO.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-2 md:col-span-2">
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('ayer')}>Ayer</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('hoy')}>Hoy</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('7dias')}>7 dias</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('mes')}>Mes</button>
            <button className="btn-primary" onClick={cargarTodo} disabled={loading}>{loading ? 'Consultando...' : 'Consultar'}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {modulosVisibles.map((mod) => (
          <button
            key={mod.key}
            className={`${moduloActivo === mod.key ? 'btn-primary' : 'btn-secondary'} text-left`}
            onClick={() => setModuloActivo(mod.key)}
          >
            {mod.label}
          </button>
        ))}
      </div>

      {moduloActivo === 'cierre' && renderModuloCierreCaja()}
      {moduloActivo === 'liquidacion' && renderModuloLiquidacion()}
      {moduloActivo === 'cartera' && renderModuloCartera()}
      {moduloActivo === 'agotarse' && renderModuloAgotarse()}
    </div>
  );
};

export default Reportes;
