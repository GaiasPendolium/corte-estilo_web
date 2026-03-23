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
  const [stats, setStats] = useState(null);
  const [resumenDiario, setResumenDiario] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await reportesService.getBIResumen({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        ...(medioPagoFiltro !== 'todos' ? { medio_pago: medioPagoFiltro } : {}),
      });
      setStats(data);
    } catch (error) {
      toast.error('Error al cargar reportes');
      setStats(null);
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

  return (
    <div className="space-y-6 fade-in">
      <section className="rounded-[28px] bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_34%),linear-gradient(135deg,#0f172a_0%,#111827_35%,#1f2937_100%)] p-6 text-white shadow-2xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-slate-300">Centro de inteligencia</p>
            <h1 className="mt-2 text-4xl font-black tracking-tight">Reportes Ejecutivos</h1>
            <p className="mt-2 max-w-2xl text-slate-300">Vista gerencial con rentabilidad, liquidez, carga operativa y alertas accionables.</p>
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
            <button className="btn-primary" onClick={loadData} disabled={loading}>{loading ? 'Consultando...' : 'Consultar'}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-5">
        <KpiCard title="Venta neta total" value={formatMoney(kpis.venta_neta_total)} hint={`Todo lo cobrado al cliente: servicios + adicionales + productos`} tone="slate" />
        <KpiCard title="Ganancia establecimiento" value={formatMoney(kpis.ganancia_establecimiento_total)} hint={`Cuadre caja: Venta neta - Pago estilistas`} tone="emerald" />
        <KpiCard title="Pago estilistas" value={formatMoney(kpis.pago_total_estilistas)} hint={`Solo saldos positivos. Descuentos espacio: ${formatMoney(kpis.descuentos_espacio_estilistas)}`} tone="sky" />
        <KpiCard title="Deudas estilistas" value={formatMoney(kpis.deudas_estilistas)} hint={`Suma de saldos negativos pendientes por cobro de espacio`} tone="amber" />
        <KpiCard title="Total ganancias" value={formatMoney(kpis.total_ganancias_negocio)} hint={`Arriendo espacios + utilidad neta productos + otros servicios no producto`} tone="amber" />
        <KpiCard title="Stock crítico" value={moneyFormatter.format(kpis.productos_bajo_stock || 0)} hint={`Promedio venta producto: ${formatMoney(ventaPromedioProducto)}`} tone="amber" />
      </div>

      <div className="card border border-emerald-100 bg-emerald-50">
        <p className="text-sm text-emerald-700 font-medium">Cuadre automático</p>
        <p className="mt-1 text-sm text-emerald-800">
          {formatMoney(kpis.venta_neta_total)} = {formatMoney(kpis.pago_total_estilistas)} + {formatMoney(kpis.ganancia_establecimiento_total)}
        </p>
        <p className="mt-1 text-xs text-emerald-700">
          Ganancia establecimiento bruta (incluye deudas estilistas): {formatMoney(kpis.ganancia_establecimiento_bruta)}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card border border-slate-200 bg-slate-50">
          <p className="text-sm text-slate-600">1. Lo que recibe hoy</p>
          <p className="mt-2 text-3xl font-black text-slate-900">{formatMoney(recibeHoy)}</p>
          <p className="mt-1 text-sm text-slate-600">Total que entró por clientes.</p>
        </div>
        <div className="card border border-blue-200 bg-blue-50">
          <p className="text-sm text-blue-700">2. Lo que paga hoy</p>
          <p className="mt-2 text-3xl font-black text-blue-900">{formatMoney(pagaHoy)}</p>
          <p className="mt-1 text-sm text-blue-700">Solo pagos positivos a estilistas.</p>
        </div>
        <div className="card border border-emerald-200 bg-emerald-50">
          <p className="text-sm text-emerald-700">3. Lo que le queda hoy</p>
          <p className="mt-2 text-3xl font-black text-emerald-900">{formatMoney(leQuedaHoy)}</p>
          <p className="mt-1 text-sm text-emerald-700">Entrada del día menos pagos del día.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm text-gray-500">Productos total vendido</p>
          <p className="mt-2 text-2xl font-black text-gray-900">{formatMoney(kpis.ingresos_productos_totales)}</p>
          <p className="mt-1 text-sm text-gray-500">Caja productos: {formatMoney(kpis.ingresos_productos_caja)} | En servicios adicionales: {formatMoney(kpis.ingresos_productos_en_servicios)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Reserva reabastecimiento</p>
          <p className="mt-2 text-2xl font-black text-gray-900">{formatMoney(kpis.reserva_reabastecimiento_productos)}</p>
          <p className="mt-1 text-sm text-gray-500">Costo de compra de productos vendidos en caja y en servicios adicionales</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Utilidad neta productos</p>
          <p className="mt-2 text-2xl font-black text-gray-900">{formatMoney(kpis.utilidad_neta_productos)}</p>
          <p className="mt-1 text-sm text-gray-500">(Venta productos caja + en servicios) - (costo compra total)</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Valor servicios (sin productos)</p>
          <p className="mt-2 text-2xl font-black text-gray-900">{formatMoney(kpis.ingresos_servicios_no_producto)}</p>
          <p className="mt-1 text-sm text-gray-500">Base servicios: {formatMoney(kpis.ingresos_servicios)} | Otros adicionales no producto: {formatMoney(kpis.otros_servicios_no_producto)}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card border border-emerald-200 bg-emerald-50">
          <p className="text-sm text-emerald-700">Disponible productos (establecimiento)</p>
          <p className="mt-2 text-2xl font-black text-emerald-900">{formatMoney(kpis.disponible_productos_despues_reabastecer)}</p>
          <p className="mt-1 text-sm text-emerald-700">Utilidad productos - comisión estilistas</p>
        </div>
        <div className="card border border-sky-200 bg-sky-50">
          <p className="text-sm text-sky-700">Ganancia servicios</p>
          <p className="mt-2 text-2xl font-black text-sky-900">{formatMoney(kpis.ingresos_servicios_totales)}</p>
          <p className="mt-1 text-sm text-sky-700">Lo cobrado en servicios, incluyendo adicionales</p>
        </div>
        <div className="card border border-amber-200 bg-amber-50">
          <p className="text-sm text-amber-700">Total operaciones</p>
          <p className="mt-2 text-2xl font-black text-amber-900">{moneyFormatter.format(Number(kpis.cantidad_servicios || 0) + Number(kpis.cantidad_ventas_productos || 0))}</p>
          <p className="mt-1 text-sm text-amber-700">{Number(kpis.cantidad_servicios || 0)} servicios y {Number(kpis.cantidad_ventas_productos || 0)} ventas</p>
        </div>
      </div>

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
                <th className="px-6 py-3 text-left">Neto</th>
                <th className="px-6 py-3 text-left">Estado</th>
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
                  <td className="table-cell">{formatMoney(s.comision_ventas_producto)}</td>
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
                    <div className={`font-semibold ${Number(s.pago_neto_estilista || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {formatMoney(s.pago_neto_estilista)}
                    </div>
                  </td>
                  <td className="table-cell">
                    {Number(s.pago_neto_estilista || 0) > 0 && <span className="text-emerald-700 font-medium">A pagar</span>}
                    {Number(s.pago_neto_estilista || 0) < 0 && <span className="text-red-700 font-medium">Debe al establecimiento</span>}
                    {Number(s.pago_neto_estilista || 0) === 0 && <span className="text-slate-600 font-medium">En cero</span>}
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
    </div>
  );
};

export default Reportes;
