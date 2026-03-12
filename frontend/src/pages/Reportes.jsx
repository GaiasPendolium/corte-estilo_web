import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { reportesService } from '../services/api';
import { toast } from 'react-toastify';
import {
  Bar,
  BarChart,
  CartesianGrid,
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

const Reportes = () => {
  const [periodo, setPeriodo] = useState('mes');
  const [fechaInicio, setFechaInicio] = useState(format(firstDay, 'yyyy-MM-dd'));
  const [fechaFin, setFechaFin] = useState(format(today, 'yyyy-MM-dd'));
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exportarCsv = async () => {
    try {
      const blob = await reportesService.exportBICsv({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      });
      
      // Verificar si es un blob válido
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
      console.error('Error descargando CSV:', error);
      toast.error(error.response?.data?.message || error.message || 'No se pudo descargar el reporte CSV');
    }
  };

  const exportarPdf = async () => {
    try {
      const blob = await reportesService.exportBIPdf({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      });
      
      // Verificar si es un blob válido
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

  const kpis = stats?.kpis || {};

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">BI de Reportes</h1>
          <p className="text-gray-600 mt-1">Venta neta, utilidades, comisiones y liquidación por estilista</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={exportarCsv}>Descargar CSV</button>
          <button className="btn-secondary" onClick={exportarPdf}>Descargar PDF</button>
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="card-header mb-1">Resumen Diario Automático</h2>
            <p className="text-sm text-gray-600">Genera resumen de cierre para enviar a administración.</p>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={cargarResumenDiario}>Generar hoy</button>
            <button className="btn-primary" onClick={copiarResumenDiario}>Copiar resumen</button>
          </div>
        </div>
        {resumenDiario && (
          <div className="mt-4 rounded-lg bg-gray-50 border border-gray-200 p-4">
            <pre className="whitespace-pre-wrap text-sm text-gray-800">{resumenDiario.texto_resumen}</pre>
          </div>
        )}
      </div>

      <div className="card grid grid-cols-1 md:grid-cols-5 gap-4">
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
        <div className="md:col-span-2 flex items-end">
          <button className="btn-primary w-full" onClick={loadData} disabled={loading}>Consultar</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="card">
          <p className="text-gray-500 text-sm">Venta neta total</p>
          <h2 className="text-3xl font-bold mt-2">${Number(kpis.venta_neta_total || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Ganancia establecimiento total</p>
          <h2 className="text-3xl font-bold mt-2">${Number(kpis.ganancia_establecimiento_total || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Utilidad neta productos</p>
          <h2 className="text-3xl font-bold mt-2">${Number(kpis.utilidad_productos || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Pago total estilistas</p>
          <h2 className="text-3xl font-bold mt-2">${Number(kpis.pago_total_estilistas || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Ingresos productos</p>
          <h2 className="text-2xl font-bold mt-2">${Number(kpis.ingresos_productos || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Comisión servicios (establecimiento)</p>
          <h2 className="text-2xl font-bold mt-2">${Number(kpis.comision_servicios_establecimiento || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Comisión por ventas de productos (estilistas)</p>
          <h2 className="text-2xl font-bold mt-2">${Number(kpis.comision_producto_estilistas || 0).toFixed(2)}</h2>
        </div>
        <div className="card">
          <p className="text-gray-500 text-sm">Productos bajos de stock</p>
          <h2 className="text-2xl font-bold mt-2">{Number(kpis.productos_bajo_stock || 0)}</h2>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="card-header">Serie diaria (línea)</h2>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={stats?.serie_diaria || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fecha" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="ventas_productos" stroke="#111827" name="Productos" />
                <Line type="monotone" dataKey="ventas_servicios" stroke="#16a34a" name="Servicios" />
                <Line type="monotone" dataKey="total" stroke="#2563eb" name="Total" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2 className="card-header">Top ventas de productos (barra)</h2>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={stats?.top_ventas_productos || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="producto_nombre" hide />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="cantidad" fill="#0f766e" name="Cantidad" />
                <Bar dataKey="total" fill="#7c3aed" name="Total" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="card-header">Liquidación por estilista</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-6 py-3 text-left">Estilista</th>
                <th className="px-6 py-3 text-left">Tipo cobro</th>
                <th className="px-6 py-3 text-left">Valor configurado</th>
                <th className="px-6 py-3 text-left">Ganancia servicios</th>
                <th className="px-6 py-3 text-left">Comisión ventas productos</th>
                <th className="px-6 py-3 text-left">Bruto</th>
                <th className="px-6 py-3 text-left">Días alquiler</th>
                <th className="px-6 py-3 text-left">Descuento espacio</th>
                <th className="px-6 py-3 text-left">Pago neto</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {(stats?.estilistas || []).map((s) => (
                <tr key={s.estilista_id} className="hover:bg-gray-50">
                  <td className="table-cell font-medium">{s.estilista_nombre}</td>
                  <td className="table-cell capitalize">{s.tipo_cobro_espacio || 'ninguno'}</td>
                  <td className="table-cell">
                    {s.tipo_cobro_espacio === 'comision'
                      ? `${Number(s.valor_cobro_espacio || 0).toFixed(2)}%`
                      : `$${Number(s.valor_cobro_espacio || 0).toFixed(2)}`}
                  </td>
                  <td className="table-cell">${Number(s.ganancias_servicios || 0).toFixed(2)}</td>
                  <td className="table-cell">${Number(s.comision_ventas_producto || 0).toFixed(2)}</td>
                  <td className="table-cell">${Number(s.ganancias_totales_brutas || 0).toFixed(2)}</td>
                  <td className="table-cell">{Number(s.dias_cobrados_alquiler || 0)}</td>
                  <td className="table-cell">${Number(s.descuento_espacio || 0).toFixed(2)}</td>
                  <td className="table-cell">${Number(s.pago_neto_estilista || 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2 className="card-header">Productos por agotarse</h2>
        {(stats?.productos_bajo_stock || []).length === 0 && <p className="text-gray-600">No hay productos en riesgo de stock.</p>}
        {(stats?.productos_bajo_stock || []).length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Producto</th>
                  <th className="px-6 py-3 text-left">Stock</th>
                  <th className="px-6 py-3 text-left">Mínimo</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {(stats?.productos_bajo_stock || []).map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="table-cell font-medium">{p.nombre}</td>
                    <td className="table-cell">{p.stock}</td>
                    <td className="table-cell">{p.stock_minimo}</td>
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

export default Reportes;
