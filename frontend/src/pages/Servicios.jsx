import { useEffect, useMemo, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiSearch, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import {
  clientesService,
  estilistasService,
  productosService,
  serviciosRealizadosService,
  serviciosService,
} from '../services/api';
import ModalForm from '../components/ModalForm';

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

const INITIAL_INICIO = {
  estilista: '',
  servicio: '',
  cliente: '',
  notas: '',
  agregar_cliente: false,
  cliente_nombre: '',
  cliente_telefono: '',
  cliente_fecha_nacimiento: '',
};

const Servicios = () => {
  const [modoVista, setModoVista] = useState('servicios');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showNuevoServicioModal, setShowNuevoServicioModal] = useState(false);
  const [showNuevoClienteModal, setShowNuevoClienteModal] = useState(false);
  const [showIniciarModal, setShowIniciarModal] = useState(false);
  const [showFinalizarModal, setShowFinalizarModal] = useState(false);

  const [estilistas, setEstilistas] = useState([]);
  const [servicios, setServicios] = useState([]);
  const [productos, setProductos] = useState([]);
  const [clientes, setClientes] = useState([]);
  const [estadoEstilistas, setEstadoEstilistas] = useState([]);
  const [serviciosEnProceso, setServiciosEnProceso] = useState([]);
  const [serviciosHistoricos, setServiciosHistoricos] = useState([]);

  const [nuevoServicio, setNuevoServicio] = useState({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
  const [nuevoCliente, setNuevoCliente] = useState({ nombre: '', telefono: '', fecha_nacimiento: '' });
  const [inicioServicio, setInicioServicio] = useState(INITIAL_INICIO);

  const [servicioFinalizarId, setServicioFinalizarId] = useState('');
  const [finalizacion, setFinalizacion] = useState({
    precio_cobrado: '',
    medio_pago: 'efectivo',
    tipo_reparto_establecimiento: 'porcentaje',
    valor_reparto_establecimiento: '',
    tiene_adicionales: false,
    adicional_shampoo: false,
    adicional_guantes: false,
    adicional_otro_producto: '',
    adicional_otro_cantidad: '1',
    busqueda_adicional: '',
    notas: '',
  });

  const cargarTodo = async () => {
    try {
      setLoading(true);
      const [estilistasRes, serviciosRes, clientesRes, serviciosRealizadosRes, estadoRes, productosRes] = await Promise.all([
        estilistasService.getAll(),
        serviciosService.getAll(),
        clientesService.getAll(),
        serviciosRealizadosService.getAll(),
        serviciosRealizadosService.getEstadoEstilistas(),
        productosService.getAll({ activo: true }),
      ]);

      const listaEstilistas = extractRows(estilistasRes);
      const listaServicios = extractRows(serviciosRes);
      const listaClientes = extractRows(clientesRes);
      const listaRealizados = extractRows(serviciosRealizadosRes);
      const listaProductos = extractRows(productosRes);

      setEstilistas(listaEstilistas);
      setServicios(listaServicios);
      setClientes(listaClientes);
      setProductos(listaProductos);
      setEstadoEstilistas(Array.isArray(estadoRes) ? estadoRes : []);
      setServiciosEnProceso(listaRealizados.filter((s) => s.estado === 'en_proceso'));
      setServiciosHistoricos(listaRealizados);
    } catch (error) {
      toast.error('No se pudo cargar el módulo operativo');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarTodo();
  }, []);

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

  const servicioSeleccionadoFinalizacion = useMemo(
    () => serviciosHistoricos.find((s) => String(s.id) === String(servicioFinalizarId)),
    [serviciosHistoricos, servicioFinalizarId]
  );

  const abrirInicioDesdePanel = (estilistaId) => {
    setInicioServicio({ ...INITIAL_INICIO, estilista: String(estilistaId) });
    setShowIniciarModal(true);
  };

  const prepararFinalizacion = (srv) => {
    setServicioFinalizarId(String(srv.id));
    setShowFinalizarModal(true);
    setFinalizacion({
      precio_cobrado: srv.precio_cobrado || '',
      medio_pago: srv.medio_pago || 'efectivo',
      tipo_reparto_establecimiento: srv.tipo_reparto_establecimiento || 'porcentaje',
      valor_reparto_establecimiento: srv.valor_reparto_establecimiento || '',
      tiene_adicionales: Boolean(srv.tiene_adicionales),
      adicional_shampoo: Boolean(srv.adicional_shampoo),
      adicional_guantes: Boolean(srv.adicional_guantes),
      adicional_otro_producto: srv.adicional_otro_producto ? String(srv.adicional_otro_producto) : '',
      adicional_otro_cantidad: String(srv.adicional_otro_cantidad || 1),
      busqueda_adicional: '',
      notas: srv.notas || '',
    });
  };

  const eliminarServicioHistorico = async (srv) => {
    const ok = window.confirm(`¿Eliminar factura de servicio ${srv.numero_factura || srv.id}?`);
    if (!ok) return;

    try {
      await serviciosRealizadosService.delete(srv.id);
      toast.success('Servicio eliminado');
      await cargarTodo();
    } catch (error) {
      toast.error('No se pudo eliminar el servicio');
    }
  };

  const buscarProductoAdicional = async () => {
    if (!finalizacion.busqueda_adicional.trim()) {
      toast.warning('Escribe nombre o código de barras');
      return;
    }

    try {
      const payload = await productosService.getAll({ search: finalizacion.busqueda_adicional.trim(), activo: true });
      const encontrados = extractRows(payload);
      const exacto = encontrados.find((p) => p.codigo_barras === finalizacion.busqueda_adicional.trim());
      const producto = exacto || encontrados[0] || null;
      if (!producto) {
        toast.info('No se encontró producto para adicional');
        return;
      }
      setFinalizacion((p) => ({ ...p, adicional_otro_producto: String(producto.id) }));
    } catch (error) {
      toast.error('No se pudo buscar el producto adicional');
    }
  };

  const prepararFinalizacionPorTarjeta = (tarjeta) => {
    const srv = serviciosEnProceso.find((s) => s.id === tarjeta.servicio_realizado_id);
    if (!srv) {
      toast.warning('No se encontro el servicio en proceso');
      return;
    }
    prepararFinalizacion(srv);
  };

  const crearServicioCatalogo = async (e) => {
    e.preventDefault();
    if (!nuevoServicio.nombre.trim() || !nuevoServicio.precio) {
      toast.warning('Nombre y precio del servicio son obligatorios');
      return;
    }

    try {
      setSaving(true);
      await serviciosService.create({
        nombre: nuevoServicio.nombre.trim(),
        descripcion: nuevoServicio.descripcion.trim() || null,
        precio: Number(nuevoServicio.precio),
        duracion_minutos: nuevoServicio.duracion_minutos ? Number(nuevoServicio.duracion_minutos) : null,
        activo: true,
      });
      toast.success('Servicio del catalogo creado');
      setNuevoServicio({ nombre: '', descripcion: '', precio: '', duracion_minutos: '' });
      setShowNuevoServicioModal(false);
      await cargarTodo();
    } catch (error) {
      toast.error('No se pudo crear el servicio');
    } finally {
      setSaving(false);
    }
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
      toast.warning('Selecciona estilista y servicio');
      return;
    }

    if (estilistasOcupados.has(Number(inicioServicio.estilista))) {
      toast.warning('Ese estilista ya esta ocupado');
      return;
    }

    const servicioSel = servicios.find((s) => s.id === Number(inicioServicio.servicio));
    let clienteId = inicioServicio.cliente ? Number(inicioServicio.cliente) : null;

    try {
      setSaving(true);

      if (inicioServicio.agregar_cliente) {
        if (!inicioServicio.cliente_nombre.trim()) {
          toast.warning('Si marcas agregar cliente, el nombre es obligatorio');
          setSaving(false);
          return;
        }

        const nuevoClienteCreado = await clientesService.create({
          nombre: inicioServicio.cliente_nombre.trim(),
          telefono: inicioServicio.cliente_telefono.trim() || null,
          fecha_nacimiento: inicioServicio.cliente_fecha_nacimiento || null,
        });
        clienteId = nuevoClienteCreado?.id || null;
      }

      await serviciosRealizadosService.create({
        estilista: Number(inicioServicio.estilista),
        servicio: Number(inicioServicio.servicio),
        cliente: clienteId,
        estado: 'en_proceso',
        precio_cobrado: servicioSel?.precio || 0,
        notas: inicioServicio.notas || null,
      });

      toast.success('Servicio iniciado, estilista en estado ocupado');
      setInicioServicio(INITIAL_INICIO);
      setShowIniciarModal(false);
      await cargarTodo();
    } catch (error) {
      toast.error('No se pudo iniciar el servicio');
    } finally {
      setSaving(false);
    }
  };

  const finalizarServicio = async (e) => {
    e.preventDefault();
    if (!servicioFinalizarId) {
      toast.warning('Selecciona un servicio en proceso para finalizar');
      return;
    }
    if (!finalizacion.precio_cobrado) {
      toast.warning('Ingresa el total cobrado del servicio');
      return;
    }

    try {
      setSaving(true);
      const seleccionado = serviciosHistoricos.find((s) => String(s.id) === String(servicioFinalizarId));
      const payload = {
        precio_cobrado: Number(finalizacion.precio_cobrado),
        medio_pago: finalizacion.medio_pago,
        tipo_reparto_establecimiento: finalizacion.tipo_reparto_establecimiento,
        valor_reparto_establecimiento: finalizacion.valor_reparto_establecimiento
          ? Number(finalizacion.valor_reparto_establecimiento)
          : 0,
        tiene_adicionales: finalizacion.tiene_adicionales,
        adicional_shampoo: finalizacion.tiene_adicionales ? finalizacion.adicional_shampoo : false,
        adicional_guantes: finalizacion.tiene_adicionales ? finalizacion.adicional_guantes : false,
        adicional_otro_producto:
          finalizacion.tiene_adicionales && finalizacion.adicional_otro_producto
            ? Number(finalizacion.adicional_otro_producto)
            : null,
        adicional_otro_cantidad: Number(finalizacion.adicional_otro_cantidad || 1),
        notas: finalizacion.notas || null,
      };

      let res;
      if (seleccionado?.estado === 'finalizado') {
        res = await serviciosRealizadosService.update(servicioFinalizarId, {
          ...payload,
          estado: 'finalizado',
        });
      } else {
        res = await serviciosRealizadosService.finalizar(servicioFinalizarId, payload);
      }
      toast.success(
        `Factura guardada. Empleado: $${Number(res.monto_estilista || 0).toFixed(2)} | Establecimiento: $${Number(
          res.monto_establecimiento || 0
        ).toFixed(2)}`
      );
      setServicioFinalizarId('');
      setShowFinalizarModal(false);
      setFinalizacion({
        precio_cobrado: '',
        medio_pago: 'efectivo',
        tipo_reparto_establecimiento: 'porcentaje',
        valor_reparto_establecimiento: '',
        tiene_adicionales: false,
        adicional_shampoo: false,
        adicional_guantes: false,
        adicional_otro_producto: '',
        adicional_otro_cantidad: '1',
        busqueda_adicional: '',
        notas: '',
      });
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo finalizar el servicio';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Operación diaria y facturación</h1>
          <p className="text-gray-600 mt-1">Gestiona servicios por empleado y genera factura con adicionales</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarTodo} disabled={loading}>
            <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
          </button>
          <button className="btn-primary inline-flex items-center gap-2" onClick={() => setShowNuevoServicioModal(true)}>
            <FiPlus /> Nuevo servicio
          </button>
          <button className="btn-primary inline-flex items-center gap-2" onClick={() => setShowNuevoClienteModal(true)}>
            <FiPlus /> Nuevo cliente
          </button>
        </div>
      </div>

      <div className="card p-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button
            className={`${modoVista === 'servicios' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setModoVista('servicios')}
          >
            Modo servicios
          </button>
          <button
            className={`${modoVista === 'ventas' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setModoVista('ventas')}
          >
            Modo venta de productos
          </button>
        </div>
      </div>

      {modoVista === 'ventas' && (
        <div className="card border border-blue-200 bg-blue-50">
          <h2 className="card-header">Venta de productos</h2>
          <p className="text-blue-900">Para crear y editar facturas de productos usa el módulo de Histórico de ventas, donde ya tienes filtros por fecha y resumen.</p>
        </div>
      )}

      {modoVista === 'servicios' && (
      <>

      <div className="card border border-dashed border-gray-300 bg-gray-50">
        <p className="text-gray-700">Tip: usa directamente los botones de cada tarjeta en el panel de empleados para cambiar entre libre y ocupado.</p>
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
                  <th className="px-6 py-3 text-right">Accion</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosEnProceso.map((srv) => (
                  <tr key={srv.id} className="hover:bg-gray-50">
                    <td className="table-cell">{srv.estilista_nombre}</td>
                    <td className="table-cell">{srv.servicio_nombre}</td>
                    <td className="table-cell">{srv.cliente_nombre || '-'}</td>
                    <td className="table-cell">${Number(srv.precio_cobrado || 0).toFixed(2)}</td>
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

      <ModalForm
        isOpen={showNuevoServicioModal}
        onClose={() => setShowNuevoServicioModal(false)}
        title="Nuevo servicio de catalogo"
        subtitle="Crea un servicio para usarlo en la operacion diaria"
        size="md"
      >
        <form className="space-y-3" onSubmit={crearServicioCatalogo}>
          <input className="input-field" placeholder="Nombre del servicio" value={nuevoServicio.nombre} onChange={(e) => setNuevoServicio((p) => ({ ...p, nombre: e.target.value }))} />
          <input className="input-field" placeholder="Descripcion" value={nuevoServicio.descripcion} onChange={(e) => setNuevoServicio((p) => ({ ...p, descripcion: e.target.value }))} />
          <div className="grid grid-cols-2 gap-3">
            <input className="input-field" type="number" min="0" step="0.01" placeholder="Precio" value={nuevoServicio.precio} onChange={(e) => setNuevoServicio((p) => ({ ...p, precio: e.target.value }))} />
            <input className="input-field" type="number" min="1" placeholder="Duracion (min)" value={nuevoServicio.duracion_minutos} onChange={(e) => setNuevoServicio((p) => ({ ...p, duracion_minutos: e.target.value }))} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Crear servicio</button>
            <button className="btn-secondary" type="button" onClick={() => setShowNuevoServicioModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <ModalForm
        isOpen={showNuevoClienteModal}
        onClose={() => setShowNuevoClienteModal(false)}
        title="Nuevo cliente"
        subtitle="Registro rapido de cliente"
        size="md"
      >
        <form className="space-y-3" onSubmit={crearCliente}>
          <input className="input-field" placeholder="Nombre del cliente" value={nuevoCliente.nombre} onChange={(e) => setNuevoCliente((p) => ({ ...p, nombre: e.target.value }))} />
          <input className="input-field" placeholder="Telefono" value={nuevoCliente.telefono} onChange={(e) => setNuevoCliente((p) => ({ ...p, telefono: e.target.value }))} />
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
        subtitle="Tipo de servicio, cobro estipulado y cliente opcional"
        size="lg"
      >
        <form className="grid grid-cols-1 md:grid-cols-4 gap-3" onSubmit={iniciarServicio}>
          <select className="input-field" value={inicioServicio.estilista} onChange={(e) => setInicioServicio((p) => ({ ...p, estilista: e.target.value }))}>
            <option value="">Selecciona empleado</option>
            {estilistas.map((e) => (
              <option key={e.id} value={e.id}>{e.nombre}</option>
            ))}
          </select>

          <select className="input-field" value={inicioServicio.servicio} onChange={(e) => setInicioServicio((p) => ({ ...p, servicio: e.target.value }))}>
            <option value="">Selecciona servicio</option>
            {servicios.map((s) => (
              <option key={s.id} value={s.id}>{s.nombre}</option>
            ))}
          </select>

          <select
            className="input-field"
            value={inicioServicio.cliente}
            onChange={(e) => setInicioServicio((p) => ({ ...p, cliente: e.target.value }))}
            disabled={inicioServicio.agregar_cliente}
          >
            <option value="">Cliente existente (opcional)</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>{c.nombre}</option>
            ))}
          </select>

          <input className="input-field" placeholder="Notas (opcional)" value={inicioServicio.notas} onChange={(e) => setInicioServicio((p) => ({ ...p, notas: e.target.value }))} />

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900 md:col-span-4">
            <p><strong>Empleado:</strong> {estilistaSeleccionadoInicio?.nombre || 'Sin seleccionar'}</p>
            <p><strong>Tipo de servicio:</strong> {servicioSeleccionadoInicio?.nombre || 'Sin seleccionar'}</p>
            <p><strong>Cobro estipulado:</strong> ${Number(servicioSeleccionadoInicio?.precio || 0).toFixed(2)}</p>
          </div>

          <label className="md:col-span-4 inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={inicioServicio.agregar_cliente}
              onChange={(e) => setInicioServicio((p) => ({ ...p, agregar_cliente: e.target.checked, cliente: e.target.checked ? '' : p.cliente }))}
            />
            Agregar informacion de cliente
          </label>

          {inicioServicio.agregar_cliente && (
            <>
              <input
                className="input-field"
                placeholder="Nombre cliente"
                value={inicioServicio.cliente_nombre}
                onChange={(e) => setInicioServicio((p) => ({ ...p, cliente_nombre: e.target.value }))}
              />
              <input
                className="input-field"
                placeholder="Telefono"
                value={inicioServicio.cliente_telefono}
                onChange={(e) => setInicioServicio((p) => ({ ...p, cliente_telefono: e.target.value }))}
              />
              <input
                className="input-field"
                type="date"
                value={inicioServicio.cliente_fecha_nacimiento}
                onChange={(e) => setInicioServicio((p) => ({ ...p, cliente_fecha_nacimiento: e.target.value }))}
              />
            </>
          )}

          <div className="md:col-span-4 flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Iniciar y marcar ocupado</button>
            <button className="btn-secondary" type="button" onClick={() => setShowIniciarModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <ModalForm
        isOpen={showFinalizarModal}
        onClose={() => setShowFinalizarModal(false)}
        title="Finalizar servicio"
        subtitle="Cierra factura y registra adicionales"
        size="lg"
      >
        <form className="grid grid-cols-1 md:grid-cols-3 gap-3" onSubmit={finalizarServicio}>
          <select className="input-field" value={servicioFinalizarId} onChange={(e) => setServicioFinalizarId(e.target.value)}>
            <option value="">Selecciona factura de servicio</option>
            {serviciosHistoricos.map((srv) => (
              <option key={srv.id} value={srv.id}>{srv.estilista_nombre} - {srv.servicio_nombre} ({srv.estado})</option>
            ))}
          </select>

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 md:col-span-2">
            <p><strong>Tipo de servicio:</strong> {servicioSeleccionadoFinalizacion?.servicio_nombre || 'Sin seleccionar'}</p>
            <p><strong>Cobro estipulado:</strong> ${Number(servicioSeleccionadoFinalizacion?.precio_cobrado || 0).toFixed(2)}</p>
            <p><strong>Cliente:</strong> {servicioSeleccionadoFinalizacion?.cliente_nombre || 'No registrado'}</p>
          </div>

          <input className="input-field" type="number" min="0" step="0.01" placeholder="Total servicio" value={finalizacion.precio_cobrado} onChange={(e) => setFinalizacion((p) => ({ ...p, precio_cobrado: e.target.value }))} />

          <select className="input-field" value={finalizacion.medio_pago} onChange={(e) => setFinalizacion((p) => ({ ...p, medio_pago: e.target.value }))}>
            {mediosPago.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>

          <select className="input-field" value={finalizacion.tipo_reparto_establecimiento} onChange={(e) => setFinalizacion((p) => ({ ...p, tipo_reparto_establecimiento: e.target.value }))}>
            <option value="porcentaje">El establecimiento se queda porcentaje</option>
            <option value="monto">El establecimiento se queda monto fijo</option>
          </select>

          <input className="input-field" type="number" min="0" step="0.01" placeholder={finalizacion.tipo_reparto_establecimiento === 'porcentaje' ? 'Porcentaje para establecimiento' : 'Monto para establecimiento'} value={finalizacion.valor_reparto_establecimiento} onChange={(e) => setFinalizacion((p) => ({ ...p, valor_reparto_establecimiento: e.target.value }))} />

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
              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={finalizacion.adicional_shampoo}
                  onChange={(e) => setFinalizacion((p) => ({ ...p, adicional_shampoo: e.target.checked }))}
                />
                Shampoo ($4000)
              </label>

              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={finalizacion.adicional_guantes}
                  onChange={(e) => setFinalizacion((p) => ({ ...p, adicional_guantes: e.target.checked }))}
                />
                Guantes ($1500)
              </label>

              <div className="grid grid-cols-3 gap-2 md:col-span-3">
                <input
                  className="input-field col-span-2"
                  placeholder="Otro producto por nombre o código"
                  value={finalizacion.busqueda_adicional}
                  onChange={(e) => setFinalizacion((p) => ({ ...p, busqueda_adicional: e.target.value }))}
                />
                <button type="button" className="btn-secondary inline-flex items-center justify-center gap-2" onClick={buscarProductoAdicional}>
                  <FiSearch /> Buscar producto
                </button>
              </div>

              <select
                className="input-field md:col-span-2"
                value={finalizacion.adicional_otro_producto}
                onChange={(e) => setFinalizacion((p) => ({ ...p, adicional_otro_producto: e.target.value }))}
              >
                <option value="">Sin otro producto</option>
                {productos.map((p) => (
                  <option key={p.id} value={p.id}>{p.nombre} - ${Number(p.precio_venta || 0).toFixed(2)} (stock {p.stock})</option>
                ))}
              </select>

              <input
                className="input-field"
                type="number"
                min="1"
                placeholder="Cantidad otro producto"
                value={finalizacion.adicional_otro_cantidad}
                onChange={(e) => setFinalizacion((p) => ({ ...p, adicional_otro_cantidad: e.target.value }))}
              />
            </>
          )}

          <div className="md:col-span-3 flex gap-2">
            <button className="btn-primary" type="submit" disabled={saving}>Finalizar y calcular reparto</button>
            <button className="btn-secondary" type="button" onClick={() => setShowFinalizarModal(false)}>Cancelar</button>
          </div>
        </form>
      </ModalForm>

      <div className="card">
        <h2 className="card-header">Histórico de servicios facturados</h2>
        {serviciosHistoricos.length === 0 && <p className="text-gray-600">No hay facturas de servicio.</p>}
        {serviciosHistoricos.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Factura</th>
                  <th className="px-6 py-3 text-left">Empleado</th>
                  <th className="px-6 py-3 text-left">Servicio</th>
                  <th className="px-6 py-3 text-left">Estado</th>
                  <th className="px-6 py-3 text-left">Total</th>
                  <th className="px-6 py-3 text-left">Adicionales</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {serviciosHistoricos.map((srv) => (
                  <tr key={srv.id} className="hover:bg-gray-50">
                    <td className="table-cell">{srv.numero_factura || '-'}</td>
                    <td className="table-cell">{srv.estilista_nombre}</td>
                    <td className="table-cell">{srv.servicio_nombre}</td>
                    <td className="table-cell capitalize">{srv.estado}</td>
                    <td className="table-cell">${Number(srv.precio_cobrado || 0).toFixed(2)}</td>
                    <td className="table-cell">${Number(srv.valor_adicionales || 0).toFixed(2)}</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => prepararFinalizacion(srv)}>
                          <FiEdit2 size={14} /> Editar
                        </button>
                        <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarServicioHistorico(srv)}>
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
      </>
      )}
    </div>
  );
};

export default Servicios;
