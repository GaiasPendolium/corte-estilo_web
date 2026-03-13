import { useEffect, useMemo, useState } from 'react';
import { FiCopy, FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { estilistasService, productosService, serviciosRealizadosService, ventasService } from '../services/api';
import ModalForm from '../components/ModalForm';
import useAuthStore from '../store/authStore';
import { canManageInvoices } from '../utils/roles';

const MEDIOS_PAGO = [
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'otros', label: 'Otros' },
];

const extractRows = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const Ventas = () => {
  const { user } = useAuthStore();
  const puedeEditarFacturas = canManageInvoices(user);
  const [modoVista, setModoVista] = useState('ventas');
  const [fechaInicio, setFechaInicio] = useState('');
  const [fechaFin, setFechaFin] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const [productos, setProductos] = useState([]);
  const [estilistas, setEstilistas] = useState([]);
  const [ventas, setVentas] = useState([]);
  const [serviciosFinalizados, setServiciosFinalizados] = useState([]);

  const [busquedaProducto, setBusquedaProducto] = useState('');
  const [productoSeleccionado, setProductoSeleccionado] = useState(null);

  const [form, setForm] = useState({
    cliente_nombre: '',
    estilista: '',
    medio_pago: 'efectivo',
    cantidad: '1',
    precio_unitario: '',
  });

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const paramsFecha = {
        ...(fechaInicio ? { fecha_inicio: fechaInicio } : {}),
        ...(fechaFin ? { fecha_fin: fechaFin } : {}),
      };
      const [productosRes, estilistasRes, ventasRes, serviciosRes] = await Promise.all([
        productosService.getAll(),
        estilistasService.getAll({ activo: true }),
        ventasService.getAll(paramsFecha),
        serviciosRealizadosService.getAll({ estado: 'finalizado', ...paramsFecha }),
      ]);
      setProductos(extractRows(productosRes));
      setEstilistas(extractRows(estilistasRes));
      setVentas(extractRows(ventasRes));
      setServiciosFinalizados(extractRows(serviciosRes));
    } catch (error) {
      toast.error('No se pudo cargar el facturador de ventas');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarDatos();
  }, [fechaInicio, fechaFin]);

  const buscarProducto = async () => {
    if (!busquedaProducto.trim()) {
      toast.warning('Ingresa código de barras o nombre');
      return;
    }

    try {
      const res = await productosService.getAll({ search: busquedaProducto.trim() });
      const encontrados = extractRows(res);
      const exactoCodigo = encontrados.find((p) => p.codigo_barras === busquedaProducto.trim());
      const producto = exactoCodigo || encontrados[0] || null;
      setProductoSeleccionado(producto);
      if (!producto) {
        toast.info('No se encontró producto');
      } else if (!editandoId) {
        setForm((prev) => ({ ...prev, precio_unitario: String(producto.precio_venta || '') }));
      }
    } catch (error) {
      toast.error('Error en búsqueda de producto');
    }
  };

  const limpiarFormulario = () => {
    setEditandoId(null);
    setShowForm(false);
    setProductoSeleccionado(null);
    setBusquedaProducto('');
    setForm({ cliente_nombre: '', estilista: '', medio_pago: 'efectivo', cantidad: '1', precio_unitario: '' });
  };

  const guardarVenta = async (e) => {
    e.preventDefault();

    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden crear o editar facturas');
      return;
    }

    if (!productoSeleccionado) {
      toast.warning('Selecciona un producto');
      return;
    }

    const cantidad = Number(form.cantidad || 0);
    const precioUnitario = Number(form.precio_unitario || 0);

    if (cantidad <= 0) {
      toast.warning('La cantidad debe ser mayor a cero');
      return;
    }
    if (precioUnitario <= 0) {
      toast.warning('El valor unitario debe ser mayor a cero');
      return;
    }

    try {
      setSaving(true);
      const payload = {
        producto: productoSeleccionado.id,
        cantidad,
        precio_unitario: precioUnitario,
        cliente_nombre: form.cliente_nombre.trim() || null,
        estilista: form.estilista ? Number(form.estilista) : null,
        medio_pago: form.medio_pago,
      };

      if (editandoId) {
        await ventasService.update(editandoId, payload);
        toast.success('Factura de producto actualizada');
      } else {
        await ventasService.create(payload);
        toast.success('Factura de producto creada');
      }

      limpiarFormulario();
      await cargarDatos();
    } catch (error) {
      const msg = error?.response?.data?.cantidad?.[0] || error?.response?.data?.detail || 'No se pudo guardar la factura';
      toast.error(String(msg));
    } finally {
      setSaving(false);
    }
  };

  const editarVenta = (venta) => {
    setEditandoId(venta.id);
    setShowForm(true);
    const producto = productos.find((p) => p.id === venta.producto) || null;
    setProductoSeleccionado(producto);
    setBusquedaProducto(producto?.codigo_barras || producto?.nombre || '');
    setForm({
      cliente_nombre: venta.cliente_nombre || '',
      estilista: venta.estilista ? String(venta.estilista) : '',
      medio_pago: venta.medio_pago || 'efectivo',
      cantidad: String(venta.cantidad || 1),
      precio_unitario: String(venta.precio_unitario || ''),
    });
  };

  const eliminarVenta = async (venta) => {
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden eliminar facturas');
      return;
    }
    const ok = window.confirm(`¿Eliminar la factura ${venta.numero_factura || venta.id}?`);
    if (!ok) return;

    try {
      await ventasService.delete(venta.id);
      toast.success('Factura eliminada');
      if (editandoId === venta.id) limpiarFormulario();
      await cargarDatos();
    } catch (error) {
      toast.error('No se pudo eliminar la factura');
    }
  };

  const copiarTexto = async (texto) => {
    if (!texto) {
      toast.info('No hay texto de factura para copiar');
      return;
    }
    try {
      await navigator.clipboard.writeText(texto);
      toast.success('Factura copiada para WhatsApp');
    } catch (error) {
      toast.error('No se pudo copiar al portapapeles');
    }
  };

  const totalVentas = useMemo(() => ventas.reduce((acc, v) => acc + Number(v.total || 0), 0), [ventas]);
  const ticketPromedio = useMemo(() => (ventas.length ? totalVentas / ventas.length : 0), [totalVentas, ventas.length]);
  const totalServicios = useMemo(
    () => serviciosFinalizados.reduce((acc, s) => acc + Number(s.precio_cobrado || 0), 0),
    [serviciosFinalizados]
  );

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Facturador de Ventas</h1>
          <p className="text-gray-600 mt-1">Histórico con filtros por fecha, resumen y control por perfil</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarDatos} disabled={loading}>
            <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          <button
            className="btn-primary inline-flex items-center gap-2"
            onClick={() => {
              setEditandoId(null);
              setShowForm(true);
              setProductoSeleccionado(null);
              setBusquedaProducto('');
              setForm({ cliente_nombre: '', estilista: '', medio_pago: 'efectivo', cantidad: '1', precio_unitario: '' });
            }}
            disabled={!puedeEditarFacturas || modoVista !== 'ventas'}
          >
            <FiPlus /> Nueva factura
          </button>
        </div>
      </div>

      <div className="card p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button className={modoVista === 'ventas' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('ventas')}>
            Ventas de productos
          </button>
          <button className={modoVista === 'servicios' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('servicios')}>
            Servicios facturados
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input className="input-field" type="date" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
          <input className="input-field" type="date" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
          <button className="btn-secondary" onClick={() => { setFechaInicio(''); setFechaFin(''); }}>Limpiar filtros</button>
          <div className="text-sm text-gray-600 flex items-center">Total resultados: {modoVista === 'ventas' ? ventas.length : serviciosFinalizados.length}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <p className="text-sm text-gray-500">Total ventas productos</p>
          <p className="text-2xl font-bold text-gray-900">${totalVentas.toFixed(2)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Ticket promedio</p>
          <p className="text-2xl font-bold text-gray-900">${ticketPromedio.toFixed(2)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Total servicios facturados</p>
          <p className="text-2xl font-bold text-gray-900">${totalServicios.toFixed(2)}</p>
        </div>
      </div>

      {modoVista === 'ventas' && (
      <>
      <ModalForm
        isOpen={showForm}
        onClose={limpiarFormulario}
        title={editandoId ? 'Editar factura de producto' : 'Nueva factura de producto'}
        subtitle="Busca producto por código o nombre y registra la venta"
        size="xl"
      >
      <form className="grid grid-cols-1 md:grid-cols-4 gap-3" onSubmit={guardarVenta}>
        <h2 className="card-header md:col-span-4">Factura de producto</h2>
        <input
          className="input-field md:col-span-3"
          placeholder="Buscar producto por código de barras o nombre"
          value={busquedaProducto}
          onChange={(e) => setBusquedaProducto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              buscarProducto();
            }
          }}
        />
        <button type="button" className="btn-secondary inline-flex items-center justify-center gap-2" onClick={buscarProducto}>
          <FiSearch /> Buscar
        </button>

        <input className="input-field" placeholder="Cliente (opcional)" value={form.cliente_nombre} onChange={(e) => setForm((p) => ({ ...p, cliente_nombre: e.target.value }))} />
        <select className="input-field" value={form.estilista} onChange={(e) => setForm((p) => ({ ...p, estilista: e.target.value }))}>
          <option value="">Estilista (opcional)</option>
          {estilistas.map((e) => (
            <option key={e.id} value={e.id}>{e.nombre}</option>
          ))}
        </select>
        <select className="input-field" value={form.medio_pago} onChange={(e) => setForm((p) => ({ ...p, medio_pago: e.target.value }))}>
          {MEDIOS_PAGO.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
        <input className="input-field" type="number" min="1" placeholder="Cantidad" value={form.cantidad} onChange={(e) => setForm((p) => ({ ...p, cantidad: e.target.value }))} />
        <input className="input-field" type="number" min="0" step="0.01" placeholder="Valor unitario" value={form.precio_unitario} onChange={(e) => setForm((p) => ({ ...p, precio_unitario: e.target.value }))} />

        {productoSeleccionado && (
          <div className="md:col-span-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            Producto: <strong>{productoSeleccionado.nombre}</strong> | Stock: <strong>{productoSeleccionado.stock}</strong>
          </div>
        )}

        <div className="md:col-span-4 flex gap-2">
          <button className="btn-primary" type="submit" disabled={saving}>
            {saving ? 'Guardando...' : editandoId ? 'Actualizar factura' : 'Crear factura'}
          </button>
          {editandoId && (
            <button type="button" className="btn-secondary" onClick={limpiarFormulario}>Cancelar</button>
          )}
        </div>
      </form>
      </ModalForm>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="card-header mb-0">Histórico de facturas de productos</h2>
          <span className="text-sm text-gray-600">Total: ${totalVentas.toFixed(2)}</span>
        </div>

        {!loading && ventas.length === 0 && <p className="text-gray-600">No hay facturas de productos registradas.</p>}

        {!loading && ventas.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Producto</th>
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Estilista</th>
                  <th className="px-6 py-3 text-left">Medio pago</th>
                  <th className="px-6 py-3 text-left">Cantidad</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {ventas.map((v) => (
                  <tr key={v.id} className="hover:bg-gray-50">
                    <td className="table-cell">{v.numero_factura || '-'}</td>
                    <td className="table-cell">{v.producto_nombre}</td>
                    <td className="table-cell">{v.cliente_nombre || '-'}</td>
                    <td className="table-cell">{v.estilista_nombre || '-'}</td>
                    <td className="table-cell capitalize">{v.medio_pago || '-'}</td>
                    <td className="table-cell">{v.cantidad}</td>
                    <td className="table-cell">${Number(v.total || 0).toFixed(2)}</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        {puedeEditarFacturas && (
                          <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => editarVenta(v)}>
                            <FiEdit2 size={14} /> Editar
                          </button>
                        )}
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => copiarTexto(v.factura_texto)}>
                          <FiCopy size={14} /> Copiar
                        </button>
                        {puedeEditarFacturas && (
                          <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarVenta(v)}>
                            <FiTrash2 size={14} /> Eliminar
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      </>
      )}

      {modoVista === 'servicios' && (
      <div className="card">
        <h2 className="card-header">Facturas de servicios finalizados</h2>
        {serviciosFinalizados.length === 0 && <p className="text-gray-600">No hay servicios finalizados con factura.</p>}
        {serviciosFinalizados.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Servicio</th>
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosFinalizados.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="table-cell">{s.numero_factura || '-'}</td>
                    <td className="table-cell">{s.servicio_nombre}</td>
                    <td className="table-cell">{s.cliente_nombre || '-'}</td>
                    <td className="table-cell">${Number(s.precio_cobrado || 0).toFixed(2)}</td>
                    <td className="table-cell text-right">
                      <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => copiarTexto(s.factura_texto)}>
                        <FiCopy size={14} /> Copiar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}
    </div>
  );
};

export default Ventas;
