import { useEffect, useMemo, useState } from 'react';
import { FiCopy, FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2, FiEye, FiX } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { estilistasService, productosService, serviciosRealizadosService, ventasService } from '../services/api';
import ModalForm from '../components/ModalForm';
import useAuthStore from '../store/authStore';
import { qzTrayService } from '../services/printing/qzTrayService';
import { ticketPrintService } from '../services/printing/ticketPrintService';
import { customerDisplayService } from '../services/customerDisplayService';
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

const normalizeSearchText = (value) =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const productMatchesSearch = (producto, query) => {
  const q = normalizeSearchText(query);
  if (!q) return true;

  const index = normalizeSearchText([
    producto.codigo_barras,
    producto.marca,
    producto.descripcion,
    producto.nombre,
    producto.presentacion,
  ].filter(Boolean).join(' '));

  if (index.includes(q)) return true;
  const terms = q.split(' ').filter(Boolean);
  return terms.every((term) => index.includes(term));
};

const formatProductSearchLabel = (producto) => {
  return [producto.marca, producto.descripcion, producto.nombre].filter(Boolean).join(' - ') || producto.nombre || 'Producto';
};

const Ventas = () => {
  const { user } = useAuthStore();
  const puedeEditarFacturas = canManageInvoices(user);
  const [modoVista, setModoVista] = useState('ventas');
  const [fechaInicio, setFechaInicio] = useState('');
  const [fechaFin, setFechaFin] = useState('');
  const [filtroUsuario, setFiltroUsuario] = useState('');
  const [filtroEmpleado, setFiltroEmpleado] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editandoId, setEditandoId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [showServicioForm, setShowServicioForm] = useState(false);
  const [ventaVisualizar, setVentaVisualizar] = useState(null);
  const [servicioVisualizar, setServicioVisualizar] = useState(null);
  const [showVisualizarFactura, setShowVisualizarFactura] = useState(false);

  const [productos, setProductos] = useState([]);
  const [estilistas, setEstilistas] = useState([]);
  const [ventas, setVentas] = useState([]);
  const [serviciosFinalizados, setServiciosFinalizados] = useState([]);

  const [busquedaProducto, setBusquedaProducto] = useState('');
  const [sugerenciasProducto, setSugerenciasProducto] = useState([]);
  const [productoSeleccionado, setProductoSeleccionado] = useState(null);
  const [servicioEditando, setServicioEditando] = useState(null);

  const [form, setForm] = useState({
    cliente_nombre: '',
    estilista: '',
    medio_pago: 'efectivo',
    cantidad: '1',
    precio_unitario: '',
  });

  const [servicioForm, setServicioForm] = useState({
    precio_cobrado: '',
    medio_pago: 'efectivo',
    notas: '',
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

  useEffect(() => {
    const q = busquedaProducto.trim().toLowerCase();
    if (!q) {
      setSugerenciasProducto([]);
      return;
    }
    setSugerenciasProducto(
      productos
        .filter((p) => productMatchesSearch(p, q))
        .slice(0, 8)
    );
  }, [busquedaProducto, productos]);

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

  const seleccionarProductoSugerido = (producto) => {
    setProductoSeleccionado(producto);
    setBusquedaProducto(formatProductSearchLabel(producto));
    setSugerenciasProducto([]);
    if (!editandoId) {
      setForm((prev) => ({ ...prev, precio_unitario: String(producto.precio_venta || '') }));
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
        const ventaCreada = await ventasService.create(payload);
        customerDisplayService.publishProductSale(ventaCreada);
        toast.success('Factura de producto creada');

        try {
          await ticketPrintService.printProductSaleAndOpenDrawer(ventaCreada);
          toast.success('Ticket impreso y caja abierta');
        } catch (printError) {
          toast.error(printError.message || 'La venta se guardo, pero no se pudo imprimir el ticket');
        }
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
    if ((venta.items || []).length > 1) {
      toast.info('Edita los productos de esta transacción desde Operación diaria.');
      return;
    }
    const ventaBase = (venta.items && venta.items[0]) ? venta.items[0] : venta;
    setEditandoId(venta.id);
    setShowForm(true);
    const producto = productos.find((p) => p.id === ventaBase.producto) || null;
    setProductoSeleccionado(producto);
    setBusquedaProducto(producto ? formatProductSearchLabel(producto) : '');
    setForm({
      cliente_nombre: ventaBase.cliente_nombre || '',
      estilista: ventaBase.estilista ? String(ventaBase.estilista) : '',
      medio_pago: ventaBase.medio_pago || 'efectivo',
      cantidad: String(ventaBase.cantidad || 1),
      precio_unitario: String(ventaBase.precio_unitario || ''),
    });
  };

  const eliminarVenta = async (venta) => {
    if ((venta.items || []).length > 1) {
      toast.info('Por ahora elimina cada ítem de la factura desde el detalle o usa Operación diaria.');
      return;
    }
    const ventaBase = (venta.items && venta.items[0]) ? venta.items[0] : venta;
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden eliminar facturas');
      return;
    }
    const ok = window.confirm(`¿Eliminar la factura ${ventaBase.numero_factura || ventaBase.id}?`);
    if (!ok) return;

    try {
      await ventasService.delete(ventaBase.id);
      toast.success('Factura eliminada');
      if (editandoId === ventaBase.id) limpiarFormulario();
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

  const reimprimirVenta = async (venta) => {
    const ventaBase = (venta.items && venta.items[0]) ? venta.items[0] : venta;
    try {
      await ticketPrintService.reprintProductSale(ventaBase);
      toast.success('Ticket reenviado a impresora');
    } catch (error) {
      toast.error(error.message || 'No se pudo reimprimir el ticket');
    }
  };

  const reimprimirServicio = async (servicio) => {
    try {
      await ticketPrintService.reprintServiceSale(servicio);
      toast.success('Ticket reenviado a impresora');
    } catch (error) {
      toast.error(error.message || 'No se pudo reimprimir el ticket');
    }
  };

  const abrirCaja = async () => {
    try {
      await qzTrayService.openDrawer();
      toast.success('Comando de apertura enviado al cajon');
    } catch (error) {
      toast.error(error.message || 'No se pudo abrir el cajon SAT');
    }
  };

  const visualizarVenta = (venta) => {
    setVentaVisualizar(venta);
    setServicioVisualizar(null);
    setShowVisualizarFactura(true);
  };

  const visualizarServicio = (servicio) => {
    setServicioVisualizar(servicio);
    setVentaVisualizar(null);
    setShowVisualizarFactura(true);
  };

  const cerrarVisualizacion = () => {
    setShowVisualizarFactura(false);
    setVentaVisualizar(null);
    setServicioVisualizar(null);
  };

  const editarServicio = (servicio) => {
    setServicioEditando(servicio);
    setServicioForm({
      precio_cobrado: String(servicio.precio_cobrado || ''),
      medio_pago: servicio.medio_pago || 'efectivo',
      notas: servicio.notas || '',
    });
    setShowServicioForm(true);
  };

  const guardarServicioEditado = async (e) => {
    e.preventDefault();
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden editar facturas de servicio');
      return;
    }
    if (!servicioEditando) return;

    try {
      setSaving(true);
      await serviciosRealizadosService.update(servicioEditando.id, {
        estado: 'finalizado',
        precio_cobrado: Number(servicioForm.precio_cobrado || 0),
        medio_pago: servicioForm.medio_pago,
        notas: servicioForm.notas || null,
      });
      toast.success('Factura de servicio actualizada');
      setShowServicioForm(false);
      setServicioEditando(null);
      await cargarDatos();
    } catch (error) {
      toast.error('No se pudo actualizar la factura de servicio');
    } finally {
      setSaving(false);
    }
  };

  const eliminarServicio = async (servicio) => {
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden eliminar facturas de servicio');
      return;
    }
    const ok = window.confirm(`¿Eliminar la factura de servicio ${servicio.numero_factura || servicio.id}?`);
    if (!ok) return;

    try {
      await serviciosRealizadosService.delete(servicio.id);
      toast.success('Factura de servicio eliminada');
      await cargarDatos();
    } catch (error) {
      toast.error('No se pudo eliminar la factura de servicio');
    }
  };

  const ventasFiltradas = useMemo(() => {
    const qUsuario = filtroUsuario.trim().toLowerCase();
    const qEmpleado = filtroEmpleado.trim().toLowerCase();
    return ventas.filter((v) => {
      const usuario = String(v.usuario_nombre || '').toLowerCase();
      const empleado = String(v.estilista_nombre || '').toLowerCase();
      const okUsuario = !qUsuario || usuario.includes(qUsuario);
      const okEmpleado = !qEmpleado || empleado.includes(qEmpleado);
      return okUsuario && okEmpleado;
    });
  }, [ventas, filtroUsuario, filtroEmpleado]);

  const ventasAgrupadas = useMemo(() => {
    const grupos = new Map();
    for (const v of ventasFiltradas) {
      const key = v.numero_factura || `SIN-${v.id}`;
      const existente = grupos.get(key);
      if (!existente) {
        grupos.set(key, {
          id: v.id,
          numero_factura: v.numero_factura,
          fecha_hora: v.fecha_hora,
          cliente_nombre: v.cliente_nombre,
          estilista_nombre: v.estilista_nombre,
          usuario_nombre: v.usuario_nombre,
          medio_pago: v.medio_pago,
          factura_texto: v.factura_texto,
          total: Number(v.total || 0),
          cantidad_total: Number(v.cantidad || 0),
          items: [v],
        });
        continue;
      }

      existente.total += Number(v.total || 0);
      existente.cantidad_total += Number(v.cantidad || 0);
      existente.items.push(v);
      if (String(v.fecha_hora || '') > String(existente.fecha_hora || '')) {
        existente.fecha_hora = v.fecha_hora;
      }
      if (!existente.factura_texto && v.factura_texto) {
        existente.factura_texto = v.factura_texto;
      }
      if (!existente.medio_pago && v.medio_pago) {
        existente.medio_pago = v.medio_pago;
      }
      if (existente.medio_pago && v.medio_pago && existente.medio_pago !== v.medio_pago) {
        existente.medio_pago = 'mixto';
      }
    }

    return Array.from(grupos.values()).sort((a, b) => String(b.fecha_hora || '').localeCompare(String(a.fecha_hora || '')));
  }, [ventasFiltradas]);

  const serviciosFiltrados = useMemo(() => {
    const qUsuario = filtroUsuario.trim().toLowerCase();
    const qEmpleado = filtroEmpleado.trim().toLowerCase();
    return serviciosFinalizados.filter((s) => {
      const usuario = String(s.usuario_nombre || '').toLowerCase();
      const empleado = String(s.estilista_nombre || '').toLowerCase();
      const okUsuario = !qUsuario || usuario.includes(qUsuario);
      const okEmpleado = !qEmpleado || empleado.includes(qEmpleado);
      return okUsuario && okEmpleado;
    });
  }, [serviciosFinalizados, filtroUsuario, filtroEmpleado]);

  const totalVentas = useMemo(() => ventasFiltradas.reduce((acc, v) => acc + Number(v.total || 0), 0), [ventasFiltradas]);
  const ticketPromedio = useMemo(() => (ventasAgrupadas.length ? totalVentas / ventasAgrupadas.length : 0), [totalVentas, ventasAgrupadas.length]);
  const totalServicios = useMemo(
    () => serviciosFiltrados.reduce((acc, s) => acc + (Number(s.precio_cobrado || 0) + Number(s.valor_adicionales || 0)), 0),
    [serviciosFiltrados]
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
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <input className="input-field" type="date" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
          <input className="input-field" type="date" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
          <input
            className="input-field"
            placeholder="Filtrar por usuario que facturó"
            value={filtroUsuario}
            onChange={(e) => setFiltroUsuario(e.target.value)}
          />
          <input
            className="input-field"
            placeholder="Filtrar por empleado"
            value={filtroEmpleado}
            onChange={(e) => setFiltroEmpleado(e.target.value)}
          />
          <button
            className="btn-secondary"
            onClick={() => {
              setFechaInicio('');
              setFechaFin('');
              setFiltroUsuario('');
              setFiltroEmpleado('');
            }}
          >
            Limpiar filtros
          </button>
          <div className="text-sm text-gray-600 flex items-center">
            Total resultados: {modoVista === 'ventas' ? ventasAgrupadas.length : serviciosFiltrados.length}
          </div>
        </div>
      </div>

      {/* Modal visualizar factura */}
      {showVisualizarFactura && (ventaVisualizar || servicioVisualizar) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <h2 className="text-xl font-bold text-gray-900">
                {ventaVisualizar ? 'Factura de Producto' : 'Factura de Servicio'}
              </h2>
              <button onClick={cerrarVisualizacion} className="text-gray-400 hover:text-gray-600">
                <FiX size={24} />
              </button>
            </div>

            <div className="px-6 py-4 space-y-6">
              {ventaVisualizar && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-gray-600">Número de factura</p>
                      <p className="font-bold text-gray-900">{ventaVisualizar.numero_factura || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Fecha</p>
                      <p className="font-bold text-gray-900">{String(ventaVisualizar.fecha_hora || '').slice(0, 19).replace('T', ' ')}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Cliente</p>
                      <p className="font-bold text-gray-900">{ventaVisualizar.cliente_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Productos</p>
                      <p className="font-bold text-gray-900">{(ventaVisualizar.items || []).length || 1}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Estilista</p>
                      <p className="font-bold text-gray-900">{ventaVisualizar.estilista_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Usuario que facturó</p>
                      <p className="font-bold text-gray-900">{ventaVisualizar.usuario_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Medio de pago</p>
                      <p className="font-bold text-gray-900 capitalize">{ventaVisualizar.medio_pago || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Cantidad total</p>
                      <p className="font-bold text-gray-900">{ventaVisualizar.cantidad_total || ventaVisualizar.cantidad}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Ítems</p>
                      <p className="font-bold text-gray-900">{(ventaVisualizar.items || []).map((x) => x.producto_nombre).join(', ') || ventaVisualizar.producto_nombre}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Total</p>
                      <p className="font-bold text-lg text-green-600">${Number(ventaVisualizar.total || 0).toFixed(2)}</p>
                    </div>
                  </div>

                  {(ventaVisualizar.items || []).length > 1 && (
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Detalle de productos</p>
                      <div className="rounded border border-gray-200 overflow-hidden">
                        <table className="min-w-full text-sm">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-3 py-2 text-left">Producto</th>
                              <th className="px-3 py-2 text-left">Cantidad</th>
                              <th className="px-3 py-2 text-left">Unitario</th>
                              <th className="px-3 py-2 text-left">Total</th>
                            </tr>
                          </thead>
                          <tbody>
                            {ventaVisualizar.items.map((item) => (
                              <tr key={item.id} className="border-t border-gray-200">
                                <td className="px-3 py-2">{item.producto_nombre}</td>
                                <td className="px-3 py-2">{item.cantidad}</td>
                                <td className="px-3 py-2">${Number(item.precio_unitario || 0).toFixed(2)}</td>
                                <td className="px-3 py-2">${Number(item.total || 0).toFixed(2)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {ventaVisualizar.factura_texto && (
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Factura para compartir:</p>
                      <div className="bg-gray-50 rounded border border-gray-200 p-3 text-sm whitespace-pre-wrap font-mono text-gray-700 max-h-64 overflow-y-auto">
                        <div className="flex justify-center mb-3 pb-3 border-b border-gray-300">
                          <img src="/corte_estilo_logo.png" alt="Logo" className="h-12 object-contain" />
                        </div>
                        {ventaVisualizar.factura_texto}
                      </div>
                    </div>
                  )}
                </>
              )}

              {servicioVisualizar && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm text-gray-600">Número de factura</p>
                      <p className="font-bold text-gray-900">{servicioVisualizar.numero_factura || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Fecha</p>
                      <p className="font-bold text-gray-900">{String(servicioVisualizar.fecha_hora || '').slice(0, 19).replace('T', ' ')}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Cliente</p>
                      <p className="font-bold text-gray-900">{servicioVisualizar.cliente_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Servicio</p>
                      <p className="font-bold text-gray-900">{servicioVisualizar.servicio_nombre}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Empleado (servicio)</p>
                      <p className="font-bold text-gray-900">{servicioVisualizar.estilista_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Usuario que facturó</p>
                      <p className="font-bold text-gray-900">{servicioVisualizar.usuario_nombre || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Medio de pago</p>
                      <p className="font-bold text-gray-900 capitalize">{servicioVisualizar.medio_pago || '-'}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Valor servicio base</p>
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.precio_cobrado || 0).toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Valor adicionales</p>
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.valor_adicionales || 0).toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Neto del servicio</p>
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.neto_servicio ?? servicioVisualizar.precio_cobrado || 0).toFixed(2)}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-sm text-gray-600">Total cobrado al cliente</p>
                      <p className="font-bold text-lg text-green-600">${(Number(servicioVisualizar.precio_cobrado || 0) + Number(servicioVisualizar.valor_adicionales || 0)).toFixed(2)}</p>
                    </div>
                    {servicioVisualizar.notas && (
                      <div className="col-span-2">
                        <p className="text-sm text-gray-600">Notas</p>
                        <p className="font-bold text-gray-900">{servicioVisualizar.notas}</p>
                      </div>
                    )}
                  </div>

                  {servicioVisualizar.factura_texto && (
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Factura para compartir:</p>
                      <div className="bg-gray-50 rounded border border-gray-200 p-3 text-sm whitespace-pre-wrap font-mono text-gray-700 max-h-64 overflow-y-auto">
                        <div className="flex justify-center mb-3 pb-3 border-b border-gray-300">
                          <img src="/corte_estilo_logo.png" alt="Logo" className="h-12 object-contain" />
                        </div>
                        {servicioVisualizar.factura_texto}
                      </div>
                    </div>
                  )}
                </>
              )}

              <div className="flex gap-2 justify-end border-t border-gray-200 pt-4">
                <button className="btn-secondary" onClick={cerrarVisualizacion}>Cerrar</button>
                <button 
                  className="btn-secondary inline-flex items-center gap-2"
                  onClick={() => copiarTexto(ventaVisualizar?.factura_texto || servicioVisualizar?.factura_texto)}
                >
                  <FiCopy size={16} /> Copiar factura
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
        subtitle="Busca producto por marca, descripción, código o nombre y registra la venta"
        size="xl"
      >
      <form className="grid grid-cols-1 md:grid-cols-4 gap-3" onSubmit={guardarVenta}>
        <h2 className="card-header md:col-span-4">Factura de producto</h2>
        <input
          className="input-field md:col-span-3"
          placeholder="Buscar producto por marca, descripción, código o nombre"
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

        {sugerenciasProducto.length > 0 && (
          <div className="md:col-span-4 rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
            {sugerenciasProducto.map((p) => (
              <button key={p.id} type="button" className="w-full text-left px-3 py-2 hover:bg-gray-50" onClick={() => seleccionarProductoSugerido(p)}>
                {formatProductSearchLabel(p)} - {p.codigo_barras || 'sin código'}
              </button>
            ))}
          </div>
        )}

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
            Producto: <strong>{formatProductSearchLabel(productoSeleccionado)}</strong> | Stock: <strong>{productoSeleccionado.stock}</strong>
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

        {!loading && ventasAgrupadas.length === 0 && <p className="text-gray-600">No hay facturas de productos con los filtros actuales.</p>}

        {!loading && ventasAgrupadas.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Fecha</th>
                  <th className="px-6 py-3 text-left">Detalle</th>
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Estilista</th>
                  <th className="px-6 py-3 text-left">Usuario facturó</th>
                  <th className="px-6 py-3 text-left">Medio pago</th>
                  <th className="px-6 py-3 text-left">Cantidad</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {ventasAgrupadas.map((v) => (
                  <tr key={v.id} className="hover:bg-gray-50">
                    <td className="table-cell">{v.numero_factura || '-'}</td>
                    <td className="table-cell">{String(v.fecha_hora || '').slice(0, 10)}</td>
                    <td className="table-cell">{(v.items || []).length > 1 ? `${v.items.length} productos` : (v.items?.[0]?.producto_nombre || v.producto_nombre || '-')}</td>
                    <td className="table-cell">{v.cliente_nombre || '-'}</td>
                    <td className="table-cell">{v.estilista_nombre || '-'}</td>
                    <td className="table-cell">{v.usuario_nombre || '-'}</td>
                    <td className="table-cell capitalize">{v.medio_pago || '-'}</td>
                    <td className="table-cell">{v.cantidad_total || v.cantidad}</td>
                    <td className="table-cell">${Number(v.total || 0).toFixed(2)}</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => visualizarVenta(v)}>
                          <FiEye size={14} /> Ver
                        </button>
                        {puedeEditarFacturas && (
                          <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => editarVenta(v)}>
                            <FiEdit2 size={14} /> Editar
                          </button>
                        )}
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => copiarTexto(v.factura_texto)}>
                          <FiCopy size={14} /> Copiar
                        </button>
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => reimprimirVenta(v)}>
                          Imprimir
                        </button>
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={abrirCaja}>
                          Abrir caja
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
      <>
      <ModalForm
        isOpen={showServicioForm}
        onClose={() => setShowServicioForm(false)}
        title="Editar factura de servicio"
        subtitle="Ajusta valores de la factura"
        size="md"
      >
        <form className="space-y-3" onSubmit={guardarServicioEditado}>
          <input className="input-field" type="number" min="0" step="0.01" placeholder="Total cobrado" value={servicioForm.precio_cobrado} onChange={(e) => setServicioForm((p) => ({ ...p, precio_cobrado: e.target.value }))} />
          <select className="input-field" value={servicioForm.medio_pago} onChange={(e) => setServicioForm((p) => ({ ...p, medio_pago: e.target.value }))}>
            {MEDIOS_PAGO.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <input className="input-field" placeholder="Notas" value={servicioForm.notas} onChange={(e) => setServicioForm((p) => ({ ...p, notas: e.target.value }))} />
          <div className="flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Guardar cambios</button>
            <button className="btn-secondary" type="button" onClick={() => setShowServicioForm(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <div className="card">
        <h2 className="card-header">Facturas de servicios finalizados</h2>
        {serviciosFiltrados.length === 0 && <p className="text-gray-600">No hay servicios finalizados con los filtros actuales.</p>}
        {serviciosFiltrados.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Fecha</th>
                  <th className="px-6 py-3 text-left">Servicio</th>
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Empleado (servicio)</th>
                  <th className="px-6 py-3 text-left">Usuario facturó</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosFiltrados.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="table-cell">{s.numero_factura || '-'}</td>
                    <td className="table-cell">{String(s.fecha_hora || '').slice(0, 10)}</td>
                    <td className="table-cell">{s.servicio_nombre}</td>
                    <td className="table-cell">{s.cliente_nombre || '-'}</td>
                    <td className="table-cell">{s.estilista_nombre || '-'}</td>
                    <td className="table-cell">{s.usuario_nombre || '-'}</td>
                    <td className="table-cell">${(Number(s.precio_cobrado || 0) + Number(s.valor_adicionales || 0)).toFixed(2)}</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => visualizarServicio(s)}>
                          <FiEye size={14} /> Ver
                        </button>
                        {puedeEditarFacturas && (
                          <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => editarServicio(s)}>
                            <FiEdit2 size={14} /> Editar
                          </button>
                        )}
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => copiarTexto(s.factura_texto)}>
                          <FiCopy size={14} /> Copiar
                        </button>
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => reimprimirServicio(s)}>
                          Imprimir
                        </button>
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={abrirCaja}>
                          Abrir caja
                        </button>
                        {puedeEditarFacturas && (
                          <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarServicio(s)}>
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
    </div>
  );
};

export default Ventas;
