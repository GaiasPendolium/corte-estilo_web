import { useEffect, useMemo, useState } from 'react';
import { format } from 'date-fns';
import { reportesService } from '../services/api';
import { toast } from 'react-toastify';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const today = new Date();
const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
const moneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const decimalMoneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const formatMoney = (value) => `$${moneyFormatter.format(Number(value || 0))}`;
const formatMoneyDetailed = (value) => `$${decimalMoneyFormatter.format(Number(value || 0))}`;
const formatLabel = (value) => String(value || '-');
const stockRiskColor = (item) => (Number(item.stock || 0) <= 0 ? '#b91c1c' : '#ea580c');
const MEDIOS_PAGO = [
  { value: 'todos', label: 'Todos los medios' },
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const MEDIOS_PAGO_ABONO = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const MEDIOS_PAGO_DETALLE = [
  { key: 'efectivo', label: 'Efectivo' },
  { key: 'nequi', label: 'Nequi' },
  { key: 'daviplata', label: 'Daviplata' },
  { key: 'otros', label: 'Otros' },
];

const KpiCard = ({ title, value, hint, tone = 'slate' }) => {
  const tones = {
    slate: 'from-slate-900 via-slate-800 to-slate-700 text-white',
    emerald: 'from-emerald-600 via-emerald-500 to-teal-500 text-white',
    amber: 'from-amber-500 via-orange-500 to-red-500 text-white',
    sky: 'from-sky-600 via-blue-600 to-indigo-600 text-white',
  };

  return (
    <div className={`rounded-3xl bg-gradient-to-br ${tones[tone]} p-5 shadow-lg`}>
      <p className="text-sm opacity-80">{title}</p>
      <p className="mt-3 text-3xl font-black tracking-tight">{value}</p>
      <p className="mt-2 text-sm opacity-80">{hint}</p>
    </div>
  );
};

const Reportes = () => {
  const [periodo, setPeriodo] = useState('mes');
  const [fechaInicio, setFechaInicio] = useState(format(firstDay, 'yyyy-MM-dd'));
  const [fechaFin, setFechaFin] = useState(format(today, 'yyyy-MM-dd'));
  const [medioPagoFiltro, setMedioPagoFiltro] = useState('todos');
  const [marcaFiltro, setMarcaFiltro] = useState('todas');
  const [estilistaFiltro, setEstilistaFiltro] = useState('todos');
  const [savingEstadoByEstilista, setSavingEstadoByEstilista] = useState({});
  const [stats, setStats] = useState(null);
  const [consumoEmpleado, setConsumoEmpleado] = useState({ resumen: [], deudas: [] });
  const [abonoPorEstilista, setAbonoPorEstilista] = useState({});
  const [savingAbonoByEstilista, setSavingAbonoByEstilista] = useState({});
  const [historialEstados, setHistorialEstados] = useState([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [resumenDiario, setResumenDiario] = useState(null);
  const [mostrarDetalleAvanzado, setMostrarDetalleAvanzado] = useState(false);
  const [mostrarResumenDetalle, setMostrarResumenDetalle] = useState(false);
  const [pagosPorEstilista, setPagosPorEstilista] = useState({});
  const [ingresosPorMedio, setIngresosPorMedio] = useState({ efectivo: 0, nequi: 0, daviplata: 0, otros: 0 });
  const [loading, setLoading] = useState(true);

  const resolveEstilistaIdFiltro = (dataStats) => {
    if (estilistaFiltro === 'todos') return undefined;
    const found = (dataStats?.estilistas || []).find((x) => x.estilista_nombre === estilistaFiltro);
    return found?.estilista_id;
  };

  const cargarHistorialEstados = async (dataStats = stats) => {
    try {
      setLoadingHistorial(true);
      const estilistaId = resolveEstilistaIdFiltro(dataStats);
      const resp = await reportesService.getEstadoPagoHistorial({
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        ...(estilistaId ? { estilista_id: estilistaId } : {}),
        limit: 80,
      });
      setHistorialEstados(resp?.items || []);
    } catch (error) {
      setHistorialEstados([]);
    } finally {
      setLoadingHistorial(false);
    }
  };

  const cargarEstadoPagoDia = async (dataStats = stats) => {
    if (fechaInicio !== fechaFin) {
      setPagosPorEstilista({});
      return;
    }

    try {
      const resp = await reportesService.getEstadoPagoEstilistaDia(fechaInicio);
      const items = resp?.items || [];
      const map = {};
      items.forEach((x) => {
        map[x.estilista_id] = {
          efectivo: String(Number(x.pago_efectivo || 0) || ''),
          nequi: String(Number(x.pago_nequi || 0) || ''),
          daviplata: String(Number(x.pago_daviplata || 0) || ''),
          otros: String(Number(x.pago_otros || 0) || ''),
        };
      });
      setPagosPorEstilista(map);
    } catch (error) {
      setPagosPorEstilista({});
    }
  };

  const cargarIngresosPorMedio = async () => {
    try {
      const baseParams = {
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      };
      const [efectivoResp, nequiResp, daviplataResp, otrosResp] = await Promise.all([
        reportesService.getBIResumen({ ...baseParams, medio_pago: 'efectivo' }),
        reportesService.getBIResumen({ ...baseParams, medio_pago: 'nequi' }),
        reportesService.getBIResumen({ ...baseParams, medio_pago: 'daviplata' }),
        reportesService.getBIResumen({ ...baseParams, medio_pago: 'otros' }),
      ]);

      setIngresosPorMedio({
        efectivo: Number(efectivoResp?.kpis?.venta_neta_total || 0),
        nequi: Number(nequiResp?.kpis?.venta_neta_total || 0),
        daviplata: Number(daviplataResp?.kpis?.venta_neta_total || 0),
        otros: Number(otrosResp?.kpis?.venta_neta_total || 0),
      });
    } catch (error) {
      setIngresosPorMedio({ efectivo: 0, nequi: 0, daviplata: 0, otros: 0 });
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [data, consumoData] = await Promise.all([
        reportesService.getBIResumen({
          periodo,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
          ...(medioPagoFiltro !== 'todos' ? { medio_pago: medioPagoFiltro } : {}),
        }),
        reportesService.getConsumoEmpleadoDeudas({
          periodo,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
        }),
      ]);
      setStats(data);
      setConsumoEmpleado({
        resumen: consumoData?.resumen || [],
        deudas: consumoData?.deudas || [],
      });
      await cargarHistorialEstados(data);
      await cargarEstadoPagoDia(data);
      await cargarIngresosPorMedio();
    } catch (error) {
      toast.error('Error al cargar reportes');
      setStats(null);
      setConsumoEmpleado({ resumen: [], deudas: [] });
      setHistorialEstados([]);
      setPagosPorEstilista({});
      setIngresosPorMedio({ efectivo: 0, nequi: 0, daviplata: 0, otros: 0 });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const exportarCsv = async () => {
    try {
      const blob = await reportesService.exportBICsv({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        ...(medioPagoFiltro !== 'todos' ? { medio_pago: medioPagoFiltro } : {}),
      });
      if (!blob || blob.size === 0) {
        toast.error('El archivo descargado está vacío');
        return;
      }
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `reporte_bi_${fechaInicio}_${fechaFin}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Reporte CSV descargado');
    } catch (error) {
      toast.error(error.response?.data?.message || error.message || 'No se pudo descargar el reporte CSV');
    }
  };

  const exportarPdf = async () => {
    try {
      const blob = await reportesService.exportBIPdf({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        ...(medioPagoFiltro !== 'todos' ? { medio_pago: medioPagoFiltro } : {}),
      });
      if (!blob || blob.size === 0) {
        toast.error('El archivo descargado está vacío');
        return;
      }
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `reporte_bi_${fechaInicio}_${fechaFin}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success('Reporte PDF descargado');
    } catch (error) {
      toast.error('No se pudo descargar el PDF');
    }
  };

  const cargarResumenDiario = async () => {
    try {
      const data = await reportesService.getResumenDiario();
      setResumenDiario(data);
    } catch (error) {
      toast.error('No se pudo cargar el resumen diario');
    }
  };

  const copiarResumenDiario = async () => {
    if (!resumenDiario?.texto_resumen) {
      toast.info('No hay resumen para copiar');
      return;
    }
    try {
      await navigator.clipboard.writeText(resumenDiario.texto_resumen);
      toast.success('Resumen diario copiado');
    } catch (error) {
      toast.error('No se pudo copiar el resumen');
    }
  };

  const aplicarRangoRapido = (tipo) => {
    const base = new Date();
    if (tipo === 'hoy') {
      const value = format(base, 'yyyy-MM-dd');
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

  const kpis = stats?.kpis || {};

  const marcasDisponibles = useMemo(() => {
    const marcas = new Set((stats?.productos_bajo_stock || []).map((item) => item.marca).filter(Boolean));
    (stats?.top_ventas_productos || []).forEach((item) => {
      if (item.producto_marca) marcas.add(item.producto_marca);
    });
    return ['todas', ...Array.from(marcas).sort((a, b) => a.localeCompare(b))];
  }, [stats]);

  const estilistasDisponibles = useMemo(
    () => ['todos', ...((stats?.estilistas || []).map((item) => item.estilista_nombre).sort((a, b) => a.localeCompare(b)))],
    [stats]
  );

  const productosBajoStockFiltrados = useMemo(() => {
    const base = stats?.productos_bajo_stock || [];
    if (marcaFiltro === 'todas') return base;
    return base.filter((item) => item.marca === marcaFiltro);
  }, [stats, marcaFiltro]);

  const topProductosFiltrados = useMemo(() => {
    const base = stats?.top_ventas_productos || [];
    if (marcaFiltro === 'todas') return base;
    return base.filter((item) => item.producto_marca === marcaFiltro);
  }, [stats, marcaFiltro]);

  const liquidacionFiltrada = useMemo(() => {
    const base = stats?.estilistas || [];
    if (estilistaFiltro === 'todos') return base;
    return base.filter((item) => item.estilista_nombre === estilistaFiltro);
  }, [stats, estilistaFiltro]);

  const consumoResumenFiltrado = useMemo(() => {
    const base = consumoEmpleado?.resumen || [];
    if (estilistaFiltro === 'todos') return base;
    return base.filter((item) => item.estilista_nombre === estilistaFiltro);
  }, [consumoEmpleado, estilistaFiltro]);

  const registrarAbonoConsumo = async (fila) => {
    const configAbono = abonoPorEstilista[fila.estilista_id] || {};
    const monto = Number(configAbono.monto || 0);
    const medioPago = configAbono.medio_pago || 'efectivo';
    if (!Number.isFinite(monto) || monto <= 0) {
      toast.warning('Ingresa un valor de abono válido');
      return;
    }

    const saldoActual = Number(fila.saldo_pendiente || 0);
    const confirmar = window.confirm(
      `Vas a registrar un abono de ${formatMoney(monto)} para ${fila.estilista_nombre}.\n` +
      `Saldo pendiente actual: ${formatMoney(saldoActual)}.\n` +
      `Medio de pago: ${medioPago}.\n\n` +
      '¿Deseas continuar?'
    );
    if (!confirmar) {
      return;
    }

    setSavingAbonoByEstilista((prev) => ({ ...prev, [fila.estilista_id]: true }));
    try {
      const resp = await reportesService.abonarConsumoEmpleado({
        estilista_id: fila.estilista_id,
        monto,
        medio_pago: medioPago,
      });
      setAbonoPorEstilista((prev) => ({ ...prev, [fila.estilista_id]: { monto: '', medio_pago: 'efectivo' } }));
      await loadData();
      toast.success(`Abono aplicado: ${formatMoney(resp?.monto_aplicado || 0)}`);
    } catch (error) {
      toast.error(error?.response?.data?.error || 'No se pudo registrar el abono');
    } finally {
      setSavingAbonoByEstilista((prev) => ({ ...prev, [fila.estilista_id]: false }));
    }
  };

  const servicioPromedio = useMemo(() => {
    if (!kpis.cantidad_servicios) return 0;
    return Number(kpis.ingresos_servicios || 0) / Number(kpis.cantidad_servicios || 1);
  }, [kpis]);

  const ventaPromedioProducto = useMemo(() => {
    if (!kpis.cantidad_ventas_productos) return 0;
    return Number(kpis.ingresos_productos || 0) / Number(kpis.cantidad_ventas_productos || 1);
  }, [kpis]);

  const recibeHoy = Number(kpis.venta_neta_total || 0);
  const pagaHoy = Number(kpis.pago_total_estilistas || 0);
  const leQuedaHoy = recibeHoy - pagaHoy;

  const actualizarPagoMedio = (estilistaId, medio, valor) => {
    setPagosPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: {
        efectivo: prev[estilistaId]?.efectivo || '',
        nequi: prev[estilistaId]?.nequi || '',
        daviplata: prev[estilistaId]?.daviplata || '',
        otros: prev[estilistaId]?.otros || '',
        [medio]: String(valor || '').replace(/[^\d.]/g, ''),
      },
    }));
  };

  const totalPagosFila = (estilistaId) => {
    const pagos = pagosPorEstilista[estilistaId] || {};
    return ['efectivo', 'nequi', 'daviplata', 'otros']
      .map((k) => Number(pagos[k] || 0))
      .reduce((acc, val) => acc + (Number.isFinite(val) ? val : 0), 0);
  };

  const totalPagosPorMedio = useMemo(() => {
    return Object.values(pagosPorEstilista).reduce(
      (acc, item) => {
        acc.efectivo += Number(item?.efectivo || 0);
        acc.nequi += Number(item?.nequi || 0);
        acc.daviplata += Number(item?.daviplata || 0);
        acc.otros += Number(item?.otros || 0);
        return acc;
      },
      { efectivo: 0, nequi: 0, daviplata: 0, otros: 0 }
    );
  }, [pagosPorEstilista]);

  const balancePorMedio = useMemo(() => {
    return MEDIOS_PAGO_DETALLE.map((m) => {
      const ingreso = Number(ingresosPorMedio[m.key] || 0);
      const liquidado = Number(totalPagosPorMedio[m.key] || 0);
      return {
        key: m.key,
        label: m.label,
        ingreso,
        liquidado,
        debeHaber: ingreso - liquidado,
      };
    });
  }, [ingresosPorMedio, totalPagosPorMedio]);

  const cambiarEstadoPagoDia = async (fila, estado) => {
    const estilistaId = fila.estilista_id;
    if (estado === 'parcial' || estado === 'sin_movimiento') return;

    const pagosDetalle = {
      efectivo: Number(pagosPorEstilista[estilistaId]?.efectivo || 0),
      nequi: Number(pagosPorEstilista[estilistaId]?.nequi || 0),
      daviplata: Number(pagosPorEstilista[estilistaId]?.daviplata || 0),
      otros: Number(pagosPorEstilista[estilistaId]?.otros || 0),
    };
    const totalPagos = Object.values(pagosDetalle).reduce((acc, val) => acc + (Number.isFinite(val) ? val : 0), 0);
    const netoPendiente = Number(fila.pago_neto_pendiente ?? fila.pago_neto_estilista ?? 0);
    const maxPagable = netoPendiente > 0 ? netoPendiente : 0;

    if (estado === 'cancelado' && fechaInicio !== fechaFin && totalPagos > 0) {
      toast.warning('Para registrar pagos por medio debes seleccionar un solo día (fecha inicio = fecha fin).');
      return;
    }

    if (estado === 'cancelado' && totalPagos > maxPagable) {
      toast.warning(`La suma por medios no puede exceder el neto a pagar (${formatMoney(maxPagable)}).`);
      return;
    }

    if (estado === 'cancelado') {
      const confirmar = window.confirm(
        `Se marcarán como CANCELADOS todos los días del rango ${fechaInicio} a ${fechaFin} para este estilista. ¿Deseas continuar?`
      );
      if (!confirmar) return;
    }

    setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: true }));
    try {
      await reportesService.setEstadoPagoEstilistaDia({
        estilista_id: estilistaId,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        estado,
        pagos_detalle: estado === 'cancelado' ? pagosDetalle : { efectivo: 0, nequi: 0, daviplata: 0, otros: 0 },
      });

      await loadData();
      toast.success(`Rango actualizado a ${estado === 'cancelado' ? 'Cancelado' : 'Pendiente'}`);
    } catch (error) {
      toast.error(error?.response?.data?.error || 'No se pudo actualizar el estado del día');
    } finally {
      setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: false }));
    }
  };

  const deshacerLiquidacionRango = async (fila) => {
    const confirmar = window.confirm(
      `Se revertirá a PENDIENTE todo el rango ${fechaInicio} a ${fechaFin} para este estilista. ¿Deseas continuar?`
    );
    if (!confirmar) return;
    await cambiarEstadoPagoDia(fila, 'pendiente');
  };

  return (
    <div className="space-y-6 fade-in">
      <section className="rounded-[28px] bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_34%),linear-gradient(135deg,#0f172a_0%,#111827_35%,#1f2937_100%)] p-6 text-white shadow-2xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-300">Centro de inteligencia</p>
            <h1 className="mt-2 text-4xl font-black tracking-tight">Reportes Ejecutivos</h1>
            <p className="mt-2 max-w-2xl text-slate-300">Vista gerencial simplificada para lectura rápida del negocio.</p>
            <span className="mt-3 inline-flex rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white">
              Modo simple activado
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary !border-white/20 !bg-white/10 !text-white" onClick={exportarCsv}>Descargar CSV</button>
            <button className="btn-secondary !border-white/20 !bg-white/10 !text-white" onClick={exportarPdf}>Descargar PDF</button>
          </div>
        </div>
      </section>

      <div className="card">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="grid grid-cols-1 md:grid-cols-6 gap-4 flex-1">
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
              <select className="input-field" value={medioPagoFiltro} onChange={(e) => setMedioPagoFiltro(e.target.value)}>
                {MEDIOS_PAGO.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Filtrar marca</label>
              <select className="input-field" value={marcaFiltro} onChange={(e) => setMarcaFiltro(e.target.value)}>
                {marcasDisponibles.map((marca) => (
                  <option key={marca} value={marca}>{marca === 'todas' ? 'Todas las marcas' : marca}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Liquidación estilista</label>
              <select className="input-field" value={estilistaFiltro} onChange={(e) => setEstilistaFiltro(e.target.value)}>
                {estilistasDisponibles.map((estilista) => (
                  <option key={estilista} value={estilista}>{estilista === 'todos' ? 'Todos los estilistas' : estilista}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('hoy')}>Hoy</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('7dias')}>7 días</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('mes')}>Mes</button>
            <button
              className="btn-secondary"
              onClick={() => setMostrarDetalleAvanzado((prev) => !prev)}
            >
              {mostrarDetalleAvanzado ? 'Ocultar detalle avanzado' : 'Ver detalle avanzado'}
            </button>
            <button className="btn-primary" onClick={loadData} disabled={loading}>{loading ? 'Consultando...' : 'Consultar'}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
        <KpiCard title="Ingresos del período" value={formatMoney(kpis.venta_neta_total)} hint="Total cobrado a clientes" tone="slate" />
        <KpiCard title="Pago a estilistas" value={formatMoney(kpis.pago_total_estilistas)} hint="Pagos positivos del período" tone="sky" />
        <KpiCard title="Ganancia del negocio" value={formatMoney(kpis.ganancia_establecimiento_total)} hint="Lo que queda para el establecimiento" tone="emerald" />
        <KpiCard title="Productos con stock crítico" value={moneyFormatter.format(kpis.productos_bajo_stock || 0)} hint="Cantidad de productos en alerta" tone="amber" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
        <KpiCard
          title="Deuda consumo empleado"
          value={formatMoney(kpis.deuda_consumo_empleado_total)}
          hint="Saldo total pendiente por consumos a crédito"
          tone="amber"
        />
      </div>

      <div className="card border border-indigo-200 bg-indigo-50">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="card-header mb-0">Control por medio de pago</h2>
            <p className="text-sm text-slate-600">Debe haber = ingresos del medio - pagos liquidados por ese mismo medio.</p>
          </div>
          <div className="text-xs text-slate-600 rounded-xl bg-white px-3 py-2 border border-indigo-100">
            {fechaInicio === fechaFin
              ? `Día: ${fechaInicio}`
              : `Rango ${fechaInicio} a ${fechaFin} (liquidado por medio visible solo para un día)`}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {balancePorMedio.map((m) => (
            <div key={m.key} className="rounded-2xl border border-indigo-100 bg-white p-4">
              <p className="text-sm font-semibold text-slate-900">{m.label}</p>
              <p className={`mt-2 text-xl font-black ${m.debeHaber >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                {formatMoney(m.debeHaber)}
              </p>
              <p className="mt-2 text-xs text-slate-600">Ingresos: {formatMoney(m.ingreso)}</p>
              <p className="text-xs text-slate-600">Liquidado: {formatMoney(m.liquidado)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card border border-slate-200 bg-slate-50">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Resumen rápido del período</h2>
            <p className="text-sm text-slate-600 mt-1">Vista corta para operación diaria.</p>
          </div>
          <button className="btn-secondary" onClick={() => setMostrarResumenDetalle((prev) => !prev)}>
            {mostrarResumenDetalle ? 'Ocultar detalles' : 'Mostrar detalles'}
          </button>
        </div>

        {mostrarResumenDetalle && (
          <>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-slate-500">Entró</p>
                <p className="font-bold text-slate-900 text-lg">{formatMoney(recibeHoy)}</p>
              </div>
              <div>
                <p className="text-slate-500">Se pagó</p>
                <p className="font-bold text-sky-900 text-lg">{formatMoney(pagaHoy)}</p>
              </div>
              <div>
                <p className="text-slate-500">Quedó</p>
                <p className="font-bold text-emerald-700 text-lg">{formatMoney(leQuedaHoy)}</p>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm text-slate-500">Productos total vendido</p>
                <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(kpis.ingresos_productos_totales)}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm text-slate-500">Reserva reabastecimiento</p>
                <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(kpis.reserva_reabastecimiento_productos)}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm text-slate-500">Utilidad neta productos</p>
                <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(kpis.utilidad_neta_productos)}</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm text-slate-500">Servicios sin productos</p>
                <p className="mt-2 text-xl font-bold text-slate-900">{formatMoney(kpis.ingresos_servicios_no_producto)}</p>
              </div>
            </div>
          </>
        )}
      </div>

      {mostrarDetalleAvanzado && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="card border border-amber-200 bg-amber-50">
            <p className="text-sm text-amber-700">Deudas estilistas</p>
            <p className="mt-2 text-2xl font-black text-amber-900">{formatMoney(kpis.deudas_estilistas)}</p>
            <p className="mt-1 text-sm text-amber-700">Saldos negativos por cobro de espacio</p>
          </div>
          <div className="card border border-slate-200 bg-white">
            <p className="text-sm text-slate-500">Total operaciones</p>
            <p className="mt-2 text-2xl font-black text-slate-900">{moneyFormatter.format(Number(kpis.cantidad_servicios || 0) + Number(kpis.cantidad_ventas_productos || 0))}</p>
            <p className="mt-1 text-sm text-slate-500">{Number(kpis.cantidad_servicios || 0)} servicios y {Number(kpis.cantidad_ventas_productos || 0)} ventas</p>
          </div>
          <div className="card border border-emerald-200 bg-emerald-50">
            <p className="text-sm text-emerald-700">Promedio por venta de producto</p>
            <p className="mt-2 text-2xl font-black text-emerald-900">{formatMoney(ventaPromedioProducto)}</p>
            <p className="mt-1 text-sm text-emerald-700">Ticket promedio de productos</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="card-header">Serie diaria</h2>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={stats?.serie_diaria || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fecha" />
                <YAxis tickFormatter={moneyFormatter.format} />
                <Tooltip formatter={(value) => formatMoneyDetailed(value)} />
                <Legend />
                <Line type="monotone" dataKey="ventas_productos" stroke="#0f766e" strokeWidth={3} name="Productos" dot={false} />
                <Line type="monotone" dataKey="ventas_servicios" stroke="#2563eb" strokeWidth={3} name="Servicios" dot={false} />
                <Line type="monotone" dataKey="total" stroke="#111827" strokeWidth={3} name="Total" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between gap-3">
            <h2 className="card-header mb-0">Top ventas de productos</h2>
            <span className="text-sm text-gray-500">Filtro marca: {marcaFiltro === 'todas' ? 'Todas' : marcaFiltro}</span>
          </div>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={topProductosFiltrados}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="producto_nombre" hide />
                <YAxis tickFormatter={moneyFormatter.format} />
                <Tooltip formatter={(value, key) => key === 'cantidad' ? value : formatMoneyDetailed(value)} labelFormatter={formatLabel} />
                <Legend />
                <Bar dataKey="cantidad" fill="#1d4ed8" name="Cantidad" radius={[6, 6, 0, 0]} />
                <Bar dataKey="total" fill="#0f766e" name="Total" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="card-header mb-0">Liquidación por estilista</h2>
            <p className="text-sm text-gray-500">Lectura simple: cuánto facturó, cuánto realmente cuenta para pagarle, qué deducciones tiene y cuánto neto recibe.</p>
            <p className="text-xs text-slate-500 mt-1">Estado aplicado al rango: {fechaInicio} a {fechaFin}. Cambiar a Pendiente revierte un error de liquidación.</p>
          </div>
          <div className="rounded-2xl bg-slate-100 px-4 py-2 text-sm text-slate-700">
            {estilistaFiltro === 'todos' ? 'Mostrando todos los estilistas' : `Mostrando: ${estilistaFiltro}`}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-sm text-slate-500">1. Base estilista</p>
            <p className="mt-2 text-sm text-slate-700">Valor de servicio sin adicionales de establecimiento.</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-sm text-slate-500">2. Comisión productos</p>
            <p className="mt-2 text-sm text-slate-700">Comisión por ventas de productos asociadas al estilista.</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-sm text-slate-500">3. Cobro espacio</p>
            <p className="mt-2 text-sm text-slate-700">Valor que el estilista paga por uso de espacio.</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-sm text-slate-500">4. Resultado final</p>
            <p className="mt-2 text-sm text-slate-700">Positivo: se paga. Negativo: queda debiendo.</p>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-6 py-3 text-left">Estilista</th>
                <th className="px-6 py-3 text-left">Base para pagar</th>
                <th className="px-6 py-3 text-left">Comisión ventas</th>
                <th className="px-6 py-3 text-left">Cobro por espacio</th>
                <th className="px-6 py-3 text-left">Días trabajados</th>
                <th className="px-6 py-3 text-left">Neto pendiente</th>
                <th className="px-6 py-3 text-left">Estado saldo</th>
                <th className="px-6 py-3 text-left">Pago efectivo</th>
                <th className="px-6 py-3 text-left">Pago Nequi</th>
                <th className="px-6 py-3 text-left">Pago Daviplata</th>
                <th className="px-6 py-3 text-left">Pago otros</th>
                <th className="px-6 py-3 text-left">Total pago</th>
                <th className="px-6 py-3 text-left">Estado pago día</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {liquidacionFiltrada.map((s) => (
                <tr key={s.estilista_id} className="hover:bg-gray-50">
                  <td className="table-cell font-medium">{s.estilista_nombre}</td>
                  <td className="table-cell">
                    <div className="font-medium text-slate-900">{formatMoney(s.ganancias_servicios)}</div>
                    <div className="text-xs text-slate-500">Base del servicio para liquidar</div>
                  </td>
                  <td className="table-cell">
                    <div className="font-medium text-slate-900">{formatMoney(s.comision_ventas_producto_caja)}</div>
                    <div className="text-xs text-slate-500">
                      Solo ventas directas de productos (según % configurado en cada producto)
                    </div>
                  </td>
                  <td className="table-cell">
                    <div className="font-medium text-slate-900 capitalize">{s.tipo_cobro_espacio || 'sin_cobro'}</div>
                    <div className="text-xs text-slate-500">
                      {s.tipo_cobro_espacio === 'porcentaje_neto'
                        ? `${Number(s.valor_cobro_espacio || 0).toFixed(2)}% de la base del servicio`
                        : s.tipo_cobro_espacio === 'costo_fijo_neto'
                          ? `${formatMoney(s.valor_cobro_espacio)} por día trabajado`
                          : 'Sin descuento'}
                    </div>
                  </td>
                  <td className="table-cell font-medium text-slate-900">{moneyFormatter.format(s.total_dias_trabajados || 0)}</td>
                  <td className="table-cell">
                    <div className={`font-semibold ${Number(s.pago_neto_pendiente || s.pago_neto_estilista || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {formatMoney(s.pago_neto_pendiente ?? s.pago_neto_estilista)}
                    </div>
                    <div className="text-xs text-slate-500">
                      Periodo completo: {formatMoney(s.pago_neto_periodo)} | Ya cancelado: {formatMoney(s.pago_neto_cancelado)}
                    </div>
                    {(s.estado_pago_rango || s.estado_pago_dia) === 'cancelado' && (
                      <div className="text-xs font-medium text-emerald-700 mt-1">Ya liquidado para todo el rango seleccionado</div>
                    )}
                  </td>
                  <td className="table-cell">
                    {Number(s.pago_neto_pendiente || s.pago_neto_estilista || 0) > 0 && <span className="text-emerald-700 font-medium">A pagar (pendiente)</span>}
                    {Number(s.pago_neto_pendiente || s.pago_neto_estilista || 0) < 0 && <span className="text-red-700 font-medium">Debe al establecimiento</span>}
                    {Number(s.pago_neto_pendiente || s.pago_neto_estilista || 0) === 0 && <span className="text-slate-600 font-medium">En cero</span>}
                  </td>
                  <td className="table-cell">
                    <input
                      className="input-field !py-2 !min-h-0"
                      type="number"
                      min="0"
                      step="1"
                      placeholder="0"
                      value={pagosPorEstilista[s.estilista_id]?.efectivo || ''}
                      onChange={(e) => actualizarPagoMedio(s.estilista_id, 'efectivo', e.target.value)}
                    />
                  </td>
                  <td className="table-cell">
                    <input
                      className="input-field !py-2 !min-h-0"
                      type="number"
                      min="0"
                      step="1"
                      placeholder="0"
                      value={pagosPorEstilista[s.estilista_id]?.nequi || ''}
                      onChange={(e) => actualizarPagoMedio(s.estilista_id, 'nequi', e.target.value)}
                    />
                  </td>
                  <td className="table-cell">
                    <input
                      className="input-field !py-2 !min-h-0"
                      type="number"
                      min="0"
                      step="1"
                      placeholder="0"
                      value={pagosPorEstilista[s.estilista_id]?.daviplata || ''}
                      onChange={(e) => actualizarPagoMedio(s.estilista_id, 'daviplata', e.target.value)}
                    />
                  </td>
                  <td className="table-cell">
                    <input
                      className="input-field !py-2 !min-h-0"
                      type="number"
                      min="0"
                      step="1"
                      placeholder="0"
                      value={pagosPorEstilista[s.estilista_id]?.otros || ''}
                      onChange={(e) => actualizarPagoMedio(s.estilista_id, 'otros', e.target.value)}
                    />
                  </td>
                  <td className="table-cell font-semibold text-slate-900">
                    {formatMoney(totalPagosFila(s.estilista_id))}
                  </td>
                  <td className="table-cell">
                    <select
                      className="input-field !py-2 !min-h-0"
                      value={s.estado_pago_rango || s.estado_pago_dia || 'pendiente'}
                      onChange={(e) => cambiarEstadoPagoDia(s, e.target.value)}
                      disabled={!!savingEstadoByEstilista[s.estilista_id] || (s.estado_pago_rango || s.estado_pago_dia) === 'sin_movimiento'}
                    >
                      <option value="pendiente">Pendiente</option>
                      <option value="cancelado">Cancelado</option>
                      {(s.estado_pago_rango || s.estado_pago_dia) === 'parcial' && <option value="parcial">Parcial</option>}
                      {(s.estado_pago_rango || s.estado_pago_dia) === 'sin_movimiento' && <option value="sin_movimiento">Sin movimiento</option>}
                    </select>
                    <div className="text-xs text-slate-500 mt-1">
                      {savingEstadoByEstilista[s.estilista_id]
                        ? 'Guardando...'
                        : `${s.dias_cancelados_rango || 0} días cancelados / ${s.total_dias_trabajados || 0} trabajados`}
                    </div>
                    {Number(s.dias_cancelados_rango || 0) > 0 && (
                      <button
                        className="mt-2 btn-secondary !px-3 !py-1 text-xs"
                        onClick={() => deshacerLiquidacionRango(s)}
                        disabled={!!savingEstadoByEstilista[s.estilista_id]}
                      >
                        Deshacer liquidación
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="card-header mb-0">Consumo Empleado y cartera</h2>
            <p className="text-sm text-gray-500">Resumen por empleado con abonos, estado de deuda y saldo restante.</p>
          </div>
          <div className="rounded-2xl bg-amber-50 px-4 py-2 text-sm text-amber-700">
            {estilistaFiltro === 'todos' ? 'Todos los empleados' : estilistaFiltro}
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-6 py-3 text-left">Empleado</th>
                <th className="px-6 py-3 text-left">Facturas consumo</th>
                <th className="px-6 py-3 text-left">Total consumido</th>
                <th className="px-6 py-3 text-left">Total abonado</th>
                <th className="px-6 py-3 text-left">Saldo</th>
                <th className="px-6 py-3 text-left">Estado</th>
                <th className="px-6 py-3 text-left">Abonar</th>
                <th className="px-6 py-3 text-left">Medio pago</th>
                <th className="px-6 py-3 text-right">Acción</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {consumoResumenFiltrado.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={9}>No hay consumos de empleado en el rango seleccionado.</td>
                </tr>
              )}
              {consumoResumenFiltrado.map((fila) => (
                <tr key={fila.estilista_id} className="hover:bg-gray-50">
                  <td className="table-cell font-medium">{fila.estilista_nombre}</td>
                  <td className="table-cell">{fila.facturas || 0}</td>
                  <td className="table-cell">{formatMoney(fila.total_consumido)}</td>
                  <td className="table-cell">{formatMoney(fila.total_abonado)}</td>
                  <td className="table-cell font-semibold">{formatMoney(fila.saldo_pendiente)}</td>
                  <td className="table-cell capitalize">{fila.estado}</td>
                  <td className="table-cell">
                    <input
                      className="input-field !py-2 !min-h-0"
                      type="number"
                      min="0"
                      step="1"
                      placeholder="0"
                      value={abonoPorEstilista[fila.estilista_id]?.monto ?? ''}
                      onChange={(e) =>
                        setAbonoPorEstilista((prev) => ({
                          ...prev,
                          [fila.estilista_id]: {
                            monto: e.target.value,
                            medio_pago: prev[fila.estilista_id]?.medio_pago || 'efectivo',
                          },
                        }))
                      }
                    />
                  </td>
                  <td className="table-cell">
                    <select
                      className="input-field !py-2 !min-h-0"
                      value={abonoPorEstilista[fila.estilista_id]?.medio_pago || 'efectivo'}
                      onChange={(e) =>
                        setAbonoPorEstilista((prev) => ({
                          ...prev,
                          [fila.estilista_id]: {
                            monto: prev[fila.estilista_id]?.monto || '',
                            medio_pago: e.target.value,
                          },
                        }))
                      }
                    >
                      {MEDIOS_PAGO_ABONO.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="table-cell text-right">
                    <button
                      className="btn-primary !px-3 !py-2"
                      disabled={!!savingAbonoByEstilista[fila.estilista_id] || Number(fila.saldo_pendiente || 0) <= 0}
                      onClick={() => registrarAbonoConsumo(fila)}
                    >
                      {savingAbonoByEstilista[fila.estilista_id] ? 'Guardando...' : 'Aplicar abono'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="card-header mb-0">Control de liquidaciones</h2>
            <p className="text-sm text-gray-500">Auditoría para reclamos: estilista, valor liquidado, quién liquidó y fecha/hora.</p>
          </div>
          <button className="btn-secondary" onClick={() => cargarHistorialEstados()} disabled={loadingHistorial}>
            {loadingHistorial ? 'Cargando...' : 'Actualizar historial'}
          </button>
        </div>

        <div className="mt-4 overflow-auto rounded-2xl border border-gray-200" style={{ maxHeight: '18rem' }}>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header sticky top-0 bg-white">
              <tr>
                <th className="px-6 py-3 text-left">Fecha</th>
                <th className="px-6 py-3 text-left">Estilista</th>
                <th className="px-6 py-3 text-left">Valor liquidado</th>
                <th className="px-6 py-3 text-left">Quién liquidó</th>
                <th className="px-6 py-3 text-left">Fecha y hora</th>
                <th className="px-6 py-3 text-left">Cambio estado</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {historialEstados.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={6}>No hay liquidaciones registradas para este rango.</td>
                </tr>
              )}
              {historialEstados.map((h) => (
                <tr key={h.id} className="hover:bg-gray-50">
                  <td className="table-cell">{h.fecha}</td>
                  <td className="table-cell font-medium text-slate-900">{h.estilista_nombre}</td>
                  <td className="table-cell font-semibold text-emerald-700">{formatMoney(h.monto_liquidado)}</td>
                  <td className="table-cell">{h.usuario_nombre || 'Sistema'}</td>
                  <td className="table-cell">{h.fecha_cambio}</td>
                  <td className="table-cell">
                    <span className="text-slate-600">{h.estado_anterior}</span> {'->'} <span className="font-semibold text-slate-900">{h.estado_nuevo}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="card-header mb-0">Productos por agotarse</h2>
            <p className="text-sm text-gray-500">Contenedor recortado con scroll interno para no alargar la página.</p>
          </div>
          <div className="rounded-2xl bg-amber-50 px-4 py-2 text-sm text-amber-700">
            {marcaFiltro === 'todas' ? 'Todas las marcas' : marcaFiltro}
          </div>
        </div>
        {productosBajoStockFiltrados.length === 0 && <p className="mt-4 text-gray-600">No hay productos en riesgo de stock para este filtro.</p>}
        {productosBajoStockFiltrados.length > 0 && (
          <div className="mt-4 overflow-auto rounded-2xl border border-gray-200" style={{ maxHeight: '24rem' }}>
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header sticky top-0 bg-white">
                <tr>
                  <th className="px-6 py-3 text-left">Marca</th>
                  <th className="px-6 py-3 text-left">Producto</th>
                  <th className="px-6 py-3 text-left">Stock</th>
                  <th className="px-6 py-3 text-left">Mínimo</th>
                  <th className="px-6 py-3 text-left">Precio venta</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {productosBajoStockFiltrados.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="table-cell">{p.marca || '-'}</td>
                    <td className="table-cell font-medium">{p.nombre}</td>
                    <td className="table-cell">
                      <span className="inline-flex rounded-full px-3 py-1 text-xs font-semibold text-white" style={{ backgroundColor: stockRiskColor(p) }}>
                        {moneyFormatter.format(p.stock)}
                      </span>
                    </td>
                    <td className="table-cell">{moneyFormatter.format(p.stock_minimo)}</td>
                    <td className="table-cell">{formatMoney(p.precio_venta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {mostrarDetalleAvanzado && (
      <div className="card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="card-header mb-1">Resumen diario automático</h2>
            <p className="text-sm text-gray-600">Genera un texto de cierre para administración.</p>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={cargarResumenDiario}>Generar hoy</button>
            <button className="btn-primary" onClick={copiarResumenDiario}>Copiar resumen</button>
          </div>
        </div>
        {resumenDiario && (
          <div className="mt-4 rounded-2xl bg-gray-50 border border-gray-200 p-4">
            <pre className="whitespace-pre-wrap text-sm text-gray-800">{resumenDiario.texto_resumen}</pre>
          </div>
        )}
      </div>
      )}
    </div>
  );
};

export default Reportes;
