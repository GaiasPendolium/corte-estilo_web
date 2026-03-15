import { useEffect, useMemo, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { productosService, serviciosService } from '../services/api';
import ModalForm from '../components/ModalForm';
import useAuthStore from '../store/authStore';
import { canManageCatalog } from '../utils/roles';

const INITIAL_FORM = {
  codigo_barras: '',
  nombre: '',
  descripcion: '',
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
  const { user } = useAuthStore();
  const puedeEditar = canManageCatalog(user);
  const [modoVista, setModoVista] = useState('inventario');
  const [productos, setProductos] = useState([]);
  const [serviciosCatalogo, setServiciosCatalogo] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [codigoBusqueda, setCodigoBusqueda] = useState('');
  const [sugerenciasProducto, setSugerenciasProducto] = useState([]);
  const [productoEncontrado, setProductoEncontrado] = useState(null);
  const [showServicioForm, setShowServicioForm] = useState(false);
  const [servicioEditingId, setServicioEditingId] = useState(null);
  const [servicioForm, setServicioForm] = useState({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
  const [filtroServicio, setFiltroServicio] = useState('');
  const [adicionales, setAdicionales] = useState({ shampoo: '4000', guantes: '1500' });

  const cargarProductos = async () => {
    try {
      setLoading(true);
      const [payloadProductos, payloadServicios] = await Promise.all([
        productosService.getAll(),
        serviciosService.getAll(),
      ]);
      setProductos(extractRows(payloadProductos));
      setServiciosCatalogo(extractRows(payloadServicios));
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

  useEffect(() => {
    const q = codigoBusqueda.trim().toLowerCase();
    if (!q) {
      setSugerenciasProducto([]);
      return;
    }
    setSugerenciasProducto(
      productos
        .filter(
          (p) =>
            (p.descripcion || '').toLowerCase().includes(q) ||
            (p.nombre || '').toLowerCase().includes(q) ||
            String(p.codigo_barras || '').toLowerCase().includes(q)
        )
        .slice(0, 8)
    );
  }, [codigoBusqueda, productos]);

  useEffect(() => {
    const shampoo = serviciosCatalogo.find((s) => (s.nombre || '').toLowerCase() === 'adicional shampoo');
    const guantes = serviciosCatalogo.find((s) => (s.nombre || '').toLowerCase() === 'adicional guantes');
    setAdicionales({
      shampoo: String(shampoo?.precio ?? 4000),
      guantes: String(guantes?.precio ?? 1500),
    });
  }, [serviciosCatalogo]);

  const guardarProducto = async (e) => {
    e.preventDefault();
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar inventario');
      return;
    }
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
        descripcion: form.descripcion.trim() || null,
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
      descripcion: producto.descripcion || '',
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
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar inventario');
      return;
    }
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
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar inventario');
      return;
    }
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

  const seleccionarProductoSugerido = (producto) => {
    setProductoEncontrado(producto);
    setCodigoBusqueda(producto.codigo_barras || producto.nombre || '');
    setSugerenciasProducto([]);
  };

  const totalInventario = useMemo(
    () => productos.reduce((acc, p) => acc + Number(p.precio_compra || 0) * Number(p.stock || 0), 0),
    [productos]
  );

  // Filtra el listado principal cuando hay texto en el buscador (descripción + nombre + código + marca)
  const productosFiltrados = useMemo(() => {
    const q = codigoBusqueda.trim().toLowerCase();
    if (!q) return productos;
    return productos.filter(
      (p) =>
        (p.descripcion || '').toLowerCase().includes(q) ||
        (p.nombre || '').toLowerCase().includes(q) ||
        String(p.codigo_barras || '').toLowerCase().includes(q) ||
        (p.marca || '').toLowerCase().includes(q)
    );
  }, [codigoBusqueda, productos]);

  const guardarServicioCatalogo = async (e) => {
    e.preventDefault();
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar servicios');
      return;
    }
    if (!servicioForm.nombre.trim() || !servicioForm.precio) {
      toast.warning('Nombre y precio son obligatorios');
      return;
    }

    try {
      const payload = {
        nombre: servicioForm.nombre.trim(),
        descripcion: servicioForm.descripcion.trim() || null,
        precio: Number(servicioForm.precio),
        duracion_minutos: servicioForm.duracion_minutos ? Number(servicioForm.duracion_minutos) : null,
        activo: true,
      };
      if (servicioEditingId) {
        await serviciosService.update(servicioEditingId, payload);
        toast.success('Servicio actualizado');
      } else {
        await serviciosService.create(payload);
        toast.success('Servicio creado');
      }
      setShowServicioForm(false);
      setServicioEditingId(null);
      setServicioForm({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
      await cargarProductos();
    } catch (error) {
      toast.error('No se pudo guardar el servicio');
    }
  };

  const editarServicioCatalogo = (servicio) => {
    setServicioEditingId(servicio.id);
    setServicioForm({
      nombre: servicio.nombre || '',
      descripcion: servicio.descripcion || '',
      precio: String(servicio.precio || ''),
      duracion_minutos: String(servicio.duracion_minutos || ''),
    });
    setShowServicioForm(true);
  };

  const eliminarServicioCatalogo = async (servicio) => {
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar servicios');
      return;
    }
    const ok = window.confirm(`¿Eliminar el servicio "${servicio.nombre}"?`);
    if (!ok) return;

    try {
      await serviciosService.delete(servicio.id);
      toast.success('Servicio eliminado');
      await cargarProductos();
    } catch (error) {
      toast.error('No se pudo eliminar el servicio');
    }
  };

  const guardarAdicionalesRapidos = async () => {
    if (!puedeEditar) {
      toast.warning('Solo administrador o gerente puede modificar servicios');
      return;
    }

    const upsert = async (nombre, precio) => {
      const existente = serviciosCatalogo.find((s) => (s.nombre || '').toLowerCase() === nombre.toLowerCase());
      const payload = {
        nombre,
        descripcion: 'Configuración de adicional rápido para operación diaria',
        precio: Number(precio || 0),
        duracion_minutos: null,
        activo: true,
      };
      if (existente) {
        await serviciosService.update(existente.id, payload);
      } else {
        await serviciosService.create(payload);
      }
    };

    try {
      await upsert('Adicional Shampoo', adicionales.shampoo);
      await upsert('Adicional Guantes', adicionales.guantes);
      toast.success('Valores de adicionales actualizados');
      await cargarProductos();
    } catch (error) {
      toast.error('No se pudieron actualizar los adicionales');
    }
  };

  const serviciosFiltrados = useMemo(() => {
    const q = filtroServicio.trim().toLowerCase();
    if (!q) return serviciosCatalogo;
    return serviciosCatalogo.filter((s) => (s.nombre || '').toLowerCase().includes(q));
  }, [filtroServicio, serviciosCatalogo]);

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Inventario y Servicio</h1>
          <p className="text-gray-600 mt-1">Solo administrador o gerente pueden editar y eliminar</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarProductos} disabled={loading}>
            <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          {modoVista === 'inventario' && (
            <button
              className="btn-primary inline-flex items-center gap-2"
              onClick={() => {
                setEditingId(null);
                setForm(INITIAL_FORM);
                setShowForm(true);
              }}
              disabled={!puedeEditar}
            >
              <FiPlus /> Nuevo producto
            </button>
          )}
        </div>
      </div>

      <div className="card p-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button className={modoVista === 'inventario' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('inventario')}>
            Inventario
          </button>
          <button
            className={modoVista === 'servicios' ? 'btn-primary' : 'btn-secondary'}
            onClick={() => {
              setModoVista('servicios');
              if (!showServicioForm) {
                setServicioEditingId(null);
                setServicioForm({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
              }
            }}
          >
            Servicios
          </button>
        </div>
      </div>

      {modoVista === 'inventario' && (
      <>

      <div className="card">
        <h2 className="card-header">Búsqueda por lector de código de barras</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 relative">
          <input
            className="input-field md:col-span-3"
            placeholder="Escanea o escribe código/nombre"
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

          {sugerenciasProducto.length > 0 && (
            <div className="md:col-span-4 rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
              {sugerenciasProducto.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="w-full text-left px-3 py-2 hover:bg-gray-50"
                  onClick={() => seleccionarProductoSugerido(p)}
                >
                  {p.descripcion ? `${p.descripcion} - ${p.nombre}` : p.nombre} — {p.codigo_barras || 'sin código'}
                </button>
              ))}
            </div>
          )}
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

        <div>
          <label className="block text-sm text-gray-600 mb-1">Código de barras</label>
          <input className="input-field" placeholder="Ej: 7701234567890" value={form.codigo_barras} onChange={(e) => setForm((p) => ({ ...p, codigo_barras: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Nombre <span className="text-red-500">*</span></label>
          <input className="input-field" placeholder="Nombre del producto" value={form.nombre} onChange={(e) => setForm((p) => ({ ...p, nombre: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Marca</label>
          <input className="input-field" placeholder="Ej: L'Oréal" value={form.marca} onChange={(e) => setForm((p) => ({ ...p, marca: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Presentación</label>
          <input className="input-field" placeholder="Ej: 500ml, 1kg" value={form.presentacion} onChange={(e) => setForm((p) => ({ ...p, presentacion: e.target.value }))} />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm text-gray-600 mb-1">Descripción <span className="text-xs text-gray-400">(aparece antes del nombre en búsquedas y listado)</span></label>
          <textarea className="input-field" rows={2} placeholder="Ej: Shampoo hidratante para cabello seco" value={form.descripcion} onChange={(e) => setForm((p) => ({ ...p, descripcion: e.target.value }))} />
        </div>

        <div className="md:col-span-3 border-t pt-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Precios y comisiones</p>
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Valor de compra</label>
          <input className="input-field" type="number" min="0" step="0.01" placeholder="0.00" value={form.precio_compra} onChange={(e) => setForm((p) => ({ ...p, precio_compra: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Valor de venta <span className="text-red-500">*</span></label>
          <input className="input-field" type="number" min="0" step="0.01" placeholder="0.00" value={form.precio_venta} onChange={(e) => setForm((p) => ({ ...p, precio_venta: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Comisión estilista (%)</label>
          <input className="input-field" type="number" min="0" step="0.01" placeholder="0" value={form.comision_estilista} onChange={(e) => setForm((p) => ({ ...p, comision_estilista: e.target.value }))} />
        </div>

        <div className="md:col-span-3 border-t pt-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Stock</p>
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Stock actual</label>
          <input className="input-field" type="number" min="0" placeholder="0" value={form.stock} onChange={(e) => setForm((p) => ({ ...p, stock: e.target.value }))} />
        </div>
        <div>
          <label className="block text-sm text-gray-600 mb-1">Stock mínimo <span className="text-xs text-gray-400">(alerta de reposición)</span></label>
          <input className="input-field" type="number" min="0" placeholder="5" value={form.stock_minimo} onChange={(e) => setForm((p) => ({ ...p, stock_minimo: e.target.value }))} />
        </div>

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

        {!loading && productosFiltrados.length === 0 && productos.length > 0 && (
          <p className="text-gray-500 text-sm">Ningún producto coincide con la búsqueda.</p>
        )}

        {!loading && productosFiltrados.length > 0 && (
          <div className="overflow-x-auto" style={{ maxHeight: 'calc(100vh - 22rem)', overflowY: 'auto' }}>
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
                {productosFiltrados.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="table-cell">{p.codigo_barras || '-'}</td>
                    <td className="table-cell font-medium">{p.descripcion ? `${p.descripcion} - ${p.nombre}` : p.nombre}</td>
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
                        {puedeEditar ? (
                          <>
                            <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => iniciarEdicion(p)}>
                              <FiEdit2 size={14} /> Editar
                            </button>
                            <button className="btn-secondary !px-3 !py-2" onClick={() => cambiarEstado(p)}>
                              {p.activo ? 'Desactivar' : 'Activar'}
                            </button>
                            <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarProducto(p)}>
                              <FiTrash2 size={14} /> Eliminar
                            </button>
                          </>
                        ) : (
                          <span className="text-sm text-gray-500">Solo visualización</span>
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
      <>
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="card-header mb-0">Catálogo de servicios</h2>
          {puedeEditar && (
            <button
              className="btn-primary inline-flex items-center gap-2"
              onClick={() => {
                setServicioEditingId(null);
                setServicioForm({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
                setShowServicioForm(true);
              }}
            >
              <FiPlus /> Nuevo servicio
            </button>
          )}
        </div>

        {!puedeEditar && <p className="text-gray-600 mb-3">Perfil con acceso de solo lectura para servicios.</p>}

        <div className="mb-4 grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            className="input-field md:col-span-2"
            placeholder="Buscar servicio por nombre"
            value={filtroServicio}
            onChange={(e) => setFiltroServicio(e.target.value)}
          />
          <button className="btn-secondary" onClick={() => setFiltroServicio('')}>Limpiar búsqueda</button>
        </div>

        <div className="mb-5 rounded-lg border border-blue-100 bg-blue-50 p-4">
          <h3 className="font-semibold text-blue-900 mb-2">Adicionales usados en operación diaria</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              className="input-field"
              type="number"
              min="0"
              step="0.01"
              value={adicionales.shampoo}
              onChange={(e) => setAdicionales((p) => ({ ...p, shampoo: e.target.value }))}
              placeholder="Valor Shampoo"
              disabled={!puedeEditar}
            />
            <input
              className="input-field"
              type="number"
              min="0"
              step="0.01"
              value={adicionales.guantes}
              onChange={(e) => setAdicionales((p) => ({ ...p, guantes: e.target.value }))}
              placeholder="Valor Guantes"
              disabled={!puedeEditar}
            />
            <button className="btn-primary" onClick={guardarAdicionalesRapidos} disabled={!puedeEditar}>Guardar adicionales</button>
          </div>
        </div>

        {serviciosCatalogo.length === 0 && <p className="text-gray-600">No hay servicios registrados.</p>}

        {serviciosFiltrados.length > 0 && (
          <div className="overflow-x-scroll">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Descripción</th>
                  <th className="px-6 py-3 text-left">Precio</th>
                  <th className="px-6 py-3 text-left">Duración</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosFiltrados.map((servicio) => (
                  <tr key={servicio.id} className="hover:bg-gray-50">
                    <td className="table-cell font-medium">{servicio.nombre}</td>
                    <td className="table-cell">{servicio.descripcion || '-'}</td>
                    <td className="table-cell">${Number(servicio.precio || 0).toFixed(2)}</td>
                    <td className="table-cell">{servicio.duracion_minutos || '-'} min</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        {puedeEditar ? (
                          <>
                            <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => editarServicioCatalogo(servicio)}>
                              <FiEdit2 size={14} /> Editar
                            </button>
                            <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarServicioCatalogo(servicio)}>
                              <FiTrash2 size={14} /> Eliminar
                            </button>
                          </>
                        ) : (
                          <span className="text-sm text-gray-500">Solo visualización</span>
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

      <ModalForm
        isOpen={showServicioForm}
        onClose={() => setShowServicioForm(false)}
        title={servicioEditingId ? 'Editar servicio' : 'Nuevo servicio'}
        subtitle="Catálogo usado para facturación"
        size="md"
      >
        <form className="space-y-3" onSubmit={guardarServicioCatalogo}>
          <input className="input-field" placeholder="Nombre" value={servicioForm.nombre} onChange={(e) => setServicioForm((p) => ({ ...p, nombre: e.target.value }))} />
          <input className="input-field" placeholder="Descripción" value={servicioForm.descripcion} onChange={(e) => setServicioForm((p) => ({ ...p, descripcion: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <input className="input-field" type="number" min="0" step="0.01" placeholder="Precio" value={servicioForm.precio} onChange={(e) => setServicioForm((p) => ({ ...p, precio: e.target.value }))} />
            <input className="input-field" type="number" min="1" placeholder="Duración (min)" value={servicioForm.duracion_minutos} onChange={(e) => setServicioForm((p) => ({ ...p, duracion_minutos: e.target.value }))} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" type="submit">{servicioEditingId ? 'Actualizar' : 'Crear servicio'}</button>
            <button type="button" className="btn-secondary" onClick={() => setShowServicioForm(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>
      </>
      )}
    </div>
  );
};

export default Productos;
