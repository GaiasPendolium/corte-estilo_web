import { useEffect, useMemo, useState } from 'react';
import { FiPlus, FiRefreshCw, FiTrash2 } from 'react-icons/fi';
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

const INITIAL_INICIO = {
  estilista: '',
  servicio: '',
  servicio_busqueda: '',
  notas: '',
};

const Servicios = () => {
  const { user } = useAuthStore();
  const puedeFacturar = true; // Todos los roles pueden registrar ventas y servicios (recepcion incluida)

  const [modoVista, setModoVista] = useState('servicios');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showNuevoClienteModal, setShowNuevoClienteModal] = useState(false);
  const [showIniciarModal, setShowIniciarModal] = useState(false);
  const [showFinalizarModal, setShowFinalizarModal] = useState(false);
  const [showConfirmacionFinalizar, setShowConfirmacionFinalizar] = useState(false);

  const [estilistas, setEstilistas] = useState([]);
  const [servicios, setServicios] = useState([]);
  const [productos, setProductos] = useState([]);
  const [clientes, setClientes] = useState([]);
  const [estadoEstilistas, setEstadoEstilistas] = useState([]);
  const [serviciosEnProceso, setServiciosEnProceso] = useState([]);

  const [nuevoCliente, setNuevoCliente] = useState({ nombre: '', telefono: '', fecha_nacimiento: '' });
  const [inicioServicio, setInicioServicio] = useState(INITIAL_INICIO);
  const [sugerenciasServicio, setSugerenciasServicio] = useState([]);

  const [servicioFinalizarId, setServicioFinalizarId] = useState('');
  const [finalizacion, setFinalizacion] = useState({
    precio_cobrado: '',
    medio_pago: 'efectivo',
    tiene_adicionales: false,
    adicionales_servicio_items: [],
    notas: '',
  });
  const [adicionalActivoKey, setAdicionalActivoKey] = useState(null);

  const [ventaForm, setVentaForm] = useState({
    cliente_nombre: '',
    estilista: '',
    medio_pago: 'efectivo',
    cantidad: '1',
    precio_unitario: '',
  });
  const [ventaBusqueda, setVentaBusqueda] = useState('');
  const [ventaSugerencias, setVentaSugerencias] = useState([]);
  const [productoVentaSeleccionado, setProductoVentaSeleccionado] = useState(null);
  const [carrito, setCarrito] = useState([]);

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
    const q = inicioServicio.servicio_busqueda.trim().toLowerCase();
    if (!q) {
      setSugerenciasServicio([]);
      return;
    }
    setSugerenciasServicio(
      servicios
        .filter((s) => (s.nombre || '').toLowerCase().includes(q) || (s.descripcion || '').toLowerCase().includes(q))
        .slice(0, 8)
    );
  }, [inicioServicio.servicio_busqueda, servicios]);

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

  const estilistasOcupados = useMemo(
    () => new Set(estadoEstilistas.filter((e) => e.estado === 'ocupado').map((e) => e.estilista_id)),
    [estadoEstilistas]
  );

  const estilistaSeleccionadoInicio = useMemo(
    () => estilistas.find((e) => e.id === Number(inicioServicio.estilista)),
    [estilistas, inicioServicio.estilista]
  );

  const servicioSeleccionadoInicio = useMemo(
    () => servicios.find((s) => s.id === Number(inicioServicio.servicio)),
    [servicios, inicioServicio.servicio]
  );

  const servicioEnProcesoSeleccionado = useMemo(
    () => serviciosEnProceso.find((s) => String(s.id) === String(servicioFinalizarId)),
    [serviciosEnProceso, servicioFinalizarId]
  );

  const serviciosAdicionalesConfigurados = useMemo(
    () => servicios.filter((s) => Boolean(s.es_adicional) && (s.activo ?? true)),
    [servicios]
  );

  const construirItemAdicional = ({ id = '', estilista_id = '', valor = '', busqueda = '' } = {}) => ({
    key: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    id: id ? String(id) : '',
    estilista_id: estilista_id ? String(estilista_id) : '',
    valor: valor ? String(valor) : '',
    busqueda: busqueda || '',
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

  const esConsumoEmpleado = modoVista === 'consumo_empleado';

  const cantidadReservadaEnCarrito = (productoId) =>
    carrito
      .filter((item) => Number(item.producto?.id) === Number(productoId))
      .reduce((acc, item) => acc + Number(item.cantidad || 0), 0);

  const totalFinalizacion = useMemo(() => {
    const precioBase = toPesoInt(finalizacion.precio_cobrado || 0);
    const adicionalesServicios = (finalizacion.adicionales_servicio_items || []).reduce(
      (acc, item) => acc + toPesoInt(item.valor || 0),
      0
    );
    return precioBase + adicionalesServicios;
  }, [finalizacion]);

  const validarPrecioMinimoProducto = (producto, precioUnitario) => {
    if (!producto) return true;
    const minimoPermitido = minimoConDescuentoEmpleado(producto.precio_venta || 0);
    if (minimoPermitido > 0 && toPesoInt(precioUnitario) < minimoPermitido) {
      toast.warning(`Descuento maximo 20%. Precio minimo unitario: ${formatCOP(minimoPermitido)}`);
      return false;
    }
    return true;
  };

  const abrirInicioDesdePanel = (estilistaId) => {
    setInicioServicio({ ...INITIAL_INICIO, estilista: String(estilistaId) });
    setShowIniciarModal(true);
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
      precio_cobrado: srv.precio_cobrado || '',
      medio_pago: srv.medio_pago || 'efectivo',
      tiene_adicionales: Boolean(srv.tiene_adicionales),
      adicionales_servicio_items: itemsIniciales,
      notas: srv.notas || '',
    });
    setAdicionalActivoKey(null);
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
    if (adicionalActivoKey === key) {
      setAdicionalActivoKey(null);
    }
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

  const iniciarServicio = async (e) => {
    e.preventDefault();
    if (!inicioServicio.estilista || !inicioServicio.servicio) {
      toast.warning('Selecciona empleado y servicio');
      return;
    }

    if (estilistasOcupados.has(Number(inicioServicio.estilista))) {
      toast.warning('Ese empleado ya está ocupado');
      return;
    }

    try {
      setSaving(true);

      await serviciosRealizadosService.create({
        estilista: Number(inicioServicio.estilista),
        servicio: Number(inicioServicio.servicio),
        estado: 'en_proceso',
        precio_cobrado: 0,
        notas: inicioServicio.notas || null,
      });

      toast.success('Servicio iniciado, empleado en estado ocupado');
      setInicioServicio(INITIAL_INICIO);
      setShowIniciarModal(false);
      await cargarTodo();
    } catch (error) {
      toast.error('No se pudo iniciar el servicio');
    } finally {
      setSaving(false);
    }
  };

  const solicitarConfirmacionFinalizar = (e) => {
    e.preventDefault();
    if (!servicioFinalizarId) {
      toast.warning('Selecciona un servicio en proceso para finalizar');
      return;
    }
    if (!finalizacion.precio_cobrado) {
      toast.warning('Ingresa el total cobrado del servicio');
      return;
    }

    if (finalizacion.tiene_adicionales) {
      const items = finalizacion.adicionales_servicio_items || [];
      if (!items.length) {
        toast.warning('Agrega al menos un servicio adicional');
        return;
      }

      const itemInvalido = items.find(
        (item) => !item.id || !item.estilista_id || toPesoInt(item.valor || 0) <= 0
      );
      if (itemInvalido) {
        toast.warning('Cada adicional debe tener servicio, empleado y valor mayor a 0');
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
            .filter((item) => item.id && item.estilista_id)
            .map((item) => ({
              id: Number(item.id),
              estilista_id: Number(item.estilista_id),
              valor: toPesoInt(item.valor || 0),
            }))
        : [];
      const flagsLegacy = mapearFlagsLegacyAdicionales(itemsNormalizados.map((x) => x.id));
      const res = await serviciosRealizadosService.finalizar(servicioFinalizarId, {
        precio_cobrado: toPesoInt(finalizacion.precio_cobrado),
        medio_pago: finalizacion.medio_pago,
        tiene_adicionales: finalizacion.tiene_adicionales,
        adicionales_servicio_ids: finalizacion.tiene_adicionales ? itemsNormalizados.map((item) => item.id) : [],
        adicionales_servicio_items: itemsNormalizados,
        adicional_shampoo: finalizacion.tiene_adicionales ? flagsLegacy.adicional_shampoo : false,
        adicional_guantes: finalizacion.tiene_adicionales ? flagsLegacy.adicional_guantes : false,
        adicional_otro_producto: null,
        adicional_otro_cantidad: 1,
        adicional_otro_descuento_empleado: false,
        adicional_otro_precio_unitario: null,
        notas: finalizacion.notas || null,
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

      try {
        await ticketPrintService.printServiceSaleAndOpenDrawer(res);
        toast.success('Ticket de servicio impreso y caja abierta');
      } catch (printError) {
        toast.error(printError.message || 'El servicio se finalizo, pero no se pudo imprimir el ticket');
      }

      setServicioFinalizarId('');
      setShowFinalizarModal(false);
      setFinalizacion({
        precio_cobrado: '',
        medio_pago: 'efectivo',
        tiene_adicionales: false,
        adicionales_servicio_items: [],
        notas: '',
      });
      setAdicionalActivoKey(null);
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo finalizar el servicio';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const seleccionarProductoCaja = (producto) => {
    if (Number(producto?.stock || 0) <= 0) {
      toast.warning('Este producto está agotado y no se puede seleccionar.');
      return;
    }
    setProductoVentaSeleccionado(producto);
    setVentaBusqueda(formatProductSearchLabel(producto));
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
      }

      try {
        if (ventaPrincipal) {
          await ticketPrintService.printProductSaleAndOpenDrawer(ventaPrincipal);
          toast.success('Ticket impreso y caja abierta');
        }
      } catch (printError) {
        toast.error(printError.message || 'La(s) venta(s) se guardaron, pero no se pudo imprimir el ticket');
      }

      setVentaForm({ cliente_nombre: '', estilista: '', medio_pago: 'efectivo', cantidad: '1', precio_unitario: '' });
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
                value={ventaBusqueda}
                onChange={(e) => setVentaBusqueda(e.target.value)}
              />
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
        <p className="text-gray-700">Tip: usa los botones en cada tarjeta para iniciar o finalizar servicio rápidamente.</p>
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
                  <button className="btn-primary !px-3 !py-2 w-full" onClick={() => abrirInicioDesdePanel(item.estilista_id)}>
                    Iniciar servicio
                  </button>
                ) : (
                  <button className="btn-danger !px-3 !py-2 w-full" onClick={() => prepararFinalizacionPorTarjeta(item)}>
                    Finalizar servicio
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
        isOpen={showIniciarModal}
        onClose={() => setShowIniciarModal(false)}
        title="Iniciar servicio"
        subtitle="Selecciona el servicio"
        size="lg"
      >
        <form className="grid grid-cols-1 md:grid-cols-3 gap-3" onSubmit={iniciarServicio}>
          <select className="input-field" value={inicioServicio.estilista} onChange={(e) => setInicioServicio((p) => ({ ...p, estilista: e.target.value }))}>
            <option value="">Selecciona empleado</option>
            {estilistas.map((e) => (
              <option key={e.id} value={e.id}>{e.nombre}</option>
            ))}
          </select>

          <div className="md:col-span-2 relative">
            <input
              className="input-field"
              placeholder="Buscar servicio por descripción o nombre"
              value={inicioServicio.servicio_busqueda}
              onChange={(e) => setInicioServicio((p) => ({ ...p, servicio_busqueda: e.target.value, servicio: '' }))}
            />
            {sugerenciasServicio.length > 0 && (
              <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
                {sugerenciasServicio.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="w-full text-left px-3 py-2 hover:bg-gray-50"
                    onClick={() => setInicioServicio((p) => ({ ...p, servicio: String(s.id), servicio_busqueda: formatServiceSearchLabel(s) }))}
                  >
                    {formatServiceSearchLabel(s)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <input className="input-field md:col-span-3" placeholder="Notas (opcional)" value={inicioServicio.notas} onChange={(e) => setInicioServicio((p) => ({ ...p, notas: e.target.value }))} />

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900 md:col-span-3">
            <p><strong>Empleado:</strong> {estilistaSeleccionadoInicio?.nombre || 'Sin seleccionar'}</p>
            <p><strong>Servicio:</strong> {servicioSeleccionadoInicio?.nombre || 'Sin seleccionar'}</p>
          </div>

          <div className="md:col-span-3 flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Iniciar servicio</button>
            <button className="btn-secondary" type="button" onClick={() => setShowIniciarModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <ModalForm
        isOpen={showFinalizarModal}
        onClose={() => setShowFinalizarModal(false)}
        title="Finalizar servicio"
        subtitle="Confirma pago y adicionales"
        size="lg"
      >
        <form className="grid grid-cols-1 md:grid-cols-3 gap-3" onSubmit={solicitarConfirmacionFinalizar}>
          <select className="input-field" value={servicioFinalizarId} onChange={(e) => setServicioFinalizarId(e.target.value)}>
            <option value="">Servicio en proceso a finalizar</option>
            {serviciosEnProceso.map((srv) => (
              <option key={srv.id} value={srv.id}>{srv.estilista_nombre} - {srv.servicio_nombre}</option>
            ))}
          </select>

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 md:col-span-2">
            <p><strong>Servicio:</strong> {servicioEnProcesoSeleccionado?.servicio_nombre || 'Sin seleccionar'}</p>
            <p><strong>Cliente:</strong> {servicioEnProcesoSeleccionado?.cliente_nombre || 'No registrado'}</p>
          </div>

          <input className="input-field" type="number" min="0" step="1" placeholder="Total servicio" value={finalizacion.precio_cobrado} onChange={(e) => setFinalizacion((p) => ({ ...p, precio_cobrado: sanitizePesoInput(e.target.value) }))} />

          <select className="input-field" value={finalizacion.medio_pago} onChange={(e) => setFinalizacion((p) => ({ ...p, medio_pago: e.target.value }))}>
            {mediosPago.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>

          <input className="input-field" placeholder="Notas finales (opcional)" value={finalizacion.notas} onChange={(e) => setFinalizacion((p) => ({ ...p, notas: e.target.value }))} />

          <label className="md:col-span-3 inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={finalizacion.tiene_adicionales}
              onChange={(e) => setFinalizacion((p) => ({ ...p, tiene_adicionales: e.target.checked }))}
            />
            Este servicio tiene adicionales
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
                  <p className="text-xs text-blue-800">Agrega uno o más servicios adicionales y asigna empleado + valor.</p>
                )}

                <div className="space-y-3">
                  {(finalizacion.adicionales_servicio_items || []).map((item) => {
                    const sugerenciasFila = serviciosAdicionalesConfigurados
                      .filter((s) => serviceMatchesSearch(s, item.busqueda || ''))
                      .slice(0, 8);

                    return (
                      <div key={item.key} className="rounded-lg border border-blue-200 bg-white p-3">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-5 relative">
                            <input
                              className="input-field"
                              placeholder="Buscar servicio adicional"
                              value={item.busqueda || ''}
                              onFocus={() => setAdicionalActivoKey(item.key)}
                              onBlur={() => setTimeout(() => setAdicionalActivoKey((curr) => (curr === item.key ? null : curr)), 120)}
                              onChange={(e) => actualizarFilaAdicional(item.key, { busqueda: e.target.value, id: '' })}
                            />
                            {adicionalActivoKey === item.key && sugerenciasFila.length > 0 && (
                              <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
                                {sugerenciasFila.map((srvAd) => (
                                  <button
                                    key={srvAd.id}
                                    type="button"
                                    className="w-full text-left px-3 py-2 hover:bg-gray-50"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                      seleccionarServicioAdicional(item.key, srvAd);
                                      setAdicionalActivoKey(null);
                                    }}
                                  >
                                    {formatServiceSearchLabel(srvAd)} - {formatCOP(srvAd.precio || 0)}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>

                          <div className="md:col-span-4">
                            <select
                              className="input-field"
                              value={item.estilista_id || ''}
                              onChange={(e) => actualizarFilaAdicional(item.key, { estilista_id: e.target.value })}
                            >
                              <option value="">Empleado que realiza el adicional</option>
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
                              step="1"
                              placeholder="Valor"
                              value={item.valor || ''}
                              onChange={(e) => actualizarFilaAdicional(item.key, { valor: sanitizePesoInput(e.target.value) })}
                            />
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
                        </div>
                      </div>
                    );
                  })}
                </div>

                {serviciosAdicionalesConfigurados.length === 0 && (
                  <p className="text-xs text-blue-800 mt-2">No hay servicios marcados como adicionales en Inventario y Servicio.</p>
                )}
              </div>
            </>
          )}

          <div className="md:col-span-3 flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Revisar y finalizar</button>
            <button className="btn-secondary" type="button" onClick={() => setShowFinalizarModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

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
