import { useEffect, useMemo, useState } from 'react';
import { FiCopy, FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2, FiEye, FiX } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { estilistasService, productosService, serviciosRealizadosService, ventasService, serviciosService } from '../services/api';
import ModalForm from '../components/ModalForm';
import DraggableSearchKeyboard from '../components/DraggableSearchKeyboard';
import useAuthStore from '../store/authStore';
import { qzTrayService } from '../services/printing/qzTrayService';
import { ticketPrintService } from '../services/printing/ticketPrintService';
import { customerDisplayService } from '../services/customerDisplayService';
import { canManageInvoices } from '../utils/roles';
import { buildThermalTicketPreview } from '../utils/thermalTicketPrint';

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
    producto.id,
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

const getStockEstado = (producto) => {
  const stock = Number(producto?.stock || 0);
  const stockMinimo = Number(producto?.stock_minimo || 0);
  if (stock <= 0) return { key: 'agotado', label: 'Agotado', badgeClass: 'bg-red-100 text-red-700 border-red-200' };
  if (stock <= stockMinimo) return { key: 'por_agotar', label: 'Por agotarse', badgeClass: 'bg-amber-100 text-amber-700 border-amber-200' };
  return { key: 'ok', label: 'Disponible', badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200' };
};

const formatServiceSearchLabel = (servicio) => {
  return [servicio.descripcion, servicio.nombre].filter(Boolean).join(' - ') || servicio.nombre || 'Servicio';
};

const formatCOP = (valor) =>
  Number(valor || 0).toLocaleString('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  });

const formatDateTimeLocalInput = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return String(value).replace(' ', 'T').slice(0, 16);
  }
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const esServicioShampooNombre = (nombre) => String(nombre || '').toLowerCase().includes('shampoo');

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
  const [showInvoiceEditForm, setShowInvoiceEditForm] = useState(false);
  const [tipoFacturaEditando, setTipoFacturaEditando] = useState('venta');
  const [ventaVisualizar, setVentaVisualizar] = useState(null);
  const [servicioVisualizar, setServicioVisualizar] = useState(null);
  const [showVisualizarFactura, setShowVisualizarFactura] = useState(false);

  const previewVentaHtml = useMemo(() => {
    if (!ventaVisualizar) return '';
    return buildThermalTicketPreview({ type: 'venta', data: ventaVisualizar });
  }, [ventaVisualizar]);

  const previewServicioHtml = useMemo(() => {
    if (!servicioVisualizar) return '';
    return buildThermalTicketPreview({ type: 'servicio', data: servicioVisualizar });
  }, [servicioVisualizar]);

  const [productos, setProductos] = useState([]);
  const [serviciosCatalogo, setServiciosCatalogo] = useState([]);
  const [estilistas, setEstilistas] = useState([]);
  const [ventas, setVentas] = useState([]);
  const [serviciosFinalizados, setServiciosFinalizados] = useState([]);

  const [busquedaProducto, setBusquedaProducto] = useState('');
  const [sugerenciasProducto, setSugerenciasProducto] = useState([]);
  const [productoSeleccionado, setProductoSeleccionado] = useState(null);
  const [servicioEditando, setServicioEditando] = useState(null);
  const [searchKeyboard, setSearchKeyboard] = useState({ visible: false, field: '' });

  const [form, setForm] = useState({
    cliente_nombre: '',
    estilista: '',
    medio_pago: 'efectivo',
    cantidad: '1',
    precio_unitario: '',
  });

  const [servicioForm, setServicioForm] = useState({
    servicio: '',
    estilista: '',
    fecha_hora: '',
    precio_cobrado: '',
    medio_pago: 'efectivo',
    tipo_reparto_establecimiento: '',
    valor_reparto_establecimiento: '',
    tiene_adicionales: false,
    adicionales_servicio_items: [],
    adicional_otro_producto: '',
    adicional_otro_cantidad: '1',
    adicional_otro_estilista: '',
    notas: '',
  });
  const [invoiceEditForm, setInvoiceEditForm] = useState({
    numero_factura: '',
    cliente_nombre: '',
    estilista: '',
    fecha_hora: '',
    medio_pago: 'efectivo',
    items: [],
  });

  const cargarDatos = async () => {
    try {
      setLoading(true);
      const paramsFecha = {
        ...(fechaInicio ? { fecha_inicio: fechaInicio } : {}),
        ...(fechaFin ? { fecha_fin: fechaFin } : {}),
      };
      const [productosRes, estilistasRes, ventasRes, serviciosRes, serviciosCatalogoRes] = await Promise.all([
        productosService.getAll(),
        estilistasService.getAll({ activo: true }),
        ventasService.getAll(paramsFecha),
        serviciosRealizadosService.getAll({ estado: 'finalizado', ...paramsFecha }),
        serviciosService.getAll({ activo: true }),
      ]);
      setProductos(extractRows(productosRes));
      setEstilistas(extractRows(estilistasRes));
      setVentas(extractRows(ventasRes));
      setServiciosFinalizados(extractRows(serviciosRes));
      setServiciosCatalogo(extractRows(serviciosCatalogoRes));
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
      } else if (Number(producto.stock || 0) <= 0) {
        toast.warning('Este producto está agotado y no se puede facturar');
        setProductoSeleccionado(null);
        return;
      } else if (!editandoId) {
        setForm((prev) => ({ ...prev, precio_unitario: String(producto.precio_venta || '') }));
      }
    } catch (error) {
      toast.error('Error en búsqueda de producto');
    }
  };

  const seleccionarProductoSugerido = (producto) => {
    if (Number(producto?.stock || 0) <= 0) {
      toast.warning('Este producto está agotado y no se puede seleccionar');
      return;
    }
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
    if (Number(productoSeleccionado.stock || 0) <= 0) {
      toast.warning('El producto está agotado');
      return;
    }
    if (!editandoId && cantidad > Number(productoSeleccionado.stock || 0)) {
      toast.warning(`Stock insuficiente. Disponible: ${Number(productoSeleccionado.stock || 0)}`);
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
    const ventaBase = (venta.items && venta.items[0]) ? venta.items[0] : venta;
    const esConsumo = (ventaBase.tipo_operacion || 'venta') === 'consumo_empleado';
    setTipoFacturaEditando(esConsumo ? 'consumo_empleado' : 'venta');
    setInvoiceEditForm({
      numero_factura: venta.numero_factura || ventaBase.numero_factura || '',
      cliente_nombre: venta.cliente_nombre || ventaBase.cliente_nombre || '',
      estilista: venta.items?.[0]?.estilista ? String(venta.items[0].estilista) : (venta.estilista ? String(venta.estilista) : ''),
      fecha_hora: formatDateTimeLocalInput(venta.fecha_hora || ventaBase.fecha_hora),
      medio_pago: venta.medio_pago || ventaBase.medio_pago || 'efectivo',
      items: (venta.items || [ventaBase]).map((x) => ({
        producto: x.producto,
        cantidad: String(x.cantidad || 1),
        precio_unitario: String(x.precio_unitario || ''),
      })),
    });
    setShowInvoiceEditForm(true);
  };

  const eliminarVenta = async (venta) => {
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden eliminar facturas');
      return;
    }

    const esTransaccion = (venta.items || []).length > 1;
    const ventaBase = (venta.items && venta.items[0]) ? venta.items[0] : venta;
    const numeroFactura = venta.numero_factura || ventaBase.numero_factura;

    const ok = window.confirm(
      esTransaccion
        ? `¿Eliminar la factura ${numeroFactura || ventaBase.id} completa? Se restaurará inventario de todos sus productos.`
        : `¿Eliminar la factura ${ventaBase.numero_factura || ventaBase.id}?`
    );
    if (!ok) return;

    try {
      if (esTransaccion && numeroFactura) {
        const resp = await ventasService.cancelByInvoice(numeroFactura);
        toast.success(`Factura cancelada (${resp?.items_eliminados || 0} ítems). Inventario restablecido.`);
      } else {
        await ventasService.delete(ventaBase.id);
        toast.success('Factura eliminada');
      }
      if (editandoId === ventaBase.id) limpiarFormulario();
      await cargarDatos();
    } catch (error) {
      toast.error('No se pudo eliminar la factura');
    }
  };

  const actualizarItemFactura = (idx, campo, valor) => {
    setInvoiceEditForm((prev) => {
      const items = [...(prev.items || [])];
      items[idx] = { ...items[idx], [campo]: valor };
      return { ...prev, items };
    });
  };

  const agregarItemFactura = () => {
    setInvoiceEditForm((prev) => ({
      ...prev,
      items: [...(prev.items || []), { producto: '', cantidad: '1', precio_unitario: '' }],
    }));
  };

  const quitarItemFactura = (idx) => {
    setInvoiceEditForm((prev) => ({
      ...prev,
      items: (prev.items || []).filter((_, i) => i !== idx),
    }));
  };

  const guardarEdicionFactura = async (e) => {
    e.preventDefault();
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden editar facturas');
      return;
    }
    if (!invoiceEditForm.numero_factura) {
      toast.warning('Factura inválida');
      return;
    }
    const items = (invoiceEditForm.items || []).map((it) => ({
      producto: Number(it.producto),
      cantidad: Number(it.cantidad),
      precio_unitario: Number(it.precio_unitario),
    }));
    if (items.length === 0) {
      toast.warning('Agrega al menos un producto');
      return;
    }
    if (items.some((it) => !it.producto || it.cantidad <= 0 || it.precio_unitario <= 0)) {
      toast.warning('Verifica producto, cantidad y valor unitario en todos los items');
      return;
    }

    try {
      setSaving(true);
      await ventasService.updateInvoiceTransaction({
        numero_factura: invoiceEditForm.numero_factura,
        cliente_nombre: invoiceEditForm.cliente_nombre || null,
        estilista: invoiceEditForm.estilista ? Number(invoiceEditForm.estilista) : null,
        fecha_hora: invoiceEditForm.fecha_hora || null,
        medio_pago: tipoFacturaEditando === 'consumo_empleado' ? 'efectivo' : invoiceEditForm.medio_pago,
        items,
      });
      toast.success(tipoFacturaEditando === 'consumo_empleado' ? 'Factura de consumo actualizada' : 'Factura de venta actualizada');
      setShowInvoiceEditForm(false);
      await cargarDatos();
    } catch (error) {
      toast.error(error?.response?.data?.error || 'No se pudo actualizar la factura');
    } finally {
      setSaving(false);
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
    try {
      await ticketPrintService.reprintProductSale(venta);
      toast.success('Ticket reenviado a impresora POS');
    } catch (error) {
      toast.error(error?.message || 'No se pudo reenviar el ticket a QZ Tray');
    }
  };

  const reimprimirServicio = async (servicio) => {
    try {
      await ticketPrintService.reprintServiceSale(servicio);
      toast.success('Ticket reenviado a impresora POS');
    } catch (error) {
      toast.error(error?.message || 'No se pudo reenviar el ticket a QZ Tray');
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

  const abrirSearchKeyboard = (field) => {
    setSearchKeyboard({ visible: true, field });
  };

  const cerrarSearchKeyboard = () => {
    setSearchKeyboard({ visible: false, field: '' });
  };

  const obtenerValorSearchKeyboard = () => {
    if (searchKeyboard.field === 'filtro_usuario') return String(filtroUsuario || '');
    if (searchKeyboard.field === 'filtro_empleado') return String(filtroEmpleado || '');
    if (searchKeyboard.field === 'busqueda_producto') return String(busquedaProducto || '');
    return '';
  };

  const asignarValorSearchKeyboard = (value) => {
    if (searchKeyboard.field === 'filtro_usuario') {
      setFiltroUsuario(value);
      return;
    }
    if (searchKeyboard.field === 'filtro_empleado') {
      setFiltroEmpleado(value);
      return;
    }
    if (searchKeyboard.field === 'busqueda_producto') {
      setBusquedaProducto(value);
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
    try {
      const adicionales = Array.isArray(servicio?.adicionales_asignados)
        ? servicio.adicionales_asignados.filter((item) => item && typeof item === 'object')
        : [];

      setServicioEditando(servicio);
      setServicioForm({
        servicio: servicio?.servicio ? String(servicio.servicio) : '',
        estilista: servicio?.estilista ? String(servicio.estilista) : '',
        fecha_hora: formatDateTimeLocalInput(servicio?.fecha_hora),
        precio_cobrado: String(servicio?.precio_cobrado || ''),
        medio_pago: servicio?.medio_pago || 'efectivo',
        tipo_reparto_establecimiento: String(servicio?.tipo_reparto_establecimiento || ''),
        valor_reparto_establecimiento: String(servicio?.valor_reparto_establecimiento ?? ''),
        tiene_adicionales: Boolean(servicio?.tiene_adicionales),
        adicionales_servicio_items: adicionales.map((item, idx) => ({
          _key: `${item.id || idx}`,
          id: String(item.servicio_id || ''),
          estilista_id: String(item.estilista_id || ''),
          valor: String(item.valor || ''),
          aplica_porcentaje_establecimiento: Boolean(item.aplica_porcentaje_establecimiento),
          porcentaje_establecimiento: String(item.porcentaje_establecimiento ?? '30'),
        })),
        adicional_otro_producto: servicio?.adicional_otro_producto ? String(servicio.adicional_otro_producto) : '',
        adicional_otro_cantidad: String(servicio?.adicional_otro_cantidad || 1),
        adicional_otro_estilista: servicio?.adicional_otro_estilista ? String(servicio.adicional_otro_estilista) : '',
        notas: servicio?.notas || '',
      });
      setShowServicioForm(true);
    } catch (error) {
      toast.error('No se pudo abrir la edición de esta factura. Intenta actualizar la lista.');
    }
  };

  const actualizarAdicionalServicio = (idx, campo, valor) => {
    setServicioForm((prev) => {
      const items = [...(prev.adicionales_servicio_items || [])];
      items[idx] = { ...items[idx], [campo]: valor };
      return { ...prev, adicionales_servicio_items: items };
    });
  };

  const agregarAdicionalServicio = () => {
    setServicioForm((prev) => ({
      ...prev,
      adicionales_servicio_items: [
        ...(prev.adicionales_servicio_items || []),
        { _key: `new-${Date.now()}`, id: '', estilista_id: '', valor: '' },
      ],
      tiene_adicionales: true,
    }));
  };

  const quitarAdicionalServicio = (idx) => {
    setServicioForm((prev) => {
      const nuevos = (prev.adicionales_servicio_items || []).filter((_, i) => i !== idx);
      return {
        ...prev,
        adicionales_servicio_items: nuevos,
        tiene_adicionales: nuevos.length > 0,
      };
    });
  };

  const guardarServicioEditado = async (e) => {
    e.preventDefault();
    if (!puedeEditarFacturas) {
      toast.warning('Solo administrador o gerente pueden editar facturas de servicio');
      return;
    }
    if (!servicioEditando) return;

    const esShampooServicio = (servicioId) => {
      const srv = serviciosCatalogo.find((s) => Number(s.id) === Number(servicioId));
      return esServicioShampooNombre(srv?.nombre);
    };

    const adicionalesNormalizados = (servicioForm.adicionales_servicio_items || [])
      .filter((it) => {
        if (!it.id || Number(it.valor || 0) <= 0) return false;
        if (esShampooServicio(it.id)) return true;
        return Boolean(it.estilista_id);
      })
      .map((it) => ({
        id: Number(it.id),
        estilista_id: esShampooServicio(it.id) ? null : Number(it.estilista_id),
        valor: Number(it.valor),
        aplica_porcentaje_establecimiento: esShampooServicio(it.id)
          ? false
          : Boolean(it.aplica_porcentaje_establecimiento),
        porcentaje_establecimiento: esShampooServicio(it.id)
          ? 0
          : Boolean(it.aplica_porcentaje_establecimiento)
          ? Number(it.porcentaje_establecimiento || 0)
          : 0,
      }));

    const idsAdicionales = adicionalesNormalizados.map((it) => it.id);

    const tieneProductoAdicional = Boolean(servicioForm.adicional_otro_producto);
    if (servicioForm.tiene_adicionales && adicionalesNormalizados.length === 0 && !tieneProductoAdicional) {
      toast.warning('Selecciona al menos un adicional: servicio, producto o ambos');
      return;
    }

    const porcentajeInvalido = (servicioForm.adicionales_servicio_items || []).find((it) => {
      if (esShampooServicio(it.id)) return false;
      if (!it.aplica_porcentaje_establecimiento) return false;
      const pct = Number(it.porcentaje_establecimiento || 0);
      return !Number.isFinite(pct) || pct <= 0 || pct > 100;
    });
    if (porcentajeInvalido) {
      toast.warning('El porcentaje para establecimiento debe ser mayor a 0 y menor o igual a 100');
      return;
    }

    if (servicioForm.adicional_otro_producto) {
      const qtyProd = Number(servicioForm.adicional_otro_cantidad || 0);
      if (!Number.isFinite(qtyProd) || qtyProd <= 0) {
        toast.warning('La cantidad del producto adicional debe ser mayor a 0');
        return;
      }
      if (!servicioForm.adicional_otro_estilista) {
        toast.warning('Selecciona el empleado que gana la comisión del producto adicional');
        return;
      }
    }

    try {
      setSaving(true);
      await serviciosRealizadosService.update(servicioEditando.id, {
        estado: 'finalizado',
        servicio: servicioForm.servicio ? Number(servicioForm.servicio) : servicioEditando.servicio,
        estilista: servicioForm.estilista ? Number(servicioForm.estilista) : servicioEditando.estilista,
        fecha_hora: servicioForm.fecha_hora || null,
        precio_cobrado: Number(servicioForm.precio_cobrado || 0),
        medio_pago: servicioForm.medio_pago,
        tipo_reparto_establecimiento: servicioForm.tipo_reparto_establecimiento || null,
        valor_reparto_establecimiento: servicioForm.tipo_reparto_establecimiento
          ? Number(servicioForm.valor_reparto_establecimiento || 0)
          : null,
        tiene_adicionales: Boolean(servicioForm.tiene_adicionales),
        adicionales_servicio_ids: servicioForm.tiene_adicionales ? idsAdicionales : [],
        adicionales_servicio_items: servicioForm.tiene_adicionales ? adicionalesNormalizados : [],
        adicional_otro_producto: servicioForm.adicional_otro_producto ? Number(servicioForm.adicional_otro_producto) : null,
        adicional_otro_estilista: servicioForm.adicional_otro_estilista ? Number(servicioForm.adicional_otro_estilista) : null,
        adicional_otro_cantidad: servicioForm.adicional_otro_producto ? Number(servicioForm.adicional_otro_cantidad || 1) : 1,
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

  const ventasProductosFiltradas = useMemo(
    () => ventasFiltradas.filter((v) => (v.tipo_operacion || 'venta') !== 'consumo_empleado'),
    [ventasFiltradas]
  );

  const consumosEmpleadoFiltrados = useMemo(
    () => ventasFiltradas.filter((v) => (v.tipo_operacion || 'venta') === 'consumo_empleado'),
    [ventasFiltradas]
  );

  const ventasAgrupadas = useMemo(() => {
    const grupos = new Map();
    for (const v of ventasProductosFiltradas) {
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
  }, [ventasProductosFiltradas]);

  const consumosEmpleadoAgrupados = useMemo(() => {
    const grupos = new Map();
    for (const v of consumosEmpleadoFiltrados) {
      const key = v.numero_factura || `CON-${v.id}`;
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
          deuda_consumo_estado: v.deuda_consumo_estado || 'pendiente',
          deuda_consumo_saldo: Number(v.deuda_consumo_saldo || 0),
          items: [v],
        });
        continue;
      }

      existente.total += Number(v.total || 0);
      existente.cantidad_total += Number(v.cantidad || 0);
      existente.items.push(v);
      existente.deuda_consumo_saldo = Math.max(existente.deuda_consumo_saldo, Number(v.deuda_consumo_saldo || 0));
      if (String(v.fecha_hora || '') > String(existente.fecha_hora || '')) {
        existente.fecha_hora = v.fecha_hora;
      }
      if (!existente.factura_texto && v.factura_texto) {
        existente.factura_texto = v.factura_texto;
      }
      if (v.deuda_consumo_estado === 'parcial') {
        existente.deuda_consumo_estado = 'parcial';
      } else if (v.deuda_consumo_estado === 'cancelado' && existente.deuda_consumo_estado !== 'parcial') {
        existente.deuda_consumo_estado = 'cancelado';
      }
    }

    return Array.from(grupos.values()).sort((a, b) => String(b.fecha_hora || '').localeCompare(String(a.fecha_hora || '')));
  }, [consumosEmpleadoFiltrados]);

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

  const totalVentas = useMemo(() => ventasProductosFiltradas.reduce((acc, v) => acc + Number(v.total || 0), 0), [ventasProductosFiltradas]);
  const totalConsumoEmpleado = useMemo(() => consumosEmpleadoFiltrados.reduce((acc, v) => acc + Number(v.total || 0), 0), [consumosEmpleadoFiltrados]);
  const ticketPromedio = useMemo(() => (ventasAgrupadas.length ? totalVentas / ventasAgrupadas.length : 0), [totalVentas, ventasAgrupadas.length]);
  const totalServicios = useMemo(
    () => serviciosFiltrados.reduce((acc, s) => acc + (Number(s.precio_cobrado || 0) + Number(s.valor_adicionales || 0)), 0),
    [serviciosFiltrados]
  );
  const totalServiciosEmpleado = useMemo(
    () => serviciosFiltrados.reduce((acc, s) => acc + Number(s.monto_estilista || 0), 0),
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
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <button className={modoVista === 'ventas' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('ventas')}>
            Ventas de productos
          </button>
          <button className={modoVista === 'servicios' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('servicios')}>
            Servicios facturados
          </button>
          <button className={modoVista === 'consumo_empleado' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('consumo_empleado')}>
            Consumo Empleado
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <input className="input-field" type="date" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
          <input className="input-field" type="date" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
          <div className="relative">
            <input
              className="input-field pr-14"
              placeholder="Filtrar por usuario que facturó"
              inputMode="search"
              enterKeyHint="search"
              value={filtroUsuario}
              onChange={(e) => setFiltroUsuario(e.target.value)}
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 btn-secondary !px-2 !py-1"
              onClick={() => abrirSearchKeyboard('filtro_usuario')}
              title="Teclado"
            >
              ⌨
            </button>
          </div>
          <div className="relative">
            <input
              className="input-field pr-14"
              placeholder="Filtrar por empleado"
              inputMode="search"
              enterKeyHint="search"
              value={filtroEmpleado}
              onChange={(e) => setFiltroEmpleado(e.target.value)}
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 btn-secondary !px-2 !py-1"
              onClick={() => abrirSearchKeyboard('filtro_empleado')}
              title="Teclado"
            >
              ⌨
            </button>
          </div>
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
            Total resultados: {modoVista === 'ventas' ? ventasAgrupadas.length : modoVista === 'servicios' ? serviciosFiltrados.length : consumosEmpleadoAgrupados.length}
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

                  {previewVentaHtml && (
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Factura para compartir:</p>
                      <div className="bg-gray-50 rounded border border-gray-200 p-3 max-h-72 overflow-y-auto">
                        <div
                          className="mx-auto"
                          style={{ width: '80mm', maxWidth: '100%' }}
                          dangerouslySetInnerHTML={{ __html: previewVentaHtml }}
                        />
                      </div>
                    </div>
                  )}
                </>
              )}

              {servicioVisualizar && (
                <>
                  {(() => {
                    const estilistaCfg = estilistas.find((e) => Number(e.id) === Number(servicioVisualizar.estilista));
                    const tipoAuto = estilistaCfg?.tipo_cobro_espacio || 'sin_cobro';
                    const valorAuto = Number(estilistaCfg?.valor_cobro_espacio || 0);
                    const tipoActual = servicioVisualizar.tipo_reparto_establecimiento || '';
                    const valorActual = Number(servicioVisualizar.valor_reparto_establecimiento || 0);
                    const origenReparto = tipoActual
                      ? `${tipoActual} ${tipoActual === 'porcentaje' ? `${valorActual}%` : `$${valorActual.toFixed(2)}`}`
                      : `Automatico por empleado: ${tipoAuto}${tipoAuto === 'porcentaje_neto' ? ` ${valorAuto}%` : tipoAuto === 'costo_fijo_neto' ? ` $${valorAuto.toFixed(2)}` : ''}`;
                    return (
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
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.neto_servicio ?? servicioVisualizar.precio_cobrado ?? 0).toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Reparto establecimiento</p>
                      <p className="font-bold text-gray-900">{origenReparto}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Valor establecimiento</p>
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.monto_establecimiento || 0).toFixed(2)}</p>
                    </div>
                    <div>
                      <p className="text-sm text-gray-600">Valor empleado</p>
                      <p className="font-bold text-gray-900">${Number(servicioVisualizar.monto_estilista || 0).toFixed(2)}</p>
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
                    );
                  })()}

                  {previewServicioHtml && (
                    <div>
                      <p className="text-sm text-gray-600 mb-2">Factura para compartir:</p>
                      <div className="bg-gray-50 rounded border border-gray-200 p-3 max-h-72 overflow-y-auto">
                        <div
                          className="mx-auto"
                          style={{ width: '80mm', maxWidth: '100%' }}
                          dangerouslySetInnerHTML={{ __html: previewServicioHtml }}
                        />
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
          <p className="text-sm text-gray-500">Total cobrado cliente (servicios)</p>
          <p className="text-2xl font-bold text-gray-900">${totalServicios.toFixed(2)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Total base empleado (servicios)</p>
          <p className="text-2xl font-bold text-gray-900">${totalServiciosEmpleado.toFixed(2)}</p>
        </div>
        <div className="card">
          <p className="text-sm text-gray-500">Total consumo empleado</p>
          <p className="text-2xl font-bold text-gray-900">${totalConsumoEmpleado.toFixed(2)}</p>
        </div>
      </div>

      <ModalForm
        isOpen={showInvoiceEditForm}
        onClose={() => setShowInvoiceEditForm(false)}
        title={tipoFacturaEditando === 'consumo_empleado' ? 'Editar factura consumo empleado' : 'Editar factura de productos'}
        subtitle="Edita empleado, medio de pago y productos facturados"
        size="xl"
      >
        <form className="space-y-3" onSubmit={guardarEdicionFactura}>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <input className="input-field" value={invoiceEditForm.numero_factura || ''} readOnly />
            <input
              className="input-field"
              type="datetime-local"
              value={invoiceEditForm.fecha_hora || ''}
              onChange={(e) => setInvoiceEditForm((p) => ({ ...p, fecha_hora: e.target.value }))}
            />
            <input
              className="input-field"
              placeholder={tipoFacturaEditando === 'consumo_empleado' ? 'Detalle opcional' : 'Cliente (opcional)'}
              value={invoiceEditForm.cliente_nombre || ''}
              onChange={(e) => setInvoiceEditForm((p) => ({ ...p, cliente_nombre: e.target.value }))}
            />
            <select
              className="input-field"
              value={invoiceEditForm.estilista || ''}
              onChange={(e) => setInvoiceEditForm((p) => ({ ...p, estilista: e.target.value }))}
            >
              <option value="">Empleado</option>
              {estilistas.map((est) => (
                <option key={est.id} value={est.id}>{est.nombre}</option>
              ))}
            </select>
            {tipoFacturaEditando !== 'consumo_empleado' ? (
              <select
                className="input-field"
                value={invoiceEditForm.medio_pago || 'efectivo'}
                onChange={(e) => setInvoiceEditForm((p) => ({ ...p, medio_pago: e.target.value }))}
              >
                {MEDIOS_PAGO.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            ) : (
              <input className="input-field" value="Consumo empleado" readOnly />
            )}
          </div>

          <div className="space-y-2">
            {(invoiceEditForm.items || []).map((it, idx) => (
              <div key={`inv-item-${idx}`} className="grid grid-cols-1 md:grid-cols-4 gap-2">
                <select
                  className="input-field"
                  value={it.producto}
                  onChange={(e) => actualizarItemFactura(idx, 'producto', e.target.value)}
                >
                  <option value="">Producto</option>
                  {productos.map((p) => (
                    <option key={p.id} value={p.id}>{formatProductSearchLabel(p)} (stock {p.stock})</option>
                  ))}
                </select>
                <input
                  className="input-field"
                  type="number"
                  min="1"
                  value={it.cantidad}
                  onChange={(e) => actualizarItemFactura(idx, 'cantidad', e.target.value)}
                />
                <input
                  className="input-field"
                  type="number"
                  min="0"
                  step="0.01"
                  value={it.precio_unitario}
                  onChange={(e) => actualizarItemFactura(idx, 'precio_unitario', e.target.value)}
                />
                <button type="button" className="btn-danger" onClick={() => quitarItemFactura(idx)}>
                  Quitar
                </button>
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <button type="button" className="btn-secondary" onClick={agregarItemFactura}>Agregar producto</button>
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Guardando...' : 'Guardar cambios'}</button>
            <button type="button" className="btn-secondary" onClick={() => setShowInvoiceEditForm(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

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
        <div className="md:col-span-3 relative">
          <input
            className="input-field pr-14"
            placeholder="Buscar producto por marca, descripción, código o nombre"
            inputMode="search"
            enterKeyHint="search"
            value={busquedaProducto}
            onChange={(e) => setBusquedaProducto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                buscarProducto();
              }
            }}
          />
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 btn-secondary !px-2 !py-1"
            onClick={() => abrirSearchKeyboard('busqueda_producto')}
            title="Teclado"
          >
            ⌨
          </button>
        </div>
        <button type="button" className="btn-secondary inline-flex items-center justify-center gap-2" onClick={buscarProducto}>
          <FiSearch /> Buscar
        </button>

        {sugerenciasProducto.length > 0 && (
          <div className="md:col-span-4 rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
            {sugerenciasProducto.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`w-full text-left px-3 py-2 hover:bg-gray-50 ${getStockEstado(p).key === 'agotado' ? 'opacity-60 cursor-not-allowed' : ''}`}
                onClick={() => seleccionarProductoSugerido(p)}
                disabled={getStockEstado(p).key === 'agotado'}
              >
                <div className="flex items-center justify-between gap-2">
                  <span>{formatProductSearchLabel(p)} - {p.codigo_barras || 'sin código'} (stock {p.stock})</span>
                  <span className={`text-xs px-2 py-1 rounded-full border ${getStockEstado(p).badgeClass}`}>{getStockEstado(p).label}</span>
                </div>
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
            Producto: <strong>{formatProductSearchLabel(productoSeleccionado)}</strong> | Stock: <strong>{productoSeleccionado.stock}</strong> | Estado: <strong>{getStockEstado(productoSeleccionado).label}</strong>
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
          <div className="max-h-[55vh] overflow-auto rounded-lg border border-gray-100">
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
        subtitle="Edita servicio principal y adicionales de la factura"
        size="xl"
      >
        <form className="space-y-3" onSubmit={guardarServicioEditado}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <select className="input-field" value={servicioForm.servicio} onChange={(e) => setServicioForm((p) => ({ ...p, servicio: e.target.value }))}>
              <option value="">Servicio principal</option>
              {serviciosCatalogo.filter((s) => !s.es_adicional).map((s) => (
                <option key={s.id} value={s.id}>{formatServiceSearchLabel(s)}</option>
              ))}
            </select>
            <select className="input-field" value={servicioForm.estilista} onChange={(e) => setServicioForm((p) => ({ ...p, estilista: e.target.value }))}>
              <option value="">Empleado principal</option>
              {estilistas.map((e) => (
                <option key={e.id} value={e.id}>{e.nombre}</option>
              ))}
            </select>
            <input
              className="input-field"
              type="datetime-local"
              value={servicioForm.fecha_hora || ''}
              onChange={(e) => setServicioForm((p) => ({ ...p, fecha_hora: e.target.value }))}
            />
          </div>
          <input className="input-field" type="number" min="0" step="0.01" placeholder="Total cobrado" value={servicioForm.precio_cobrado} onChange={(e) => setServicioForm((p) => ({ ...p, precio_cobrado: e.target.value }))} />
          <select className="input-field" value={servicioForm.medio_pago} onChange={(e) => setServicioForm((p) => ({ ...p, medio_pago: e.target.value }))}>
            {MEDIOS_PAGO.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <select
              className="input-field"
              value={servicioForm.tipo_reparto_establecimiento || ''}
              onChange={(e) => setServicioForm((p) => ({ ...p, tipo_reparto_establecimiento: e.target.value }))}
            >
              <option value="">Automatico por configuracion del empleado</option>
              <option value="porcentaje">Porcentaje para establecimiento</option>
              <option value="monto">Monto fijo para establecimiento</option>
            </select>
            <input
              className="input-field"
              type="number"
              min="0"
              step="0.01"
              placeholder="Valor reparto establecimiento"
              value={servicioForm.valor_reparto_establecimiento || ''}
              onChange={(e) => setServicioForm((p) => ({ ...p, valor_reparto_establecimiento: e.target.value }))}
            />
          </div>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={Boolean(servicioForm.tiene_adicionales)}
              onChange={(e) =>
                setServicioForm((p) => ({
                  ...p,
                  tiene_adicionales: e.target.checked,
                  adicionales_servicio_items: e.target.checked ? p.adicionales_servicio_items : [],
                  adicional_otro_producto: e.target.checked ? p.adicional_otro_producto : '',
                  adicional_otro_cantidad: e.target.checked ? p.adicional_otro_cantidad : '1',
                  adicional_otro_estilista: e.target.checked ? p.adicional_otro_estilista : '',
                }))
              }
            />
            Esta factura tiene adicionales (servicio y/o producto)
          </label>

          {servicioForm.tiene_adicionales && (
            <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-blue-900">Servicios adicionales facturados</p>
                <button type="button" className="btn-secondary !px-3 !py-1" onClick={agregarAdicionalServicio}>Agregar adicional</button>
              </div>

              <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3">
                <p className="text-sm font-medium text-indigo-900 mb-2">Producto de venta adicional</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <select
                    className="input-field"
                    value={servicioForm.adicional_otro_producto || ''}
                    onChange={(e) => setServicioForm((p) => ({ ...p, adicional_otro_producto: e.target.value }))}
                  >
                    <option value="">Sin producto adicional</option>
                    {productos.map((p) => (
                      <option key={p.id} value={p.id}>{formatProductSearchLabel(p)} - {formatCOP(p.precio_venta || 0)}</option>
                    ))}
                  </select>

                  <input
                    className="input-field"
                    type="number"
                    min="1"
                    step="1"
                    placeholder="Cantidad"
                    value={servicioForm.adicional_otro_cantidad || '1'}
                    onChange={(e) => setServicioForm((p) => ({ ...p, adicional_otro_cantidad: e.target.value }))}
                  />

                  <select
                    className="input-field"
                    value={servicioForm.adicional_otro_estilista || ''}
                    onChange={(e) => setServicioForm((p) => ({ ...p, adicional_otro_estilista: e.target.value }))}
                  >
                    <option value="">Empleado comisión producto</option>
                    {estilistas.map((e) => (
                      <option key={e.id} value={e.id}>{e.nombre}</option>
                    ))}
                  </select>
                </div>
              </div>

              {(servicioForm.adicionales_servicio_items || []).map((it, idx) => (
                <div key={it._key || `ad-${idx}`} className="grid grid-cols-1 md:grid-cols-12 gap-2 rounded border border-blue-200 bg-white p-2">
                  <div className="md:col-span-5">
                    <select className="input-field" value={it.id} onChange={(e) => actualizarAdicionalServicio(idx, 'id', e.target.value)}>
                      <option value="">Servicio adicional</option>
                      {serviciosCatalogo.filter((s) => s.es_adicional).map((s) => (
                        <option key={s.id} value={s.id}>{formatServiceSearchLabel(s)}</option>
                      ))}
                    </select>
                  </div>
                  <div className="md:col-span-4">
                    <select
                      className="input-field"
                      value={it.estilista_id}
                      disabled={esServicioShampooNombre(serviciosCatalogo.find((s) => Number(s.id) === Number(it.id))?.nombre)}
                      onChange={(e) => actualizarAdicionalServicio(idx, 'estilista_id', e.target.value)}
                    >
                      <option value="">
                        {esServicioShampooNombre(serviciosCatalogo.find((s) => Number(s.id) === Number(it.id))?.nombre)
                          ? 'No aplica (ganancia establecimiento)'
                          : 'Empleado'}
                      </option>
                      {estilistas.map((e) => (
                        <option key={e.id} value={e.id}>{e.nombre}</option>
                      ))}
                    </select>
                  </div>
                  <div className="md:col-span-2">
                    <input
                      className="input-field"
                      type="number"
                      min="0"
                      step="0.01"
                      value={it.valor}
                      onChange={(e) => actualizarAdicionalServicio(idx, 'valor', e.target.value)}
                      placeholder="Valor"
                    />
                  </div>
                  <div className="md:col-span-1 flex items-center">
                    <button type="button" className="btn-danger !px-2 !py-2 w-full" onClick={() => quitarAdicionalServicio(idx)}>
                      <FiTrash2 size={14} />
                    </button>
                  </div>

                  <div className="md:col-span-8">
                    <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={Boolean(it.aplica_porcentaje_establecimiento)}
                        onChange={(e) =>
                          actualizarAdicionalServicio(idx, 'aplica_porcentaje_establecimiento', e.target.checked)
                        }
                      />
                      Este adicional tiene ganancia para establecimiento
                    </label>
                  </div>

                  <div className="md:col-span-4">
                    <input
                      className="input-field"
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      placeholder="% establecimiento"
                      disabled={!it.aplica_porcentaje_establecimiento}
                      value={it.porcentaje_establecimiento || ''}
                      onChange={(e) => actualizarAdicionalServicio(idx, 'porcentaje_establecimiento', e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
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
                  <th className="px-6 py-3 text-left">Base empleado</th>
                  <th className="px-6 py-3 text-left">Total cliente</th>
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
                    <td className="table-cell">${Number(s.monto_estilista || 0).toFixed(2)}</td>
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

      {modoVista === 'consumo_empleado' && (
      <>
      <div className="card">
        <h2 className="card-header">Facturas de consumo de empleado</h2>
        {consumosEmpleadoAgrupados.length === 0 && <p className="text-gray-600">No hay consumos de empleado con los filtros actuales.</p>}
        {consumosEmpleadoAgrupados.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Fecha</th>
                  <th className="px-6 py-3 text-left">Empleado</th>
                  <th className="px-6 py-3 text-left">Items</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-left">Saldo</th>
                  <th className="px-6 py-3 text-left">Estado</th>
                  <th className="px-6 py-3 text-left">Usuario facturó</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {consumosEmpleadoAgrupados.map((v) => (
                  <tr key={v.id} className="hover:bg-gray-50">
                    <td className="table-cell">{v.numero_factura || '-'}</td>
                    <td className="table-cell">{String(v.fecha_hora || '').slice(0, 10)}</td>
                    <td className="table-cell">{v.estilista_nombre || '-'}</td>
                    <td className="table-cell">{(v.items || []).length}</td>
                    <td className="table-cell">${Number(v.total || 0).toFixed(2)}</td>
                    <td className="table-cell">${Number(v.deuda_consumo_saldo || 0).toFixed(2)}</td>
                    <td className="table-cell capitalize">{v.deuda_consumo_estado || 'pendiente'}</td>
                    <td className="table-cell">{v.usuario_nombre || '-'}</td>
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

      <DraggableSearchKeyboard
        visible={searchKeyboard.visible}
        value={obtenerValorSearchKeyboard()}
        onChange={asignarValorSearchKeyboard}
        onClose={cerrarSearchKeyboard}
        title="Teclado de búsqueda"
      />
    </div>
  );
};

export default Ventas;
