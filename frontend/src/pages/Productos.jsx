import { useEffect, useMemo, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { productosService } from '../services/api';
import ModalForm from '../components/ModalForm';

const INITIAL_FORM = {
  codigo_barras: '',
  nombre: '',
  marca: '',
  presentacion: '',
  precio_compra: '',
  precio_venta: '',
  comision_estilista: '',
  stock: '0',
  stock_minimo: '5',
};

const extractRows = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const Productos = () => {
  const [productos, setProductos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [codigoBusqueda, setCodigoBusqueda] = useState('');
  const [productoEncontrado, setProductoEncontrado] = useState(null);

  const cargarProductos = async () => {
    try {
      setLoading(true);
      const payload = await productosService.getAll();
      setProductos(extractRows(payload));
    } catch (error) {
      toast.error('No se pudo cargar inventario');
      setProductos([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarProductos();
  }, []);

  const guardarProducto = async (e) => {
    e.preventDefault();
    if (!form.nombre.trim()) {
      toast.warning('El nombre es obligatorio');
      return;
    }
    if (!form.precio_venta) {
      toast.warning('El valor de venta es obligatorio');
      return;
    }

    try {
      setSaving(true);
      const payload = {
        codigo_barras: form.codigo_barras.trim() || null,
        nombre: form.nombre.trim(),
        marca: form.marca.trim() || null,
        presentacion: form.presentacion.trim() || null,
        precio_compra: form.precio_compra ? Number(form.precio_compra) : null,
        precio_venta: Number(form.precio_venta),
        comision_estilista: form.comision_estilista ? Number(form.comision_estilista) : 0,
        stock: Number(form.stock || 0),
        stock_minimo: Number(form.stock_minimo || 5),
      };

      if (editingId) {
        const actual = productos.find((p) => p.id === editingId);
        payload.activo = actual?.activo ?? true;
        await productosService.update(editingId, payload);
        toast.success('Producto actualizado');
      } else {
        payload.activo = true;
        await productosService.create(payload);
        toast.success('Producto guardado en inventario');
      }

      setEditingId(null);
      setForm(INITIAL_FORM);
      setShowForm(false);
      await cargarProductos();
    } catch (error) {
      const data = error?.response?.data;
      const firstError = typeof data === 'object' ? Object.values(data)[0] : null;
      const message = Array.isArray(firstError) ? firstError[0] : firstError || 'No se pudo guardar producto';
      toast.error(String(message));
    } finally {
      setSaving(false);
    }
  };

  const iniciarEdicion = (producto) => {
    setEditingId(producto.id);
    setShowForm(true);
    setForm({
      codigo_barras: producto.codigo_barras || '',
      nombre: producto.nombre || '',
      marca: producto.marca || '',
      presentacion: producto.presentacion || '',
      precio_compra: producto.precio_compra ?? '',
      precio_venta: producto.precio_venta ?? '',
      comision_estilista: producto.comision_estilista ?? '',
      stock: producto.stock ?? 0,
      stock_minimo: producto.stock_minimo ?? 5,
    });
  };

  const cancelarEdicion = () => {
    setEditingId(null);
    setForm(INITIAL_FORM);
    setShowForm(false);
  };

  const cambiarEstado = async (producto) => {
    const accion = producto.activo ? 'desactivar' : 'activar';
    const ok = window.confirm(`¿Deseas ${accion} el producto "${producto.nombre}"?`);
    if (!ok) return;

    try {
      await productosService.update(producto.id, {
        codigo_barras: producto.codigo_barras,
        nombre: producto.nombre,
        marca: producto.marca,
        presentacion: producto.presentacion,
        descripcion: producto.descripcion,
        precio_compra: producto.precio_compra,
        precio_venta: producto.precio_venta,
        comision_estilista: producto.comision_estilista,
        stock: producto.stock,
        stock_minimo: producto.stock_minimo,
        activo: !producto.activo,
      });
      toast.success(`Producto ${producto.activo ? 'desactivado' : 'activado'}`);
      await cargarProductos();
    } catch (error) {
      toast.error('No se pudo cambiar el estado del producto');
    }
  };

  const eliminarProducto = async (producto) => {
    const ok = window.confirm(`¿Eliminar el producto "${producto.nombre}"? Esta acción no se puede deshacer.`);
    if (!ok) return;

    try {
      await productosService.delete(producto.id);
      toast.success('Producto eliminado');
      if (editingId === producto.id) {
        cancelarEdicion();
      }
      await cargarProductos();
    } catch (error) {
      toast.error('No se pudo eliminar el producto');
    }
  };

  const buscarPorCodigo = async () => {
    if (!codigoBusqueda.trim()) {
      toast.warning('Escanea o escribe un código de barras');
      return;
    }

    try {
      const payload = await productosService.getAll({ search: codigoBusqueda.trim() });
      const encontrados = extractRows(payload);
      const exacto = encontrados.find((p) => p.codigo_barras === codigoBusqueda.trim());
      const producto = exacto || encontrados[0] || null;
      setProductoEncontrado(producto);
      if (!producto) {
        toast.info('No se encontró producto con ese código');
      }
    } catch (error) {
      toast.error('Error buscando por código de barras');
      setProductoEncontrado(null);
    }
  };

  const totalInventario = useMemo(
    () => productos.reduce((acc, p) => acc + Number(p.precio_compra || 0) * Number(p.stock || 0), 0),
    [productos]
  );

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Inventario de Productos</h1>
          <p className="text-gray-600 mt-1">Gestión por código de barras, costos y comisiones</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarProductos} disabled={loading}>
            <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          <button
            className="btn-primary inline-flex items-center gap-2"
            onClick={() => {
              setEditingId(null);
              setForm(INITIAL_FORM);
              setShowForm(true);
            }}
          >
            <FiPlus /> Nuevo producto
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="card-header">Búsqueda por lector de código de barras</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            className="input-field md:col-span-3"
            placeholder="Escanea o ingresa código de barras"
            value={codigoBusqueda}
            onChange={(e) => setCodigoBusqueda(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                buscarPorCodigo();
              }
            }}
          />
          <button className="btn-primary inline-flex items-center justify-center gap-2" onClick={buscarPorCodigo}>
            <FiSearch /> Buscar
          </button>
        </div>

        {productoEncontrado && (
          <div className="mt-4 rounded-lg border border-green-200 bg-green-50 p-4">
            <p className="font-semibold text-green-900">Producto encontrado: {productoEncontrado.nombre}</p>
            <p className="text-sm text-green-800 mt-1">
              Marca: {productoEncontrado.marca || '-'} | Presentación: {productoEncontrado.presentacion || '-'} | Stock: {productoEncontrado.stock}
            </p>
          </div>
        )}
      </div>

      <ModalForm
        isOpen={showForm}
        onClose={cancelarEdicion}
        title={editingId ? 'Editar producto' : 'Registrar producto'}
        subtitle="Inventario, costos y comisiones"
        size="xl"
      >
      <form className="grid grid-cols-1 md:grid-cols-3 gap-3" onSubmit={guardarProducto}>
        <div className="md:col-span-3 flex items-center justify-between gap-3">
          <h2 className="card-header mb-0">{editingId ? 'Editar producto' : 'Registrar producto en inventario'}</h2>
          {editingId && (
            <button type="button" className="btn-secondary" onClick={cancelarEdicion}>
              Cancelar edición
            </button>
          )}
        </div>
        <input className="input-field" placeholder="Código de barras" value={form.codigo_barras} onChange={(e) => setForm((p) => ({ ...p, codigo_barras: e.target.value }))} />
        <input className="input-field" placeholder="Nombre" value={form.nombre} onChange={(e) => setForm((p) => ({ ...p, nombre: e.target.value }))} />
        <input className="input-field" placeholder="Marca" value={form.marca} onChange={(e) => setForm((p) => ({ ...p, marca: e.target.value }))} />
        <input className="input-field" placeholder="Presentación" value={form.presentacion} onChange={(e) => setForm((p) => ({ ...p, presentacion: e.target.value }))} />
        <input className="input-field" type="number" min="0" step="0.01" placeholder="Valor de compra" value={form.precio_compra} onChange={(e) => setForm((p) => ({ ...p, precio_compra: e.target.value }))} />
        <input className="input-field" type="number" min="0" step="0.01" placeholder="Valor de venta" value={form.precio_venta} onChange={(e) => setForm((p) => ({ ...p, precio_venta: e.target.value }))} />
        <input className="input-field" type="number" min="0" step="0.01" placeholder="Comisión estilista (%)" value={form.comision_estilista} onChange={(e) => setForm((p) => ({ ...p, comision_estilista: e.target.value }))} />
        <input className="input-field" type="number" min="0" placeholder="Stock" value={form.stock} onChange={(e) => setForm((p) => ({ ...p, stock: e.target.value }))} />
        <input className="input-field" type="number" min="0" placeholder="Stock mínimo" value={form.stock_minimo} onChange={(e) => setForm((p) => ({ ...p, stock_minimo: e.target.value }))} />
        <button className="btn-primary md:col-span-3" type="submit" disabled={saving}>
          {saving ? 'Guardando...' : editingId ? 'Actualizar producto' : 'Guardar producto'}
        </button>
      </form>
      </ModalForm>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="card-header mb-0">Listado de inventario</h2>
          <span className="text-sm text-gray-600">Valor inventario compra: ${totalInventario.toFixed(2)}</span>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-gray-900"></div>
          </div>
        )}

        {!loading && productos.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-800">Sin productos en inventario</h2>
            <p className="text-gray-600 mt-1">Registra el primer producto con el formulario superior.</p>
          </div>
        )}

        {!loading && productos.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Código</th>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Marca</th>
                  <th className="px-6 py-3 text-left">Presentación</th>
                  <th className="px-6 py-3 text-left">Compra</th>
                  <th className="px-6 py-3 text-left">Venta</th>
                  <th className="px-6 py-3 text-left">Comisión %</th>
                  <th className="px-6 py-3 text-left">Stock</th>
                  <th className="px-6 py-3 text-left">Estado</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {productos.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="table-cell">{p.codigo_barras || '-'}</td>
                    <td className="table-cell font-medium">{p.nombre}</td>
                    <td className="table-cell">{p.marca || '-'}</td>
                    <td className="table-cell">{p.presentacion || '-'}</td>
                    <td className="table-cell">${Number(p.precio_compra || 0).toFixed(2)}</td>
                    <td className="table-cell">${Number(p.precio_venta || 0).toFixed(2)}</td>
                    <td className="table-cell">{Number(p.comision_estilista || 0).toFixed(2)}%</td>
                    <td className="table-cell">{p.stock}</td>
                    <td className="table-cell">
                      {p.activo ? (
                        <span className="px-2 py-1 rounded-full text-xs bg-green-100 text-green-800">Activo</span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-xs bg-gray-200 text-gray-700">Inactivo</span>
                      )}
                    </td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => iniciarEdicion(p)}>
                          <FiEdit2 size={14} /> Editar
                        </button>
                        <button className="btn-secondary !px-3 !py-2" onClick={() => cambiarEstado(p)}>
                          {p.activo ? 'Desactivar' : 'Activar'}
                        </button>
                        <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarProducto(p)}>
                          <FiTrash2 size={14} /> Eliminar
                        </button>
                      </div>
                    </td>
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

export default Productos;
