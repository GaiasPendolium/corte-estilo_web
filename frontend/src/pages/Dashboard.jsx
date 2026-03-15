import { useEffect, useMemo, useState } from 'react';
import { FiActivity, FiAlertCircle, FiDollarSign, FiScissors, FiShoppingBag, FiTrendingUp } from 'react-icons/fi';
import { reportesService } from '../services/api';
import { format } from 'date-fns';
import { toast } from 'react-toastify';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const moneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const formatMoney = (value) => `$${moneyFormatter.format(Number(value || 0))}`;

const MetricPanel = ({ title, value, detail, icon: Icon, accent }) => (
  <div className={`rounded-[26px] border p-5 shadow-sm ${accent}`}>
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm uppercase tracking-[0.18em] opacity-70">{title}</p>
        <p className="mt-3 text-3xl font-black tracking-tight">{value}</p>
        <p className="mt-2 text-sm opacity-75">{detail}</p>
      </div>
      <div className="rounded-2xl bg-white/70 p-3 shadow-sm">
        <Icon size={24} />
      </div>
    </div>
  </div>
);

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    cargarDatos();
  }, []);

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const hoy = new Date();
      const primerDia = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
      const data = await reportesService.getBIResumen({
        periodo: 'mes',
        fecha_inicio: format(primerDia, 'yyyy-MM-dd'),
        fecha_fin: format(hoy, 'yyyy-MM-dd'),
      });
      setStats(data);
    } catch (error) {
      toast.error('Error al cargar los datos del dashboard');
    } finally {
      setLoading(false);
    }
  };

  const kpis = stats?.kpis || {};

  const metricas = useMemo(() => {
    const ventasProductos = Number(kpis.ingresos_productos || 0);
    const ventasServicios = Number(kpis.ingresos_servicios || 0);
    const total = Number(kpis.venta_neta_total || 0);
    const cantidadVentas = Number(kpis.cantidad_ventas_productos || 0);
    const cantidadServicios = Number(kpis.cantidad_servicios || 0);
    const ticketProducto = cantidadVentas ? ventasProductos / cantidadVentas : 0;
    const ticketServicio = cantidadServicios ? ventasServicios / cantidadServicios : 0;
    const margenProductos = ventasProductos ? (Number(kpis.utilidad_productos || 0) / ventasProductos) * 100 : 0;
    const participacionServicios = total ? (ventasServicios / total) * 100 : 0;

    return {
      ticketProducto,
      ticketServicio,
      margenProductos,
      participacionServicios,
    };
  }, [kpis]);

  const topProductos = useMemo(() => (stats?.top_ventas_productos || []).slice(0, 6), [stats]);
  const alertasStock = useMemo(() => (stats?.productos_bajo_stock || []).slice(0, 8), [stats]);
  const topEstilistas = useMemo(
    () => [...(stats?.estilistas || [])].sort((a, b) => Number(b.pago_neto_estilista || 0) - Number(a.pago_neto_estilista || 0)).slice(0, 5),
    [stats]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 fade-in">
      <section className="rounded-[30px] bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.24),_transparent_26%),radial-gradient(circle_at_bottom_right,_rgba(16,185,129,0.18),_transparent_28%),linear-gradient(135deg,#020617_0%,#0f172a_45%,#1e293b_100%)] p-6 text-white shadow-2xl">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-300">Control ejecutivo</p>
            <h1 className="mt-2 text-4xl font-black tracking-tight">Dashboard Operativo</h1>
            <p className="mt-2 max-w-3xl text-slate-300">Visión mensual del negocio con foco en rentabilidad, eficiencia comercial, presión de inventario y payout del equipo.</p>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:w-[28rem]">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
              <p className="text-xs uppercase tracking-wide text-slate-300">Rango</p>
              <p className="mt-2 text-lg font-semibold">{stats?.fecha_inicio} al {stats?.fecha_fin}</p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur">
              <p className="text-xs uppercase tracking-wide text-slate-300">Participación servicios</p>
              <p className="mt-2 text-lg font-semibold">{metricas.participacionServicios.toFixed(1)}%</p>
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
        <MetricPanel title="Venta neta" value={formatMoney(kpis.venta_neta_total)} detail={`${Number(kpis.cantidad_servicios || 0)} servicios + ${Number(kpis.cantidad_ventas_productos || 0)} ventas`} icon={FiDollarSign} accent="bg-slate-950 text-white border-slate-900" />
        <MetricPanel title="Ganancia negocio" value={formatMoney(kpis.ganancia_establecimiento_total)} detail={`Productos: ${formatMoney(kpis.ganancia_establecimiento_productos)} | Servicios: ${formatMoney(kpis.comision_servicios_establecimiento)}`} icon={FiTrendingUp} accent="bg-emerald-50 text-emerald-950 border-emerald-100" />
        <MetricPanel title="Pago estilistas" value={formatMoney(kpis.pago_total_estilistas)} detail={`Descuentos espacio: ${formatMoney(kpis.descuentos_espacio_estilistas)}`} icon={FiScissors} accent="bg-sky-50 text-sky-950 border-sky-100" />
        <MetricPanel title="Stock crítico" value={moneyFormatter.format(kpis.productos_bajo_stock || 0)} detail={`Margen productos: ${metricas.margenProductos.toFixed(1)}%`} icon={FiAlertCircle} accent="bg-amber-50 text-amber-950 border-amber-100" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-6">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="card-header mb-0">Comportamiento diario</h2>
              <p className="text-sm text-gray-500">Cruza servicios, productos y total facturado por día.</p>
            </div>
            <div className="rounded-2xl bg-slate-100 px-4 py-2 text-sm text-slate-700">Ticket servicio: {formatMoney(metricas.ticketServicio)}</div>
          </div>
          <div className="mt-4" style={{ width: '100%', height: 340 }}>
            <ResponsiveContainer>
              <AreaChart data={stats?.serie_diaria || []}>
                <defs>
                  <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0f766e" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#0f766e" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fecha" />
                <YAxis tickFormatter={moneyFormatter.format} />
                <Tooltip formatter={(value) => formatMoney(value)} />
                <Legend />
                <Area type="monotone" dataKey="total" stroke="#0f766e" strokeWidth={3} fill="url(#colorTotal)" name="Total" />
                <Area type="monotone" dataKey="ventas_servicios" stroke="#2563eb" strokeWidth={2} fillOpacity={0} name="Servicios" />
                <Area type="monotone" dataKey="ventas_productos" stroke="#f97316" strokeWidth={2} fillOpacity={0} name="Productos" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2 className="card-header">Pulso comercial</h2>
          <div className="grid grid-cols-1 gap-4">
            <div className="rounded-2xl bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">Ticket promedio producto</p>
                  <p className="mt-2 text-2xl font-black text-slate-900">{formatMoney(metricas.ticketProducto)}</p>
                </div>
                <FiShoppingBag className="text-slate-700" size={22} />
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">Utilidad productos</p>
                  <p className="mt-2 text-2xl font-black text-slate-900">{formatMoney(kpis.utilidad_productos)}</p>
                </div>
                <FiActivity className="text-slate-700" size={22} />
              </div>
            </div>
            <div className="rounded-2xl bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">Comisión productos estilistas</p>
                  <p className="mt-2 text-2xl font-black text-slate-900">{formatMoney(kpis.comision_producto_estilistas)}</p>
                </div>
                <FiScissors className="text-slate-700" size={22} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="card-header">Top productos del mes</h2>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={topProductos} layout="vertical" margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={moneyFormatter.format} />
                <YAxis type="category" dataKey="producto_nombre" width={110} />
                <Tooltip formatter={(value, key) => key === 'cantidad' ? value : formatMoney(value)} />
                <Legend />
                <Bar dataKey="total" fill="#1d4ed8" name="Facturación" radius={[0, 8, 8, 0]} />
                <Bar dataKey="cantidad" fill="#0f766e" name="Cantidad" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="card-header mb-0">Top estilistas por pago neto</h2>
              <p className="text-sm text-gray-500">Referente rápido para liquidación y ocupación rentable.</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {topEstilistas.map((item, index) => (
              <div key={item.estilista_id} className="rounded-2xl border border-gray-200 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-gray-400">#{index + 1}</p>
                    <p className="text-lg font-semibold text-gray-900">{item.estilista_nombre}</p>
                    <p className="text-sm text-gray-500">Servicios: {formatMoney(item.ganancias_servicios)} | Ventas: {formatMoney(item.comision_ventas_producto)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-gray-500">Pago neto</p>
                    <p className="text-xl font-black text-emerald-700">{formatMoney(item.pago_neto_estilista)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="card-header mb-0">Alertas de inventario</h2>
            <p className="text-sm text-gray-500">Lista corta para actuar rápido sin bajar demasiado en la pantalla.</p>
          </div>
          <div className="rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-700">{moneyFormatter.format(alertasStock.length)} referencias críticas</div>
        </div>
        {alertasStock.length === 0 ? (
          <p className="mt-4 text-gray-600">No hay productos en riesgo de stock.</p>
        ) : (
          <div className="mt-4 overflow-auto rounded-2xl border border-gray-200" style={{ maxHeight: '22rem' }}>
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header sticky top-0 bg-white">
                <tr>
                  <th className="px-6 py-3 text-left">Marca</th>
                  <th className="px-6 py-3 text-left">Producto</th>
                  <th className="px-6 py-3 text-left">Stock</th>
                  <th className="px-6 py-3 text-left">Mínimo</th>
                  <th className="px-6 py-3 text-left">Precio</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {alertasStock.map((producto) => (
                  <tr key={producto.id} className="hover:bg-gray-50">
                    <td className="table-cell">{producto.marca || '-'}</td>
                    <td className="table-cell font-medium">{producto.nombre}</td>
                    <td className="table-cell text-red-700 font-semibold">{moneyFormatter.format(producto.stock)}</td>
                    <td className="table-cell">{moneyFormatter.format(producto.stock_minimo)}</td>
                    <td className="table-cell">{formatMoney(producto.precio_venta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
