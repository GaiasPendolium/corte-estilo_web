import { useState, useEffect, useCallback } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiDownload, FiPrinter } from 'react-icons/fi';
import { toast } from 'react-toastify';
import creditosService from '../services/creditosService';
import ModalForm from '../components/ModalForm';
import useAuthStore from '../store/authStore';
import { hasMenuPermission, hasSubmenuPermission } from '../utils/permissions';

const moneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const formatMoney = (value) => `$${moneyFormatter.format(Number(value || 0))}`;
const todayStr = () => new Date().toISOString().slice(0, 10);

const ESTADO_BADGE = {
  activo: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  cancelado: 'bg-slate-100 text-slate-600 border-slate-200',
  vencido: 'bg-rose-100 text-rose-700 border-rose-200',
};

const ESTADO_LABEL = {
  activo: 'Activo',
  cancelado: 'Cancelado',
  vencido: 'Vencido',
};

const calcularDiasRestantes = (fechaVencimiento) => {
  if (!fechaVencimiento) return 0;
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const venc = new Date(`${fechaVencimiento}T00:00:00`);
  return Math.round((venc - hoy) / (1000 * 60 * 60 * 24));
};

const extraerData = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const mensajeError = (error, fallback) => {
  const data = error?.response?.data;
  if (!data) return fallback;
  if (data.error) return data.error;
  const primerCampo = Object.values(data)[0];
  if (Array.isArray(primerCampo)) return primerCampo[0];
  if (typeof primerCampo === 'string') return primerCampo;
  return fallback;
};

const Creditos = () => {
  const { user } = useAuthStore();

  const puedeVer = hasMenuPermission(user, 'creditos', 'view');
  const puedeCrear = hasMenuPermission(user, 'creditos', 'create');
  const puedeEditar = hasMenuPermission(user, 'creditos', 'edit');
  const puedeEliminar = hasMenuPermission(user, 'creditos', 'delete');
  const puedeAbonar = hasSubmenuPermission(user, 'creditos', 'abonos', 'create');
  const puedeEditarAbono = hasSubmenuPermission(user, 'creditos', 'abonos', 'edit');
  const puedeEliminarAbono = hasSubmenuPermission(user, 'creditos', 'abonos', 'delete');
  const puedeVerReportes = hasSubmenuPermission(user, 'creditos', 'reportes', 'view');
  const puedeExportarExcel = hasSubmenuPermission(user, 'creditos', 'reportes', 'export_excel');
  const puedeExportarPdf = hasSubmenuPermission(user, 'creditos', 'reportes', 'export_pdf');
  const puedeImprimir = hasSubmenuPermission(user, 'creditos', 'reportes', 'print');

  const [loading, setLoading] = useState(true);
  const [empleados, setEmpleados] = useState([]);
  const [estilistaActivoId, setEstilistaActivoId] = useState(null);
  const [creditosEmpleado, setCreditosEmpleado] = useState([]);
  const [abonosEmpleado, setAbonosEmpleado] = useState([]);
  const [creditoActivoId, setCreditoActivoId] = useState(null);
  const [creditoDetalle, setCreditoDetalle] = useState(null);
  const [exportando, setExportando] = useState(false);

  const [showNuevoCredito, setShowNuevoCredito] = useState(false);
  const [formCredito, setFormCredito] = useState({
    valor_prestado: '', porcentaje_interes: '', plazo_dias: '30', fecha_inicio: todayStr(), observaciones: '',
  });
  const [savingCredito, setSavingCredito] = useState(false);

  const [showEditarCredito, setShowEditarCredito] = useState(false);
  const [formEditarCredito, setFormEditarCredito] = useState({
    id: null, observaciones: '', porcentaje_interes: '', plazo_dias: '', fecha_inicio: '', tieneAbonos: false,
  });
  const [savingEditarCredito, setSavingEditarCredito] = useState(false);

  const [formAbono, setFormAbono] = useState({ valor_abono: '', fecha: todayStr(), observaciones: '' });
  const [savingAbono, setSavingAbono] = useState(false);

  const [editandoAbonoId, setEditandoAbonoId] = useState(null);
  const [formEditarAbono, setFormEditarAbono] = useState({ valor_abono: '', fecha: '', observaciones: '' });
  const [savingEditAbono, setSavingEditAbono] = useState(false);

  const cargarEmpleados = useCallback(async () => {
    try {
      setLoading(true);
      const data = await creditosService.getPorEmpleado();
      setEmpleados(extraerData(data));
    } catch (error) {
      toast.error('No se pudieron cargar los créditos.');
      setEmpleados([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (puedeVer) cargarEmpleados();
  }, [puedeVer, cargarEmpleados]);

  const cargarDatosEmpleado = useCallback(async (estId) => {
    if (!estId) {
      setCreditosEmpleado([]);
      setAbonosEmpleado([]);
      return;
    }
    try {
      const [creditosResp, abonosResp] = await Promise.all([
        creditosService.getCreditos({ estilista: estId }),
        creditosService.getAbonosPorEstilista(estId),
      ]);
      setCreditosEmpleado(extraerData(creditosResp));
      setAbonosEmpleado(extraerData(abonosResp));
    } catch (error) {
      toast.error('No se pudo cargar el historial del empleado.');
    }
  }, []);

  useEffect(() => {
    cargarDatosEmpleado(estilistaActivoId);
    setCreditoActivoId(null);
    setCreditoDetalle(null);
  }, [estilistaActivoId, cargarDatosEmpleado]);

  const cargarDetalleCredito = useCallback(async (creditoId) => {
    if (!creditoId) {
      setCreditoDetalle(null);
      return;
    }
    try {
      const data = await creditosService.getCredito(creditoId);
      setCreditoDetalle(data);
    } catch (error) {
      toast.error('No se pudo cargar el detalle del crédito.');
    }
  }, []);

  useEffect(() => {
    cargarDetalleCredito(creditoActivoId);
  }, [creditoActivoId, cargarDetalleCredito]);

  const recargarTodo = async () => {
    await cargarEmpleados();
    await cargarDatosEmpleado(estilistaActivoId);
    if (creditoActivoId) await cargarDetalleCredito(creditoActivoId);
  };

  const empleadoActivo = empleados.find((e) => Number(e.id) === Number(estilistaActivoId)) || null;

  // ---- Crédito: crear ----
  const abrirNuevoCredito = () => {
    setFormCredito({ valor_prestado: '', porcentaje_interes: '', plazo_dias: '30', fecha_inicio: todayStr(), observaciones: '' });
    setShowNuevoCredito(true);
  };

  const guardarNuevoCredito = async (e) => {
    e.preventDefault();
    if (!estilistaActivoId) return;
    const valorPrestado = Number(formCredito.valor_prestado || 0);
    if (valorPrestado <= 0) {
      toast.warning('Ingresa un valor prestado mayor a cero.');
      return;
    }
    setSavingCredito(true);
    try {
      await creditosService.crearCredito({
        estilista: estilistaActivoId,
        valor_prestado: valorPrestado,
        porcentaje_interes: Number(formCredito.porcentaje_interes || 0),
        plazo_dias: Number(formCredito.plazo_dias || 30),
        fecha_inicio: formCredito.fecha_inicio,
        observaciones: formCredito.observaciones,
      });
      toast.success('Crédito creado correctamente.');
      setShowNuevoCredito(false);
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo crear el crédito.'));
    } finally {
      setSavingCredito(false);
    }
  };

  // ---- Crédito: editar / cancelar ----
  const abrirEditarCredito = (credito) => {
    setFormEditarCredito({
      id: credito.id,
      observaciones: credito.observaciones || '',
      porcentaje_interes: String(credito.porcentaje_interes ?? ''),
      plazo_dias: String(credito.plazo_dias ?? ''),
      fecha_inicio: credito.fecha_inicio || '',
      tieneAbonos: Number(credito.abonos_count || 0) > 0,
    });
    setShowEditarCredito(true);
  };

  const guardarEditarCredito = async (e) => {
    e.preventDefault();
    setSavingEditarCredito(true);
    try {
      const payload = { observaciones: formEditarCredito.observaciones };
      if (!formEditarCredito.tieneAbonos) {
        payload.porcentaje_interes = Number(formEditarCredito.porcentaje_interes || 0);
        payload.plazo_dias = Number(formEditarCredito.plazo_dias || 0);
        payload.fecha_inicio = formEditarCredito.fecha_inicio;
      }
      await creditosService.actualizarCredito(formEditarCredito.id, payload);
      toast.success('Crédito actualizado correctamente.');
      setShowEditarCredito(false);
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo actualizar el crédito.'));
    } finally {
      setSavingEditarCredito(false);
    }
  };

  const cancelarCredito = async (credito) => {
    if (!window.confirm(`¿Marcar el crédito #${credito.id} como cancelado?`)) return;
    try {
      await creditosService.actualizarCredito(credito.id, {
        estado: 'cancelado',
        observaciones: credito.observaciones || '',
      });
      toast.success('Crédito marcado como cancelado.');
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo cancelar el crédito.'));
    }
  };

  // ---- Crédito: eliminar (solo si no tiene abonos) ----
  const eliminarCredito = async (credito) => {
    if (Number(credito.abonos_count || 0) > 0) return;
    if (!window.confirm(`¿Eliminar el crédito #${credito.id}? Esta acción no se puede deshacer.`)) return;
    try {
      await creditosService.eliminarCredito(credito.id);
      toast.success('Crédito eliminado.');
      if (Number(creditoActivoId) === Number(credito.id)) setCreditoActivoId(null);
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo eliminar el crédito.'));
    }
  };

  // ---- Abono: crear ----
  const registrarAbono = async (e) => {
    e.preventDefault();
    if (!creditoActivoId) return;
    const valorAbono = Number(formAbono.valor_abono || 0);
    if (valorAbono <= 0) {
      toast.warning('Ingresa un valor de abono mayor a cero.');
      return;
    }
    setSavingAbono(true);
    try {
      await creditosService.crearAbono({
        credito: creditoActivoId,
        fecha: formAbono.fecha,
        valor_abono: valorAbono,
        observaciones: formAbono.observaciones,
      });
      toast.success('Abono registrado correctamente.');
      setFormAbono({ valor_abono: '', fecha: todayStr(), observaciones: '' });
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo registrar el abono.'));
    } finally {
      setSavingAbono(false);
    }
  };

  // ---- Abono: editar ----
  const iniciarEdicionAbono = (abono) => {
    setEditandoAbonoId(abono.id);
    setFormEditarAbono({
      valor_abono: String(abono.valor_abono),
      fecha: abono.fecha,
      observaciones: abono.observaciones || '',
    });
  };

  const guardarEdicionAbono = async (abonoId) => {
    const valorAbono = Number(formEditarAbono.valor_abono || 0);
    if (valorAbono <= 0) {
      toast.warning('Ingresa un valor de abono mayor a cero.');
      return;
    }
    setSavingEditAbono(true);
    try {
      await creditosService.editarAbono(abonoId, {
        credito: creditoActivoId,
        fecha: formEditarAbono.fecha,
        valor_abono: valorAbono,
        observaciones: formEditarAbono.observaciones,
      });
      toast.success('Abono actualizado correctamente.');
      setEditandoAbonoId(null);
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo actualizar el abono.'));
    } finally {
      setSavingEditAbono(false);
    }
  };

  // ---- Abono: eliminar ----
  const eliminarAbono = async (abono) => {
    if (!window.confirm('¿Eliminar este abono? Esta acción no se puede deshacer.')) return;
    try {
      await creditosService.eliminarAbono(abono.id);
      toast.success('Abono eliminado.');
      await recargarTodo();
    } catch (error) {
      toast.error(mensajeError(error, 'No se pudo eliminar el abono.'));
    }
  };

  // ---- Exportar / imprimir ----
  const descargarBlob = (blob, filename) => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  const nombreArchivoBase = () => {
    const nombre = empleadoActivo ? empleadoActivo.nombre.replace(/\s+/g, '_') : 'todos';
    return `creditos_${nombre}_${todayStr()}`;
  };

  const exportarExcel = async () => {
    setExportando(true);
    try {
      const blob = await creditosService.exportarExcel(estilistaActivoId);
      descargarBlob(blob, `${nombreArchivoBase()}.csv`);
      toast.success('Excel exportado correctamente.');
    } catch (error) {
      toast.error('No se pudo exportar a Excel.');
    } finally {
      setExportando(false);
    }
  };

  const exportarPdf = async () => {
    setExportando(true);
    try {
      const blob = await creditosService.exportarPdf(estilistaActivoId);
      descargarBlob(blob, `${nombreArchivoBase()}.pdf`);
      toast.success('PDF exportado correctamente.');
    } catch (error) {
      toast.error('No se pudo exportar a PDF.');
    } finally {
      setExportando(false);
    }
  };

  const imprimir = () => window.print();

  if (!puedeVer) {
    return <div className="card text-slate-500">No tienes permiso para ver el módulo de Créditos.</div>;
  }

  return (
    <div className="space-y-6 fade-in">
      <section className="relative overflow-hidden rounded-[30px] border border-slate-800 bg-[radial-gradient(circle_at_15%_20%,rgba(139,92,246,0.22),transparent_30%),radial-gradient(circle_at_85%_15%,rgba(168,85,247,0.22),transparent_34%),linear-gradient(120deg,#020617_0%,#1f1f3f_45%,#2a1a4a_100%)] p-7 text-white shadow-2xl print:hidden">
        <div className="absolute -right-14 -top-14 h-44 w-44 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute -left-12 bottom-0 h-40 w-40 rounded-full bg-violet-300/10 blur-3xl" />
        <div className="relative z-10">
          <h1 className="text-3xl md:text-4xl font-black tracking-tight">Créditos de Empleados</h1>
          <p className="text-slate-300 mt-2 max-w-3xl">Gestiona créditos otorgados a empleados, registra abonos y consulta el historial completo de pagos.</p>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-6">
        <aside className="card border border-slate-200 bg-slate-50 print:hidden">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h3 className="card-header mb-0">Empleados</h3>
            <button className="btn-secondary !py-1.5" onClick={cargarEmpleados} disabled={loading}>
              {loading ? '...' : 'Actualizar'}
            </button>
          </div>
          <div className="space-y-2 max-h-[68vh] overflow-y-auto pr-1">
            {empleados.length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">No hay empleados con créditos registrados.</div>
            )}
            {empleados.map((item) => {
              const estId = Number(item.id);
              const activo = estId === Number(estilistaActivoId);
              return (
                <button
                  key={estId}
                  type="button"
                  onClick={() => setEstilistaActivoId(estId)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${activo ? 'border-emerald-400 bg-emerald-50 shadow-md' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                >
                  <p className="font-semibold text-slate-900">{item.nombre}</p>
                  <p className="text-xs text-slate-500 mt-1">Saldo pendiente: <b>{formatMoney(item.saldo_pendiente)}</b></p>
                  <p className="text-xs text-violet-700 mt-1">Activos: {item.creditos_activos} · Cancelados: {item.creditos_cancelados}</p>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="space-y-4">
          {!empleadoActivo && (
            <div className="card text-slate-500">Selecciona un empleado en el panel izquierdo para ver su historial de créditos.</div>
          )}

          {empleadoActivo && (
            <>
              <div className="card border border-violet-200 bg-violet-50">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="card-header mb-0">{empleadoActivo.nombre}</h2>
                  {puedeCrear && (
                    <button className="btn-primary inline-flex items-center gap-2 print:hidden" onClick={abrirNuevoCredito}>
                      <FiPlus /> Nuevo crédito
                    </button>
                  )}
                </div>
                <div className="mt-4 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Total otorgado</p>
                    <p className="text-lg font-black text-slate-900">{formatMoney(empleadoActivo.total_otorgado)}</p>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Total prestado</p>
                    <p className="text-lg font-black text-slate-900">{formatMoney(empleadoActivo.total_prestado)}</p>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Total abonado</p>
                    <p className="text-lg font-black text-sky-700">{formatMoney(empleadoActivo.total_abonado)}</p>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Saldo pendiente</p>
                    <p className="text-lg font-black text-rose-700">{formatMoney(empleadoActivo.saldo_pendiente)}</p>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Créditos activos</p>
                    <p className="text-lg font-black text-emerald-700">{empleadoActivo.creditos_activos}</p>
                  </div>
                  <div className="rounded-xl border border-violet-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Créditos cancelados</p>
                    <p className="text-lg font-black text-slate-500">{empleadoActivo.creditos_cancelados}</p>
                  </div>
                </div>
              </div>

              <div className="card">
                <h2 className="card-header">Historial de créditos</h2>
                <div className="mt-3 overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="table-header">
                      <tr>
                        <th className="px-4 py-3 text-left">#</th>
                        <th className="px-4 py-3 text-left">Fecha creación</th>
                        <th className="px-4 py-3 text-left">Prestado</th>
                        <th className="px-4 py-3 text-left">Interés</th>
                        <th className="px-4 py-3 text-left">Total</th>
                        <th className="px-4 py-3 text-left">Abonado</th>
                        <th className="px-4 py-3 text-left">Saldo</th>
                        <th className="px-4 py-3 text-left">Vencimiento</th>
                        <th className="px-4 py-3 text-left">Estado</th>
                        <th className="px-4 py-3 text-left print:hidden">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {creditosEmpleado.length === 0 && (
                        <tr><td className="table-cell text-slate-500" colSpan={10}>Este empleado no tiene créditos registrados.</td></tr>
                      )}
                      {creditosEmpleado.map((credito) => {
                        const estadoMostrado = credito.estado_calculado || credito.estado;
                        const diasRestantes = calcularDiasRestantes(credito.fecha_vencimiento);
                        const puedeEliminarEste = puedeEliminar && Number(credito.abonos_count || 0) === 0;
                        return (
                          <tr
                            key={credito.id}
                            className={`cursor-pointer ${Number(creditoActivoId) === credito.id ? 'bg-violet-100' : 'hover:bg-slate-50'}`}
                            onClick={() => setCreditoActivoId(credito.id)}
                          >
                            <td className="table-cell font-semibold">#{credito.id}</td>
                            <td className="table-cell">{(credito.fecha_creacion || '').slice(0, 10) || '-'}</td>
                            <td className="table-cell">{formatMoney(credito.valor_prestado)}</td>
                            <td className="table-cell">{formatMoney(credito.valor_interes)} ({credito.porcentaje_interes}%)</td>
                            <td className="table-cell font-semibold">{formatMoney(credito.valor_total)}</td>
                            <td className="table-cell text-sky-700">{formatMoney(credito.valor_total - credito.saldo_actual)}</td>
                            <td className="table-cell text-rose-700 font-semibold">{formatMoney(credito.saldo_actual)}</td>
                            <td className="table-cell">
                              {credito.fecha_vencimiento}
                              {Number(credito.saldo_actual) > 0 && (
                                <span className={`block text-xs ${diasRestantes < 0 ? 'text-rose-600' : 'text-slate-500'}`}>
                                  {diasRestantes >= 0 ? `${diasRestantes} día(s) restantes` : `${Math.abs(diasRestantes)} día(s) vencido`}
                                </span>
                              )}
                            </td>
                            <td className="table-cell">
                              <span className={`inline-flex items-center rounded-full border px-2 py-1 text-xs font-semibold uppercase ${ESTADO_BADGE[estadoMostrado] || ESTADO_BADGE.activo}`}>
                                {ESTADO_LABEL[estadoMostrado] || estadoMostrado}
                              </span>
                            </td>
                            <td className="table-cell print:hidden" onClick={(e) => e.stopPropagation()}>
                              <div className="flex items-center gap-2">
                                {puedeEditar && (
                                  <button className="text-violet-600 hover:text-violet-800" title="Editar crédito" onClick={() => abrirEditarCredito(credito)}>
                                    <FiEdit2 />
                                  </button>
                                )}
                                {puedeEliminar && (
                                  <button
                                    className={puedeEliminarEste ? 'text-rose-500 hover:text-rose-700' : 'text-rose-300 cursor-not-allowed'}
                                    title={puedeEliminarEste ? 'Eliminar crédito' : 'No se puede eliminar: ya tiene abonos registrados'}
                                    disabled={!puedeEliminarEste}
                                    onClick={() => puedeEliminarEste && eliminarCredito(credito)}
                                  >
                                    <FiTrash2 />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {creditoDetalle && (
                <div className="card border border-sky-200 bg-sky-50">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="card-header mb-0">Crédito #{creditoDetalle.id} — Detalle y abonos</h2>
                    {puedeEditar && (creditoDetalle.estado_calculado || creditoDetalle.estado) !== 'cancelado' && (
                      <button className="btn-secondary !py-1.5 print:hidden" onClick={() => cancelarCredito(creditoDetalle)}>
                        Marcar como cancelado
                      </button>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div><p className="text-slate-500">Días transcurridos</p><p className="font-semibold">{creditoDetalle.dias_transcurridos}</p></div>
                    <div><p className="text-slate-500">Días restantes</p><p className="font-semibold">{creditoDetalle.dias_restantes}</p></div>
                    <div><p className="text-slate-500">Creado por</p><p className="font-semibold">{creditoDetalle.usuario_creador_nombre || '-'}</p></div>
                    <div><p className="text-slate-500">Última edición</p><p className="font-semibold">{creditoDetalle.usuario_editor_nombre || '-'}</p></div>
                  </div>
                  {creditoDetalle.observaciones && (
                    <p className="mt-2 text-sm text-slate-600">Observaciones: {creditoDetalle.observaciones}</p>
                  )}

                  {puedeAbonar && Number(creditoDetalle.saldo_actual) > 0 && (
                    <form onSubmit={registrarAbono} className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end bg-white rounded-xl border border-sky-200 p-3 print:hidden">
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Fecha</label>
                        <input type="date" className="input-field" value={formAbono.fecha} onChange={(e) => setFormAbono((p) => ({ ...p, fecha: e.target.value }))} />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Valor a abonar</label>
                        <input type="number" min="1" className="input-field" value={formAbono.valor_abono} onChange={(e) => setFormAbono((p) => ({ ...p, valor_abono: e.target.value }))} placeholder="0" />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Observaciones</label>
                        <input type="text" className="input-field" value={formAbono.observaciones} onChange={(e) => setFormAbono((p) => ({ ...p, observaciones: e.target.value }))} />
                      </div>
                      <button type="submit" className="btn-primary" disabled={savingAbono}>
                        {savingAbono ? 'Guardando...' : 'Registrar abono'}
                      </button>
                    </form>
                  )}

                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="table-header">
                        <tr>
                          <th className="px-4 py-3 text-left">Fecha</th>
                          <th className="px-4 py-3 text-left">Valor</th>
                          <th className="px-4 py-3 text-left">Saldo antes</th>
                          <th className="px-4 py-3 text-left">Saldo después</th>
                          <th className="px-4 py-3 text-left">Usuario</th>
                          <th className="px-4 py-3 text-left">Observaciones</th>
                          {(puedeEditarAbono || puedeEliminarAbono) && <th className="px-4 py-3 text-left print:hidden">Acciones</th>}
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {(creditoDetalle.abonos || []).length === 0 && (
                          <tr><td className="table-cell text-slate-500" colSpan={7}>Este crédito no tiene abonos registrados.</td></tr>
                        )}
                        {(creditoDetalle.abonos || []).map((abono) => {
                          const editando = editandoAbonoId === abono.id;
                          return (
                            <tr key={abono.id}>
                              {editando ? (
                                <>
                                  <td className="table-cell">
                                    <input type="date" className="input-field !py-1" value={formEditarAbono.fecha} onChange={(e) => setFormEditarAbono((p) => ({ ...p, fecha: e.target.value }))} />
                                  </td>
                                  <td className="table-cell">
                                    <input type="number" min="1" className="input-field !py-1" value={formEditarAbono.valor_abono} onChange={(e) => setFormEditarAbono((p) => ({ ...p, valor_abono: e.target.value }))} />
                                  </td>
                                  <td className="table-cell">{formatMoney(abono.saldo_anterior)}</td>
                                  <td className="table-cell text-slate-400">Se recalcula al guardar</td>
                                  <td className="table-cell">{abono.usuario_nombre || '-'}</td>
                                  <td className="table-cell">
                                    <input type="text" className="input-field !py-1" value={formEditarAbono.observaciones} onChange={(e) => setFormEditarAbono((p) => ({ ...p, observaciones: e.target.value }))} />
                                  </td>
                                  <td className="table-cell print:hidden">
                                    <div className="flex gap-2">
                                      <button className="btn-primary !py-1 !px-2 text-xs" disabled={savingEditAbono} onClick={() => guardarEdicionAbono(abono.id)}>
                                        {savingEditAbono ? '...' : 'Guardar'}
                                      </button>
                                      <button className="btn-secondary !py-1 !px-2 text-xs" onClick={() => setEditandoAbonoId(null)}>Cancelar</button>
                                    </div>
                                  </td>
                                </>
                              ) : (
                                <>
                                  <td className="table-cell">{abono.fecha}</td>
                                  <td className="table-cell text-sky-700 font-semibold">{formatMoney(abono.valor_abono)}</td>
                                  <td className="table-cell">{formatMoney(abono.saldo_anterior)}</td>
                                  <td className="table-cell">{formatMoney(abono.saldo_restante)}</td>
                                  <td className="table-cell">{abono.usuario_nombre || '-'}</td>
                                  <td className="table-cell text-sm text-slate-600">{abono.observaciones || '-'}</td>
                                  {(puedeEditarAbono || puedeEliminarAbono) && (
                                    <td className="table-cell print:hidden">
                                      <div className="flex gap-2">
                                        {puedeEditarAbono && (
                                          <button className="text-violet-600 hover:text-violet-800" onClick={() => iniciarEdicionAbono(abono)}><FiEdit2 /></button>
                                        )}
                                        {puedeEliminarAbono && (
                                          <button className="text-rose-500 hover:text-rose-700" onClick={() => eliminarAbono(abono)}><FiTrash2 /></button>
                                        )}
                                      </div>
                                    </td>
                                  )}
                                </>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="card">
                <h2 className="card-header">Historial de pagos</h2>
                <p className="text-sm text-slate-500 mb-3">Todos los abonos realizados por este empleado, en todos sus créditos (incluidos los ya cancelados).</p>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="table-header">
                      <tr>
                        <th className="px-4 py-3 text-left">Fecha</th>
                        <th className="px-4 py-3 text-left">Crédito</th>
                        <th className="px-4 py-3 text-left">Valor abonado</th>
                        <th className="px-4 py-3 text-left">Saldo antes</th>
                        <th className="px-4 py-3 text-left">Saldo después</th>
                        <th className="px-4 py-3 text-left">Usuario</th>
                        <th className="px-4 py-3 text-left">Observaciones</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {abonosEmpleado.length === 0 && (
                        <tr><td className="table-cell text-slate-500" colSpan={7}>Sin pagos registrados todavía.</td></tr>
                      )}
                      {abonosEmpleado.map((abono) => (
                        <tr key={abono.id}>
                          <td className="table-cell">{abono.fecha}</td>
                          <td className="table-cell font-semibold">#{abono.credito}</td>
                          <td className="table-cell text-sky-700 font-semibold">{formatMoney(abono.valor_abono)}</td>
                          <td className="table-cell">{formatMoney(abono.saldo_anterior)}</td>
                          <td className="table-cell">{formatMoney(abono.saldo_restante)}</td>
                          <td className="table-cell">{abono.usuario_nombre || '-'}</td>
                          <td className="table-cell text-sm text-slate-600">{abono.observaciones || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {puedeVerReportes && (
                <div className="card border border-emerald-200 bg-emerald-50 print:hidden">
                  <h2 className="card-header">Reportes</h2>
                  <div className="flex flex-wrap gap-2">
                    {puedeExportarExcel && (
                      <button className="btn-secondary inline-flex items-center gap-2" onClick={exportarExcel} disabled={exportando}>
                        <FiDownload /> Exportar Excel
                      </button>
                    )}
                    {puedeExportarPdf && (
                      <button className="btn-secondary inline-flex items-center gap-2" onClick={exportarPdf} disabled={exportando}>
                        <FiDownload /> Exportar PDF
                      </button>
                    )}
                    {puedeImprimir && (
                      <button className="btn-secondary inline-flex items-center gap-2" onClick={imprimir}>
                        <FiPrinter /> Imprimir
                      </button>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>

      <ModalForm isOpen={showNuevoCredito} title="Nuevo crédito" subtitle={empleadoActivo?.nombre} onClose={() => setShowNuevoCredito(false)} size="md">
        <form className="grid grid-cols-1 md:grid-cols-2 gap-3" onSubmit={guardarNuevoCredito}>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Valor prestado</label>
            <input type="number" min="1" className="input-field" value={formCredito.valor_prestado} onChange={(e) => setFormCredito((p) => ({ ...p, valor_prestado: e.target.value }))} required />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Interés (%)</label>
            <input type="number" min="0" step="0.01" className="input-field" value={formCredito.porcentaje_interes} onChange={(e) => setFormCredito((p) => ({ ...p, porcentaje_interes: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Plazo (días)</label>
            <input type="number" min="1" className="input-field" value={formCredito.plazo_dias} onChange={(e) => setFormCredito((p) => ({ ...p, plazo_dias: e.target.value }))} required />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Fecha de inicio</label>
            <input type="date" className="input-field" value={formCredito.fecha_inicio} onChange={(e) => setFormCredito((p) => ({ ...p, fecha_inicio: e.target.value }))} required />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-slate-600 mb-1">Observaciones</label>
            <textarea className="input-field" rows={2} value={formCredito.observaciones} onChange={(e) => setFormCredito((p) => ({ ...p, observaciones: e.target.value }))} />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setShowNuevoCredito(false)}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={savingCredito}>{savingCredito ? 'Guardando...' : 'Crear crédito'}</button>
          </div>
        </form>
      </ModalForm>

      <ModalForm isOpen={showEditarCredito} title={`Editar crédito #${formEditarCredito.id || ''}`} onClose={() => setShowEditarCredito(false)} size="md">
        <form className="grid grid-cols-1 md:grid-cols-2 gap-3" onSubmit={guardarEditarCredito}>
          {formEditarCredito.tieneAbonos && (
            <p className="md:col-span-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2">
              Este crédito ya tiene abonos registrados: solo se pueden editar las observaciones.
            </p>
          )}
          <div>
            <label className="block text-xs text-slate-600 mb-1">Interés (%)</label>
            <input type="number" min="0" step="0.01" className="input-field" disabled={formEditarCredito.tieneAbonos} value={formEditarCredito.porcentaje_interes} onChange={(e) => setFormEditarCredito((p) => ({ ...p, porcentaje_interes: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Plazo (días)</label>
            <input type="number" min="1" className="input-field" disabled={formEditarCredito.tieneAbonos} value={formEditarCredito.plazo_dias} onChange={(e) => setFormEditarCredito((p) => ({ ...p, plazo_dias: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs text-slate-600 mb-1">Fecha de inicio</label>
            <input type="date" className="input-field" disabled={formEditarCredito.tieneAbonos} value={formEditarCredito.fecha_inicio} onChange={(e) => setFormEditarCredito((p) => ({ ...p, fecha_inicio: e.target.value }))} />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs text-slate-600 mb-1">Observaciones</label>
            <textarea className="input-field" rows={2} value={formEditarCredito.observaciones} onChange={(e) => setFormEditarCredito((p) => ({ ...p, observaciones: e.target.value }))} />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setShowEditarCredito(false)}>Cancelar</button>
            <button type="submit" className="btn-primary" disabled={savingEditarCredito}>{savingEditarCredito ? 'Guardando...' : 'Guardar cambios'}</button>
          </div>
        </form>
      </ModalForm>
    </div>
  );
};

export default Creditos;
