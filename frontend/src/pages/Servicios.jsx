import { useEffect, useMemo, useState } from 'react';
import { FiCheckCircle, FiDollarSign, FiPlus, FiRefreshCw, FiScissors, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import {
  clientesService,
  estilistasService,
  productosService,
  serviciosRealizadosService,
  ventasService,
  serviciosService,
} from '../services/api';
import ModalForm from '../components/ModalForm';
import DraggableSearchKeyboard from '../components/DraggableSearchKeyboard';
import { ticketPrintService } from '../services/printing/ticketPrintService';
import { customerDisplayService } from '../services/customerDisplayService';
import useAuthStore from '../store/authStore';

// Todos los perfiles autenticados pueden registrar ventas y servicios (operación diaria)
// Solo admin/gerente pueden EDITAR o ELIMINAR del historial (controlado en Ventas.jsx y backend)

const mediosPago = [
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

const fetchAllRows = async (getAllFn, params = {}) => {
  let page = 1;
  const all = [];

  while (true) {
    const payload = await getAllFn({ ...params, page });
    const rows = extractRows(payload);
    all.push(...rows);

    if (!payload?.next || rows.length === 0) break;
    page += 1;
  }

  return all;
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

const getProductoStockEstado = (producto) => {
  const stock = Number(producto?.stock || 0);
  const stockMinimo = Number(producto?.stock_minimo || 0);

  if (stock <= 0) {
    return { key: 'agotado', label: 'Agotado', badgeClass: 'bg-red-100 text-red-700 border-red-200' };
  }
  if (stock <= stockMinimo) {
    return { key: 'por_agotar', label: 'Por agotarse', badgeClass: 'bg-amber-100 text-amber-700 border-amber-200' };
  }
  return { key: 'ok', label: 'Disponible', badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200' };
};

const formatServiceSearchLabel = (servicio) => {
  return [servicio.descripcion, servicio.nombre].filter(Boolean).join(' - ') || servicio.nombre || 'Servicio';
};

const formatServiceCompactLabel = (servicio) => {
  return servicio?.nombre || servicio?.descripcion || 'Servicio';
};

const formatProductCompactLabel = (producto) => {
  return [producto?.marca, producto?.nombre || producto?.descripcion].filter(Boolean).join(' - ') || producto?.nombre || 'Producto';
};

const serviceMatchesSearch = (servicio, query) => {
  const q = normalizeSearchText(query);
  if (!q) return true;

  const index = normalizeSearchText([
    servicio.nombre,
    servicio.descripcion,
  ].filter(Boolean).join(' '));

  if (index.includes(q)) return true;
  const terms = q.split(' ').filter(Boolean);
  return terms.every((term) => index.includes(term));
};

const isShampooServiceName = (nombre) => {
  const n = String(nombre || '').toLowerCase();
  return n.includes('shampoo');
};

const isDepilationServiceName = (nombre) => {
  const n = String(nombre || '').toLowerCase();
  return n.includes('depilacion') || n.includes('depilación');
};

const isPestanasServiceName = (nombre) => {
  const n = String(nombre || '').toLowerCase();
  return n.includes('pesta');
};

const moneyFormatterCOP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const toPesoInt = (value) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n);
};

const toPositiveInt = (value) => {
  const n = Math.trunc(Number(value));
  return Number.isFinite(n) && n > 0 ? n : 0;
};

const formatCOP = (value) => moneyFormatterCOP.format(toPesoInt(value));

const sanitizePesoInput = (value) => String(value ?? '').replace(/[^\d]/g, '');

const minimoConDescuentoEmpleado = (precioBase) => {
  const base = toPesoInt(precioBase);
  if (base <= 0) return 0;
  return Math.ceil(base * 0.8);
};

const Servicios = () => {
  const { user } = useAuthStore();
  const puedeFacturar = true; // Todos los roles pueden registrar ventas y servicios (recepcion incluida)

  const [modoVista, setModoVista] = useState('servicios');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showNuevoClienteModal, setShowNuevoClienteModal] = useState(false);
  const [showFinalizarModal, setShowFinalizarModal] = useState(false);
  const [showConfirmacionFinalizar, setShowConfirmacionFinalizar] = useState(false);

  const [estilistas, setEstilistas] = useState([]);
  const [servicios, setServicios] = useState([]);
  const [productos, setProductos] = useState([]);
  const [clientes, setClientes] = useState([]);
  const [estadoEstilistas, setEstadoEstilistas] = useState([]);
  const [serviciosEnProceso, setServiciosEnProceso] = useState([]);

  const [nuevoCliente, setNuevoCliente] = useState({ nombre: '', telefono: '', fecha_nacimiento: '' });

  const [servicioFinalizarId, setServicioFinalizarId] = useState('');
  const [finalizacion, setFinalizacion] = useState({
    estilista: '',
    servicio: '',
    precio_cobrado: '',
    medio_pago: 'efectivo',
    valor_recibido: '',
    tipo_reparto_establecimiento: '',
    valor_reparto_establecimiento: '30',
    tiene_adicionales: false,
    adicionales_servicio_items: [],
    adicional_otro_producto: '',
    adicional_otro_cantidad: '1',
    adicional_otro_estilista: '',
    notas: '',
  });
  const [productoAdicionalBusqueda, setProductoAdicionalBusqueda] = useState('');
  const [productoAdicionalSugerencias, setProductoAdicionalSugerencias] = useState([]);
  const [keypad, setKeypad] = useState({ visible: false, field: '', itemKey: null });
  const [searchKeyboard, setSearchKeyboard] = useState({ visible: false, field: '' });

  const [ventaForm, setVentaForm] = useState({
    cliente_nombre: '',
    estilista: '',
    medio_pago: 'efectivo',
    valor_recibido: '',
    cantidad: '1',
    precio_unitario: '',
  });
  const [ventaBusqueda, setVentaBusqueda] = useState('');
  const [ventaSugerencias, setVentaSugerencias] = useState([]);
  const [productoVentaSeleccionado, setProductoVentaSeleccionado] = useState(null);
  const [carrito, setCarrito] = useState([]);

  const abrirTecladoWindows = async () => {
    try {
      if (navigator?.virtualKeyboard && typeof navigator.virtualKeyboard.show === 'function') {
        navigator.virtualKeyboard.show();
        toast.success('Teclado virtual activado');
        return;
      }
    } catch (error) {
      // Continúa con fallback para Windows.
    }

    const intentarUri = (uri) => {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      iframe.src = uri;
      document.body.appendChild(iframe);
      setTimeout(() => {
        if (iframe.parentNode) {
          iframe.parentNode.removeChild(iframe);
        }
      }, 1200);
    };

    try {
      intentarUri('ms-inputapp:');
      toast.info('Intentando abrir teclado táctil de Windows');
      return;
    } catch (error) {
      // Último fallback con configuración de Windows.
    }

    try {
      intentarUri('ms-settings:easeofaccess-keyboard');
      toast.info('Abre Windows > Teclado táctil para activarlo');
    } catch (error) {
      toast.warning('No se pudo abrir el teclado desde el navegador. Activa el teclado táctil en Windows.');
    }
  };

  const cargarTodo = async () => {
    try {
      setLoading(true);
      const [listaEstilistas, listaServicios, listaClientes, listaRealizados, estadoRes, listaProductos] = await Promise.all([
        fetchAllRows(estilistasService.getAll, { activo: true }),
        fetchAllRows(serviciosService.getAll, { activo: true }),
        fetchAllRows(clientesService.getAll),
        fetchAllRows(serviciosRealizadosService.getAll, { estado: 'en_proceso' }),
        serviciosRealizadosService.getEstadoEstilistas(),
        fetchAllRows(productosService.getAll, { activo: true }),
      ]);

      setEstilistas(listaEstilistas);
      setServicios(listaServicios);
      setClientes(listaClientes);
      setProductos(listaProductos);
      setEstadoEstilistas(Array.isArray(estadoRes) ? estadoRes : []);
      setServiciosEnProceso(listaRealizados.filter((s) => s.estado === 'en_proceso'));
    } catch (error) {
      toast.error('No se pudo cargar el módulo operativo');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarTodo();
  }, []);

  useEffect(() => {
    const q = ventaBusqueda.trim().toLowerCase();
    if (!q) {
      setVentaSugerencias([]);
      return;
    }
    setVentaSugerencias(
      productos
        .filter((p) => productMatchesSearch(p, q))
    );
  }, [ventaBusqueda, productos]);

  useEffect(() => {
    const q = productoAdicionalBusqueda.trim().toLowerCase();
    if (!q) {
      setProductoAdicionalSugerencias([]);
      return;
    }

    setProductoAdicionalSugerencias(
      productos.filter((p) => productMatchesSearch(p, q)).slice(0, 10)
    );
  }, [productoAdicionalBusqueda, productos]);

  const estilistasOcupados = useMemo(
    () => new Set(estadoEstilistas.filter((e) => e.estado === 'ocupado').map((e) => e.estilista_id)),
    [estadoEstilistas]
  );

  const servicioEnProcesoSeleccionado = useMemo(
    () => serviciosEnProceso.find((s) => String(s.id) === String(servicioFinalizarId)),
    [serviciosEnProceso, servicioFinalizarId]
  );

  const servicioPrincipalSeleccionado = useMemo(() => {
    if (servicioEnProcesoSeleccionado?.servicio_nombre) return servicioEnProcesoSeleccionado;
    return servicios.find((s) => Number(s.id) === Number(finalizacion.servicio || 0)) || null;
  }, [servicioEnProcesoSeleccionado, servicios, finalizacion.servicio]);

  const servicioPrincipalCatalogo = useMemo(() => {
    const idSrv = Number(servicioEnProcesoSeleccionado?.servicio || finalizacion.servicio || 0);
    if (!idSrv) return null;
    return servicios.find((s) => Number(s.id) === idSrv) || null;
  }, [servicioEnProcesoSeleccionado, finalizacion.servicio, servicios]);

  const servicioPrincipalEsShampoo = useMemo(
    () => isShampooServiceName(servicioPrincipalSeleccionado?.servicio_nombre || servicioPrincipalSeleccionado?.nombre),
    [servicioPrincipalSeleccionado]
  );

  const servicioPrincipalEsPestanas = useMemo(
    () => isPestanasServiceName(servicioPrincipalSeleccionado?.servicio_nombre || servicioPrincipalSeleccionado?.nombre),
    [servicioPrincipalSeleccionado]
  );

  const servicioPrincipalPermiteReparto = useMemo(
    () => Boolean(servicioPrincipalCatalogo?.es_adicional) && !servicioPrincipalEsShampoo,
    [servicioPrincipalCatalogo, servicioPrincipalEsShampoo]
  );

  const serviciosAdicionalesConfigurados = useMemo(
    () => servicios.filter((s) => {
      if (!(s.activo ?? true)) return false;
      if (Boolean(s.es_adicional)) return true;
      return isShampooServiceName(s.nombre) || isDepilationServiceName(s.nombre);
    }),
    [servicios]
  );

  const serviciosAdicionalesMap = useMemo(
    () => new Map(serviciosAdicionalesConfigurados.map((s) => [Number(s.id), s])),
    [serviciosAdicionalesConfigurados]
  );

  const esServicioShampoo = (servicioId) => {
    const srv = serviciosAdicionalesMap.get(Number(servicioId || 0));
    return isShampooServiceName(srv?.nombre);
  };

  const esServicioDepilacion = (servicioId) => {
    const srv = serviciosAdicionalesMap.get(Number(servicioId || 0));
    return isDepilationServiceName(srv?.nombre);
  };

  const construirItemAdicional = ({
    id = '',
    estilista_id = '',
    valor = '',
    busqueda = '',
    aplica_porcentaje_establecimiento = false,
    porcentaje_establecimiento = '30',
  } = {}) => ({
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    id: id ? String(id) : '',
    estilista_id: estilista_id ? String(estilista_id) : '',
    valor: valor ? String(valor) : '',
    busqueda: busqueda || '',
    aplica_porcentaje_establecimiento: Boolean(aplica_porcentaje_establecimiento),
    porcentaje_establecimiento: String(porcentaje_establecimiento ?? '30'),
  });

  const mapearFlagsLegacyAdicionales = (adicionalesIds) => {
    const ids = new Set((adicionalesIds || []).map((id) => Number(id)));
    const seleccionados = serviciosAdicionalesConfigurados.filter((s) => ids.has(Number(s.id)));
    return {
      adicional_shampoo: seleccionados.some((s) => (s.nombre || '').toLowerCase().includes('shampoo')),
      adicional_guantes: seleccionados.some((s) => (s.nombre || '').toLowerCase().includes('guantes')),
    };
  };

  const totalVentaCaja = useMemo(() => {
    const cantidad = toPositiveInt(ventaForm.cantidad || 0);
    const precio = toPesoInt(ventaForm.precio_unitario || 0);
    return cantidad * precio;
  }, [ventaForm]);

  const totalCarrito = useMemo(
    () => carrito.reduce((acc, item) => acc + item.cantidad * item.precio_unitario, 0),
    [carrito]
  );

  const totalVentaOperacion = useMemo(() => {
    let total = totalCarrito;
    if (productoVentaSeleccionado) {
      const cantidad = toPositiveInt(ventaForm.cantidad || 0);
      const precio = toPesoInt(ventaForm.precio_unitario || 0);
      if (cantidad > 0 && precio > 0) {
        total += cantidad * precio;
      }
    }
    return total;
  }, [totalCarrito, productoVentaSeleccionado, ventaForm.cantidad, ventaForm.precio_unitario]);

  const devueltaVenta = useMemo(() => {
    if (ventaForm.medio_pago !== 'efectivo') return 0;
    const recibido = toPesoInt(ventaForm.valor_recibido || 0);
    return Math.max(0, recibido - totalVentaOperacion);
  }, [ventaForm.medio_pago, ventaForm.valor_recibido, totalVentaOperacion]);

  const esConsumoEmpleado = modoVista === 'consumo_empleado';

  const cantidadReservadaEnCarrito = (productoId) =>
    carrito
      .filter((item) => Number(item.producto?.id) === Number(productoId))
      .reduce((acc, item) => acc + Number(item.cantidad || 0), 0);

  const resumenCobroFinalizacion = useMemo(() => {
    const precioBase = toPesoInt(finalizacion.precio_cobrado || 0);
    const adicionalesServicios = finalizacion.tiene_adicionales
      ? (finalizacion.adicionales_servicio_items || []).reduce(
          (acc, item) => acc + toPesoInt(item.valor || 0),
          0
        )
      : 0;
    const productoAdicionalSeleccionado = productos.find(
      (p) => Number(p.id) === Number(finalizacion.adicional_otro_producto || 0)
    );
    const cantidadProductoAdicional = toPositiveInt(finalizacion.adicional_otro_cantidad || 0);
    const aplicaInsumoPestanas =
      servicioPrincipalEsPestanas
      && finalizacion.tipo_reparto_establecimiento === 'porcentaje'
      && Number(finalizacion.valor_reparto_establecimiento || 0) > 0;
    const totalProductoAdicional = finalizacion.tiene_adicionales && productoAdicionalSeleccionado
      ? cantidadProductoAdicional * toPesoInt(productoAdicionalSeleccionado.precio_venta || 0)
      : 0;

    const total = precioBase + adicionalesServicios + (aplicaInsumoPestanas ? 0 : totalProductoAdicional);
    return {
      precioBase,
      adicionalesServicios,
      totalProductoAdicional,
      aplicaInsumoPestanas,
      total,
    };
  }, [finalizacion, productos, servicioPrincipalEsPestanas]);

  const totalFinalizacion = resumenCobroFinalizacion.total;

  const devueltaServicio = useMemo(() => {
    if (finalizacion.medio_pago !== 'efectivo') return 0;
    const recibido = toPesoInt(finalizacion.valor_recibido || 0);
    return Math.max(0, recibido - totalFinalizacion);
  }, [finalizacion.medio_pago, finalizacion.valor_recibido, totalFinalizacion]);

  const validarPrecioMinimoProducto = (producto, precioUnitario) => {
    if (!producto) return true;
    const minimoPermitido = minimoConDescuentoEmpleado(producto.precio_venta || 0);
    if (minimoPermitido > 0 && toPesoInt(precioUnitario) < minimoPermitido) {
      toast.warning(`Descuento maximo 20%. Precio minimo unitario: ${formatCOP(minimoPermitido)}`);
      return false;
    }
    return true;
  };

  const abrirFacturacionDirecta = (estilistaId) => {
    setServicioFinalizarId('');
    setShowFinalizarModal(true);
    setFinalizacion({
      estilista: String(estilistaId || ''),
      servicio: '',
      precio_cobrado: '',
      medio_pago: 'efectivo',
      valor_recibido: '',
      tipo_reparto_establecimiento: '',
      valor_reparto_establecimiento: '30',
      tiene_adicionales: false,
      adicionales_servicio_items: [],
      adicional_otro_producto: '',
      adicional_otro_cantidad: '1',
      adicional_otro_estilista: '',
      notas: '',
    });
    setProductoAdicionalBusqueda('');
    setProductoAdicionalSugerencias([]);
  };

  const prepararFinalizacion = (srv) => {
    const idsLegacy = serviciosAdicionalesConfigurados
      .filter((cfg) => {
        const nombre = (cfg.nombre || '').toLowerCase();
        if (nombre.includes('shampoo')) return Boolean(srv.adicional_shampoo);
        if (nombre.includes('guantes')) return Boolean(srv.adicional_guantes);
        return false;
      })
      .map((cfg) => Number(cfg.id));

    const adicionalesAsignados = Array.isArray(srv.adicionales_asignados) ? srv.adicionales_asignados : [];
    const itemsIniciales = adicionalesAsignados.length > 0
      ? adicionalesAsignados.map((item) =>
          construirItemAdicional({
            id: item.servicio_id,
            estilista_id: item.estilista_id,
            valor: toPesoInt(item.valor || 0),
            busqueda: item.servicio_nombre || '',
            aplica_porcentaje_establecimiento: Boolean(item.aplica_porcentaje_establecimiento),
            porcentaje_establecimiento: String(item.porcentaje_establecimiento ?? '30'),
          })
        )
      : idsLegacy.map((id) => {
          const cfg = serviciosAdicionalesConfigurados.find((s) => Number(s.id) === Number(id));
          return construirItemAdicional({
            id,
            estilista_id: srv.estilista ? String(srv.estilista) : '',
            valor: toPesoInt(cfg?.precio || 0),
            busqueda: formatServiceSearchLabel(cfg || {}),
          });
        });

    setServicioFinalizarId(String(srv.id));
    setShowFinalizarModal(true);
    setFinalizacion({
      estilista: srv.estilista ? String(srv.estilista) : '',
      servicio: srv.servicio ? String(srv.servicio) : '',
      precio_cobrado: srv.precio_cobrado || '',
      medio_pago: srv.medio_pago || 'efectivo',
      valor_recibido: '',
      tipo_reparto_establecimiento: srv.tipo_reparto_establecimiento || '',
      valor_reparto_establecimiento: String(srv.valor_reparto_establecimiento ?? '30'),
      tiene_adicionales: Boolean(srv.tiene_adicionales),
      adicionales_servicio_items: itemsIniciales,
      adicional_otro_producto: srv.adicional_otro_producto ? String(srv.adicional_otro_producto) : '',
      adicional_otro_cantidad: String(srv.adicional_otro_cantidad || 1),
      adicional_otro_estilista: srv.adicional_otro_estilista ? String(srv.adicional_otro_estilista) : '',
      notas: srv.notas || '',
    });
    const productoSrv = productos.find((p) => Number(p.id) === Number(srv.adicional_otro_producto || 0));
    setProductoAdicionalBusqueda(productoSrv ? formatProductCompactLabel(productoSrv) : '');
    setProductoAdicionalSugerencias([]);
  };

  const prepararFinalizacionPorTarjeta = (tarjeta) => {
    const srv = serviciosEnProceso.find((s) => s.id === tarjeta.servicio_realizado_id);
    if (!srv) {
      toast.warning('No se encontró el servicio en proceso');
      return;
    }
    prepararFinalizacion(srv);
  };

  const agregarFilaAdicional = () => {
    setFinalizacion((prev) => ({
      ...prev,
      adicionales_servicio_items: [...(prev.adicionales_servicio_items || []), construirItemAdicional()],
    }));
  };

  const actualizarFilaAdicional = (key, cambios) => {
    setFinalizacion((prev) => ({
      ...prev,
      adicionales_servicio_items: (prev.adicionales_servicio_items || []).map((item) =>
        item.key === key ? { ...item, ...cambios } : item
      ),
    }));
  };

  const eliminarFilaAdicional = (key) => {
    setFinalizacion((prev) => ({
      ...prev,
      adicionales_servicio_items: (prev.adicionales_servicio_items || []).filter((item) => item.key !== key),
    }));
  };

  const seleccionarServicioAdicional = (key, servicio) => {
    setFinalizacion((prev) => ({
      ...prev,
      adicionales_servicio_items: (prev.adicionales_servicio_items || []).map((item) => {
        if (item.key !== key) return item;
        return {
          ...item,
          id: String(servicio.id),
          busqueda: formatServiceSearchLabel(servicio),
          valor: item.valor || String(toPesoInt(servicio.precio || 0)),
          estilista_id: esServicioShampoo(servicio.id) ? '' : item.estilista_id,
          aplica_porcentaje_establecimiento: esServicioShampoo(servicio.id) ? false : item.aplica_porcentaje_establecimiento,
          porcentaje_establecimiento: esServicioShampoo(servicio.id)
            ? '0'
            : esServicioDepilacion(servicio.id)
            ? (item.porcentaje_establecimiento || '30')
            : item.porcentaje_establecimiento,
        };
      }),
    }));
  };

  const crearCliente = async (e) => {
    e.preventDefault();
    if (!nuevoCliente.nombre.trim()) {
      toast.warning('El nombre del cliente es obligatorio');
      return;
    }

    try {
      setSaving(true);
      await clientesService.create({
        nombre: nuevoCliente.nombre.trim(),
        telefono: nuevoCliente.telefono.trim() || null,
        fecha_nacimiento: nuevoCliente.fecha_nacimiento || null,
      });
      toast.success('Cliente registrado');
      setNuevoCliente({ nombre: '', telefono: '', fecha_nacimiento: '' });
      setShowNuevoClienteModal(false);
      await cargarTodo();
    } catch (error) {
      toast.error('No se pudo registrar el cliente');
    } finally {
      setSaving(false);
    }
  };

  const solicitarConfirmacionFinalizar = (e) => {
    e.preventDefault();
    if (!servicioFinalizarId && (!finalizacion.estilista || !finalizacion.servicio)) {
      toast.warning('Selecciona empleado y servicio para facturar');
      return;
    }

    if (!servicioFinalizarId && estilistasOcupados.has(Number(finalizacion.estilista))) {
      toast.warning('Ese empleado ya está ocupado, finaliza primero su servicio en proceso.');
      return;
    }
    if (!finalizacion.precio_cobrado) {
      toast.warning('Ingresa el total cobrado del servicio');
      return;
    }

    if (servicioPrincipalPermiteReparto && finalizacion.tipo_reparto_establecimiento === 'porcentaje') {
      const pct = Number(finalizacion.valor_reparto_establecimiento || 0);
      if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
        toast.warning('El porcentaje de ganancia del establecimiento debe ser mayor a 0 y menor o igual a 100.');
        return;
      }
    }

    if (finalizacion.tiene_adicionales) {
      const items = finalizacion.adicionales_servicio_items || [];
      const itemsConContenido = items.filter((item) => {
        const id = String(item?.id || '').trim();
        const estilista = String(item?.estilista_id || '').trim();
        const valor = toPesoInt(item?.valor || 0);
        return Boolean(id || estilista || valor > 0);
      });

      const productoAdicional = finalizacion.adicional_otro_producto
        ? productos.find((p) => Number(p.id) === Number(finalizacion.adicional_otro_producto))
        : null;
      const tieneServicioAdicional = itemsConContenido.length > 0;
      const tieneProductoAdicional = Boolean(productoAdicional);

      if (!tieneServicioAdicional && !tieneProductoAdicional) {
        toast.warning('Selecciona al menos un adicional: servicio, producto o ambos');
        return;
      }

      if (tieneServicioAdicional) {
        const itemInvalido = itemsConContenido.find(
          (item) => {
            if (!item.id || toPesoInt(item.valor || 0) <= 0) return true;
            if (esServicioShampoo(item.id)) return false;
            return !item.estilista_id;
          }
        );
        if (itemInvalido) {
          toast.warning('Cada servicio adicional debe tener servicio, empleado y valor mayor a 0');
          return;
        }

        const porcentajeInvalido = itemsConContenido.find((item) => {
          if (!item.aplica_porcentaje_establecimiento) return false;
          const pct = Number(item.porcentaje_establecimiento || 0);
          return !Number.isFinite(pct) || pct <= 0 || pct > 100;
        });
        if (porcentajeInvalido) {
          toast.warning('El porcentaje para establecimiento debe ser mayor a 0 y menor o igual a 100');
          return;
        }
      }

      if (tieneProductoAdicional) {
        const qtyProdAd = toPositiveInt(finalizacion.adicional_otro_cantidad || 0);
        if (qtyProdAd <= 0) {
          toast.warning('La cantidad del producto adicional debe ser mayor a 0');
          return;
        }

        const aplicaInsumoPestanas =
          servicioPrincipalEsPestanas
          && finalizacion.tipo_reparto_establecimiento === 'porcentaje'
          && Number(finalizacion.valor_reparto_establecimiento || 0) > 0;

        if (!aplicaInsumoPestanas && !finalizacion.adicional_otro_estilista) {
          toast.warning('Selecciona el empleado que gana la comisión del producto adicional');
          return;
        }

        const stockDisponible = Number(productoAdicional.stock || 0);
        if (qtyProdAd > stockDisponible) {
          toast.warning(`Stock insuficiente para producto adicional. Disponible: ${stockDisponible}`);
          return;
        }
      }
    }

    if (finalizacion.medio_pago === 'efectivo') {
      const valorRecibido = toPesoInt(finalizacion.valor_recibido || 0);
      if (valorRecibido <= 0) {
        toast.warning('Ingresa el valor recibido en efectivo');
        return;
      }
      if (valorRecibido < totalFinalizacion) {
        toast.warning('El valor recibido no puede ser menor al total a cobrar');
        return;
      }
    }

    setShowConfirmacionFinalizar(true);
  };

  const finalizarServicio = async () => {
    setShowConfirmacionFinalizar(false);
    try {
      setSaving(true);
      const itemsNormalizados = finalizacion.tiene_adicionales
        ? (finalizacion.adicionales_servicio_items || [])
            .filter((item) => {
              if (!item.id || toPesoInt(item.valor || 0) <= 0) return false;
              if (esServicioShampoo(item.id)) return true;
              return Boolean(item.estilista_id);
            })
            .map((item) => ({
              id: Number(item.id),
              estilista_id: esServicioShampoo(item.id) ? null : Number(item.estilista_id),
              valor: toPesoInt(item.valor || 0),
              aplica_porcentaje_establecimiento: esServicioShampoo(item.id)
                ? false
                : Boolean(item.aplica_porcentaje_establecimiento),
              porcentaje_establecimiento: esServicioShampoo(item.id)
                ? 0
                : Boolean(item.aplica_porcentaje_establecimiento)
                ? Number(item.porcentaje_establecimiento || 0)
                : 0,
            }))
        : [];
      const flagsLegacy = mapearFlagsLegacyAdicionales(itemsNormalizados.map((x) => x.id));
      const qtyProductoAdicional = toPositiveInt(finalizacion.adicional_otro_cantidad || 0);
      const productoAdicionalId = finalizacion.tiene_adicionales && finalizacion.adicional_otro_producto
        ? Number(finalizacion.adicional_otro_producto)
        : null;
      const aplicaInsumoPestanas =
        servicioPrincipalEsPestanas
        && finalizacion.tipo_reparto_establecimiento === 'porcentaje'
        && Number(finalizacion.valor_reparto_establecimiento || 0) > 0;
      const tipoRepartoPrincipal = servicioPrincipalEsShampoo
        ? 'porcentaje'
        : (servicioPrincipalPermiteReparto ? finalizacion.tipo_reparto_establecimiento : '');
      const valorRepartoPrincipal = servicioPrincipalEsShampoo
        ? 100
        : (servicioPrincipalPermiteReparto && finalizacion.tipo_reparto_establecimiento === 'porcentaje'
          ? Number(finalizacion.valor_reparto_establecimiento || 0)
          : null);

      const payloadFinalizacion = {
        precio_cobrado: toPesoInt(finalizacion.precio_cobrado),
        medio_pago: finalizacion.medio_pago,
        tipo_reparto_establecimiento: tipoRepartoPrincipal || null,
        valor_reparto_establecimiento: valorRepartoPrincipal,
        tiene_adicionales: finalizacion.tiene_adicionales,
        adicionales_servicio_ids: finalizacion.tiene_adicionales ? itemsNormalizados.map((item) => item.id) : [],
        adicionales_servicio_items: itemsNormalizados,
        adicional_shampoo: finalizacion.tiene_adicionales ? flagsLegacy.adicional_shampoo : false,
        adicional_guantes: finalizacion.tiene_adicionales ? flagsLegacy.adicional_guantes : false,
        adicional_otro_producto: productoAdicionalId,
        adicional_otro_estilista: (productoAdicionalId && !aplicaInsumoPestanas) ? Number(finalizacion.adicional_otro_estilista) : null,
        adicional_otro_cantidad: productoAdicionalId ? qtyProductoAdicional : 1,
        adicional_otro_descuento_empleado: false,
        adicional_otro_precio_unitario: null,
        notas: finalizacion.notas || null,
      };

      const res = servicioFinalizarId
        ? await serviciosRealizadosService.finalizar(servicioFinalizarId, payloadFinalizacion)
        : await serviciosRealizadosService.create({
            ...payloadFinalizacion,
            estilista: Number(finalizacion.estilista),
            servicio: Number(finalizacion.servicio),
            estado: 'finalizado',
          });

      const estilistaFinalizado = estilistas.find((e) => e.id === Number(res?.estilista));
      const usaCobroFijoEspacio = (estilistaFinalizado?.tipo_cobro_espacio || '') === 'costo_fijo_neto';

      customerDisplayService.publishServiceSale(res);

      toast.success(
        usaCobroFijoEspacio
          ? `Factura guardada. Base empleado: ${formatCOP(res.monto_estilista || 0)} | Cobro fijo de espacio se aplica en Reportes por día trabajado.`
          : `Factura guardada. Empleado: ${formatCOP(res.monto_estilista || 0)} | Establecimiento: ${formatCOP(
              res.monto_establecimiento || 0
            )}`
      );

      if (finalizacion.medio_pago === 'efectivo') {
        toast.info(`Devueltas al cliente: ${formatCOP(devueltaServicio)}`);
      }

      try {
        await ticketPrintService.printServiceSaleAndOpenDrawer(res);
        toast.success('Ticket de servicio impreso y caja abierta');
      } catch (printError) {
        toast.error(printError.message || 'El servicio se finalizo, pero no se pudo imprimir el ticket');
      }

      setServicioFinalizarId('');
      setShowFinalizarModal(false);
      setFinalizacion({
        estilista: '',
        servicio: '',
        precio_cobrado: '',
        medio_pago: 'efectivo',
        valor_recibido: '',
        tipo_reparto_establecimiento: '',
        valor_reparto_establecimiento: '30',
        tiene_adicionales: false,
        adicionales_servicio_items: [],
        adicional_otro_producto: '',
        adicional_otro_cantidad: '1',
        adicional_otro_estilista: '',
        notas: '',
      });
      setProductoAdicionalBusqueda('');
      setProductoAdicionalSugerencias([]);
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo finalizar el servicio';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const abrirKeypad = (field, itemKey = null) => {
    setKeypad({ visible: true, field, itemKey });
  };

  const abrirSearchKeyboard = (field) => {
    setSearchKeyboard({ visible: true, field });
  };

  const cerrarSearchKeyboard = () => {
    setSearchKeyboard({ visible: false, field: '' });
  };

  const obtenerValorSearchKeyboard = () => {
    if (!searchKeyboard.field) return '';
    if (searchKeyboard.field === 'venta_busqueda') return String(ventaBusqueda || '');
    if (searchKeyboard.field === 'producto_adicional_busqueda') return String(productoAdicionalBusqueda || '');
    return '';
  };

  const asignarValorSearchKeyboard = (value) => {
    if (searchKeyboard.field === 'venta_busqueda') {
      setVentaBusqueda(value);
      return;
    }
    if (searchKeyboard.field === 'producto_adicional_busqueda') {
      setProductoAdicionalBusqueda(value);
      setFinalizacion((p) => ({ ...p, adicional_otro_producto: '' }));
    }
  };

  const cerrarKeypad = () => {
    setKeypad({ visible: false, field: '', itemKey: null });
  };

  const obtenerValorKeypad = () => {
    if (!keypad.field) return '';
    if (keypad.field === 'precio_cobrado') return String(finalizacion.precio_cobrado || '');
    if (keypad.field === 'valor_recibido') return String(finalizacion.valor_recibido || '');
    if (keypad.field === 'adicional_valor' && keypad.itemKey) {
      const item = (finalizacion.adicionales_servicio_items || []).find((x) => x.key === keypad.itemKey);
      return String(item?.valor || '');
    }
    return '';
  };

  const asignarValorKeypad = (value) => {
    const limpio = sanitizePesoInput(value);
    if (keypad.field === 'precio_cobrado') {
      setFinalizacion((p) => ({ ...p, precio_cobrado: limpio }));
      return;
    }
    if (keypad.field === 'valor_recibido') {
      setFinalizacion((p) => ({ ...p, valor_recibido: limpio }));
      return;
    }
    if (keypad.field === 'adicional_valor' && keypad.itemKey) {
      actualizarFilaAdicional(keypad.itemKey, { valor: limpio });
    }
  };

  const pulsarKeypad = (token) => {
    const actual = obtenerValorKeypad();
    if (token === 'C') {
      asignarValorKeypad('');
      return;
    }
    if (token === 'DEL') {
      asignarValorKeypad(actual.slice(0, -1));
      return;
    }
    if (token === '000') {
      asignarValorKeypad(`${actual}000`);
      return;
    }
    asignarValorKeypad(`${actual}${token}`);
  };

  const seleccionarProductoCaja = (producto) => {
    if (Number(producto?.stock || 0) <= 0) {
      toast.warning('Este producto está agotado y no se puede seleccionar.');
      return;
    }
    setProductoVentaSeleccionado(producto);
    // En caja dejamos el buscador limpio para escaneos consecutivos.
    setVentaBusqueda('');
    setVentaSugerencias([]);
    setVentaForm((prev) => ({ ...prev, precio_unitario: String(toPesoInt(producto.precio_venta || 0)) }));
  };

  const agregarAlCarrito = () => {
    if (!productoVentaSeleccionado) {
      toast.warning('Selecciona un producto');
      return;
    }
    const cantidad = toPositiveInt(ventaForm.cantidad || 0);
    const precioUnitario = toPesoInt(ventaForm.precio_unitario || 0);
    if (cantidad <= 0 || precioUnitario <= 0) {
      toast.warning('Cantidad y valor unitario deben ser mayores a cero');
      return;
    }
    const stockActual = Number(productoVentaSeleccionado.stock || 0);
    const reservado = cantidadReservadaEnCarrito(productoVentaSeleccionado.id);
    const disponible = stockActual - reservado;
    if (disponible <= 0) {
      toast.warning('No hay stock disponible para este producto.');
      return;
    }
    if (cantidad > disponible) {
      toast.warning(`Stock insuficiente para agregar. Disponible: ${disponible}`);
      return;
    }
    if (!validarPrecioMinimoProducto(productoVentaSeleccionado, precioUnitario)) return;
    setCarrito((prev) => [
      ...prev,
      { _key: Date.now(), producto: productoVentaSeleccionado, cantidad, precio_unitario: precioUnitario },
    ]);
    setProductoVentaSeleccionado(null);
    setVentaBusqueda('');
    setVentaForm((prev) => ({ ...prev, cantidad: '1', precio_unitario: '' }));
    setVentaSugerencias([]);
  };

  const registrarVentaCaja = async (e) => {
    e.preventDefault();
    if (!puedeFacturar) {
      toast.warning('Solo administrador o gerente pueden crear facturas');
      return;
    }

    if (esConsumoEmpleado && !ventaForm.estilista) {
      toast.warning('Selecciona el empleado para registrar el consumo');
      return;
    }

    // Build items: carrito items + current product selection if filled
    const itemsParaRegistrar = [...carrito];
    if (productoVentaSeleccionado) {
      const cantidad = toPositiveInt(ventaForm.cantidad || 0);
      const precioUnitario = toPesoInt(ventaForm.precio_unitario || 0);
      if (cantidad > 0 && precioUnitario > 0) {
        if (!validarPrecioMinimoProducto(productoVentaSeleccionado, precioUnitario)) {
          return;
        }
        itemsParaRegistrar.push({ _key: 'current', producto: productoVentaSeleccionado, cantidad, precio_unitario: precioUnitario });
      }
    }

    if (itemsParaRegistrar.length === 0) {
      toast.warning('Agrega al menos un producto al carrito');
      return;
    }

    const totalCobroVenta = itemsParaRegistrar.reduce(
      (acc, item) => acc + (Number(item.cantidad || 0) * Number(item.precio_unitario || 0)),
      0
    );

    if (!esConsumoEmpleado && ventaForm.medio_pago === 'efectivo') {
      const valorRecibido = toPesoInt(ventaForm.valor_recibido || 0);
      if (valorRecibido <= 0) {
        toast.warning('Ingresa el valor recibido en efectivo');
        return;
      }
      if (valorRecibido < totalCobroVenta) {
        toast.warning('El valor recibido no puede ser menor al total de la venta');
        return;
      }
    }

    const cantidadPorProducto = new Map();
    for (const item of itemsParaRegistrar) {
      const pid = Number(item.producto?.id || item.producto);
      const qty = Number(item.cantidad || 0);
      cantidadPorProducto.set(pid, Number(cantidadPorProducto.get(pid) || 0) + qty);
    }
    for (const [pid, qty] of cantidadPorProducto.entries()) {
      const prod = productos.find((p) => Number(p.id) === Number(pid));
      const stock = Number(prod?.stock || 0);
      if (qty > stock) {
        toast.warning(`Stock insuficiente para ${prod?.nombre || 'producto'}. Disponible: ${stock}`);
        return;
      }
    }

    try {
      setSaving(true);
      const transaccion = await ventasService.createTransaction({
        cliente_nombre: ventaForm.cliente_nombre.trim() || null,
        estilista: ventaForm.estilista ? Number(ventaForm.estilista) : null,
        medio_pago: esConsumoEmpleado ? 'efectivo' : ventaForm.medio_pago,
        tipo_operacion: esConsumoEmpleado ? 'consumo_empleado' : 'venta',
        items: itemsParaRegistrar.map((item) => ({
          producto: item.producto.id,
          cantidad: item.cantidad,
          precio_unitario: item.precio_unitario,
        })),
      });

      const ventaPrincipal = transaccion?.venta_principal || null;
      if (ventaPrincipal) {
        customerDisplayService.publishProductSale(ventaPrincipal);
      }

      const deudaInfo = transaccion?.deuda;
      if (esConsumoEmpleado) {
        toast.success(
          `Consumo registrado ${transaccion?.numero_factura || ''}. Saldo pendiente: ${formatCOP(deudaInfo?.saldo_pendiente || 0)}`
        );
      } else {
        toast.success(`Factura ${transaccion?.numero_factura || ''} registrada con ${itemsParaRegistrar.length} producto(s)`);
        if (ventaForm.medio_pago === 'efectivo') {
          const devuelta = Math.max(0, toPesoInt(ventaForm.valor_recibido || 0) - totalCobroVenta);
          toast.info(`Devueltas al cliente: ${formatCOP(devuelta)}`);
        }
      }

      try {
        if (ventaPrincipal) {
          const ventaParaImprimir = {
            ...ventaPrincipal,
            numero_factura: transaccion?.numero_factura || ventaPrincipal.numero_factura,
            fecha_hora: ventaPrincipal.fecha_hora || new Date().toISOString(),
            cliente_nombre: ventaForm.cliente_nombre || ventaPrincipal.cliente_nombre,
            estilista_nombre: estilistas.find((e) => Number(e.id) === Number(ventaForm.estilista))?.nombre || ventaPrincipal.estilista_nombre,
            medio_pago: esConsumoEmpleado ? 'efectivo' : ventaForm.medio_pago,
            total: totalCobroVenta,
            items: itemsParaRegistrar.map((item) => ({
              producto_nombre: item.producto?.nombre || item.producto?.descripcion || 'Producto',
              cantidad: item.cantidad,
              precio_unitario: item.precio_unitario,
              total: Number(item.cantidad || 0) * Number(item.precio_unitario || 0),
            })),
          };

          await ticketPrintService.printProductSaleAndOpenDrawer(ventaParaImprimir);
          toast.success('Ticket impreso y caja abierta');
        }
      } catch (printError) {
        toast.error(printError.message || 'La(s) venta(s) se guardaron, pero no se pudo imprimir el ticket');
      }

      setVentaForm({ cliente_nombre: '', estilista: '', medio_pago: 'efectivo', valor_recibido: '', cantidad: '1', precio_unitario: '' });
      setVentaBusqueda('');
      setProductoVentaSeleccionado(null);
      setVentaSugerencias([]);
      setCarrito([]);
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.cantidad?.[0] || error?.response?.data?.detail || 'No se pudo registrar la venta';
      toast.error(String(msg));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Operación diaria</h1>
          <p className="text-gray-600 mt-1">Gestiona servicios en curso y caja rápida de venta</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarTodo} disabled={loading}>
            <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          <button className="btn-secondary inline-flex items-center gap-2" onClick={abrirTecladoWindows}>
            Teclado Windows
          </button>
          <button className="btn-primary inline-flex items-center gap-2" onClick={() => setShowNuevoClienteModal(true)}>
            <FiPlus /> Nuevo cliente
          </button>
        </div>
      </div>

      <div className="card p-2">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <button className={modoVista === 'servicios' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('servicios')}>
            Modo servicios
          </button>
          <button className={modoVista === 'ventas' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('ventas')}>
            Modo venta productos
          </button>
          <button className={modoVista === 'consumo_empleado' ? 'btn-primary' : 'btn-secondary'} onClick={() => setModoVista('consumo_empleado')}>
            Consumo Empleado
          </button>
        </div>
      </div>

      {(modoVista === 'ventas' || modoVista === 'consumo_empleado') && (
        <div className="card space-y-4">
          <h2 className="card-header">
            {esConsumoEmpleado ? 'Caja registradora - Consumo de empleado' : 'Caja registradora - Venta de productos'}
          </h2>
          {!puedeFacturar && <p className="text-amber-700">Este perfil solo puede visualizar. Para facturar usa Administrador o Gerente.</p>}
          {esConsumoEmpleado && (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
              Este modo registra productos usados por el empleado y crea una cuenta por cobrar automática.
            </p>
          )}

          <form className="grid grid-cols-1 md:grid-cols-4 gap-3" onSubmit={registrarVentaCaja}>
            <div className="md:col-span-4 relative">
              <label className="block text-sm text-gray-600 mb-1">Escanear código de barras o buscar por marca / descripción / nombre</label>
              <input
                className="input-field"
                placeholder="Ej: L'Oréal, hidratante, shampoo o 770123456"
                inputMode="search"
                enterKeyHint="search"
                value={ventaBusqueda}
                onChange={(e) => {
                  const valor = e.target.value;
                  setVentaBusqueda(valor);

                  const codigo = String(valor || '').trim();
                  if (!codigo) return;

                  const exacto = productos.find((p) => String(p.codigo_barras || '').trim() === codigo);
                  if (exacto) {
                    seleccionarProductoCaja(exacto);
                  }
                }}
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  className="btn-secondary !px-5 !py-3 inline-flex items-center gap-3 text-lg font-bold border-2 border-indigo-300 bg-indigo-50 text-indigo-900 hover:bg-indigo-100"
                  onClick={() => abrirSearchKeyboard('venta_busqueda')}
                >
                  <span className="text-2xl" aria-hidden="true">⌨</span>
                  <span>Abrir teclado A-Z</span>
                </button>
              </div>
              {ventaSugerencias.length > 0 && (
                <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
                  {ventaSugerencias.map((p) => (
                    (() => {
                      const estadoStock = getProductoStockEstado(p);
                      return (
                    <button
                      key={p.id}
                      type="button"
                      className={`w-full text-left px-3 py-2 hover:bg-gray-50 ${estadoStock.key === 'agotado' ? 'opacity-60 cursor-not-allowed' : ''}`}
                      disabled={estadoStock.key === 'agotado'}
                      onClick={() => seleccionarProductoCaja(p)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span>{formatProductSearchLabel(p)} - {formatCOP(p.precio_venta || 0)} (stock {p.stock})</span>
                        <span className={`text-xs px-2 py-1 rounded-full border ${estadoStock.badgeClass}`}>{estadoStock.label}</span>
                      </div>
                    </button>
                      );
                    })()
                  ))}
                </div>
              )}
            </div>

            <input
              className="input-field"
              placeholder={esConsumoEmpleado ? 'Detalle opcional (ej. uso interno)' : 'Cliente'}
              value={ventaForm.cliente_nombre}
              onChange={(e) => setVentaForm((p) => ({ ...p, cliente_nombre: e.target.value }))}
            />

            <select className="input-field" value={ventaForm.estilista} onChange={(e) => setVentaForm((p) => ({ ...p, estilista: e.target.value }))}>
              <option value="">{esConsumoEmpleado ? 'Empleado (obligatorio)' : 'Empleado (opcional)'}</option>
              {estilistas.map((e) => (
                <option key={e.id} value={e.id}>{e.nombre}</option>
              ))}
            </select>

            {!esConsumoEmpleado && (
              <select className="input-field" value={ventaForm.medio_pago} onChange={(e) => setVentaForm((p) => ({ ...p, medio_pago: e.target.value }))}>
                {mediosPago.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            )}

            {!esConsumoEmpleado && ventaForm.medio_pago === 'efectivo' && (
              <input
                className="input-field"
                type="number"
                min="0"
                step="1"
                placeholder="Valor recibido"
                value={ventaForm.valor_recibido || ''}
                onChange={(e) => setVentaForm((p) => ({ ...p, valor_recibido: sanitizePesoInput(e.target.value) }))}
              />
            )}

            <input className="input-field" type="number" min="1" placeholder="Cantidad" value={ventaForm.cantidad} onChange={(e) => setVentaForm((p) => ({ ...p, cantidad: e.target.value }))} />
            <input className="input-field" type="number" min="0" step="1" placeholder="Valor unitario" value={ventaForm.precio_unitario} onChange={(e) => setVentaForm((p) => ({ ...p, precio_unitario: sanitizePesoInput(e.target.value) }))} />

            <div className="md:col-span-4 rounded-lg border border-blue-200 bg-blue-50 p-4 flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-800">Producto seleccionado</p>
                <p className="font-semibold text-blue-950">{productoVentaSeleccionado ? formatProductSearchLabel(productoVentaSeleccionado) : 'Ninguno'}</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-blue-800">Total unitario</p>
                <p className="text-2xl font-bold text-blue-950">{formatCOP(totalVentaCaja)}</p>
              </div>
            </div>

            <div className="md:col-span-4">
              <button
                className="btn-secondary w-full inline-flex items-center justify-center gap-2"
                type="button"
                onClick={agregarAlCarrito}
                disabled={!productoVentaSeleccionado || Number(productoVentaSeleccionado?.stock || 0) <= 0}
              >
                <FiPlus /> Agregar al carrito
              </button>
            </div>

            {carrito.length > 0 && (
              <div className="md:col-span-4 space-y-2">
                <p className="text-sm font-medium text-gray-700">
                  Carrito ({carrito.length} {carrito.length === 1 ? 'producto' : 'productos'})
                </p>
                {carrito.map((item) => (
                  <div key={item._key} className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
                    <div>
                      <p className="font-medium text-sm">{formatProductSearchLabel(item.producto)}</p>
                      <p className="text-xs text-gray-500">x{item.cantidad} × {formatCOP(item.precio_unitario)}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <p className="font-bold text-gray-900">{formatCOP(item.cantidad * item.precio_unitario)}</p>
                      <button
                        type="button"
                        className="text-red-500 hover:text-red-700"
                        onClick={() => setCarrito((prev) => prev.filter((i) => i._key !== item._key))}
                      >
                        <FiTrash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
                <div className="flex justify-between items-center px-3 py-2 bg-gray-100 rounded-lg">
                  <p className="font-medium text-gray-700">Total carrito</p>
                  <p className="font-bold text-lg text-gray-900">{formatCOP(totalCarrito)}</p>
                </div>
              </div>
            )}

            {!esConsumoEmpleado && ventaForm.medio_pago === 'efectivo' && (
              <div className="md:col-span-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 flex items-center justify-between">
                <p className="text-sm text-emerald-800">Devueltas al cliente</p>
                <p className="font-bold text-emerald-900">{formatCOP(devueltaVenta)}</p>
              </div>
            )}

            <div className="md:col-span-4">
              <button className="btn-primary w-full" type="submit" disabled={saving || !puedeFacturar}>
                {saving
                  ? 'Guardando...'
                  : carrito.length > 0
                  ? `${esConsumoEmpleado ? 'Registrar consumo' : 'Registrar'} ${carrito.length + (productoVentaSeleccionado ? 1 : 0)} producto(s)`
                  : esConsumoEmpleado ? 'Registrar consumo' : 'Registrar venta'}
              </button>
            </div>
          </form>
        </div>
      )}

      {modoVista === 'servicios' && (
      <>
      <div className="card border border-dashed border-gray-300 bg-gray-50">
        <p className="text-gray-700">Facturación rápida: selecciona empleado libre y registra el servicio en un solo paso.</p>
      </div>

      <div className="card">
        <h2 className="card-header">Panel de empleados libres y ocupados</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {estadoEstilistas.map((item) => (
            <div key={item.estilista_id} className={`rounded-lg border p-4 ${item.estado === 'ocupado' ? 'border-red-300 bg-red-50' : 'border-green-300 bg-green-50'}`}>
              <p className="font-semibold">{item.estilista_nombre}</p>
              <p className="text-sm mt-1">Estado: <span className="font-medium capitalize">{item.estado}</span></p>
              {item.estado === 'ocupado' && (
                <p className="text-sm mt-1">Servicio: {item.servicio_nombre}{item.cliente_nombre ? ` - ${item.cliente_nombre}` : ''}</p>
              )}
              <div className="mt-3">
                {item.estado === 'libre' ? (
                  <button className="btn-primary !px-3 !py-2 w-full inline-flex items-center justify-center gap-2" onClick={() => abrirFacturacionDirecta(item.estilista_id)}>
                    <FiScissors /> Facturar servicio
                  </button>
                ) : (
                  <button className="btn-danger !px-3 !py-2 w-full inline-flex items-center justify-center gap-2" onClick={() => prepararFinalizacionPorTarjeta(item)}>
                    <FiCheckCircle /> Finalizar servicio
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card space-y-4">
        <h2 className="card-header">Servicios en proceso</h2>
        {serviciosEnProceso.length === 0 && <p className="text-gray-600">No hay servicios en proceso.</p>}
        {serviciosEnProceso.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Empleado</th>
                  <th className="px-6 py-3 text-left">Servicio</th>
                  <th className="px-6 py-3 text-left">Cliente</th>
                  <th className="px-6 py-3 text-left">Precio base</th>
                  <th className="px-6 py-3 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosEnProceso.map((srv) => (
                  <tr key={srv.id} className="hover:bg-gray-50">
                    <td className="table-cell">{srv.estilista_nombre}</td>
                    <td className="table-cell">{srv.servicio_nombre}</td>
                    <td className="table-cell">{srv.cliente_nombre || '-'}</td>
                    <td className="table-cell">{formatCOP(srv.precio_cobrado || 0)}</td>
                    <td className="table-cell text-right">
                      <button className="btn-primary !px-3 !py-2" onClick={() => prepararFinalizacion(srv)}>
                        Finalizar
                      </button>
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

      <ModalForm
        isOpen={showNuevoClienteModal}
        onClose={() => setShowNuevoClienteModal(false)}
        title="Nuevo cliente"
        subtitle="Registro rápido"
        size="md"
      >
        <form className="space-y-3" onSubmit={crearCliente}>
          <input className="input-field" placeholder="Nombre del cliente" value={nuevoCliente.nombre} onChange={(e) => setNuevoCliente((p) => ({ ...p, nombre: e.target.value }))} />
          <input className="input-field" placeholder="Teléfono" value={nuevoCliente.telefono} onChange={(e) => setNuevoCliente((p) => ({ ...p, telefono: e.target.value }))} />
          <input className="input-field" type="date" value={nuevoCliente.fecha_nacimiento} onChange={(e) => setNuevoCliente((p) => ({ ...p, fecha_nacimiento: e.target.value }))} />
          <div className="flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Guardar cliente</button>
            <button className="btn-secondary" type="button" onClick={() => setShowNuevoClienteModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <ModalForm
        isOpen={showFinalizarModal}
        onClose={() => setShowFinalizarModal(false)}
        title="Finalizar servicio"
        subtitle="Facturación rápida con adicionales"
        size="lg"
      >
        <form className="grid grid-cols-1 md:grid-cols-3 gap-3" onSubmit={solicitarConfirmacionFinalizar}>
          <select
            className="input-field"
            value={finalizacion.estilista || ''}
            disabled={Boolean(servicioFinalizarId)}
            onChange={(e) => setFinalizacion((p) => ({ ...p, estilista: e.target.value }))}
          >
            <option value="">Empleado</option>
            {estilistas.map((e) => (
              <option key={e.id} value={e.id}>{e.nombre}</option>
            ))}
          </select>

          <select
            className="input-field"
            value={finalizacion.servicio || ''}
            disabled={Boolean(servicioFinalizarId)}
            onChange={(e) => setFinalizacion((p) => ({ ...p, servicio: e.target.value }))}
          >
            <option value="">Servicio</option>
            {servicios.filter((s) => (s.activo ?? true)).map((srv) => (
              <option key={srv.id} value={srv.id}>{formatServiceCompactLabel(srv)}</option>
            ))}
          </select>

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 md:col-span-2">
            <p><strong>Servicio:</strong> {servicioPrincipalSeleccionado?.servicio_nombre || servicioPrincipalSeleccionado?.nombre || 'Sin seleccionar'}</p>
            <p><strong>Cliente:</strong> {servicioEnProcesoSeleccionado?.cliente_nombre || 'No registrado'}</p>
          </div>

          <div className="md:col-span-2 flex gap-2">
            <input
              className="input-field"
              type="text"
              inputMode="numeric"
              readOnly
              placeholder="Total servicio"
              value={finalizacion.precio_cobrado || ''}
              onClick={() => abrirKeypad('precio_cobrado')}
            />
            <button type="button" className="btn-secondary !px-3 inline-flex items-center gap-1" onClick={() => abrirKeypad('precio_cobrado')}>
              <FiDollarSign />
            </button>
          </div>

          <select className="input-field" value={finalizacion.medio_pago} onChange={(e) => setFinalizacion((p) => ({ ...p, medio_pago: e.target.value }))}>
            {mediosPago.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>

          {finalizacion.medio_pago === 'efectivo' && (
            <div className="flex gap-2">
              <input
                className="input-field"
                type="text"
                inputMode="numeric"
                readOnly
                placeholder="Valor recibido"
                value={finalizacion.valor_recibido || ''}
                onClick={() => abrirKeypad('valor_recibido')}
              />
              <button type="button" className="btn-secondary !px-3 inline-flex items-center gap-1" onClick={() => abrirKeypad('valor_recibido')}>
                <FiDollarSign />
              </button>
            </div>
          )}

          <input className="input-field" placeholder="Notas finales (opcional)" value={finalizacion.notas} onChange={(e) => setFinalizacion((p) => ({ ...p, notas: e.target.value }))} />

          {servicioPrincipalEsShampoo && (
            <div className="md:col-span-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Shampoo en servicio principal: la ganancia se asigna 100% al establecimiento.
            </div>
          )}

          {servicioPrincipalPermiteReparto && !servicioPrincipalEsShampoo && (
            <>
              <label className="md:col-span-3 flex items-start gap-3 rounded-xl border-2 border-emerald-300 bg-emerald-50 p-4 shadow-sm cursor-pointer">
                <input
                  className="mt-1 h-5 w-5"
                  type="checkbox"
                  checked={finalizacion.tipo_reparto_establecimiento === 'porcentaje'}
                  onChange={(e) =>
                    setFinalizacion((p) => ({
                      ...p,
                      tipo_reparto_establecimiento: e.target.checked ? 'porcentaje' : '',
                      valor_reparto_establecimiento: e.target.checked
                        ? (p.valor_reparto_establecimiento || '30')
                        : '30',
                    }))
                  }
                />
                <div className="flex-1">
                  <p className="text-base font-bold text-emerald-900 inline-flex items-center gap-2">
                    <FiDollarSign className="text-emerald-700" /> Aplicar ganancia para establecimiento en servicio principal
                  </p>
                  <p className="text-sm text-emerald-800 mt-1">
                    Activa esta opción para asignar porcentaje de ganancia al establecimiento en este servicio.
                  </p>
                </div>
              </label>
              <input
                className="input-field"
                type="number"
                min="0"
                max="100"
                step="0.01"
                placeholder="% establecimiento"
                value={finalizacion.valor_reparto_establecimiento || ''}
                disabled={finalizacion.tipo_reparto_establecimiento !== 'porcentaje'}
                onChange={(e) =>
                  setFinalizacion((p) => ({ ...p, valor_reparto_establecimiento: e.target.value }))
                }
              />
            </>
          )}

          <label className="md:col-span-3 flex items-start gap-3 rounded-xl border-2 border-indigo-300 bg-indigo-50 p-4 shadow-sm cursor-pointer">
            <input
              className="mt-1 h-5 w-5"
              type="checkbox"
              checked={finalizacion.tiene_adicionales}
              onChange={(e) =>
                setFinalizacion((p) => ({
                  ...p,
                  tiene_adicionales: e.target.checked,
                  adicionales_servicio_items: e.target.checked ? p.adicionales_servicio_items : [],
                  adicional_otro_producto: e.target.checked ? p.adicional_otro_producto : '',
                  adicional_otro_cantidad: e.target.checked ? p.adicional_otro_cantidad : '1',
                  adicional_otro_estilista: e.target.checked ? p.adicional_otro_estilista : '',
                }))
              }
            />
            <div className="flex-1">
              <p className="text-base font-bold text-indigo-900 inline-flex items-center gap-2">
                <FiPlus className="text-indigo-700" /> Este servicio tiene adicionales
              </p>
              <p className="text-sm text-indigo-800 mt-1">Activa esta opción para agregar servicios o productos adicionales en la misma factura.</p>
            </div>
          </label>

          {finalizacion.tiene_adicionales && (
            <>
              <div className="md:col-span-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-medium text-blue-900">Servicios adicionales realizados</p>
                  <button type="button" className="btn-secondary !px-3 !py-1" onClick={agregarFilaAdicional}>
                    <FiPlus className="inline mr-1" /> Agregar adicional
                  </button>
                </div>

                {(finalizacion.adicionales_servicio_items || []).length === 0 && (
                  <p className="text-xs text-blue-800">Puedes agregar servicios adicionales, un producto adicional, o ambos.</p>
                )}

                <div className="space-y-3">
                  {(finalizacion.adicionales_servicio_items || []).map((item) => {
                    return (
                      <div key={item.key} className="rounded-lg border border-blue-200 bg-white p-3">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-5">
                            <select
                              className="input-field"
                              value={item.id || ''}
                              onChange={(e) => {
                                const srvAd = serviciosAdicionalesConfigurados.find((s) => Number(s.id) === Number(e.target.value));
                                if (srvAd) {
                                  seleccionarServicioAdicional(item.key, srvAd);
                                } else {
                                  actualizarFilaAdicional(item.key, { id: '', busqueda: '' });
                                }
                              }}
                            >
                              <option value="">Servicio adicional</option>
                              {serviciosAdicionalesConfigurados.map((srvAd) => (
                                <option key={srvAd.id} value={srvAd.id}>
                                  {formatServiceCompactLabel(srvAd)} - {formatCOP(srvAd.precio || 0)}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div className="md:col-span-4">
                            <select
                              className="input-field"
                              value={item.estilista_id || ''}
                              disabled={esServicioShampoo(item.id)}
                              onChange={(e) => actualizarFilaAdicional(item.key, { estilista_id: e.target.value })}
                            >
                              <option value="">{esServicioShampoo(item.id) ? 'No aplica (ganancia establecimiento)' : 'Empleado que realiza el adicional'}</option>
                              {estilistas.map((e) => (
                                <option key={e.id} value={e.id}>{e.nombre}</option>
                              ))}
                            </select>
                          </div>

                          <div className="md:col-span-2 flex gap-2">
                            <input
                              className="input-field"
                              type="text"
                              inputMode="numeric"
                              readOnly
                              placeholder="Valor"
                              value={item.valor || ''}
                              onClick={() => abrirKeypad('adicional_valor', item.key)}
                            />
                            <button type="button" className="btn-secondary !px-2" onClick={() => abrirKeypad('adicional_valor', item.key)}>
                              <FiDollarSign />
                            </button>
                          </div>

                          <div className="md:col-span-1 flex items-center justify-center">
                            <button
                              type="button"
                              className="text-red-600 hover:text-red-800"
                              onClick={() => eliminarFilaAdicional(item.key)}
                              title="Eliminar adicional"
                            >
                              <FiTrash2 />
                            </button>
                          </div>

                          <div className="md:col-span-8">
                            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                              <input
                                type="checkbox"
                                checked={esServicioShampoo(item.id) ? false : Boolean(item.aplica_porcentaje_establecimiento)}
                                disabled={esServicioShampoo(item.id)}
                                onChange={(e) =>
                                  actualizarFilaAdicional(item.key, {
                                    aplica_porcentaje_establecimiento: e.target.checked,
                                    porcentaje_establecimiento: e.target.checked
                                      ? (item.porcentaje_establecimiento || '30')
                                      : '0',
                                  })
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
                              value={item.porcentaje_establecimiento || ''}
                              disabled={esServicioShampoo(item.id) || !item.aplica_porcentaje_establecimiento}
                              onChange={(e) =>
                                actualizarFilaAdicional(item.key, {
                                  porcentaje_establecimiento: e.target.value,
                                })
                              }
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {serviciosAdicionalesConfigurados.length === 0 && (
                  <p className="text-xs text-blue-800 mt-2">No hay servicios marcados como adicionales en Inventario y Servicio.</p>
                )}

                <div className="mt-4 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
                  <p className="text-sm font-medium text-indigo-900 mb-2">Producto de venta adicional (un solo ticket)</p>
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                    <div className="md:col-span-6 relative">
                      <input
                        className="input-field"
                        placeholder="Buscar producto por código, marca o nombre"
                        inputMode="search"
                        enterKeyHint="search"
                        value={productoAdicionalBusqueda}
                        onChange={(e) => {
                          setProductoAdicionalBusqueda(e.target.value);
                          setFinalizacion((p) => ({ ...p, adicional_otro_producto: '' }));
                        }}
                      />
                      <div className="mt-2 flex justify-end">
                        <button
                          type="button"
                          className="btn-secondary !px-5 !py-3 inline-flex items-center gap-3 text-lg font-bold border-2 border-indigo-300 bg-indigo-50 text-indigo-900 hover:bg-indigo-100"
                          onClick={() => abrirSearchKeyboard('producto_adicional_busqueda')}
                        >
                          <span className="text-2xl" aria-hidden="true">⌨</span>
                          <span>Abrir teclado A-Z</span>
                        </button>
                      </div>
                      {productoAdicionalSugerencias.length > 0 && (
                        <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
                          {productoAdicionalSugerencias.map((p) => {
                            const estadoStock = getProductoStockEstado(p);
                            return (
                              <button
                                key={p.id}
                                type="button"
                                className={`w-full text-left px-3 py-2 hover:bg-gray-50 ${estadoStock.key === 'agotado' ? 'opacity-60 cursor-not-allowed' : ''}`}
                                disabled={estadoStock.key === 'agotado'}
                                onClick={() => {
                                  setFinalizacion((prev) => ({ ...prev, adicional_otro_producto: String(p.id) }));
                                  setProductoAdicionalBusqueda(formatProductCompactLabel(p));
                                  setProductoAdicionalSugerencias([]);
                                }}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span>{formatProductCompactLabel(p)} - {formatCOP(p.precio_venta || 0)} (stock {p.stock})</span>
                                  <span className={`text-xs px-2 py-1 rounded-full border ${estadoStock.badgeClass}`}>{estadoStock.label}</span>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    <div className="md:col-span-2">
                      <input
                        className="input-field"
                        type="number"
                        min="1"
                        step="1"
                        placeholder="Cantidad"
                        value={finalizacion.adicional_otro_cantidad || '1'}
                        onChange={(e) =>
                          setFinalizacion((p) => ({ ...p, adicional_otro_cantidad: sanitizePesoInput(e.target.value) || '1' }))
                        }
                      />
                    </div>

                    <div className="md:col-span-4">
                      <select
                        className="input-field"
                        value={finalizacion.adicional_otro_estilista || ''}
                        disabled={resumenCobroFinalizacion.aplicaInsumoPestanas}
                        onChange={(e) => setFinalizacion((p) => ({ ...p, adicional_otro_estilista: e.target.value }))}
                      >
                        <option value="">{resumenCobroFinalizacion.aplicaInsumoPestanas ? 'No aplica comisión (insumo establecimiento)' : 'Empleado que gana comisión de producto'}</option>
                        {estilistas.map((e) => (
                          <option key={e.id} value={e.id}>{e.nombre}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {finalizacion.adicional_otro_producto && (
                    (() => {
                      const productoSel = productos.find((p) => Number(p.id) === Number(finalizacion.adicional_otro_producto));
                      if (!productoSel) return null;
                      const qtySel = toPositiveInt(finalizacion.adicional_otro_cantidad || 0);
                      const totalSel = qtySel * toPesoInt(productoSel.precio_venta || 0);
                      const pctComision = Number(productoSel.comision_estilista || 0);
                      const valorComision = totalSel * (pctComision / 100);
                      return (
                        <div className="mt-3 rounded border border-indigo-200 bg-white p-2 text-xs text-indigo-900">
                          <p>Producto: <strong>{formatProductCompactLabel(productoSel)}</strong></p>
                          <p>{resumenCobroFinalizacion.aplicaInsumoPestanas ? 'Costo insumo:' : 'Total producto adicional:'} <strong>{formatCOP(totalSel)}</strong></p>
                          {!resumenCobroFinalizacion.aplicaInsumoPestanas && <p>Comisión ({pctComision}%): <strong>{formatCOP(valorComision)}</strong></p>}
                        </div>
                      );
                    })()
                  )}
                </div>
              </div>
            </>
          )}

          <div className="md:col-span-3 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3">
            <p className="text-sm text-emerald-900 font-semibold">Total a cobrar al cliente</p>
            <p className="text-3xl font-extrabold text-emerald-950 mt-1">{formatCOP(totalFinalizacion)}</p>
            <div className="mt-2 text-xs text-emerald-900 grid grid-cols-1 md:grid-cols-3 gap-1">
              <p>Servicio base: <strong>{formatCOP(resumenCobroFinalizacion.precioBase)}</strong></p>
              <p>Servicios adicionales: <strong>{formatCOP(resumenCobroFinalizacion.adicionalesServicios)}</strong></p>
              <p>{resumenCobroFinalizacion.aplicaInsumoPestanas ? 'Insumo (descuento establecimiento):' : 'Producto adicional:'} <strong>{formatCOP(resumenCobroFinalizacion.totalProductoAdicional)}</strong></p>
            </div>
            {finalizacion.medio_pago === 'efectivo' && (
              <div className="mt-2 text-xs">
                {toPesoInt(finalizacion.valor_recibido || 0) >= totalFinalizacion ? (
                  <p className="text-emerald-800">Devuelta estimada: <strong>{formatCOP(devueltaServicio)}</strong></p>
                ) : (
                  <p className="text-rose-700">
                    Falta por recibir: <strong>{formatCOP(totalFinalizacion - toPesoInt(finalizacion.valor_recibido || 0))}</strong>
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="md:col-span-3 flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Revisar y finalizar</button>
            <button className="btn-secondary" type="button" onClick={() => setShowFinalizarModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      {keypad.visible && (
        <div className="fixed inset-0 z-[60] bg-black/40 flex items-center justify-center p-4" onClick={cerrarKeypad}>
          <div className="w-full max-w-xs rounded-2xl bg-white shadow-2xl border border-slate-200 p-4" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm text-slate-500 mb-1">Teclado numérico</p>
            <p className="text-2xl font-bold text-slate-900 mb-3">{formatCOP(obtenerValorKeypad() || 0)}</p>
            <div className="grid grid-cols-3 gap-2">
              {['7', '8', '9', '4', '5', '6', '1', '2', '3', '000', '0', 'DEL'].map((token) => (
                <button
                  key={token}
                  type="button"
                  className="btn-secondary !py-3"
                  onClick={() => pulsarKeypad(token)}
                >
                  {token}
                </button>
              ))}
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button type="button" className="btn-danger !py-3" onClick={() => pulsarKeypad('C')}>Limpiar</button>
              <button type="button" className="btn-primary !py-3" onClick={cerrarKeypad}>Aceptar</button>
            </div>
          </div>
        </div>
      )}

      <DraggableSearchKeyboard
        visible={searchKeyboard.visible}
        value={obtenerValorSearchKeyboard()}
        onChange={asignarValorSearchKeyboard}
        onClose={cerrarSearchKeyboard}
        title="Teclado de búsqueda"
      />

      {showConfirmacionFinalizar && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden">
            <div className="bg-blue-600 px-6 py-4">
              <h3 className="text-lg font-bold text-white">Confirmar finalización de servicio</h3>
            </div>
            <div className="p-6 space-y-4">
              <div className="bg-blue-50 border-l-4 border-blue-600 p-4">
                <p className="text-sm text-blue-700 mb-2">Monto a cobrar al cliente:</p>
                <p className="text-4xl font-bold text-blue-950">{formatCOP(totalFinalizacion)}</p>
              </div>
              <div className="text-sm text-gray-600 space-y-1">
                <p><strong>Empleado:</strong> {servicioEnProcesoSeleccionado?.estilista_nombre || '-'}</p>
                <p><strong>Servicio:</strong> {servicioEnProcesoSeleccionado?.servicio_nombre || '-'}</p>
                <p><strong>Cliente:</strong> {servicioEnProcesoSeleccionado?.cliente_nombre || '-'}</p>
                <p><strong>Medio de pago:</strong> {finalizacion.medio_pago}</p>
                {finalizacion.medio_pago === 'efectivo' && (
                  <>
                    <p><strong>Valor recibido:</strong> {formatCOP(finalizacion.valor_recibido || 0)}</p>
                    <p><strong>Devueltas:</strong> {formatCOP(devueltaServicio)}</p>
                  </>
                )}
              </div>
              <div className="bg-yellow-50 border border-yellow-200 p-3 rounded text-sm text-yellow-800">
                <p>¿Deseas proceder con la finalización y cobro del servicio?</p>
              </div>
            </div>
            <div className="bg-gray-100 px-6 py-3 flex gap-2 justify-end">
              <button
                type="button"
                className="btn-secondary px-4 py-2"
                onClick={() => setShowConfirmacionFinalizar(false)}
                disabled={saving}
              >
                Cancelar (editar)
              </button>
              <button
                type="button"
                className="btn-primary px-4 py-2"
                onClick={finalizarServicio}
                disabled={saving}
              >
                {saving ? 'Finalizando...' : 'Aceptar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Servicios;
