import { useState, useEffect } from 'react';
import { FiDollarSign, FiPackage, FiTrendingUp, FiAlertCircle } from 'react-icons/fi';
import { reportesService, productosService } from '../services/api';
import { format } from 'date-fns';
import { toast } from 'react-toastify';

const Dashboard = () => {
  const [estadisticas, setEstadisticas] = useState(null);
  const [productosBajoStock, setProductosBajoStock] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    cargarDatos();
  }, []);

  const cargarDatos = async () => {
    try {
      setLoading(true);
      
      // Obtener estadísticas del mes actual
      const hoy = new Date();
      const primerDia = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
      
      const [stats, productos] = await Promise.all([
        reportesService.getEstadisticasGenerales({
          fecha_inicio: format(primerDia, 'yyyy-MM-dd'),
          fecha_fin: format(hoy, 'yyyy-MM-dd'),
        }),
        productosService.getBajoStock(),
      ]);
      
      setEstadisticas(stats);
      setProductosBajoStock(productos);
    } catch (error) {
      console.error('Error al cargar datos:', error);
      toast.error('Error al cargar los datos del dashboard');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 fade-in">
      {/* Título */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">Resumen general del negocio</p>
      </div>

      {/* Tarjetas de estadísticas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Ventas */}
        <div className="card bg-gradient-to-br from-blue-500 to-blue-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-blue-100 text-sm font-medium">Ventas  Productos</p>
              <p className="text-3xl font-bold mt-2">
                ${estadisticas?.total_ventas_productos?.toLocaleString('es-MX', { minimumFractionDigits: 2 }) || '0.00'}
              </p>
              <p className="text-blue-100 text-sm mt-1">
                {estadisticas?.cantidad_ventas || 0} transacciones
              </p>
            </div>
            <div className="bg-white bg-opacity-20 p-3 rounded-full">
              <FiDollarSign size={32} />
            </div>
          </div>
        </div>

        {/* Total Servicios */}
        <div className="card bg-gradient-to-br from-green-500 to-green-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 text-sm font-medium">Ingresos Servicios</p>
              <p className="text-3xl font-bold mt-2">
                ${estadisticas?.total_servicios?.toLocaleString('es-MX', { minimumFractionDigits: 2 }) || '0.00'}
              </p>
              <p className="text-green-100 text-sm mt-1">
                {estadisticas?.cantidad_servicios || 0} servicios
              </p>
            </div>
            <div className="bg-white bg-opacity-20 p-3 rounded-full">
              <FiPackage size={32} />
            </div>
          </div>
        </div>

        {/* Total General */}
        <div className="card bg-gradient-to-br from-purple-500 to-purple-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-purple-100 text-sm font-medium">Ingresos Totales</p>
              <p className="text-3xl font-bold mt-2">
                ${estadisticas?.total_general?.toLocaleString('es-MX', { minimumFractionDigits: 2 }) || '0.00'}
              </p>
              <p className="text-purple-100 text-sm mt-1">
                Este mes
              </p>
            </div>
            <div className="bg-white bg-opacity-20 p-3 rounded-full">
              <FiTrendingUp size={32} />
            </div>
          </div>
        </div>

        {/* Productos bajo stock */}
        <div className="card bg-gradient-to-br from-red-500 to-red-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-red-100 text-sm font-medium">Productos Bajo Stock</p>
              <p className="text-3xl font-bold mt-2">
                {estadisticas?.productos_bajo_stock || 0}
              </p>
              <p className="text-red-100 text-sm mt-1">
                Requieren atención
              </p>
            </div>
            <div className="bg-white bg-opacity-20 p-3 rounded-full">
              <FiAlertCircle size={32} />
            </div>
          </div>
        </div>
      </div>

      {/* Productos con bajo stock */}
      {productosBajoStock.length > 0 && (
        <div className="card">
          <h2 className="card-header flex items-center space-x-2">
            <FiAlertCircle className="text-red-600" />
            <span>Productos que necesitan reposición</span>
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Stock Actual</th>
                  <th className="px-6 py-3 text-left">Stock Mínimo</th>
                  <th className="px-6 py-3 text-left">Precio</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {productosBajoStock.map((producto) => (
                  <tr key={producto.id} className="hover:bg-gray-50">
                    <td className="table-cell font-medium">{producto.nombre}</td>
                    <td className="table-cell">
                      <span className="px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800">
                        {producto.stock}
                      </span>
                    </td>
                    <td className="table-cell">{producto.stock_minimo}</td>
                    <td className="table-cell">
                      ${producto.precio_venta.toLocaleString('es-MX', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
