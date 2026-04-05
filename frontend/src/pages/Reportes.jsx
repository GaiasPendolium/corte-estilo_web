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
  const [estilistaActivoLiquidacion, setEstilistaActivoLiquidacion] = useState(null);
  const [pagosPorEstilista, setPagosPorEstilista] = useState({});
  const [estadoDiaPorEstilista, setEstadoDiaPorEstilista] = useState({});
  const [abonoPuestoPorEstilista, setAbonoPuestoPorEstilista] = useState({});
  const [abonoPuestoAcumuladoPorEstilista, setAbonoPuestoAcumuladoPorEstilista] = useState({});
  const [medioAbonoPuestoPorEstilista, setMedioAbonoPuestoPorEstilista] = useState({});
  const [cobroConsumoPorEstilista, setCobroConsumoPorEstilista] = useState({});
  const [medioCobroConsumoPorEstilista, setMedioCobroConsumoPorEstilista] = useState({});
  const [deudaConsumoSeleccionadaPorEstilista, setDeudaConsumoSeleccionadaPorEstilista] = useState({});
  const [savingEstadoByEstilista, setSavingEstadoByEstilista] = useState({});
  const [numericPadTarget, setNumericPadTarget] = useState(null);
  const [desgloseLiquidacion, setDesgloseLiquidacion] = useState(null);
  const [loadingDesgloseLiquidacion, setLoadingDesgloseLiquidacion] = useState(false);
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

      if (moduloActivo !== 'liquidacion') {
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
  }, [paramsBase, periodo, fechaInicio, fechaFin, esRecepcion, moduloActivo]);

  useEffect(() => {
    cargarTodo();
  }, [cargarTodo]);

  useEffect(() => {
    const lista = biData?.estilistas || [];
    if (!lista.length) {
      setEstilistaActivoLiquidacion(null);
      return;
    }
    if (estilistaActivoLiquidacion && lista.some((x) => Number(x.estilista_id) === Number(estilistaActivoLiquidacion))) {
      return;
    }
    setEstilistaActivoLiquidacion(Number(lista[0].estilista_id));
  }, [biData, estilistaActivoLiquidacion]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;

    let cancelado = false;
    const cargarEstadoDia = async () => {
      try {
        const fechaDia = fechaFin || format(new Date(), 'yyyy-MM-dd');
        const estadoDia = await reportesService.getEstadoPagoEstilistaDia(fechaDia);
        if (cancelado) return;

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
        setAbonoPuestoAcumuladoPorEstilista(
          Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, Number(x.abono_puesto || 0)]))
        );
        setAbonoPuestoPorEstilista({});
        setMedioAbonoPuestoPorEstilista(
          Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, x.medio_abono_puesto || 'efectivo']))
        );
      } catch (err) {
        if (cancelado) return;
        setPagosPorEstilista({});
        setEstadoDiaPorEstilista({});
        setAbonoPuestoPorEstilista({});
        setAbonoPuestoAcumuladoPorEstilista({});
        setMedioAbonoPuestoPorEstilista({});
      }
    };

    cargarEstadoDia();
    return () => {
      cancelado = true;
    };
  }, [moduloActivo, fechaFin]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;
    if (!estilistaActivoLiquidacion) {
      setDesgloseLiquidacion(null);
      return;
    }
    if (!fechaInicio || !fechaFin) return;

    let cancelado = false;
    const cargarDesglose = async () => {
      try {
        setLoadingDesgloseLiquidacion(true);
        const resp = await reportesService.getBIDesgloseEstilista({
          estilista_id: estilistaActivoLiquidacion,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
        });
        if (cancelado) return;
        setDesgloseLiquidacion(resp || null);
      } catch (err) {
        if (cancelado) return;
        setDesgloseLiquidacion(null);
      } finally {
        if (!cancelado) setLoadingDesgloseLiquidacion(false);
      }
    };

    cargarDesglose();
    return () => {
      cancelado = true;
    };
  }, [moduloActivo, estilistaActivoLiquidacion, fechaInicio, fechaFin]);

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

  const cobrarConsumoEnDeudas = async ({ estilistaId, deudaId, monto, medioPago, fecha }) => {
    const deudas = (carteraData?.deudas || [])
      .filter((d) => Number(d.estilista_id) === Number(estilistaId) && Number(d.saldo_pendiente || 0) > 0)
      .sort((a, b) => String(a.fecha_hora || '').localeCompare(String(b.fecha_hora || '')));

    if (deudaId) {
      const deudaObjetivo = deudas.find((d) => Number(d.deuda_id) === Number(deudaId));
      if (!deudaObjetivo) {
        return { cobrado: 0, restante: Number(monto || 0) };
      }

      const saldo = Number(deudaObjetivo.saldo_pendiente || 0);
      const abono = Math.min(Number(monto || 0), Math.max(saldo, 0));
      if (abono <= 0) return { cobrado: 0, restante: Number(monto || 0) };

      await reportesService.abonarConsumoEmpleado({
        estilista_id: estilistaId,
        deuda_id: deudaObjetivo.deuda_id,
        monto: abono,
        medio_pago: medioPago,
        notas: `Cobro consumo integrado en liquidacion ${fecha}`,
      });

      return { cobrado: abono, restante: Math.max(Number(monto || 0) - abono, 0) };
    }

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
  const fechaLiquidacion = fechaFin || format(new Date(), 'yyyy-MM-dd');
  
  const pago_efectivo = Number(pagosPorEstilista[estilistaId]?.efectivo || 0);
  const pago_nequi = Number(pagosPorEstilista[estilistaId]?.nequi || 0);
  const pago_daviplata = Number(pagosPorEstilista[estilistaId]?.daviplata || 0);
  const pago_otros = Number(pagosPorEstilista[estilistaId]?.otros || 0);
  const abono_puesto = Number(abonoPuestoPorEstilista[estilistaId] || 0);
  const medio_abono_puesto = medioAbonoPuestoPorEstilista[estilistaId] || 'efectivo';
  const saldoConsumoEmpleado = Number(resumenPorEstilista[estilistaId]?.saldo_pendiente || 0);
  const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[estilistaId] || 0);
  const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(saldoConsumoEmpleado, 0));
  const deudaConsumoSeleccionada = Number(deudaConsumoSeleccionadaPorEstilista[estilistaId] || 0);
  const medioCobroConsumo = medioCobroConsumoPorEstilista[estilistaId] || 'efectivo';
  const valorTotalEmpleado = Number((fila.valor_total_empleado ?? fila.facturacion_servicios ?? fila.ganancias_servicios) || 0);
  const comisionesEmpleado = Number(fila.comision_ventas_producto || 0);
  const topePagoEmpleado = Math.max(Number(fila.pago_neto_pendiente ?? (valorTotalEmpleado + comisionesEmpleado)), 0);

  if (pago_efectivo + pago_nequi + pago_daviplata + pago_otros > topePagoEmpleado) {
    toast.warning(`El pago al empleado no puede superar ${formatMoney(topePagoEmpleado)} para el día ${fechaLiquidacion}.`);
    return;
  }
  
  setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: true }));
  
  try {
    let resumenCobro = null;
    if (cobroConsumoAplicado > 0) {
      resumenCobro = await cobrarConsumoEnDeudas({
        estilistaId,
        deudaId: deudaConsumoSeleccionada > 0 ? deudaConsumoSeleccionada : null,
        monto: cobroConsumoAplicado,
        medioPago: medioCobroConsumo,
        fecha: fechaLiquidacion,
      });
    }

    const resultado = await reportesService.liquidarDiaV2({
      estilista_id: estilistaId,
      fecha: fechaLiquidacion,
      pago_efectivo,
      pago_nequi,
      pago_daviplata,
      pago_otros,
      abono_puesto,
      medio_abono_puesto,
      notas: `Liquidación ${fechaLiquidacion}`,
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
      <section className="rounded-3xl bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 p-6 text-white shadow-2xl">
        <h2 className="text-2xl font-black tracking-tight">Liquidación Inteligente</h2>
        <p className="mt-2 text-sm text-slate-200">Selecciona un empleado y liquida todo en una sola vista: pendiente de pago, deuda de puesto, consumos y medios.</p>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-6">
        <aside className="card border border-slate-200 bg-slate-50">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h3 className="card-header mb-0">Empleados</h3>
            <button className="btn-secondary !py-1.5" onClick={cargarTodo} disabled={loading}>Actualizar</button>
          </div>
          <div className="space-y-2 max-h-[68vh] overflow-y-auto pr-1">
            {(biData?.estilistas || []).length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">No hay empleados para liquidar.</div>
            )}
            {(biData?.estilistas || []).map((item) => {
              const estId = Number(item.estilista_id);
              const activo = estId === Number(estilistaActivoLiquidacion);
              const totalPendiente = Math.max(Number(item.pago_neto_pendiente || 0), 0);
              const consumoPendiente = Number(resumenPorEstilista[estId]?.saldo_pendiente || 0);
              const deudaPuesto = Number(item.deuda_total_acumulada || 0);
              return (
                <button
                  key={estId}
                  type="button"
                  onClick={() => setEstilistaActivoLiquidacion(estId)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${activo ? 'border-emerald-400 bg-emerald-50 shadow-md' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                >
                  <p className="font-semibold text-slate-900">{item.estilista_nombre}</p>
                  <p className="text-xs text-slate-500 mt-1">Pendiente pago: <b>{formatMoney(totalPendiente)}</b></p>
                  <p className="text-xs text-rose-600 mt-1">Consumo: {formatMoney(consumoPendiente)}</p>
                  <p className="text-xs text-amber-700 mt-1">Puesto: {formatMoney(deudaPuesto)}</p>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="space-y-4">
          {!estilistaActivoLiquidacion && (
            <div className="card text-slate-500">Selecciona un empleado para ver su resumen integral.</div>
          )}

          {(() => {
            const empleado = (biData?.estilistas || []).find((x) => Number(x.estilista_id) === Number(estilistaActivoLiquidacion));
            if (!empleado) return null;

            const estId = Number(empleado.estilista_id);
            const valorTotalEmpleado = Number((empleado.valor_total_empleado ?? empleado.facturacion_servicios ?? empleado.ganancias_servicios) || 0);
            const comisionesEmpleado = Number(empleado.comision_ventas_producto || 0);
            const generadoEmpleado = valorTotalEmpleado + comisionesEmpleado;
            const pendientePagoEmpleado = Math.max(Number(desgloseLiquidacion?.resumen?.pago_neto_pendiente ?? empleado.pago_neto_pendiente ?? generadoEmpleado), 0);
            const consumoPendiente = Number(resumenPorEstilista[estId]?.saldo_pendiente || 0);
            const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[estId] || 0);
            const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(consumoPendiente, 0));
            const abonoPuestoDigitado = Math.max(Number(abonoPuestoPorEstilista[estId] || 0), 0);
            const deudaPuestoAcumulada = Number(empleado.deuda_total_acumulada || 0);
            const netoEstimado = Math.max(pendientePagoEmpleado, 0);
            const pagoDigitado = totalPagoMedios(estId);
            const saldoPorPagar = Math.max(netoEstimado - pagoDigitado, 0);
            const historialPagosEmpleado = (historialEstados || []).filter((h) => Number(h.estilista_id) === estId);
            const historialDiarioLiquidacion = Object.values(
              historialPagosEmpleado.reduce((acc, h) => {
                const fecha = h.fecha || '-';
                const previo = acc[fecha] || {
                  fecha,
                  pago_empleado_dia: 0,
                  abono_puesto_dia: 0,
                  saldo_puesto_cierre: Number(h.pendiente_puesto || 0),
                  fecha_cambio: h.fecha_cambio || '',
                  usuario_nombre: h.usuario_nombre || 'Sistema',
                };

                const pagoDia = Number(previo.pago_empleado_dia || 0) + Number(h.monto_liquidado || 0);
                const cambioPrevio = String(previo.fecha_cambio || '');
                const cambioActual = String(h.fecha_cambio || '');
                const usarActualComoCierre = cambioActual >= cambioPrevio;

                acc[fecha] = {
                  ...previo,
                  pago_empleado_dia: pagoDia,
                  // Muestra el abono de la última operación del día para evitar
                  // mezclar históricos antiguos guardados como acumulados.
                  abono_puesto_dia: usarActualComoCierre ? Number(h.abono_puesto || 0) : Number(previo.abono_puesto_dia || 0),
                  saldo_puesto_cierre: usarActualComoCierre ? Number(h.pendiente_puesto || 0) : Number(previo.saldo_puesto_cierre || 0),
                  fecha_cambio: usarActualComoCierre ? (h.fecha_cambio || previo.fecha_cambio) : previo.fecha_cambio,
                  usuario_nombre: usarActualComoCierre ? (h.usuario_nombre || previo.usuario_nombre) : previo.usuario_nombre,
                };

                return acc;
              }, {})
            ).sort((a, b) => String(b.fecha || '').localeCompare(String(a.fecha || '')));
            const historialAbonosConsumo = (carteraData?.abonos_historial || []).filter((h) => Number(h.estilista_id) === estId);
            const deudasEmpleado = (carteraData?.deudas || []).filter((d) => Number(d.estilista_id) === estId && Number(d.saldo_pendiente || 0) > 0);
            const diasPendientes = desgloseLiquidacion?.desglose_por_dia?.filter((d) => String(d.incluido_en || d.estado || '').toLowerCase() !== 'cancelado') || [];

            return (
              <>
                <div className="card border border-emerald-200 bg-emerald-50">
                  <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
                    <div>
                      <h3 className="text-2xl font-black text-slate-900">{empleado.estilista_nombre}</h3>
                      <p className="text-sm text-slate-600 mt-1">Resumen calculado con los filtros superiores actualmente aplicados.</p>
                      <p className="text-xs text-slate-500 mt-1">Liquidando el día: <b>{fechaFin}</b> (según filtro superior).</p>
                      <p className="text-xs text-slate-500 mt-1">Pendiente por pagar calculado en rango: <b>{fechaInicio}</b> a <b>{fechaFin}</b>.</p>
                    </div>
                  </div>

                  <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Días pendientes en rango</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{loadingDesgloseLiquidacion ? '...' : diasPendientes.length}</p>
                  </div>

                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Generado empleado</p>
                      <p className="text-xl font-black text-slate-900 mt-1">{formatMoney(generadoEmpleado)}</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Pendiente por pagar</p>
                      <p className="text-xl font-black text-emerald-700 mt-1">{formatMoney(pendientePagoEmpleado)}</p>
                      <p className="text-[11px] text-slate-500 mt-1">Valor base antes de deducciones de consumo y abono a puesto.</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Consumo pendiente</p>
                      <p className="text-xl font-black text-rose-700 mt-1">{formatMoney(consumoPendiente)}</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Deuda puesto acumulada</p>
                      <p className="text-xl font-black text-amber-700 mt-1">{formatMoney(deudaPuestoAcumulada)}</p>
                      <p className="text-[11px] text-slate-500 mt-1">Debe puesto = cobros de puesto no cubiertos por abonos registrados.</p>
                    </div>
                  </div>
                </div>

                <div className="card border border-slate-200 bg-white">
                  <h4 className="card-header mb-2">Días incluidos en el pendiente por pagar (antes de liquidar)</h4>
                  <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
                    {loadingDesgloseLiquidacion && <p className="text-sm text-slate-500">Cargando días pendientes...</p>}
                    {!loadingDesgloseLiquidacion && diasPendientes.length === 0 && (
                      <p className="text-sm text-slate-500">No hay días pendientes en el rango seleccionado.</p>
                    )}
                    {!loadingDesgloseLiquidacion && diasPendientes.map((d) => (
                      <div key={`dia-${d.fecha}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                        <div className="flex justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">{d.fecha}</p>
                          <p className="text-sm font-bold text-emerald-700">{formatMoney(d.neto_dia)}</p>
                        </div>
                        <p className="text-xs text-slate-600 mt-1">Base servicio: {formatMoney(d.base_servicio)} | Comisión: {formatMoney(d.comision_productos)}</p>
                        <p className="text-xs text-slate-600">Descuento puesto: {formatMoney(d.descuento_espacio)}</p>
                        <p className="text-xs text-slate-500">Estado día: {d.estado || 'pendiente'}</p>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card border border-slate-200 bg-white">
                  <h4 className="card-header mb-3">Liquidación integrada</h4>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                        <p className="text-sm font-semibold text-emerald-900">1) Pago al empleado</p>
                        <p className="text-xs text-emerald-800">Ingresa solo lo que realmente se le entrega a la empleada.</p>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        {['efectivo', 'nequi', 'daviplata', 'otros'].map((medio) => (
                          <div key={medio}>
                            <label className="block text-xs text-slate-600 mb-1 capitalize">Pago {medio}</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.[medio] || ''}
                              onFocus={() => setNumericPadTarget({ estilistaId: estId, field: medio })}
                              onChange={(e) => actualizarPagoMedio(estId, medio, e.target.value)}
                            />
                          </div>
                        ))}
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Factura de consumo a abonar</label>
                        <select
                          className="input-field"
                          value={deudaConsumoSeleccionadaPorEstilista[estId] || ''}
                          onChange={(e) => setDeudaConsumoSeleccionadaPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          <option value="">Distribuir automático (más antigua primero)</option>
                          {deudasEmpleado.map((d) => (
                            <option key={d.deuda_id} value={d.deuda_id}>
                              {(d.numero_factura || `Deuda ${d.deuda_id}`)} - Saldo {formatMoney(d.saldo_pendiente)}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Cobro consumo a aplicar</label>
                        <input
                          className="input-field"
                          type="number"
                          min="0"
                          step="1"
                          value={cobroConsumoPorEstilista[estId] || ''}
                          onFocus={() => setNumericPadTarget({ estilistaId: estId, field: 'cobro_consumo' })}
                          onChange={(e) => setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                        />
                        <p className="text-xs text-slate-500 mt-1">Aplicado: {formatMoney(cobroConsumoAplicado)} de {formatMoney(consumoPendiente)}</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Medio cobro consumo</label>
                        <select
                          className="input-field"
                          value={medioCobroConsumoPorEstilista[estId] || 'efectivo'}
                          onChange={(e) => setMedioCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </div>

                    </div>

                    <div className="space-y-3">
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                        <p className="text-sm font-semibold text-amber-900">2) Abonos y deducciones</p>
                        <p className="text-xs text-amber-800">Estos valores descuentan o cubren deuda, no son pago directo a la empleada.</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Abono puesto (esta operación)</label>
                        <input
                          className="input-field"
                          type="number"
                          min="0"
                          step="1"
                          value={abonoPuestoPorEstilista[estId] || ''}
                          onFocus={() => setNumericPadTarget({ estilistaId: estId, field: 'abono_puesto' })}
                          onChange={(e) => setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                        />
                        <p className="text-xs text-slate-500 mt-1">Acumulado del día antes de guardar: {formatMoney(abonoPuestoAcumuladoPorEstilista[estId] || 0)}</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Medio abono puesto</label>
                        <select
                          className="input-field"
                          value={medioAbonoPuestoPorEstilista[estId] || 'efectivo'}
                          onChange={(e) => setMedioAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </div>

                      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                        <p className="text-sm text-slate-700">Objetivo pago al empleado</p>
                        <p className="text-3xl font-black text-indigo-900 mt-1">{formatMoney(netoEstimado)}</p>
                        <p className="text-xs text-slate-600 mt-2">Pagado digitado: {formatMoney(pagoDigitado)}</p>
                        <p className="text-xs text-amber-700">Saldo pendiente: {formatMoney(saldoPorPagar)}</p>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                        <p className="text-sm font-semibold text-slate-800">Resumen claro de movimientos</p>
                        <div className="mt-2 space-y-1 text-xs text-slate-700">
                          <p>Total a pagar al empleado (día): <b>{formatMoney(pendientePagoEmpleado)}</b></p>
                          <p>(-) Pagado digitado por medios: <b>{formatMoney(pagoDigitado)}</b></p>
                          <p className="pt-1 text-amber-800">(=) Saldo pendiente de pago al empleado: <b>{formatMoney(saldoPorPagar)}</b></p>
                          <p className="pt-2 text-slate-600">Abono a puesto (se registra aparte, no descuenta el pago al empleado): <b>{formatMoney(abonoPuestoDigitado)}</b></p>
                          <p className="text-slate-600">Cobro consumo aplicado (se registra aparte): <b>{formatMoney(cobroConsumoAplicado)}</b></p>
                        </div>
                      </div>

                      <button
                        className="btn-primary !w-full !py-3"
                        onClick={() => aplicarEstadoLiquidacion(empleado)}
                        disabled={!!savingEstadoByEstilista[estId]}
                      >
                        {savingEstadoByEstilista[estId] ? 'Procesando...' : 'Liquidar y registrar movimientos'}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div className="card border border-amber-200 bg-amber-50">
                    <h4 className="card-header mb-2">Facturas de consumo pendientes</h4>
                    <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                      {deudasEmpleado.length === 0 && <p className="text-sm text-slate-500">No tiene consumo pendiente.</p>}
                      {deudasEmpleado.map((d) => (
                        <div key={d.deuda_id} className="rounded-xl border border-amber-200 bg-white p-3">
                          <p className="text-sm font-semibold text-slate-900">{d.numero_factura || `Deuda ${d.deuda_id}`}</p>
                          <p className="text-xs text-slate-500">{d.fecha_hora || '-'}</p>
                          <p className="text-xs text-rose-700 mt-1">Saldo: {formatMoney(d.saldo_pendiente)}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="card border border-sky-200 bg-sky-50">
                    <h4 className="card-header mb-2">Historial diario de liquidación (por fecha)</h4>
                    <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                      {historialDiarioLiquidacion.length === 0 && <p className="text-sm text-slate-500">Sin movimientos registrados.</p>}
                      {historialDiarioLiquidacion.map((h) => (
                        <div key={`hist-dia-${h.fecha}`} className="rounded-xl border border-sky-200 bg-white p-3">
                          <div className="flex justify-between gap-2">
                            <p className="text-sm font-semibold text-slate-900">{h.fecha || '-'}</p>
                            <p className="text-sm font-bold text-emerald-700">Pago empleado: {formatMoney(h.pago_empleado_dia)}</p>
                          </div>
                          <p className="text-xs text-slate-500">{h.fecha_cambio || '-'}</p>
                          <p className="text-xs text-sky-700 mt-1">Abono puesto (última operación del día): {formatMoney(h.abono_puesto_dia)}</p>
                          <p className="text-xs text-amber-700">Saldo puesto al cierre del día: {formatMoney(h.saldo_puesto_cierre)}</p>
                          <p className="text-xs text-slate-500">Usuario: {h.usuario_nombre || 'Sistema'}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="card border border-violet-200 bg-violet-50">
                  <h4 className="card-header mb-2">Historial de abonos de consumo del empleado</h4>
                  <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                    {historialAbonosConsumo.length === 0 && <p className="text-sm text-slate-500">Sin abonos de consumo registrados.</p>}
                    {historialAbonosConsumo.map((a) => (
                      <div key={a.abono_id} className="rounded-xl border border-violet-200 bg-white p-3">
                        <div className="flex justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">{a.numero_factura || '-'}</p>
                          <p className="text-sm font-bold text-violet-700">{formatMoney(a.monto)}</p>
                        </div>
                        <p className="text-xs text-slate-500">{a.fecha_hora || '-'}</p>
                        <p className="text-xs text-slate-600 mt-1">Medio: {a.medio_pago || '-'}</p>
                        <p className="text-xs text-slate-600">{a.notas || 'Sin notas'}</p>
                      </div>
                    ))}
                  </div>
                </div>

              </>
            );
          })()}
        </section>
      </div>

      <NumericPad
        visible={!!numericPadTarget}
        value={getNumericPadValue()}
        onChange={setNumericPadValue}
        onClose={() => setNumericPadTarget(null)}
      />
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
