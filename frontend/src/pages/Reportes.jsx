import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { format } from 'date-fns';
import { reportesService, productosService } from '../services/api';
import { toast } from 'react-toastify';
import useAuthStore from '../store/authStore';
import { hasSubmenuPermission } from '../utils/permissions';

const today = new Date();
const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

const MODULOS = [
  { key: 'cierre', label: '1. Cierre de Caja (Resumen Global)' },
  { key: 'liquidacion', label: '2. Liquidación Empleado (Por Día)' },
  { key: 'cartera', label: '3. Cartera Empleado' },
  { key: 'ajuste', label: '4. Ajuste Diario' },
  { key: 'agotarse', label: '5. Productos por Agotarse' },
];
const REPORTES_UI_VERSION = '2026-04-06 v4';

const MODULO_META = {
  cierre: {
    subtitle: 'Ingresos, egresos y cuadre diario por medios',
    accent: 'from-sky-500/20 to-cyan-500/10',
    border: 'border-sky-300/60',
  },
  ajuste: {
    subtitle: 'Ajustes centralizados por empleado y fecha',
    accent: 'from-emerald-500/20 to-teal-500/10',
    border: 'border-emerald-300/60',
  },
  liquidacion: {
    subtitle: 'Pago empleado, puesto y consumo en una sola vista',
    accent: 'from-indigo-500/20 to-blue-500/10',
    border: 'border-indigo-300/60',
  },
  cartera: {
    subtitle: 'Control de facturas, abonos y saldos pendientes',
    accent: 'from-amber-500/20 to-orange-500/10',
    border: 'border-amber-300/60',
  },
  agotarse: {
    subtitle: 'Productos críticos con stock bajo',
    accent: 'from-rose-500/20 to-red-500/10',
    border: 'border-rose-300/60',
  },
};

const MEDIOS_PAGO = [
  { value: 'todos', label: 'Todos los medios' },
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const MEDIOS_PAGO_OPERACION = [
  { value: 'efectivo', label: 'Efectivo' },
  { value: 'nequi', label: 'Nequi' },
  { value: 'daviplata', label: 'Daviplata' },
  { value: 'otros', label: 'Otros' },
];

const moneyFormatter = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const formatMoney = (value) => `$${moneyFormatter.format(Number(value || 0))}`;

const KpiCard = ({ title, value, hint, tone = 'slate' }) => {
  const tones = {
    slate: 'from-slate-900 to-slate-700 text-white',
    emerald: 'from-emerald-600 to-teal-500 text-white',
    sky: 'from-sky-600 to-blue-600 text-white',
    amber: 'from-amber-500 to-orange-500 text-white',
  };

  return (
    <div className={`rounded-2xl bg-gradient-to-br ${tones[tone]} p-5 shadow-lg`}>
      <p className="text-sm opacity-85">{title}</p>
      <p className="mt-2 text-2xl font-black">{value}</p>
      <p className="mt-2 text-xs opacity-85">{hint}</p>
    </div>
  );
};

const NumericPad = ({ visible, value, onChange, onClose }) => {
  if (!visible) return null;

  const append = (token) => {
    const current = String(value || '');
    if (token === 'DEL') {
      onChange(current.slice(0, -1));
      return;
    }
    if (token === 'C') {
      onChange('');
      return;
    }
    if (token === '00') {
      onChange(`${current}00`);
      return;
    }
    onChange(`${current}${token}`);
  };

  return (
    <div className="fixed bottom-4 right-4 z-[80] w-[280px] rounded-2xl border border-slate-300 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-100 px-4 py-2 rounded-t-2xl">
        <span className="text-sm font-semibold text-slate-700">Teclado numérico</span>
        <button type="button" className="btn-secondary !px-3 !py-1" onClick={onClose}>Cerrar</button>
      </div>
      <div className="p-3">
        <div className="mb-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-right text-lg font-bold text-slate-900 min-h-[44px]">
          {value || '0'}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '00', 'DEL'].map((k) => (
            <button key={k} type="button" className="btn-secondary !py-3" onClick={() => append(k)}>
              {k}
            </button>
          ))}
        </div>
        <button type="button" className="btn-danger !w-full !py-3 mt-2" onClick={() => append('C')}>Limpiar</button>
      </div>
    </div>
  );
};

const Reportes = () => {
  const { user } = useAuthStore();
  const rolUsuario = String(user?.rol || '').trim().toLowerCase();
  const esAdministrador = rolUsuario === 'administrador';
  const puedeCorregirLiquidacion = rolUsuario === 'administrador' || rolUsuario === 'gerente';
  const esRecepcion = rolUsuario === 'recepcion';
  const [moduloActivo, setModuloActivo] = useState('cierre');
  const [periodo, setPeriodo] = useState('mes');
  const [fechaInicio, setFechaInicio] = useState(format(firstDay, 'yyyy-MM-dd'));
  const [fechaFin, setFechaFin] = useState(format(today, 'yyyy-MM-dd'));
  const [medioPago, setMedioPago] = useState('todos');

  const [loading, setLoading] = useState(true);
  const [cierreCaja, setCierreCaja] = useState(null);
  const [biData, setBiData] = useState(null);
  const [carteraData, setCarteraData] = useState({ resumen: [], deudas: [], abonos_historial: [] });
  const [carteraDataLiquidacionGlobal, setCarteraDataLiquidacionGlobal] = useState({ resumen: [], deudas: [], abonos_historial: [] });
  const [abonoPorDeuda, setAbonoPorDeuda] = useState({});
  const [medioAbonoPorDeuda, setMedioAbonoPorDeuda] = useState({});
  const [savingAbonoByDeuda, setSavingAbonoByDeuda] = useState({});
  const [editMontoByAbono, setEditMontoByAbono] = useState({});
  const [editMedioByAbono, setEditMedioByAbono] = useState({});
  const [editFechaByAbono, setEditFechaByAbono] = useState({});
  const [editNotasByAbono, setEditNotasByAbono] = useState({});
  const [savingEditByAbono, setSavingEditByAbono] = useState({});
  const [deudaActivaHistorial, setDeudaActivaHistorial] = useState(null);
  const [filtroCarteraEstilistaId, setFiltroCarteraEstilistaId] = useState('todos');
  const [mostrarFacturasSaldadas, setMostrarFacturasSaldadas] = useState(false);
  const [estilistaActivoLiquidacion, setEstilistaActivoLiquidacion] = useState(null);
  const [pagosPorEstilista, setPagosPorEstilista] = useState({});
  const [estadoDiaPorEstilista, setEstadoDiaPorEstilista] = useState({});
  const [abonoPuestoPorEstilista, setAbonoPuestoPorEstilista] = useState({});
  const [modoCobroPuestoPorEstilista, setModoCobroPuestoPorEstilista] = useState({});
  const [porcentajePuestoPorEstilista, setPorcentajePuestoPorEstilista] = useState({});
  const [abonoPuestoAcumuladoPorEstilista, setAbonoPuestoAcumuladoPorEstilista] = useState({});
  const [medioAbonoPuestoPorEstilista, setMedioAbonoPuestoPorEstilista] = useState({});
  const [aplicaComisionVentasPorEstilista, setAplicaComisionVentasPorEstilista] = useState({});
  const [cobroConsumoPorEstilista, setCobroConsumoPorEstilista] = useState({});
  const [medioCobroConsumoPorEstilista, setMedioCobroConsumoPorEstilista] = useState({});
  const [deudaConsumoSeleccionadasPorEstilista, setDeudaConsumoSeleccionadasPorEstilista] = useState({});
  const [modoCorreccionPorEstilista, setModoCorreccionPorEstilista] = useState({});
  const [savingEstadoByEstilista, setSavingEstadoByEstilista] = useState({});
  const [skipDescuentoPuestoPorEstilista, setSkipDescuentoPuestoPorEstilista] = useState({});
  const [deudaPuestoModal, setDeudaPuestoModal] = useState({ open: false, estilista_id: null, fecha: '', monto: '', notas: '', loading: false });
  const [numericPadTarget, setNumericPadTarget] = useState(null);
  const [desgloseLiquidacion, setDesgloseLiquidacion] = useState(null);
  const [loadingDesgloseLiquidacion, setLoadingDesgloseLiquidacion] = useState(false);
  const [historialEstados, setHistorialEstados] = useState([]);
  const [loadingHistorial, setLoadingHistorial] = useState(false);
  const [cuadreDiarioByEstilista, setCuadreDiarioByEstilista] = useState({});
  const [savingCuadreDiaByKey, setSavingCuadreDiaByKey] = useState({});
  const [nuevaFechaEspacioById, setNuevaFechaEspacioById] = useState({});
  const [montoMoverEspacioById, setMontoMoverEspacioById] = useState({});
  const [savingFechaEspacioById, setSavingFechaEspacioById] = useState({});
  const [editFechaAbonoConsumoById, setEditFechaAbonoConsumoById] = useState({});
  const [savingFechaAbonoConsumoById, setSavingFechaAbonoConsumoById] = useState({});
  const [ajusteDiarioRows, setAjusteDiarioRows] = useState([]);
  const [loadingAjusteDiario, setLoadingAjusteDiario] = useState(false);
  const [ajusteDiarioEditsByKey, setAjusteDiarioEditsByKey] = useState({});
  const [savingAjusteDiarioByKey, setSavingAjusteDiarioByKey] = useState({});
  const [filtroAjusteTexto, setFiltroAjusteTexto] = useState('');
  const [soloPendientesAjuste, setSoloPendientesAjuste] = useState(false);
  const [vistaSimpleLiquidacion, setVistaSimpleLiquidacion] = useState(true);
  const [pasoLiquidacion, setPasoLiquidacion] = useState(1);
  const [cierreTabActiva, setCierreTabActiva] = useState('medios');
  const [reabastecerByProductoId, setReabastecerByProductoId] = useState({});
  const [savingStockByProductoId, setSavingStockByProductoId] = useState({});
  const cargarTodoSeqRef = useRef(0);

  const calcularPendientePagoEmpleado = useCallback((fila) => {
    const pendienteConsolidado = Number(fila?.pendiente_pago_empleado ?? fila?.pago_neto_pendiente ?? 0);
    if (Number.isFinite(pendienteConsolidado) && pendienteConsolidado >= 0) {
      return pendienteConsolidado;
    }

    const pendienteBackend = Number(fila?.pago_neto_pendiente ?? 0);
    if (Number.isFinite(pendienteBackend) && pendienteBackend >= 0) {
      return pendienteBackend;
    }

    const valorTotalEmpleado = Number((fila?.valor_total_empleado ?? fila?.facturacion_servicios ?? fila?.ganancias_servicios) || 0);
    const comisionesEmpleado = Number(fila?.comision_ventas_producto || 0);
    const deudaPuestoAcumulada = Number(fila?.deuda_total_acumulada || 0);
    const pagadoEmpleadoPeriodo = Number(fila?.pagado_empleado_periodo || 0);
    return Math.max((valorTotalEmpleado + comisionesEmpleado) - deudaPuestoAcumulada - pagadoEmpleadoPeriodo, 0);
  }, []);

  const puedeAjustarFechaEspacio = rolUsuario === 'administrador' || rolUsuario === 'gerente';
  const puedeAjustarFechaAbonoConsumo = !esRecepcion;

  const ajustarFechaPagoEspacio = async (item) => {
    const estadoId = Number(item?.estado_pago_id || 0);
    const fechaNueva = String(nuevaFechaEspacioById[estadoId] || '').trim();
    const montoMoverRaw = montoMoverEspacioById[estadoId];
    const montoMover = Number(montoMoverRaw || item?.valor_pagado || 0);

    if (!estadoId) {
      toast.error('No se puede ajustar este registro porque no tiene identificador editable.');
      return;
    }
    if (!fechaNueva) {
      toast.warning('Selecciona una fecha nueva.');
      return;
    }
    if (!Number.isFinite(montoMover) || montoMover <= 0) {
      toast.warning('Ingresa un monto a mover mayor a 0.');
      return;
    }

    setSavingFechaEspacioById((prev) => ({ ...prev, [estadoId]: true }));
    try {
      await reportesService.moverFechaEstadoPagoDia({
        estado_pago_id: estadoId,
        nueva_fecha: fechaNueva,
        monto_mover: montoMover,
      });
      toast.success('Pago de espacio ajustado correctamente.');
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo ajustar la fecha del pago de espacio.';
      toast.error(String(msg));
    } finally {
      setSavingFechaEspacioById((prev) => ({ ...prev, [estadoId]: false }));
    }
  };

  const ajustarFechaAbonoConsumo = async (item) => {
    const abonoId = Number(item?.abono_id || 0);
    const fechaNueva = String(editFechaAbonoConsumoById[abonoId] || '').trim();

    if (!abonoId) {
      toast.error('Este registro no tiene identificador de abono editable.');
      return;
    }
    if (!fechaNueva) {
      toast.warning('Selecciona una fecha para el abono.');
      return;
    }

    setSavingFechaAbonoConsumoById((prev) => ({ ...prev, [abonoId]: true }));
    try {
      await reportesService.editarAbonoConsumoEmpleado({
        abono_id: abonoId,
        fecha: fechaNueva,
      });
      toast.success('Fecha de abono actualizada.');
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo actualizar la fecha del abono.';
      toast.error(String(msg));
    } finally {
      setSavingFechaAbonoConsumoById((prev) => ({ ...prev, [abonoId]: false }));
    }
  };

  const reabastecerProducto = async (item) => {
    const productoId = Number(item?.id || 0);
    const cantidad = Number(reabastecerByProductoId[productoId] || 0);
    const stockActual = Number(item?.stock || 0);

    if (!productoId) {
      toast.error('Producto inválido.');
      return;
    }
    if (!Number.isFinite(cantidad) || cantidad <= 0) {
      toast.warning('Ingresa una cantidad de reabastecimiento mayor a 0.');
      return;
    }

    const nuevoStock = stockActual + cantidad;
    setSavingStockByProductoId((prev) => ({ ...prev, [productoId]: true }));
    try {
      await productosService.ajustarStock(
        productoId,
        nuevoStock,
        `Reabastecimiento desde Reportes (+${cantidad})`
      );
      toast.success('Stock actualizado correctamente.');
      setReabastecerByProductoId((prev) => ({ ...prev, [productoId]: '' }));
      await cargarTodo();
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo actualizar el stock.';
      toast.error(String(msg));
    } finally {
      setSavingStockByProductoId((prev) => ({ ...prev, [productoId]: false }));
    }
  };

  const toMontoNoNegativo = (value) => {
    const n = Number(String(value ?? '').replace(/[^\d.]/g, ''));
    if (!Number.isFinite(n) || n < 0) return 0;
    return n;
  };

  const ajusteDiarioRowsFiltradas = useMemo(() => {
    const q = String(filtroAjusteTexto || '').trim().toLowerCase();
    return (ajusteDiarioRows || []).filter((fila) => {
      if (soloPendientesAjuste && Number(fila.pendiente_pago_empleado || 0) <= 0) return false;
      if (!q) return true;
      return (
        String(fila.estilista_nombre || '').toLowerCase().includes(q)
        || String(fila.fecha || '').toLowerCase().includes(q)
      );
    });
  }, [ajusteDiarioRows, filtroAjusteTexto, soloPendientesAjuste]);

  const resumenAjusteDiario = useMemo(() => {
    let generado = 0;
    let pendiente = 0;
    let consumo = 0;
    let abonoPuesto = 0;
    let filasModificadas = 0;

    (ajusteDiarioRowsFiltradas || []).forEach((fila) => {
      const key = `${fila.estilista_id}|${fila.fecha}`;
      const edit = ajusteDiarioEditsByKey[key] || {};
      generado += Number(fila.generado_total || 0);
      pendiente += Number(fila.pendiente_pago_empleado || 0);
      consumo += Number(fila.cobro_consumo_dia || 0);
      abonoPuesto += toMontoNoNegativo(edit.abono_puesto ?? fila.abono_puesto);

      const dif = (
        toMontoNoNegativo(edit.pago_efectivo) !== toMontoNoNegativo(fila.pago_efectivo)
        || toMontoNoNegativo(edit.pago_nequi) !== toMontoNoNegativo(fila.pago_nequi)
        || toMontoNoNegativo(edit.pago_daviplata) !== toMontoNoNegativo(fila.pago_daviplata)
        || toMontoNoNegativo(edit.pago_otros) !== toMontoNoNegativo(fila.pago_otros)
        || toMontoNoNegativo(edit.abono_puesto) !== toMontoNoNegativo(fila.abono_puesto)
        || String(edit.medio_abono_puesto || 'efectivo') !== String(fila.medio_abono_puesto || 'efectivo')
        || Boolean(edit.aplica_comision_ventas ?? true) !== Boolean(fila.aplica_comision_ventas ?? true)
        || toMontoNoNegativo(edit.cobro_consumo_objetivo) !== toMontoNoNegativo(fila.cobro_consumo_dia)
      );
      if (dif) filasModificadas += 1;
    });

    return { generado, pendiente, consumo, abonoPuesto, filasModificadas };
  }, [ajusteDiarioRowsFiltradas, ajusteDiarioEditsByKey]);

  const actualizarCuadreDiaCampo = (estilistaId, fecha, campo, valor) => {
    setCuadreDiarioByEstilista((prev) => {
      const porEstilista = prev[estilistaId] || {};
      const actual = porEstilista[fecha] || {
        pago_efectivo: '',
        pago_nequi: '',
        pago_daviplata: '',
        pago_otros: '',
        abono_puesto: '',
        medio_abono_puesto: 'efectivo',
        aplica_comision_ventas: true,
      };
      const nextValue = (campo === 'medio_abono_puesto')
        ? valor
        : campo === 'aplica_comision_ventas'
          ? Boolean(valor)
        : String(valor || '').replace(/[^\d.]/g, '');

      return {
        ...prev,
        [estilistaId]: {
          ...porEstilista,
          [fecha]: {
            ...actual,
            [campo]: nextValue,
          },
        },
      };
    });
  };

  const modulosVisibles = useMemo(() => {
    const permitidosPorRol = esRecepcion
      ? MODULOS.filter((mod) => mod.key === 'cierre' || mod.key === 'liquidacion' || mod.key === 'ajuste')
      : MODULOS;

    return permitidosPorRol.filter((mod) => hasSubmenuPermission(user, 'reportes', mod.key, 'view'));
  }, [esRecepcion, user]);

  useEffect(() => {
    if (modulosVisibles.some((mod) => mod.key === moduloActivo)) return;
    setModuloActivo(modulosVisibles[0]?.key || 'cierre');
  }, [modulosVisibles, moduloActivo]);

  const paramsBase = useMemo(
    () => ({
      periodo,
      fecha_inicio: fechaInicio,
      fecha_fin: fechaFin,
      ...(medioPago !== 'todos' ? { medio_pago: medioPago } : {}),
    }),
    [periodo, fechaInicio, fechaFin, medioPago]
  );

  const cargarCarteraLiquidacionGlobal = useCallback(async () => {
    if (esRecepcion) {
      setCarteraDataLiquidacionGlobal({ resumen: [], deudas: [], abonos_historial: [] });
      return;
    }

    try {
      const carteraGlobalResp = await reportesService.getConsumoEmpleadoDeudas({
        periodo: 'personalizado',
        fecha_inicio: '2020-01-01',
        fecha_fin: format(new Date(), 'yyyy-MM-dd'),
      });
      setCarteraDataLiquidacionGlobal({
        resumen: carteraGlobalResp?.resumen || [],
        deudas: carteraGlobalResp?.deudas || [],
        abonos_historial: carteraGlobalResp?.abonos_historial || [],
      });
    } catch (err) {
      setCarteraDataLiquidacionGlobal({ resumen: [], deudas: [], abonos_historial: [] });
    }
  }, [esRecepcion]);

  const cargarAjusteDiarioUnificado = useCallback(async () => {
    if (esRecepcion) {
      setAjusteDiarioRows([]);
      setAjusteDiarioEditsByKey({});
      return;
    }

    setLoadingAjusteDiario(true);
    try {
      const resp = await reportesService.getReporteAjusteDiario({
        periodo,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
      });
      const filas = resp?.items || [];
      setAjusteDiarioRows(filas);

      const mapaEdits = {};
      filas.forEach((r) => {
        const key = `${r.estilista_id}|${r.fecha}`;
        mapaEdits[key] = {
          pago_efectivo: String(Number(r.pago_efectivo || 0) || ''),
          pago_nequi: String(Number(r.pago_nequi || 0) || ''),
          pago_daviplata: String(Number(r.pago_daviplata || 0) || ''),
          pago_otros: String(Number(r.pago_otros || 0) || ''),
          abono_puesto: String(Number(r.abono_puesto || 0) || ''),
          medio_abono_puesto: r.medio_abono_puesto || 'efectivo',
          aplica_comision_ventas: Boolean(r.aplica_comision_ventas ?? true),
          cobro_consumo_objetivo: String(Number(r.cobro_consumo_dia || 0) || ''),
          medio_cobro_consumo: 'efectivo',
        };
      });
      setAjusteDiarioEditsByKey(mapaEdits);
    } catch (error) {
      setAjusteDiarioRows([]);
      setAjusteDiarioEditsByKey({});
      toast.error('No se pudo cargar el ajuste diario unificado.');
    } finally {
      setLoadingAjusteDiario(false);
    }
  }, [esRecepcion, periodo, fechaInicio, fechaFin]);

  const cargarTodo = useCallback(async () => {
    const reqSeq = ++cargarTodoSeqRef.current;
    try {
      setLoading(true);
      const [cierreResp, biResp] = await Promise.all([
        reportesService.getCierreCaja(paramsBase),
        reportesService.getBIResumen(paramsBase),
      ]);

      let carteraResp = null;
      if (!esRecepcion) {
        [carteraResp] = await Promise.all([
          reportesService.getConsumoEmpleadoDeudas({
            periodo,
            fecha_inicio: fechaInicio,
            fecha_fin: fechaFin,
          }),
        ]);
      }

      if (reqSeq !== cargarTodoSeqRef.current) return;

      setCierreCaja(cierreResp || null);
      setBiData(biResp || null);
      setCarteraData({
        resumen: carteraResp?.resumen || [],
        deudas: carteraResp?.deudas || [],
        abonos_historial: carteraResp?.abonos_historial || [],
      });
      try {
        setLoadingHistorial(true);
        const hist = await reportesService.getEstadoPagoHistorial({
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
          limit: 200,
        });
        if (reqSeq === cargarTodoSeqRef.current) {
          setHistorialEstados(hist?.items || []);
        }
      } catch (err) {
        if (reqSeq === cargarTodoSeqRef.current) {
          setHistorialEstados([]);
        }
      } finally {
        if (reqSeq === cargarTodoSeqRef.current) {
          setLoadingHistorial(false);
        }
      }

      if (moduloActivo !== 'liquidacion') {
        setPagosPorEstilista({});
        setEstadoDiaPorEstilista({});
        setAbonoPuestoPorEstilista({});
        setModoCobroPuestoPorEstilista({});
        setPorcentajePuestoPorEstilista({});
        setMedioAbonoPuestoPorEstilista({});
        setAplicaComisionVentasPorEstilista({});
        setCobroConsumoPorEstilista({});
        setMedioCobroConsumoPorEstilista({});
      }
    } catch (error) {
      if (reqSeq !== cargarTodoSeqRef.current) return;
      toast.error('No se pudieron cargar los reportes');
      setCierreCaja(null);
      setBiData(null);
      setCarteraData({ resumen: [], deudas: [], abonos_historial: [] });
    } finally {
      if (reqSeq === cargarTodoSeqRef.current) {
        setLoading(false);
      }
    }
  }, [paramsBase, periodo, fechaInicio, fechaFin, esRecepcion, moduloActivo]);

  useEffect(() => {
    cargarTodo();
  }, [cargarTodo]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;
    cargarCarteraLiquidacionGlobal();
  }, [moduloActivo, cargarCarteraLiquidacionGlobal]);

  useEffect(() => {
    const lista = biData?.estilistas || [];
    if (!lista.length) {
      setEstilistaActivoLiquidacion(null);
      return;
    }
    if (estilistaActivoLiquidacion && lista.some((x) => Number(x.estilista_id) === Number(estilistaActivoLiquidacion))) {
      return;
    }
    setEstilistaActivoLiquidacion(Number(lista[0].estilista_id));
  }, [biData, estilistaActivoLiquidacion]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;

    let cancelado = false;
    const cargarEstadoDia = async () => {
      try {
        const fechaDia = fechaFin || format(new Date(), 'yyyy-MM-dd');
        const estadoDia = await reportesService.getEstadoPagoEstilistaDia(fechaDia);
        if (cancelado) return;

        const mapPagos = {};
        const mapEstado = {};
        (estadoDia?.items || []).forEach((x) => {
          mapPagos[x.estilista_id] = {
            efectivo: String(Number(x.pago_efectivo || 0) || ''),
            nequi: String(Number(x.pago_nequi || 0) || ''),
            daviplata: String(Number(x.pago_daviplata || 0) || ''),
            otros: String(Number(x.pago_otros || 0) || ''),
          };
          mapEstado[x.estilista_id] = x.estado || 'pendiente';
        });

        setPagosPorEstilista(mapPagos);
        setEstadoDiaPorEstilista(mapEstado);
        setAbonoPuestoAcumuladoPorEstilista(
          Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, Number(x.abono_puesto || 0)]))
        );
        setAbonoPuestoPorEstilista({});
        setMedioAbonoPuestoPorEstilista(
          Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, x.medio_abono_puesto || 'efectivo']))
        );
        setAplicaComisionVentasPorEstilista(
          Object.fromEntries((estadoDia?.items || []).map((x) => [x.estilista_id, Boolean(x.aplica_comision_ventas ?? true)]))
        );
      } catch (err) {
        if (cancelado) return;
        setPagosPorEstilista({});
        setEstadoDiaPorEstilista({});
        setAbonoPuestoPorEstilista({});
        setAbonoPuestoAcumuladoPorEstilista({});
        setMedioAbonoPuestoPorEstilista({});
        setAplicaComisionVentasPorEstilista({});
      }
    };

    cargarEstadoDia();
    return () => {
      cancelado = true;
    };
  }, [moduloActivo, fechaFin]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;
    if (!estilistaActivoLiquidacion) {
      setDesgloseLiquidacion(null);
      return;
    }
    if (!fechaInicio || !fechaFin) return;

    let cancelado = false;
    const cargarDesglose = async () => {
      try {
        setLoadingDesgloseLiquidacion(true);
        const resp = await reportesService.getBIDesgloseEstilista({
          estilista_id: estilistaActivoLiquidacion,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
        });
        if (cancelado) return;
        setDesgloseLiquidacion(resp || null);
      } catch (err) {
        if (cancelado) return;
        setDesgloseLiquidacion(null);
      } finally {
        if (!cancelado) setLoadingDesgloseLiquidacion(false);
      }
    };

    cargarDesglose();
    return () => {
      cancelado = true;
    };
  }, [moduloActivo, estilistaActivoLiquidacion, fechaInicio, fechaFin]);

  useEffect(() => {
    if (moduloActivo !== 'ajuste') return;
    cargarAjusteDiarioUnificado();
  }, [moduloActivo, cargarAjusteDiarioUnificado]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;
    if (!estilistaActivoLiquidacion || !fechaInicio || !fechaFin) return;

    let cancelado = false;
    const cargarCuadreDiario = async () => {
      try {
        const resp = await reportesService.getEstadoPagoEstilistaDiaRango({
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
          estilista_id: estilistaActivoLiquidacion,
        });
        if (cancelado) return;

        const mapa = {};
        (resp?.items || []).forEach((x) => {
          mapa[String(x.fecha || '')] = {
            pago_efectivo: String(Number(x.pago_efectivo || 0) || ''),
            pago_nequi: String(Number(x.pago_nequi || 0) || ''),
            pago_daviplata: String(Number(x.pago_daviplata || 0) || ''),
            pago_otros: String(Number(x.pago_otros || 0) || ''),
            abono_puesto: String(Number(x.abono_puesto || 0) || ''),
            medio_abono_puesto: x.medio_abono_puesto || 'efectivo',
            aplica_comision_ventas: Boolean(x.aplica_comision_ventas ?? true),
          };
        });

        setCuadreDiarioByEstilista((prev) => ({
          ...prev,
          [estilistaActivoLiquidacion]: mapa,
        }));
      } catch (error) {
        if (cancelado) return;
        setCuadreDiarioByEstilista((prev) => ({
          ...prev,
          [estilistaActivoLiquidacion]: prev[estilistaActivoLiquidacion] || {},
        }));
      }
    };

    cargarCuadreDiario();
    return () => {
      cancelado = true;
    };
  }, [moduloActivo, estilistaActivoLiquidacion, fechaInicio, fechaFin]);

  useEffect(() => {
    if (moduloActivo !== 'liquidacion') return;
    if (!vistaSimpleLiquidacion) return;
    if (Number(pasoLiquidacion) !== 3) return;

    const estId = Number(estilistaActivoLiquidacion || 0);
    if (!estId) return;

    const empleado = (biData?.estilistas || []).find((x) => Number(x.estilista_id) === estId);
    if (!empleado) return;

    const sugeridoPuesto = Math.max(Number(empleado.deuda_total_acumulada || 0), 0);
    const resumenEstilista = (carteraDataLiquidacionGlobal?.resumen || []).find((x) => Number(x.estilista_id) === estId);
    const sugeridoConsumo = Math.max(Number(resumenEstilista?.saldo_pendiente || 0), 0);

    setAbonoPuestoPorEstilista((prev) => {
      const actual = String(prev?.[estId] ?? '').trim();
      if (actual !== '') return prev;
      return {
        ...prev,
        [estId]: String(sugeridoPuesto),
      };
    });

    setCobroConsumoPorEstilista((prev) => {
      const actual = String(prev?.[estId] ?? '').trim();
      if (actual !== '') return prev;
      return {
        ...prev,
        [estId]: String(sugeridoConsumo),
      };
    });
  }, [
    moduloActivo,
    vistaSimpleLiquidacion,
    pasoLiquidacion,
    estilistaActivoLiquidacion,
    biData,
    carteraDataLiquidacionGlobal,
  ]);

  useEffect(() => {
    if (!vistaSimpleLiquidacion) return;
    if (pasoLiquidacion === 3 || pasoLiquidacion === 4) return;
    setPasoLiquidacion(3);
  }, [vistaSimpleLiquidacion, pasoLiquidacion]);

  const aplicarRangoRapido = (tipo) => {
    const base = new Date();
    if (tipo === 'hoy') {
      const value = format(base, 'yyyy-MM-dd');
      setFechaInicio(value);
      setFechaFin(value);
      setPeriodo('personalizado');
      return;
    }
    if (tipo === 'ayer') {
      const ayer = new Date(base);
      ayer.setDate(base.getDate() - 1);
      const value = format(ayer, 'yyyy-MM-dd');
      setFechaInicio(value);
      setFechaFin(value);
      setPeriodo('personalizado');
      return;
    }
    if (tipo === '7dias') {
      const inicio = new Date(base);
      inicio.setDate(base.getDate() - 6);
      setFechaInicio(format(inicio, 'yyyy-MM-dd'));
      setFechaFin(format(base, 'yyyy-MM-dd'));
      setPeriodo('personalizado');
      return;
    }

    const inicioMes = new Date(base.getFullYear(), base.getMonth(), 1);
    setFechaInicio(format(inicioMes, 'yyyy-MM-dd'));
    setFechaFin(format(base, 'yyyy-MM-dd'));
    setPeriodo('mes');
  };

  const resumen = cierreCaja?.resumen || {};
  const medios = cierreCaja?.medios?.detalle || [];
  const productos = cierreCaja?.productos || { detalle: [] };
  const espacios = cierreCaja?.espacios || { detalle: [] };
  const serviciosEst = cierreCaja?.servicios_establecimiento || { detalle: [] };
  const ingresoServiciosTarjeta = Number(
    serviciosEst?.total_ganancia ?? resumen?.ingresos_servicios_establecimiento ?? 0
  );
  const ingresoProductosTarjeta = Number(productos?.ingresos_venta_neto_comision ?? productos?.ingresos_venta ?? 0);
  const ingresoEspaciosTarjeta = Number(resumen?.ingresos_espacios ?? espacios?.total_recibido ?? 0);
  const gananciaTotalTarjeta = ingresoServiciosTarjeta + ingresoProductosTarjeta + ingresoEspaciosTarjeta;
  const liquidacionPagadoCaja = Number(resumen?.liquidacion_empleados ?? 0);
  const pendienteLiquidacionReal = Number(biData?.kpis?.pago_total_estilistas_neto ?? 0);

  const liquidacionTotal = (biData?.estilistas || []).reduce((sum, item) => {
    const generadoConsolidado = Number(item?.generado_total_empleado ?? 0);
    if (Number.isFinite(generadoConsolidado) && generadoConsolidado >= 0) {
      return sum + generadoConsolidado;
    }

    const generadoPeriodo = Number(item?.pago_neto_periodo ?? 0);
    if (Number.isFinite(generadoPeriodo) && generadoPeriodo >= 0) {
      return sum + generadoPeriodo;
    }
    const valorTotalEmpleado = Number((item.valor_total_empleado ?? item.facturacion_servicios ?? item.ganancias_servicios) || 0);
    const comisionesEmpleado = Number(item.comision_ventas_producto || 0);
    return sum + (valorTotalEmpleado + comisionesEmpleado);
  }, 0);
  const liquidacionPendiente = Number.isFinite(pendienteLiquidacionReal)
    ? Math.max(pendienteLiquidacionReal, 0)
    : Math.max(liquidacionTotal - liquidacionPagadoCaja, 0);

  const actualizarPagoMedio = (estilistaId, medio, valor) => {
    const limpio = String(valor || '').replace(/[^\d.]/g, '');
    setPagosPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: {
        efectivo: prev[estilistaId]?.efectivo || '',
        nequi: prev[estilistaId]?.nequi || '',
        daviplata: prev[estilistaId]?.daviplata || '',
        otros: prev[estilistaId]?.otros || '',
        [medio]: limpio,
      },
    }));
  };

  const totalPagoMedios = (estilistaId) => {
    const pagos = pagosPorEstilista[estilistaId] || {};
    return ['efectivo', 'nequi', 'daviplata', 'otros']
      .map((k) => Number(pagos[k] || 0))
      .reduce((acc, val) => acc + (Number.isFinite(val) ? val : 0), 0);
  };

  const getNumericPadValue = () => {
    if (!numericPadTarget?.estilistaId || !numericPadTarget?.field) return '';
    const estId = numericPadTarget.estilistaId;
    const field = numericPadTarget.field;
    if (['efectivo', 'nequi', 'daviplata', 'otros'].includes(field)) {
      return pagosPorEstilista[estId]?.[field] || '';
    }
    if (field === 'abono_puesto') return abonoPuestoPorEstilista[estId] || '';
    if (field === 'cobro_consumo') return cobroConsumoPorEstilista[estId] || '';
    return '';
  };

  const setNumericPadValue = (nextValue) => {
    if (!numericPadTarget?.estilistaId || !numericPadTarget?.field) return;
    const estId = numericPadTarget.estilistaId;
    const field = numericPadTarget.field;
    const limpio = String(nextValue || '').replace(/[^\d.]/g, '');

    if (['efectivo', 'nequi', 'daviplata', 'otros'].includes(field)) {
      setPagosPorEstilista((prev) => ({
        ...prev,
        [estId]: {
          efectivo: prev[estId]?.efectivo || '',
          nequi: prev[estId]?.nequi || '',
          daviplata: prev[estId]?.daviplata || '',
          otros: prev[estId]?.otros || '',
          [field]: limpio,
        },
      }));
      return;
    }

    if (field === 'abono_puesto') {
      setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: limpio }));
      return;
    }

    if (field === 'cobro_consumo') {
      setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: limpio }));
    }
  };

  const toggleDeudaConsumoSeleccion = (estilistaId, deudaId) => {
    const idStr = String(deudaId);
    setDeudaConsumoSeleccionadasPorEstilista((prev) => {
      const actuales = prev[estilistaId] || [];
      const existe = actuales.includes(idStr);
      const siguiente = existe
        ? actuales.filter((x) => x !== idStr)
        : [...actuales, idStr];
      return { ...prev, [estilistaId]: siguiente };
    });
  };

  const seleccionarTodasDeudasConsumo = (estilistaId, deudasEmpleado) => {
    const ids = (deudasEmpleado || []).map((d) => String(d.deuda_id));
    setDeudaConsumoSeleccionadasPorEstilista((prev) => ({ ...prev, [estilistaId]: ids }));
  };

  const limpiarSeleccionDeudasConsumo = (estilistaId) => {
    setDeudaConsumoSeleccionadasPorEstilista((prev) => ({ ...prev, [estilistaId]: [] }));
  };

  const actualizarAjusteDiarioCampo = (key, campo, valor) => {
    setAjusteDiarioEditsByKey((prev) => {
      const actual = prev[key] || {
        pago_efectivo: '',
        pago_nequi: '',
        pago_daviplata: '',
        pago_otros: '',
        abono_puesto: '',
        medio_abono_puesto: 'efectivo',
        aplica_comision_ventas: true,
        cobro_consumo_objetivo: '',
        medio_cobro_consumo: 'efectivo',
      };

      const nextValue = ['medio_abono_puesto', 'medio_cobro_consumo'].includes(campo)
        ? valor
        : campo === 'aplica_comision_ventas'
          ? Boolean(valor)
        : String(valor || '').replace(/[^\d.]/g, '');

      return {
        ...prev,
        [key]: {
          ...actual,
          [campo]: nextValue,
        },
      };
    });
  };

  const guardarAjusteDiarioFila = async (fila) => {
    const key = `${fila.estilista_id}|${fila.fecha}`;
    const edit = ajusteDiarioEditsByKey[key] || {};

    const pago_efectivo = toMontoNoNegativo(edit.pago_efectivo);
    const pago_nequi = toMontoNoNegativo(edit.pago_nequi);
    const pago_daviplata = toMontoNoNegativo(edit.pago_daviplata);
    const pago_otros = toMontoNoNegativo(edit.pago_otros);
    const abono_puesto = toMontoNoNegativo(edit.abono_puesto);
    const medio_abono_puesto = edit.medio_abono_puesto || 'efectivo';
    const aplica_comision_ventas = Boolean(edit.aplica_comision_ventas ?? true);
    const generadoConComision = Number(fila.generado_total_con_comision ?? fila.generado_total ?? 0);
    const generadoSinComision = Number(fila.generado_total_sin_comision ?? fila.generado_total ?? 0);
    const generadoObjetivo = Math.max(aplica_comision_ventas ? generadoConComision : generadoSinComision, 0);
    const consumo_actual = Math.max(Number(fila.cobro_consumo_dia || 0), 0);
    const consumo_obj = toMontoNoNegativo(edit.cobro_consumo_objetivo);
    const medio_cobro_consumo = edit.medio_cobro_consumo || 'efectivo';

    const total_pago = pago_efectivo + pago_nequi + pago_daviplata + pago_otros;
    const tope = generadoObjetivo;
    if (total_pago > tope) {
      toast.warning(`El pago al empleado no puede superar ${formatMoney(tope)} para ${fila.fecha}.`);
      return;
    }

    setSavingAjusteDiarioByKey((prev) => ({ ...prev, [key]: true }));
    try {
      if (consumo_obj < consumo_actual) {
        toast.info('Para disminuir cobros de consumo ya registrados, usa la edición de abonos en Cartera.');
      }

      const extra_consumo = Math.max(consumo_obj - consumo_actual, 0);
      await reportesService.liquidarOperacionIntegral({
        estilista_id: fila.estilista_id,
        fecha: fila.fecha,
        pago_efectivo,
        pago_nequi,
        pago_daviplata,
        pago_otros,
        abono_puesto,
        medio_abono_puesto,
        aplica_comision_ventas,
        forzar_reemplazo_dia: true,
        consumo_monto: extra_consumo,
        deuda_ids: [],
        medio_cobro_consumo,
        notas: `Ajuste unificado ${fila.fecha}`,
      });

      toast.success(`Ajuste guardado para ${fila.estilista_nombre} - ${fila.fecha}.`);
      await Promise.all([cargarTodo(), cargarCarteraLiquidacionGlobal(), cargarAjusteDiarioUnificado()]);
    } catch (error) {
      const msg = error?.response?.data?.error || error?.message || 'No se pudo guardar el ajuste diario.';
      toast.error(String(msg));
    } finally {
      setSavingAjusteDiarioByKey((prev) => ({ ...prev, [key]: false }));
    }
  };

  const resumenPorEstilista = useMemo(() => {
    const mapa = {};
    (carteraData?.resumen || []).forEach((item) => {
      mapa[item.estilista_id] = item;
    });
    return mapa;
  }, [carteraData]);

  const resumenPorEstilistaLiquidacion = useMemo(() => {
    const mapa = {};
    (carteraDataLiquidacionGlobal?.resumen || []).forEach((item) => {
      mapa[item.estilista_id] = item;
    });
    return mapa;
  }, [carteraDataLiquidacionGlobal]);

  const opcionesEstilistaCartera = useMemo(
    () => [...(carteraData?.resumen || [])]
      .sort((a, b) => String(a.estilista_nombre || '').localeCompare(String(b.estilista_nombre || ''), 'es')),
    [carteraData]
  );

  const deudasCarteraFiltradas = useMemo(() => {
    return (carteraData?.deudas || []).filter((deuda) => {
      const coincideEstilista = filtroCarteraEstilistaId === 'todos'
        ? true
        : Number(deuda.estilista_id) === Number(filtroCarteraEstilistaId);
      const saldo = Number(deuda.saldo_pendiente || 0);
      const mostrarPorSaldo = mostrarFacturasSaldadas ? true : saldo > 0.5;
      return coincideEstilista && mostrarPorSaldo;
    });
  }, [carteraData, filtroCarteraEstilistaId, mostrarFacturasSaldadas]);

  const resumenCarteraVisible = useMemo(() => {
    let totalCargado = 0;
    let totalAbonado = 0;
    let totalPendiente = 0;
    let facturasPendientes = 0;

    deudasCarteraFiltradas.forEach((deuda) => {
      const total = Number(deuda.total_cargo || 0);
      const abonado = Number(deuda.total_abonado || 0);
      const saldo = Number(deuda.saldo_pendiente || 0);
      totalCargado += total;
      totalAbonado += abonado;
      totalPendiente += saldo;
      if (saldo > 0.5) facturasPendientes += 1;
    });

    return {
      facturas: deudasCarteraFiltradas.length,
      totalCargado,
      totalAbonado,
      totalPendiente,
      facturasPendientes,
    };
  }, [deudasCarteraFiltradas]);

  const deudaSeleccionada = useMemo(
    () => deudasCarteraFiltradas.find((d) => Number(d.deuda_id) === Number(deudaActivaHistorial)) || null,
    [deudasCarteraFiltradas, deudaActivaHistorial]
  );

  useEffect(() => {
    if (!deudaActivaHistorial) return;
    if (deudasCarteraFiltradas.some((d) => Number(d.deuda_id) === Number(deudaActivaHistorial))) return;
    setDeudaActivaHistorial(null);
  }, [deudasCarteraFiltradas, deudaActivaHistorial]);

  const abonarFacturaCartera = async (deuda) => {
    const deudaId = Number(deuda?.deuda_id || 0);
    const monto = Number(abonoPorDeuda[deudaId] || 0);
    const medio = medioAbonoPorDeuda[deudaId] || 'efectivo';

    if (!deudaId) {
      toast.error('Factura inválida.');
      return;
    }
    if (!Number.isFinite(monto) || monto <= 0) {
      toast.error('Ingresa un valor de abono mayor a 0.');
      return;
    }

    setSavingAbonoByDeuda((prev) => ({ ...prev, [deudaId]: true }));
    try {
      await reportesService.abonarConsumoEmpleado({
        estilista_id: deuda.estilista_id,
        deuda_id: deudaId,
        monto,
        medio_pago: medio,
        notas: `Abono cartera factura ${deuda.numero_factura || deudaId}`,
      });
      toast.success('Abono registrado correctamente.');
      setAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: '' }));
      await cargarTodo();
      setDeudaActivaHistorial(deudaId);
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo registrar el abono.';
      toast.error(msg);
    } finally {
      setSavingAbonoByDeuda((prev) => ({ ...prev, [deudaId]: false }));
    }
  };

  const editarAbonoCartera = async (abono, deuda) => {
    const abonoId = Number(abono?.abono_id || 0);
    const monto = Number(editMontoByAbono[abonoId] || 0);
    const medio = editMedioByAbono[abonoId] || abono.medio_pago || 'efectivo';
    const fecha = editFechaByAbono[abonoId] || String(abono.fecha_hora || '').slice(0, 10);
    const notas = editNotasByAbono[abonoId] ?? (abono.notas || '');
    if (!abonoId) {
      toast.error('Abono inválido.');
      return;
    }
    if (!Number.isFinite(monto) || monto <= 0) {
      toast.error('El nuevo valor del abono debe ser mayor a 0.');
      return;
    }

    setSavingEditByAbono((prev) => ({ ...prev, [abonoId]: true }));
    try {
      await reportesService.editarAbonoConsumoEmpleado({
        abono_id: abonoId,
        monto,
        medio_pago: medio,
        notas,
        fecha,
      });
      toast.success('Abono actualizado.');
      await cargarTodo();
      setDeudaActivaHistorial(deuda?.deuda_id || null);
    } catch (error) {
      const msg = error?.response?.data?.error || 'No se pudo editar el abono.';
      toast.error(msg);
    } finally {
      setSavingEditByAbono((prev) => ({ ...prev, [abonoId]: false }));
    }
  };

const aplicarEstadoLiquidacion = async (fila) => {
  const estilistaId = fila.estilista_id;
  const fechaLiquidacion = fechaFin || format(new Date(), 'yyyy-MM-dd');
  const esCorreccion = Boolean(modoCorreccionPorEstilista[estilistaId]);
  
  const pago_efectivo = Number(pagosPorEstilista[estilistaId]?.efectivo || 0);
  const pago_nequi = Number(pagosPorEstilista[estilistaId]?.nequi || 0);
  const pago_daviplata = Number(pagosPorEstilista[estilistaId]?.daviplata || 0);
  const pago_otros = Number(pagosPorEstilista[estilistaId]?.otros || 0);
  const abono_puesto_digitado = Number(abonoPuestoPorEstilista[estilistaId] || 0);
  const puesto_modo = modoCobroPuestoPorEstilista[estilistaId] || 'fijo';
  const puesto_porcentaje = Math.max(Number(porcentajePuestoPorEstilista[estilistaId] || 0), 0);
  const diaBase = (desgloseLiquidacion?.desglose_por_dia || []).find((d) => String(d.fecha || '') === String(fechaLiquidacion));
  const basePorcentajeDia = Math.max(Number(diaBase?.neto_dia || 0), 0);
  const abono_puesto = puesto_modo === 'porcentaje'
    ? Math.max(Math.round((basePorcentajeDia * puesto_porcentaje) / 100), 0)
    : abono_puesto_digitado;
  const medio_abono_puesto = medioAbonoPuestoPorEstilista[estilistaId] || 'efectivo';
  const aplica_comision_ventas = Boolean(aplicaComisionVentasPorEstilista[estilistaId] ?? true);
  const saldoConsumoEmpleado = Number(resumenPorEstilistaLiquidacion[estilistaId]?.saldo_pendiente || 0);
  const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[estilistaId] || 0);
  const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(saldoConsumoEmpleado, 0));
  const deudasConsumoSeleccionadas = (deudaConsumoSeleccionadasPorEstilista[estilistaId] || [])
    .map((x) => Number(x))
    .filter((x) => Number.isFinite(x) && x > 0);
  const medioCobroConsumo = medioCobroConsumoPorEstilista[estilistaId] || 'efectivo';
  const topePagoEmpleado = (() => {
    const dia = (desgloseLiquidacion?.desglose_por_dia || []).find((d) => String(d.fecha || '') === String(fechaLiquidacion));
    if (dia) return Math.max(Number(dia.neto_dia || 0), 0);
    return calcularPendientePagoEmpleado(fila);
  })();

  if (pago_efectivo + pago_nequi + pago_daviplata + pago_otros > topePagoEmpleado) {
    toast.warning(`El pago al empleado no puede superar ${formatMoney(topePagoEmpleado)} para el día ${fechaLiquidacion}.`);
    return;
  }
  
  setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: true }));
  
  try {
    const resultado = await reportesService.liquidarOperacionIntegral({
      estilista_id: estilistaId,
      fecha: fechaLiquidacion,
      pago_efectivo,
      pago_nequi,
      pago_daviplata,
      pago_otros,
      abono_puesto,
      medio_abono_puesto,
      aplica_comision_ventas,
      puesto_modo,
      puesto_porcentaje,
      forzar_reemplazo_dia: esCorreccion,
      consumo_monto: cobroConsumoAplicado,
      deuda_ids: deudasConsumoSeleccionadas,
      medio_cobro_consumo: medioCobroConsumo,
      notas: `Liquidación ${fechaLiquidacion}`,
    });
    const g = resultado.liquidacion.ganancias_totales;
    const d = resultado.liquidacion.descuento_puesto;
    const d_ant = resultado.puesto.deuda_anterior;
    const d_tot = resultado.puesto.deuda_total;
    const p = resultado.pagos.total;
    const s = resultado.puesto.saldo_pendiente;
    
    const msgDeuda = d_ant > 0 ? ` (${formatMoney(d_ant)} anterior + ${formatMoney(d)} hoy)` : '';
    const msgConsumo = Number(resultado?.consumo_integrado?.monto_aplicado || 0) > 0
      ? ` - Consumo cobrado ${formatMoney(resultado?.consumo_integrado?.monto_aplicado || 0)}`
      : '';
    toast.success(`✓ ${resultado.estilista.nombre}: Gan ${formatMoney(g)} - Puesto ${formatMoney(d_tot)}${msgDeuda}${msgConsumo} - Pagado ${formatMoney(p)} - Saldo ${formatMoney(s)}`);
    
    // Actualizar estado localmente de inmediato para UI responsiva
    setEstadoDiaPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: resultado.estado,
    }));

    if (esCorreccion) {
      setModoCorreccionPorEstilista((prev) => ({ ...prev, [estilistaId]: false }));
    }
    
    await Promise.all([cargarTodo(), cargarCarteraLiquidacionGlobal()]);
  } catch (error) {
    const msg = error?.response?.data?.error || error?.message || 'No se pudo procesar la liquidación.';
    toast.error(`❌ ${msg}`);
  } finally {
    setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: false }));
  }
};

const aplicarLiquidacionSimple = async ({
  fila,
  pendientePagoEmpleado,
  abonoPuestoAplicado,
  cobroConsumoAplicado,
  deudasConsumoSeleccionadas,
  pagosPorMedio = null,
}) => {
  const estilistaId = Number(fila?.estilista_id || 0);
  if (!estilistaId) {
    toast.error('No se pudo identificar el empleado para liquidar.');
    return;
  }

  // DEBUG: Log para ver el estado
  console.log('DEBUG aplicarLiquidacionSimple:', {
    estilistaId,
    skipDescuentoPuestoPorEstilista,
    skipValue: skipDescuentoPuestoPorEstilista[estilistaId],
    allKeys: Object.keys(skipDescuentoPuestoPorEstilista),
  });

  const fechaLiquidacion = fechaFin || format(new Date(), 'yyyy-MM-dd');
  if (String(fechaInicio || '') !== String(fechaLiquidacion || '')) {
    toast.warning('La liquidación simple opera por día. Usa el mismo valor en fecha inicio y fecha fin.');
    return;
  }
  const totalDescuentos = Math.max(Number(abonoPuestoAplicado || 0), 0);
  const pagoFinalEmpleado = Math.max(Number(pendientePagoEmpleado || 0) - totalDescuentos, 0);
  const pago_efectivo = Math.max(Number(pagosPorMedio?.efectivo || 0), 0);
  const pago_nequi = Math.max(Number(pagosPorMedio?.nequi || 0), 0);
  const pago_daviplata = Math.max(Number(pagosPorMedio?.daviplata || 0), 0);
  const pago_otros = Math.max(Number(pagosPorMedio?.otros || 0), 0);
  const totalPagosDigitados = pago_efectivo + pago_nequi + pago_daviplata + pago_otros;
  const usarAutoEfectivo = totalPagosDigitados <= 0;
  if (!usarAutoEfectivo && totalPagosDigitados > pagoFinalEmpleado) {
    toast.warning(`Los pagos digitados (${formatMoney(totalPagosDigitados)}) superan el total final a pagar (${formatMoney(pagoFinalEmpleado)}).`);
    return;
  }
  const puesto_modo = modoCobroPuestoPorEstilista[estilistaId] || 'fijo';
  const puesto_porcentaje = Number(porcentajePuestoPorEstilista[estilistaId] || 0);
  const medio_abono_puesto = medioAbonoPuestoPorEstilista[estilistaId] || 'efectivo';
  const aplica_comision_ventas = Boolean(aplicaComisionVentasPorEstilista[estilistaId] ?? true);
  const medioCobroConsumo = medioCobroConsumoPorEstilista[estilistaId] || 'efectivo';
  const skip_puesto = Boolean(skipDescuentoPuestoPorEstilista[estilistaId] || false);

  setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: true }));
  try {
    const payload = {
      estilista_id: estilistaId,
      fecha: fechaLiquidacion,
      pago_efectivo: usarAutoEfectivo ? pagoFinalEmpleado : pago_efectivo,
      pago_nequi: usarAutoEfectivo ? 0 : pago_nequi,
      pago_daviplata: usarAutoEfectivo ? 0 : pago_daviplata,
      pago_otros: usarAutoEfectivo ? 0 : pago_otros,
      abono_puesto: skip_puesto ? 0 : Number(abonoPuestoAplicado || 0),
      medio_abono_puesto,
      aplica_comision_ventas,
      puesto_modo,
      puesto_porcentaje,
      forzar_reemplazo_dia: false,
      skip_descuento_puesto: skip_puesto,
      consumo_monto: cobroConsumoAplicado,
      deuda_ids: deudasConsumoSeleccionadas,
      medio_cobro_consumo: medioCobroConsumo,
      notas: `Liquidación simple ${fechaLiquidacion}`,
    };

    console.log('=== LIQUIDACIÓN DEBUG ===');
    console.log('Payload a enviar:', payload);
    console.log('skip_puesto:', skip_puesto, '(tipo:', typeof skip_puesto + ')');
    console.log('abonoPuestoAplicado:', abonoPuestoAplicado);
    console.log('pagoFinalEmpleado:', pagoFinalEmpleado);
    console.log('totalPagosDigitados:', totalPagosDigitados);

    await reportesService.liquidarOperacionIntegral(payload);

    toast.success(`Liquidación guardada. Pago final empleado: ${formatMoney(pagoFinalEmpleado)}.`);
    setPasoLiquidacion(3);
    await Promise.all([cargarTodo(), cargarCarteraLiquidacionGlobal()]);
  } catch (error) {
    const msg = error?.response?.data?.error || error?.message || 'No se pudo guardar la liquidación simple.';
    toast.error(String(msg));
  } finally {
    setSavingEstadoByEstilista((prev) => ({ ...prev, [estilistaId]: false }));
  }
};

const guardarCuadreDiario = async ({ estilistaId, fecha, netoDia }) => {
  const key = `${estilistaId}|${fecha}`;
  const porEstilista = cuadreDiarioByEstilista[estilistaId] || {};
  const fila = porEstilista[fecha] || {};

  const pago_efectivo = toMontoNoNegativo(fila.pago_efectivo);
  const pago_nequi = toMontoNoNegativo(fila.pago_nequi);
  const pago_daviplata = toMontoNoNegativo(fila.pago_daviplata);
  const pago_otros = toMontoNoNegativo(fila.pago_otros);
  const abono_puesto = toMontoNoNegativo(fila.abono_puesto);
  const medio_abono_puesto = fila.medio_abono_puesto || 'efectivo';
  const aplica_comision_ventas = Boolean(fila.aplica_comision_ventas ?? true);

  const totalPagoEmpleado = pago_efectivo + pago_nequi + pago_daviplata + pago_otros;
  const topePagoDia = Math.max(Number(netoDia || 0), 0);
  if (totalPagoEmpleado > topePagoDia) {
    toast.warning(`El pago al empleado no puede superar ${formatMoney(topePagoDia)} para el día ${fecha}.`);
    return;
  }

  setSavingCuadreDiaByKey((prev) => ({ ...prev, [key]: true }));
  try {
    await reportesService.liquidarDiaV2({
      estilista_id: estilistaId,
      fecha,
      pago_efectivo,
      pago_nequi,
      pago_daviplata,
      pago_otros,
      abono_puesto,
      medio_abono_puesto,
      aplica_comision_ventas,
      forzar_reemplazo_dia: true,
      notas: `Cuadre diario ${fecha}`,
    });

    toast.success(`Cuadre diario guardado para ${fecha}.`);
    await Promise.all([cargarTodo(), cargarCarteraLiquidacionGlobal()]);
  } catch (error) {
    const msg = error?.response?.data?.error || error?.message || 'No se pudo guardar el cuadre del día.';
    toast.error(String(msg));
  } finally {
    setSavingCuadreDiaByKey((prev) => ({ ...prev, [key]: false }));
  }
};

  const precargarCorreccionLiquidacion = (empleado, registroDia) => {
    const estilistaId = Number(empleado?.estilista_id || 0);
    if (!estilistaId || !registroDia) return;

    setEstilistaActivoLiquidacion(estilistaId);
    if (registroDia.fecha) {
      setFechaFin(String(registroDia.fecha));
    }

    const pagoEmpleadoDia = Math.max(Number(registroDia.pago_empleado_dia || 0), 0);
    const abonoPuestoDia = Math.max(Number(registroDia.abono_puesto_dia || 0), 0);
    const medioAbono = registroDia.medio_abono_puesto || 'efectivo';
    const aplicaComisionVentas = Boolean(registroDia.aplica_comision_ventas ?? true);

    setPagosPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: {
        efectivo: String(pagoEmpleadoDia || ''),
        nequi: '',
        daviplata: '',
        otros: '',
      },
    }));

    setAbonoPuestoPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: String(abonoPuestoDia || ''),
    }));

    setMedioAbonoPuestoPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: medioAbono,
    }));

    setAplicaComisionVentasPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: aplicaComisionVentas,
    }));

    setModoCorreccionPorEstilista((prev) => ({
      ...prev,
      [estilistaId]: true,
    }));

    toast.info(`Valores precargados para corregir ${registroDia.fecha || 'el día seleccionado'}. Ajusta y vuelve a liquidar.`);
  };

  const cargarDeudaPuestoManual = async () => {
    const { estilista_id, fecha, monto, notas } = deudaPuestoModal;

    if (!estilista_id || !fecha || !monto || Number(monto) <= 0) {
      toast.error('Completa todos los campos requeridos y el monto debe ser mayor a 0.');
      return;
    }

    setDeudaPuestoModal((prev) => ({ ...prev, loading: true }));
    try {
      const resultado = await reportesService.cargarDeudaPuestoDia({
        estilista_id: Number(estilista_id),
        fecha,
        monto_deuda: Number(monto),
        notas: String(notas || ''),
      });

      toast.success(`✓ Deuda cargada: ${resultado.estilista_nombre} - ${formatMoney(Number(resultado.monto_cargado))}`);
      setDeudaPuestoModal({ open: false, estilista_id: null, fecha: '', monto: '', notas: '', loading: false });
      await Promise.all([cargarTodo(), cargarCarteraLiquidacionGlobal()]);
    } catch (error) {
      const msg = error?.response?.data?.error || error?.message || 'No se pudo cargar la deuda.';
      toast.error(String(msg));
    } finally {
      setDeudaPuestoModal((prev) => ({ ...prev, loading: false }));
    }
  };

  const eliminarRegistroHistorial = async (registro) => {
    if (!puedeCorregirLiquidacion) {
      toast.error('Solo administrador o gerente pueden corregir registros del historial');
      return;
    }

    const ok = window.confirm(
      `Se eliminará el historial de ${registro.estilista_nombre || 'empleado'} del día ${registro.fecha || '-'} y su registro diario asociado. ¿Deseas continuar?`
    );
    if (!ok) return;

    try {
      await reportesService.deleteEstadoPagoHistorial(registro.id);
      toast.success('Registro eliminado correctamente');
      await cargarTodo();
    } catch (err) {
      const msg = err?.response?.data?.error || 'No se pudo eliminar el registro del historial';
      toast.error(msg);
    }
  };

  const exportarCierreCsv = () => {
    try {
      const csvEscape = (value) => {
        const raw = String(value ?? '');
        if (raw.includes(',') || raw.includes('"') || raw.includes('\n')) {
          return `"${raw.replace(/"/g, '""')}"`;
        }
        return raw;
      };

      const ingresosTotales = Number(resumen?.total_ingresos || (ingresoServiciosTarjeta + ingresoProductosTarjeta + ingresoEspaciosTarjeta));
      const pagosEmpleados = Number(liquidacionPagadoCaja || 0);
      const gananciaNeta = ingresosTotales - pagosEmpleados;

      const rows = [
        ['Cierre de Caja'],
        ['Rango', `${fechaInicio} a ${fechaFin}`],
        [],
        ['Resumen General'],
        ['Ingresos Totales', ingresosTotales],
        ['Pagos a Empleados', pagosEmpleados],
        ['Ganancia Neta', gananciaNeta],
        [],
      ];

      if (cierreTabActiva === 'medios') {
        rows.push(['Detalle: Medios de Pago']);
        rows.push(['Medio', 'Ingresos', 'Liquidacion', 'Saldo']);
        medios.forEach((m) => rows.push([m.medio_pago || '-', Number(m.ingresos || 0), Number(m.salidas || 0), Number(m.saldo || 0)]));
      }

      if (cierreTabActiva === 'productos') {
        rows.push(['Detalle: Productos']);
        rows.push(['Fecha', 'Origen', 'Descripcion', 'Cantidad', 'Venta', 'Compra', 'Comision', 'Ganancia Neta']);
        (productos?.detalle || []).forEach((item) => {
          rows.push([
            item.fecha_hora || item.fecha || '-',
            item.origen || '-',
            item.descripcion || '-',
            Number(item.cantidad || 0),
            Number(item.valor_venta || 0),
            Number(item.valor_compra || 0),
            Number(item.comision_empleado || 0),
            Number(item.ganancia_neta || 0),
          ]);
        });
      }

      if (cierreTabActiva === 'servicios') {
        rows.push(['Detalle: Servicios']);
        rows.push(['Fecha', 'Tipo servicio', 'Valor servicio', 'Ganancia establecimiento']);
        (serviciosEst?.detalle || []).forEach((item) => {
          rows.push([
            item.fecha_hora || item.fecha || '-',
            item.tipo_servicio || '-',
            Number(item.valor_servicio || 0),
            Number(item.ganancia_establecimiento || 0),
          ]);
        });
      }

      if (cierreTabActiva === 'espacios') {
        rows.push(['Detalle: Espacios']);
        rows.push(['Fecha', 'Empleado', 'Valor pagado']);
        (espacios?.detalle || []).forEach((item) => {
          rows.push([
            item.fecha || '-',
            item.estilista_nombre || '-',
            Number(item.valor_pagado || 0),
          ]);
        });
      }

      const csv = `\uFEFF${rows.map((r) => r.map(csvEscape).join(',')).join('\n')}`;
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `cierre_caja_${fechaInicio}_${fechaFin}_${cierreTabActiva}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
      toast.success('CSV de cierre exportado correctamente.');
    } catch (error) {
      toast.error('No se pudo exportar el CSV del cierre.');
    }
  };

  const renderModuloCierreCaja = () => {
    const ingresosTotales = Number(resumen?.total_ingresos || (ingresoServiciosTarjeta + ingresoProductosTarjeta + ingresoEspaciosTarjeta));
    const pagosEmpleados = Number(liquidacionPagadoCaja || 0);
    const gananciaNeta = Number(resumen?.ganancia_total ?? (ingresosTotales - pagosEmpleados));
    const totalIngresosCategorias = ingresoServiciosTarjeta + ingresoProductosTarjeta + ingresoEspaciosTarjeta;
    const desgloseCategorias = [
      { key: 'servicios', label: 'Servicios', valor: ingresoServiciosTarjeta },
      { key: 'productos', label: 'Productos', valor: ingresoProductosTarjeta },
      { key: 'espacios', label: 'Espacios', valor: ingresoEspaciosTarjeta },
    ];

    const tabsDetalles = [
      { key: 'medios', label: 'Medios de pago' },
      { key: 'productos', label: 'Productos vendidos' },
      { key: 'servicios', label: 'Servicios' },
      { key: 'espacios', label: 'Espacios' },
    ];

    const mediosTotales = cierreCaja?.medios?.totales || {};
    const totalIngresosMedios = Number(mediosTotales.ingresos || 0);
    const totalSalidasMedios = Number(mediosTotales.salidas || 0);
    const saldoNetoMedios = Number(mediosTotales.saldo || (totalIngresosMedios - totalSalidasMedios));

    const totalServiciosDetalle = Number((serviciosEst?.detalle || []).reduce(
      (acc, item) => acc + Number(item?.valor_servicio || 0),
      0
    ));
    const totalGananciaServicios = Number(serviciosEst?.total_ganancia || 0);

    const totalPagosEspacios = Number(espacios?.total_recibido || 0);
    const totalRegistrosEspacios = Number((espacios?.detalle || []).length || 0);

    return (
      <div className="space-y-6">
        <section className="card border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-2xl font-black text-slate-900">Cierre de Caja</h2>
              <p className="text-sm text-slate-600 mt-1">Resumen financiero del negocio para el rango seleccionado.</p>
            </div>
            <button type="button" className="btn-secondary" onClick={exportarCierreCsv}>Exportar CSV</button>
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="rounded-2xl border border-sky-200 bg-sky-50 p-5">
            <p className="text-xs uppercase tracking-wide text-sky-700 font-semibold">Total ingresos</p>
            <p className="text-3xl font-black text-sky-900 mt-2">{formatMoney(ingresosTotales)}</p>
          </div>
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
            <p className="text-xs uppercase tracking-wide text-rose-700 font-semibold">Pagado a empleados</p>
            <p className="text-3xl font-black text-rose-900 mt-2">{formatMoney(pagosEmpleados)}</p>
            <p className="text-xs text-rose-700 mt-1">Pendiente de liquidacion: {formatMoney(liquidacionPendiente)}</p>
          </div>
          <div className="rounded-2xl border border-emerald-300 bg-emerald-50 p-5 shadow-sm">
            <p className="text-xs uppercase tracking-wide text-emerald-700 font-semibold">Ganancia neta</p>
            <p className="text-4xl font-black text-emerald-900 mt-2">{formatMoney(gananciaNeta)}</p>
            <p className="text-xs text-emerald-700 mt-1">Ingresos - pagos a empleados</p>
          </div>
        </section>

        <section className="card border border-slate-200 bg-white">
          <h3 className="card-header mb-3">Desglose de ingresos</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {desgloseCategorias.map((item) => {
              const porcentaje = totalIngresosCategorias > 0 ? (Number(item.valor || 0) / totalIngresosCategorias) * 100 : 0;
              return (
                <div key={`desglose-${item.key}`} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">{item.label}</p>
                  <p className="text-2xl font-black text-slate-900 mt-1">{formatMoney(item.valor)}</p>
                  <p className="text-xs text-slate-600 mt-1">{porcentaje.toFixed(1)}% del total de categorias</p>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card border border-slate-200 bg-white">
          <h3 className="card-header mb-3">Visualizacion rapida</h3>
          <div className="space-y-3">
            {desgloseCategorias.map((item) => {
              const porcentaje = totalIngresosCategorias > 0 ? (Number(item.valor || 0) / totalIngresosCategorias) * 100 : 0;
              return (
                <div key={`bar-${item.key}`}>
                  <div className="flex items-center justify-between text-sm text-slate-700 mb-1">
                    <span>{item.label}</span>
                    <span>{formatMoney(item.valor)}</span>
                  </div>
                  <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
                    <div className={`h-full rounded-full ${item.key === 'servicios' ? 'bg-sky-500' : item.key === 'productos' ? 'bg-slate-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(Math.max(porcentaje, 0), 100)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="card border border-slate-200 bg-white">
          <div className="flex flex-wrap gap-2">
            {tabsDetalles.map((tab) => (
              <button
                key={`tab-cierre-${tab.key}`}
                type="button"
                className={`px-3 py-2 rounded-xl border text-sm font-semibold ${cierreTabActiva === tab.key ? 'border-sky-300 bg-sky-50 text-sky-900' : 'border-slate-200 bg-slate-50 text-slate-700'}`}
                onClick={() => setCierreTabActiva(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {cierreTabActiva === 'medios' && (
            <>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Ingresos por medios</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(totalIngresosMedios)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Pagos empleados</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(totalSalidasMedios)}</p>
                </div>
                <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3">
                  <p className="text-xs text-emerald-700">Saldo neto medios</p>
                  <p className={`text-xl font-black ${saldoNetoMedios >= 0 ? 'text-emerald-900' : 'text-rose-800'}`}>{formatMoney(saldoNetoMedios)}</p>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="table-header">
                    <tr>
                      <th className="px-4 py-3 text-left">Medio</th>
                      <th className="px-4 py-3 text-left">Ingresos</th>
                      <th className="px-4 py-3 text-left">Pagos empleados</th>
                      <th className="px-4 py-3 text-left">Saldo</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {medios.length === 0 && (
                      <tr>
                        <td className="table-cell text-slate-500" colSpan={4}>No hay movimientos para el rango seleccionado.</td>
                      </tr>
                    )}
                    {medios.map((m) => (
                      <tr key={`medio-${m.medio_pago}`}>
                        <td className="table-cell capitalize font-medium">{m.medio_pago || '-'}</td>
                        <td className="table-cell">{formatMoney(m.ingresos)}</td>
                        <td className="table-cell">{formatMoney(m.salidas)}</td>
                        <td className={`table-cell font-semibold ${Number(m.saldo || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                          {formatMoney(m.saldo)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {cierreTabActiva === 'productos' && (
            <>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Ingreso productos</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(productos.ingresos_venta)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Valor compra</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(productos.valor_compra)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Abonos consumo dia</p>
                  <p className="text-xl font-black text-sky-800">{formatMoney(productos.total_abonos_consumo_dia || 0)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-emerald-50 p-3">
                  <p className="text-xs text-emerald-700">Ganancia neta productos</p>
                  <p className="text-xl font-black text-emerald-900">{formatMoney(productos.ganancia_neta)}</p>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="table-header">
                    <tr>
                      <th className="px-4 py-3 text-left">Fecha</th>
                      <th className="px-4 py-3 text-left">Origen</th>
                      <th className="px-4 py-3 text-left">Descripcion</th>
                      <th className="px-4 py-3 text-left">Cantidad</th>
                      <th className="px-4 py-3 text-left">Valor venta</th>
                      <th className="px-4 py-3 text-left">Valor compra</th>
                      <th className="px-4 py-3 text-left">Comision</th>
                      <th className="px-4 py-3 text-left">Ganancia neta</th>
                      {puedeAjustarFechaAbonoConsumo && <th className="px-4 py-3 text-left">Ajustar fecha abono</th>}
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {(productos.detalle || []).length === 0 && (
                      <tr>
                        <td className="table-cell text-slate-500" colSpan={puedeAjustarFechaAbonoConsumo ? 9 : 8}>No hay detalle de productos en el rango seleccionado.</td>
                      </tr>
                    )}
                    {(productos.detalle || []).map((item, idx) => (
                      <tr key={`prod-tab-${item.fecha_hora || item.fecha || 'x'}-${idx}`}>
                        <td className="table-cell">{item.fecha_hora || item.fecha || '-'}</td>
                        <td className="table-cell">{item.origen || '-'}</td>
                        <td className="table-cell">{item.descripcion || '-'}</td>
                        <td className="table-cell">{item.cantidad || 0}</td>
                        <td className="table-cell">{formatMoney(item.valor_venta)}</td>
                        <td className="table-cell">{formatMoney(item.valor_compra)}</td>
                        <td className="table-cell">{formatMoney(item.comision_empleado || 0)}</td>
                        <td className={`table-cell font-semibold ${Number(item.ganancia_neta || 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{formatMoney(item.ganancia_neta)}</td>
                        {puedeAjustarFechaAbonoConsumo && (
                          <td className="table-cell">
                            {item.origen === 'consumo_empleado_abono' && item.abono_id ? (
                              <div className="flex items-center gap-2">
                                <input
                                  type="date"
                                  className="input-field !py-2 !w-40"
                                  value={editFechaAbonoConsumoById[item.abono_id] || String(item.fecha || '').slice(0, 10)}
                                  onChange={(e) => setEditFechaAbonoConsumoById((prev) => ({ ...prev, [item.abono_id]: e.target.value }))}
                                />
                                <button
                                  type="button"
                                  className="btn-secondary !py-2 !px-3"
                                  onClick={() => ajustarFechaAbonoConsumo(item)}
                                  disabled={!!savingFechaAbonoConsumoById[item.abono_id]}
                                >
                                  {savingFechaAbonoConsumoById[item.abono_id] ? 'Guardando...' : 'Guardar'}
                                </button>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-500">No editable</span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {cierreTabActiva === 'servicios' && (
            <>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Valor servicios</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(totalServiciosDetalle)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Registros</p>
                  <p className="text-xl font-black text-slate-900">{(serviciosEst.detalle || []).length}</p>
                </div>
                <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3">
                  <p className="text-xs text-emerald-700">Ganancia establecimiento</p>
                  <p className="text-xl font-black text-emerald-900">{formatMoney(totalGananciaServicios)}</p>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="table-header">
                    <tr>
                      <th className="px-4 py-3 text-left">Fecha</th>
                      <th className="px-4 py-3 text-left">Tipo servicio</th>
                      <th className="px-4 py-3 text-left">Valor servicio</th>
                      <th className="px-4 py-3 text-left">Ganancia establecimiento</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {(serviciosEst.detalle || []).length === 0 && (
                      <tr>
                        <td className="table-cell text-slate-500" colSpan={4}>No hay servicios con ganancia para establecimiento en el rango.</td>
                      </tr>
                    )}
                    {(serviciosEst.detalle || []).map((item, idx) => (
                      <tr key={`srv-tab-${item.fecha_hora || item.fecha || 'x'}-${item.numero_factura || idx}-${idx}`}>
                        <td className="table-cell">{item.fecha_hora || item.fecha || '-'}</td>
                        <td className="table-cell">{item.tipo_servicio || '-'}</td>
                        <td className="table-cell">{formatMoney(item.valor_servicio)}</td>
                        <td className="table-cell font-semibold text-emerald-700">{formatMoney(item.ganancia_establecimiento)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {cierreTabActiva === 'espacios' && (
            <>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Total recibido</p>
                  <p className="text-xl font-black text-slate-900">{formatMoney(totalPagosEspacios)}</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs text-slate-500">Registros</p>
                  <p className="text-xl font-black text-slate-900">{totalRegistrosEspacios}</p>
                </div>
                <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3">
                  <p className="text-xs text-emerald-700">Promedio por registro</p>
                  <p className="text-xl font-black text-emerald-900">{formatMoney(totalRegistrosEspacios > 0 ? totalPagosEspacios / totalRegistrosEspacios : 0)}</p>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="table-header">
                    <tr>
                      <th className="px-4 py-3 text-left">Fecha</th>
                      <th className="px-4 py-3 text-left">Empleado</th>
                      <th className="px-4 py-3 text-left">Valor pagado</th>
                      {puedeAjustarFechaEspacio && <th className="px-4 py-3 text-left">Ajustar fecha / monto</th>}
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {(espacios.detalle || []).length === 0 && (
                      <tr>
                        <td className="table-cell text-slate-500" colSpan={puedeAjustarFechaEspacio ? 4 : 3}>No hay pagos por espacio registrados en el rango.</td>
                      </tr>
                    )}
                    {(espacios.detalle || []).map((item, idx) => (
                      <tr key={`esp-tab-${item.estado_pago_id || 'x'}-${item.fecha || 'x'}-${item.estilista_id || idx}-${idx}`}>
                        <td className="table-cell">{item.fecha || '-'}</td>
                        <td className="table-cell">{item.estilista_nombre || '-'}</td>
                        <td className="table-cell font-semibold text-sky-700">{formatMoney(item.valor_pagado)}</td>
                        {puedeAjustarFechaEspacio && (
                          <td className="table-cell">
                            {item.estado_pago_id ? (
                              <div className="flex items-center gap-2">
                                <input
                                  type="number"
                                  min="1"
                                  step="1"
                                  className="input-field !py-1 !w-28"
                                  value={montoMoverEspacioById[item.estado_pago_id] ?? item.valor_pagado}
                                  onChange={(e) => setMontoMoverEspacioById((prev) => ({ ...prev, [item.estado_pago_id]: e.target.value }))}
                                  title="Monto a mover"
                                />
                                <input
                                  type="date"
                                  className="input-field !py-1 !w-40"
                                  value={nuevaFechaEspacioById[item.estado_pago_id] || item.fecha || ''}
                                  onChange={(e) => setNuevaFechaEspacioById((prev) => ({ ...prev, [item.estado_pago_id]: e.target.value }))}
                                />
                                <button
                                  type="button"
                                  className="btn-secondary !py-1 !px-2 text-xs"
                                  onClick={() => ajustarFechaPagoEspacio(item)}
                                  disabled={!!savingFechaEspacioById[item.estado_pago_id]}
                                >
                                  {savingFechaEspacioById[item.estado_pago_id] ? 'Guardando...' : 'Guardar'}
                                </button>
                              </div>
                            ) : (
                              <span className="text-xs text-slate-500">No editable</span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    );
  };

  const renderModuloLiquidacion = () => (
    <div className="space-y-6">
      <section className="rounded-3xl bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 p-6 text-white shadow-2xl">
        <h2 className="text-2xl font-black tracking-tight">Liquidación Inteligente</h2>
        <p className="mt-2 text-sm text-slate-200">Vista por día para liquidar lo que gana el empleado con menor complejidad operativa.</p>
        <div className="mt-3 inline-flex flex-wrap gap-1 rounded-xl border border-white/30 bg-white/10 p-1">
          <button
            type="button"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${vistaSimpleLiquidacion === true ? 'bg-white text-slate-900' : 'text-white'}`}
            onClick={() => setVistaSimpleLiquidacion(true)}
          >
            Vista simple
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${vistaSimpleLiquidacion === false ? 'bg-white text-slate-900' : 'text-white'}`}
            onClick={() => setVistaSimpleLiquidacion(false)}
          >
            Vista avanzada
          </button>
          <button
            type="button"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${vistaSimpleLiquidacion === 'deuda' ? 'bg-white text-slate-900' : 'text-white'}`}
            onClick={() => setVistaSimpleLiquidacion('deuda')}
          >
            Cargar deuda
          </button>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-6">
        <aside className="card border border-slate-200 bg-slate-50">
          <div className="flex items-center justify-between gap-2 mb-3">
            <h3 className="card-header mb-0">Empleados</h3>
            <button className="btn-secondary !py-1.5" onClick={cargarTodo} disabled={loading}>Actualizar</button>
          </div>
          <div className="space-y-2 max-h-[68vh] overflow-y-auto pr-1">
            {(biData?.estilistas || []).length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">No hay empleados para liquidar.</div>
            )}
            {(biData?.estilistas || []).map((item) => {
              const estId = Number(item.estilista_id);
              const activo = estId === Number(estilistaActivoLiquidacion);
              const totalPendiente = calcularPendientePagoEmpleado(item);
              const consumoPendiente = Number(resumenPorEstilistaLiquidacion[estId]?.saldo_pendiente || 0);
              const deudaPuesto = Number(item.deuda_total_acumulada || 0);
              return (
                <button
                  key={estId}
                  type="button"
                  onClick={() => {
                    setEstilistaActivoLiquidacion(estId);
                    setPasoLiquidacion(vistaSimpleLiquidacion ? 3 : 1);
                  }}
                  className={`w-full rounded-2xl border p-3 text-left transition ${activo ? 'border-emerald-400 bg-emerald-50 shadow-md' : 'border-slate-200 bg-white hover:border-slate-300'}`}
                >
                  <p className="font-semibold text-slate-900">{item.estilista_nombre}</p>
                  <p className="text-xs text-slate-500 mt-1">Pendiente pago: <b>{formatMoney(totalPendiente)}</b></p>
                  <p className="text-xs text-rose-600 mt-1">Consumo: {formatMoney(consumoPendiente)}</p>
                  <p className="text-xs text-amber-700 mt-1">Puesto: {formatMoney(deudaPuesto)}</p>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="space-y-4">
          {!estilistaActivoLiquidacion && (
            <div className="card text-slate-500">Selecciona un empleado para ver su resumen integral.</div>
          )}

          {(() => {
            const empleado = (biData?.estilistas || []).find((x) => Number(x.estilista_id) === Number(estilistaActivoLiquidacion));
            if (!empleado) return null;

            const estId = Number(empleado.estilista_id);
            const valorTotalEmpleado = Number((empleado.valor_total_empleado ?? empleado.facturacion_servicios ?? empleado.ganancias_servicios) || 0);
            const comisionesEmpleado = Number(empleado.comision_ventas_producto || 0);
            const generadoEmpleadoCalculado = valorTotalEmpleado + comisionesEmpleado;
            const generadoEmpleado = Math.max(
              Number(empleado?.generado_total_empleado ?? empleado?.pago_neto_periodo ?? generadoEmpleadoCalculado),
              0
            );
            const pendientePagoEmpleado = calcularPendientePagoEmpleado(empleado);
            const consumoPendiente = Number(resumenPorEstilistaLiquidacion[estId]?.saldo_pendiente || 0);
            const cobroConsumoDigitado = Number(cobroConsumoPorEstilista[estId] || 0);
            const cobroConsumoAplicado = Math.min(Math.max(cobroConsumoDigitado, 0), Math.max(consumoPendiente, 0));
            const abonoPuestoDigitado = Math.max(Number(abonoPuestoPorEstilista[estId] || 0), 0);
            const modoCobroPuesto = modoCobroPuestoPorEstilista[estId] || 'fijo';
            const porcentajePuestoDigitado = Math.max(Number(porcentajePuestoPorEstilista[estId] || 0), 0);
            const deudaPuestoAcumulada = Number(empleado.deuda_total_acumulada || 0);
            const netoEstimado = Math.max(pendientePagoEmpleado, 0);
            const pagoDigitado = totalPagoMedios(estId);
            const saldoPorPagar = Math.max(netoEstimado - pagoDigitado, 0);
            const historialPagosEmpleado = (historialEstados || []).filter((h) => Number(h.estilista_id) === estId);
            const diasPendientes = desgloseLiquidacion?.desglose_por_dia?.filter((d) => String(d.incluido_en || d.estado || '').toLowerCase() !== 'cancelado') || [];
            const diasCuadre = [...diasPendientes].sort((a, b) => String(b.fecha || '').localeCompare(String(a.fecha || '')));
            const descuentoPorFecha = diasPendientes.reduce((acc, d) => {
              acc[String(d.fecha || '')] = Number(d.descuento_espacio || 0);
              return acc;
            }, {});
            const generadoPorFecha = diasPendientes.reduce((acc, d) => {
              acc[String(d.fecha || '')] = Math.max(Number(d.neto_dia || 0), 0);
              return acc;
            }, {});
            const historialDiarioLiquidacion = Object.values(
              historialPagosEmpleado.reduce((acc, h) => {
                const fecha = h.fecha || '-';
                const previo = acc[fecha] || {
                  fecha,
                  historial_id: Number(h.id || 0),
                  pago_empleado_dia: 0,
                  abono_puesto_dia: 0,
                  medio_abono_puesto: h.medio_abono_puesto || 'efectivo',
                  saldo_puesto_cierre: Number(h.pendiente_puesto || 0),
                  fecha_cambio: h.fecha_cambio || '',
                  usuario_nombre: h.usuario_nombre || 'Sistema',
                };

                const pagoDia = Number(previo.pago_empleado_dia || 0) + Number(h.monto_liquidado || 0);
                const cambioPrevio = String(previo.fecha_cambio || '');
                const cambioActual = String(h.fecha_cambio || '');
                const usarActualComoCierre = cambioActual >= cambioPrevio;

                acc[fecha] = {
                  ...previo,
                  historial_id: usarActualComoCierre ? Number(h.id || previo.historial_id || 0) : Number(previo.historial_id || 0),
                  pago_empleado_dia: pagoDia,
                  // Muestra el abono de la última operación del día para evitar
                  // mezclar históricos antiguos guardados como acumulados.
                  abono_puesto_dia: usarActualComoCierre ? Number(h.abono_puesto || 0) : Number(previo.abono_puesto_dia || 0),
                  medio_abono_puesto: usarActualComoCierre ? (h.medio_abono_puesto || previo.medio_abono_puesto || 'efectivo') : (previo.medio_abono_puesto || 'efectivo'),
                  saldo_puesto_cierre: usarActualComoCierre ? Number(h.pendiente_puesto || 0) : Number(previo.saldo_puesto_cierre || 0),
                  fecha_cambio: usarActualComoCierre ? (h.fecha_cambio || previo.fecha_cambio) : previo.fecha_cambio,
                  usuario_nombre: usarActualComoCierre ? (h.usuario_nombre || previo.usuario_nombre) : previo.usuario_nombre,
                };

                return acc;
              }, {})
            )
              .map((h) => {
                const descuentoDia = Number(descuentoPorFecha[String(h.fecha || '')] || 0);
                const abonoRegistrado = Number(h.abono_puesto_dia || 0);
                const abonoAplicadoDia = descuentoDia > 0 ? Math.min(abonoRegistrado, descuentoDia) : abonoRegistrado;
                const abonoArrastre = Math.max(abonoRegistrado - abonoAplicadoDia, 0);
                return {
                  ...h,
                  descuento_dia: descuentoDia,
                  abono_aplicado_dia: abonoAplicadoDia,
                  abono_arrastre: abonoArrastre,
                };
              })
              .sort((a, b) => String(b.fecha || '').localeCompare(String(a.fecha || '')));
            const historialDiarioPorFecha = historialDiarioLiquidacion.reduce((acc, h) => {
              acc[String(h.fecha || '')] = h;
              return acc;
            }, {});
            const historialAbonosConsumo = (carteraDataLiquidacionGlobal?.abonos_historial || []).filter((h) => Number(h.estilista_id) === estId);
            const pagoConsumoPorFecha = historialAbonosConsumo.reduce((acc, a) => {
              const fecha = String(a.fecha_hora || '').slice(0, 10);
              if (!fecha) return acc;
              acc[fecha] = Number(acc[fecha] || 0) + Number(a.monto || 0);
              return acc;
            }, {});
            const deudasEmpleado = (carteraDataLiquidacionGlobal?.deudas || []).filter((d) => Number(d.estilista_id) === estId && Number(d.saldo_pendiente || 0) > 0);
            const deudasConsumoSeleccionadas = deudaConsumoSeleccionadasPorEstilista[estId] || [];
            const cuadrePorFecha = cuadreDiarioByEstilista[estId] || {};
            const fechaOperacionSimple = String(fechaFin || '');
            const diaSeleccionadoSimple = (desgloseLiquidacion?.desglose_por_dia || []).find(
              (d) => String(d.fecha || '') === fechaOperacionSimple
            );
            const generadoEmpleadoSimple = diaSeleccionadoSimple
              ? Math.max(Number(diaSeleccionadoSimple.base_servicio || 0), 0)
              : Math.max(Number(empleado?.valor_total_empleado || 0), 0);
            const descuentoPuestoDiaSimple = diaSeleccionadoSimple
              ? Math.max(Number(diaSeleccionadoSimple.descuento_espacio || 0), 0)
              : 0;
            const puestoPendienteSimple = Math.max(Number(deudaPuestoAcumulada || 0), 0);
            const puestoTotalSimple = Math.max(descuentoPuestoDiaSimple + puestoPendienteSimple, 0);
            const abonoPuestoCalculado = modoCobroPuesto === 'porcentaje'
              ? Math.round((Math.max(generadoEmpleadoSimple, 0) * porcentajePuestoDigitado) / 100)
              : abonoPuestoDigitado;
            const tieneValorPuestoDigitado = String(abonoPuestoPorEstilista[estId] || '').trim().length > 0;
            const tienePorcentajeDigitado = String(porcentajePuestoPorEstilista[estId] || '').trim().length > 0;
            const tienePuestoManual = modoCobroPuesto === 'porcentaje' ? tienePorcentajeDigitado : tieneValorPuestoDigitado;
            const skipPuestoEstilista = Boolean(skipDescuentoPuestoPorEstilista[estId] || false);
            const descuentoPuestoAplicado = skipPuestoEstilista
              ? 0  // No aplicar descuento si skip está marcado
              : (tienePuestoManual
                  ? Math.max(abonoPuestoCalculado, 0)
                  : descuentoPuestoDiaSimple);
            const descuentoConsumoAplicado = cobroConsumoAplicado;
            const totalDescuentosSimple = descuentoPuestoAplicado;
            const totalPagarFinalSimple = Math.max(generadoEmpleadoSimple - totalDescuentosSimple, 0);
            const pagosSimple = pagosPorEstilista[estId] || {};
            const pagoEfectivoSimple = Math.max(Number(pagosSimple.efectivo || 0), 0);
            const pagoNequiSimple = Math.max(Number(pagosSimple.nequi || 0), 0);
            const pagoDaviplataSimple = Math.max(Number(pagosSimple.daviplata || 0), 0);
            const pagoOtrosSimple = Math.max(Number(pagosSimple.otros || 0), 0);
            const totalPagosDigitadosSimple = pagoEfectivoSimple + pagoNequiSimple + pagoDaviplataSimple + pagoOtrosSimple;
            const saldoOperativoSimple = Math.max(totalPagarFinalSimple - totalPagosDigitadosSimple, 0);
            const abonoPuestoAvanzadoCalculado = modoCobroPuesto === 'porcentaje'
              ? Math.max(Math.round((Math.max(generadoEmpleadoSimple, 0) * porcentajePuestoDigitado) / 100), 0)
              : abonoPuestoDigitado;

            if (vistaSimpleLiquidacion === 'deuda') {
              return (
                <>
                  <div className="card border border-violet-200 bg-violet-50">
                    <h3 className="card-header mb-3">Cargar deuda de puesto manual</h3>
                    <p className="text-xs text-slate-600 mb-4">Selecciona un empleado, fecha y monto para cargar deuda de puesto manualmente.</p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs text-slate-600 mb-2">Empleado</label>
                        <select
                          className="input-field"
                          value={deudaPuestoModal.estilista_id || ''}
                          onChange={(e) => setDeudaPuestoModal((prev) => ({ ...prev, estilista_id: e.target.value }))}
                        >
                          <option value="">Selecciona un empleado</option>
                          {(biData?.estilistas || []).map((est) => (
                            <option key={est.estilista_id} value={est.estilista_id}>
                              {est.estilista_nombre}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-2">Fecha</label>
                        <input
                          type="date"
                          className="input-field"
                          value={deudaPuestoModal.fecha}
                          onChange={(e) => setDeudaPuestoModal((prev) => ({ ...prev, fecha: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-2">Monto de deuda</label>
                        <input
                          type="number"
                          className="input-field"
                          min="0"
                          step="1"
                          value={deudaPuestoModal.monto}
                          onChange={(e) => setDeudaPuestoModal((prev) => ({ ...prev, monto: e.target.value }))}
                          placeholder="0"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-600 mb-2">Notas (opcional)</label>
                        <input
                          type="text"
                          className="input-field"
                          value={deudaPuestoModal.notas}
                          onChange={(e) => setDeudaPuestoModal((prev) => ({ ...prev, notas: e.target.value }))}
                          placeholder="Ej: No laboró"
                        />
                      </div>
                    </div>

                    <div className="mt-4 flex gap-2">
                      <button
                        className="btn-primary flex-1"
                        onClick={cargarDeudaPuestoManual}
                        disabled={deudaPuestoModal.loading}
                      >
                        {deudaPuestoModal.loading ? 'Cargando...' : 'Cargar deuda'}
                      </button>
                    </div>
                  </div>
                </>
              );
            }

            if (vistaSimpleLiquidacion === true) {
              return (
                <>
                  {String(fechaInicio || '') !== String(fechaFin || '') && (
                    <div className="card border border-amber-300 bg-amber-50 text-amber-900">
                      Esta vista liquida un solo día. Para evitar diferencias, usa la misma fecha en inicio y fin.
                    </div>
                  )}
                  <div className="card border border-slate-200 bg-white">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="rounded-2xl border border-sky-200 bg-sky-50 p-4">
                        <p className="text-xs uppercase tracking-wide text-sky-700 font-semibold">Total generado</p>
                        <p className="text-2xl font-black text-sky-900 mt-1">{formatMoney(generadoEmpleadoSimple)}</p>
                        <p className="text-[11px] text-sky-700 mt-1">Base empleado por servicios del día. Fecha operativa: {fechaOperacionSimple || '-'}</p>
                      </div>
                      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                        <p className="text-xs uppercase tracking-wide text-rose-700 font-semibold">Total descuentos</p>
                        <p className="text-2xl font-black text-rose-900 mt-1">{formatMoney(totalDescuentosSimple)}</p>
                        <p className="text-[11px] text-rose-700 mt-1">Solo descuento de puesto del día o valor ingresado en Paso 1.</p>
                      </div>
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                        <p className="text-xs uppercase tracking-wide text-emerald-700 font-semibold">Total a pagar final</p>
                        <p className="text-3xl font-black text-emerald-900 mt-1">{formatMoney(totalPagarFinalSimple)}</p>
                      </div>
                    </div>
                  </div>

                  <div className="card border border-slate-200 bg-white">
                    <div className="flex flex-wrap gap-2">
                      {[3, 4].map((paso, idx) => {
                        const activo = pasoLiquidacion === paso;
                        const completado = pasoLiquidacion > paso;
                        return (
                          <button
                            key={`paso-${paso}`}
                            type="button"
                            className={`px-3 py-2 rounded-xl border text-sm font-semibold ${activo ? 'border-sky-400 bg-sky-100 text-sky-900' : completado ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-slate-200 bg-slate-50 text-slate-700'}`}
                            onClick={() => setPasoLiquidacion(paso)}
                          >
                            Paso {idx + 1}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {pasoLiquidacion === 3 && (
                    <div className="card border border-rose-200 bg-rose-50">
                      <h4 className="card-header mb-2">Paso 1: Aplicar descuentos</h4>
                      <div className="mb-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3">
                          <p className="text-xs text-amber-800">Pendiente cobro puesto</p>
                          <p className="text-2xl font-black text-amber-900">{formatMoney(Math.max(deudaPuestoAcumulada, 0))}</p>
                        </div>
                        <div className="rounded-xl border border-rose-300 bg-rose-100 p-3">
                          <p className="text-xs text-rose-800">Pendiente consumo cartera</p>
                          <p className="text-2xl font-black text-rose-900">{formatMoney(Math.max(consumoPendiente, 0))}</p>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div className="rounded-xl border border-amber-200 bg-white p-3">
                          <p className="text-sm font-semibold text-slate-900">Alquiler del puesto</p>
                          <div className="mt-1 space-y-1 text-xs text-slate-700">
                            <p>Valor puesto día filtrado: <span className="font-semibold text-amber-800">{formatMoney(descuentoPuestoDiaSimple)}</span></p>
                            <p>Valor pendiente: <span className="font-semibold text-amber-800">{formatMoney(puestoPendienteSimple)}</span></p>
                            <p>Valor total (día + pendiente): <span className="font-semibold text-amber-900">{formatMoney(puestoTotalSimple)}</span></p>
                          </div>
                          <label className="flex items-start gap-2 mt-3 mb-3 p-2 rounded-lg bg-red-50 border border-red-200 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={Boolean(skipDescuentoPuestoPorEstilista[estId])}
                              onChange={(e) => {
                                setSkipDescuentoPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.checked }));
                                if (e.target.checked) {
                                  setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: '0' }));
                                }
                              }}
                              className="mt-1"
                            />
                            <span className="text-xs text-red-800">
                              <strong>⚠️ No descontar puesto este día</strong>
                              <br />El costo del puesto se sumará a la deuda del empleado.
                            </span>
                          </label>
                          {!skipDescuentoPuestoPorEstilista[estId] && (
                            <>
                              <label className="block text-xs text-slate-600 mb-1">Tipo de cobro del puesto</label>
                          <select
                            className="input-field"
                            value={modoCobroPuesto}
                            onChange={(e) => setModoCobroPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                          >
                            <option value="fijo">Valor fijo</option>
                            <option value="porcentaje">Porcentaje del generado del día</option>
                          </select>

                          {modoCobroPuesto === 'fijo' ? (
                            <>
                              <button
                                type="button"
                                className="btn-secondary !py-1 !px-2 text-xs mt-2"
                                onClick={() => setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: String(puestoPendienteSimple) }))}
                              >
                                Usar pendiente completo
                              </button>
                              <label className="block text-xs text-slate-600 mt-2 mb-1">Valor a descontar</label>
                              <input
                                className="input-field"
                                type="number"
                                min="0"
                                step="1"
                                value={abonoPuestoPorEstilista[estId] || ''}
                                onChange={(e) => setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                              />
                            </>
                          ) : (
                            <>
                              <label className="block text-xs text-slate-600 mt-2 mb-1">Porcentaje (%)</label>
                              <input
                                className="input-field"
                                type="number"
                                min="0"
                                step="0.1"
                                value={porcentajePuestoPorEstilista[estId] || ''}
                                onChange={(e) => setPorcentajePuestoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                              />
                              <p className="text-[11px] text-slate-600 mt-1">Base: generado del día {formatMoney(Math.max(generadoEmpleadoSimple, 0))}</p>
                              <p className="text-[11px] text-amber-700 mt-1">Calculado hoy: {formatMoney(abonoPuestoCalculado)}</p>
                            </>
                          )}
                          <label className="block text-xs text-slate-600 mt-2 mb-1">Medio del abono</label>
                          <select
                            className="input-field"
                            value={medioAbonoPuestoPorEstilista[estId] || 'efectivo'}
                            onChange={(e) => setMedioAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                          >
                            {MEDIOS_PAGO_OPERACION.map((m) => (
                              <option key={`medio-puesto-${m.value}`} value={m.value}>{m.label}</option>
                            ))}
                          </select>
                          <label className="block text-xs text-slate-600 mt-2 mb-1">Comisión de ventas al empleado</label>
                          <select
                            className="input-field"
                            value={Boolean(aplicaComisionVentasPorEstilista[estId] ?? true) ? 'si' : 'no'}
                            onChange={(e) => setAplicaComisionVentasPorEstilista((prev) => ({ ...prev, [estId]: e.target.value === 'si' }))}
                          >
                            <option value="si">Sí, aplica</option>
                            <option value="no">No aplica (ingreso establecimiento)</option>
                          </select>
                          <p className="text-xs text-amber-700 mt-2">Aplicado: {formatMoney(descuentoPuestoAplicado)}</p>
                          <p className="text-[11px] text-slate-600 mt-1">Se registra como abono de puesto y no se vuelve a descontar del pendiente.</p>
                            </>
                          )}
                        </div>

                        <div className="rounded-xl border border-rose-200 bg-white p-3">
                          <p className="text-sm font-semibold text-slate-900">Consumo de productos</p>
                          <p className="text-xs text-slate-600 mt-1">Pendiente actual: <span className="font-semibold text-rose-700">{formatMoney(Math.max(consumoPendiente, 0))}</span></p>
                          <div className="mt-2 flex items-center gap-2">
                            <button type="button" className="btn-secondary !py-1 !px-2 text-xs" onClick={() => seleccionarTodasDeudasConsumo(estId, deudasEmpleado)}>Seleccionar todas</button>
                            <button type="button" className="btn-secondary !py-1 !px-2 text-xs" onClick={() => limpiarSeleccionDeudasConsumo(estId)}>Limpiar</button>
                            <button
                              type="button"
                              className="btn-secondary !py-1 !px-2 text-xs"
                              onClick={() => setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: String(Math.max(consumoPendiente, 0)) }))}
                            >
                              Usar pendiente consumo
                            </button>
                          </div>
                          <div className="mt-2 max-h-40 overflow-y-auto space-y-2 pr-1">
                            {deudasEmpleado.length === 0 && <p className="text-xs text-slate-500">No hay facturas pendientes.</p>}
                            {deudasEmpleado.map((d) => (
                              <label key={`deuda-simple-${d.deuda_id}`} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={deudasConsumoSeleccionadas.includes(String(d.deuda_id))}
                                  onChange={() => toggleDeudaConsumoSeleccion(estId, d.deuda_id)}
                                />
                                <span className="text-xs text-slate-700">{d.numero_factura || `Deuda ${d.deuda_id}`} - {formatMoney(d.saldo_pendiente)}</span>
                              </label>
                            ))}
                          </div>
                          <label className="block text-xs text-slate-600 mt-2 mb-1">Valor a descontar por consumo</label>
                          <input
                            className="input-field"
                            type="number"
                            min="0"
                            step="1"
                            value={cobroConsumoPorEstilista[estId] || ''}
                            onChange={(e) => setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                          />
                          <label className="block text-xs text-slate-600 mt-2 mb-1">Medio del cobro consumo</label>
                          <select
                            className="input-field"
                            value={medioCobroConsumoPorEstilista[estId] || 'efectivo'}
                            onChange={(e) => setMedioCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                          >
                            {MEDIOS_PAGO_OPERACION.map((m) => (
                              <option key={`medio-consumo-${m.value}`} value={m.value}>{m.label}</option>
                            ))}
                          </select>
                          <p className="text-xs text-rose-700 mt-2">Aplicado: {formatMoney(descuentoConsumoAplicado)}</p>
                        </div>
                      </div>
                      <div className="mt-3 rounded-xl border border-rose-200 bg-white p-3">
                        <p className="text-sm text-slate-700">Descuento total en tiempo real</p>
                        <p className="text-2xl font-black text-rose-700">{formatMoney(totalDescuentosSimple)}</p>
                        <p className="text-[11px] text-slate-600 mt-1">El descuento de puesto ya está incluido en el pendiente mostrado.</p>
                      </div>
                      <div className="mt-3 flex gap-2">
                        <button className="btn-primary" onClick={() => setPasoLiquidacion(4)}>Siguiente</button>
                      </div>
                    </div>
                  )}

                  {pasoLiquidacion === 4 && (
                    <div className="card border border-emerald-200 bg-emerald-50">
                      <h4 className="card-header mb-2">Paso 2: Total final a pagar</h4>
                      <div className="rounded-2xl border border-emerald-300 bg-white p-4">
                        <p className="text-sm text-slate-700">Total generado base</p>
                        <p className="text-lg font-bold text-slate-900">{formatMoney(generadoEmpleadoSimple)}</p>
                        <p className="text-sm text-rose-700 mt-2">(-) Descuentos: {formatMoney(totalDescuentosSimple)}</p>
                        <p className="text-sm text-slate-700 mt-2">Pagos digitados por medios: {formatMoney(totalPagosDigitadosSimple)}</p>
                        <p className="text-sm text-amber-700 mt-1">Saldo operativo por pagar: {formatMoney(saldoOperativoSimple)}</p>
                        <p className="text-xs text-slate-500">Puesto aplicado: {formatMoney(descuentoPuestoAplicado)}. Cobro consumo (registro aparte): {formatMoney(descuentoConsumoAplicado)}.</p>
                        <p className="text-4xl font-black text-emerald-800 mt-3">{formatMoney(totalPagarFinalSimple)}</p>
                      </div>

                      <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-4">
                        <p className="text-sm font-semibold text-slate-800">Medios de pago del total final</p>
                        <p className="text-xs text-slate-600 mt-1">Si no llenas estos campos, al confirmar se registra todo en efectivo.</p>
                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                          <div>
                            <label className="block text-xs text-slate-600 mb-1">Efectivo</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.efectivo || ''}
                              onChange={(e) => actualizarPagoMedio(estId, 'efectivo', e.target.value)}
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-600 mb-1">Nequi</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.nequi || ''}
                              onChange={(e) => actualizarPagoMedio(estId, 'nequi', e.target.value)}
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-600 mb-1">Daviplata</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.daviplata || ''}
                              onChange={(e) => actualizarPagoMedio(estId, 'daviplata', e.target.value)}
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-slate-600 mb-1">Otros</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.otros || ''}
                              onChange={(e) => actualizarPagoMedio(estId, 'otros', e.target.value)}
                            />
                          </div>
                        </div>
                      </div>

                      <div className="mt-3 flex gap-2">
                        <button className="btn-secondary" onClick={() => setPasoLiquidacion(3)}>Anterior</button>
                        <button
                          className="btn-primary"
                          onClick={() => aplicarLiquidacionSimple({
                            fila: empleado,
                            pendientePagoEmpleado: generadoEmpleadoSimple,
                            abonoPuestoAplicado: descuentoPuestoAplicado,
                            cobroConsumoAplicado: descuentoConsumoAplicado,
                            deudasConsumoSeleccionadas,
                            pagosPorMedio: {
                              efectivo: pagoEfectivoSimple,
                              nequi: pagoNequiSimple,
                              daviplata: pagoDaviplataSimple,
                              otros: pagoOtrosSimple,
                            },
                          })}
                          disabled={!!savingEstadoByEstilista[estId]}
                        >
                          {savingEstadoByEstilista[estId] ? 'Guardando...' : 'Confirmar liquidación'}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              );
            }

            return (
              <>
                <div className="card border border-emerald-200 bg-emerald-50">
                  <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
                    <div>
                      <h3 className="text-2xl font-black text-slate-900">{empleado.estilista_nombre}</h3>
                      <p className="text-sm text-slate-600 mt-1">Resumen calculado con los filtros superiores actualmente aplicados.</p>
                      <p className="text-xs text-slate-500 mt-1">Liquidando el día: <b>{fechaFin}</b> (según filtro superior).</p>
                      <p className="text-xs text-slate-500 mt-1">Pendiente por pagar calculado en rango: <b>{fechaInicio}</b> a <b>{fechaFin}</b>.</p>
                    </div>
                  </div>

                  <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
                    <p className="text-xs text-slate-500">Días pendientes en rango</p>
                    <p className="text-xl font-black text-slate-900 mt-1">{loadingDesgloseLiquidacion ? '...' : diasPendientes.length}</p>
                  </div>

                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Generado empleado</p>
                      <p className="text-xl font-black text-slate-900 mt-1">{formatMoney(generadoEmpleado)}</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Pendiente por pagar</p>
                      <p className="text-xl font-black text-emerald-700 mt-1">{formatMoney(pendientePagoEmpleado)}</p>
                      <p className="text-[11px] text-slate-500 mt-1">Generado del periodo menos lo ya pagado al empleado.</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Consumo pendiente</p>
                      <p className="text-xl font-black text-rose-700 mt-1">{formatMoney(consumoPendiente)}</p>
                    </div>
                    <div className="rounded-xl border border-white bg-white p-3">
                      <p className="text-xs text-slate-500">Deuda puesto acumulada</p>
                      <p className="text-xl font-black text-amber-700 mt-1">{formatMoney(deudaPuestoAcumulada)}</p>
                      <p className="text-[11px] text-slate-500 mt-1">Debe puesto = cobros de puesto no cubiertos por abonos registrados.</p>
                    </div>
                  </div>
                </div>

                <div className="card border border-slate-200 bg-white">
                  <h4 className="card-header mb-2">Días incluidos en el pendiente por pagar (antes de liquidar)</h4>
                  <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
                    {loadingDesgloseLiquidacion && <p className="text-sm text-slate-500">Cargando días pendientes...</p>}
                    {!loadingDesgloseLiquidacion && diasPendientes.length === 0 && (
                      <p className="text-sm text-slate-500">No hay días pendientes en el rango seleccionado.</p>
                    )}
                    {!loadingDesgloseLiquidacion && diasPendientes.map((d) => (
                      <div key={`dia-${d.fecha}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                        {(() => {
                          const histDia = historialDiarioPorFecha[String(d.fecha || '')] || {};
                          const pagoEmpleadoDia = Number(histDia.pago_empleado_dia || 0);
                          const netoDia = Number(d.neto_dia || 0);
                          const pendienteEmpleadoDia = Math.max(netoDia - pagoEmpleadoDia, 0);
                          return (
                            <>
                              <div className="flex justify-between gap-2">
                                <p className="text-sm font-semibold text-slate-900">{d.fecha}</p>
                                <p className="text-sm font-bold text-emerald-700">Pendiente día: {formatMoney(pendienteEmpleadoDia)}</p>
                              </div>
                              <p className="text-xs text-slate-600 mt-1">Neto día (antes de pagos): {formatMoney(netoDia)}</p>
                              <p className="text-xs text-slate-600">Pago registrado en historial: {formatMoney(pagoEmpleadoDia)}</p>
                              <p className="text-xs text-slate-600">Base servicio: {formatMoney(d.base_servicio)} | Comisión: {formatMoney(d.comision_productos)}</p>
                              <p className="text-xs text-slate-600">Descuento puesto: {formatMoney(d.descuento_espacio)}</p>
                              <p className="text-xs text-slate-500">Estado día: {d.estado || 'pendiente'}</p>
                            </>
                          );
                        })()}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card border border-indigo-200 bg-indigo-50">
                  <h4 className="card-header mb-2">Cuadre diario editable (por fecha)</h4>
                  <p className="text-xs text-slate-600 mb-3">Ajusta medios pagados al empleado y abono de puesto por cada día. Al guardar, se reemplaza solo ese día.</p>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-indigo-200">
                      <thead className="bg-indigo-100 text-indigo-900 text-xs uppercase tracking-wide">
                        <tr>
                          <th className="px-3 py-2 text-left">Fecha</th>
                          <th className="px-3 py-2 text-left">Neto día</th>
                          <th className="px-3 py-2 text-left">Efectivo</th>
                          <th className="px-3 py-2 text-left">Nequi</th>
                          <th className="px-3 py-2 text-left">Daviplata</th>
                          <th className="px-3 py-2 text-left">Otros</th>
                          <th className="px-3 py-2 text-left">Abono puesto</th>
                          <th className="px-3 py-2 text-left">Medio abono</th>
                          <th className="px-3 py-2 text-left">Comisión ventas</th>
                          <th className="px-3 py-2 text-left">Acción</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-indigo-100">
                        {diasCuadre.length === 0 && (
                          <tr>
                            <td className="table-cell text-slate-500" colSpan={10}>No hay días en el rango para cuadrar.</td>
                          </tr>
                        )}
                        {diasCuadre.map((d) => {
                          const fechaDia = String(d.fecha || '');
                          const key = `${estId}|${fechaDia}`;
                          const histDia = historialDiarioPorFecha[fechaDia] || {};
                          const filaCuadre = cuadrePorFecha[fechaDia] || {};
                          const pagoHistorial = Math.max(Number(histDia.pago_empleado_dia || 0), 0);
                          const pagoEfectivo = filaCuadre.pago_efectivo ?? (pagoHistorial ? String(pagoHistorial) : '');
                          const pagoNequi = filaCuadre.pago_nequi ?? '';
                          const pagoDaviplata = filaCuadre.pago_daviplata ?? '';
                          const pagoOtros = filaCuadre.pago_otros ?? '';
                          const abonoPuesto = filaCuadre.abono_puesto ?? (histDia.abono_puesto_dia ? String(Number(histDia.abono_puesto_dia || 0)) : '');
                          const medioAbono = filaCuadre.medio_abono_puesto || histDia.medio_abono_puesto || 'efectivo';
                          const aplicaComisionVentasDia = Boolean(filaCuadre.aplica_comision_ventas ?? histDia.aplica_comision_ventas ?? true);
                          const totalPagoFila = toMontoNoNegativo(pagoEfectivo) + toMontoNoNegativo(pagoNequi) + toMontoNoNegativo(pagoDaviplata) + toMontoNoNegativo(pagoOtros);
                          const netoDia = Math.max(Number(d.neto_dia || 0), 0);
                          const excedido = totalPagoFila > netoDia;

                          return (
                            <tr key={`cuadre-dia-${fechaDia}`} className="align-top">
                              <td className="table-cell font-semibold text-slate-900">{fechaDia || '-'}</td>
                              <td className="table-cell">
                                <p className="font-semibold text-slate-900">{formatMoney(netoDia)}</p>
                                <p className="text-[11px] text-slate-500">Base {formatMoney(d.base_servicio)} + Com. {formatMoney(d.comision_productos)} - Puesto {formatMoney(d.descuento_espacio)}</p>
                              </td>
                              <td className="table-cell">
                                <input
                                  className="input-field !py-2 !w-24"
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={pagoEfectivo}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'pago_efectivo', e.target.value)}
                                />
                              </td>
                              <td className="table-cell">
                                <input
                                  className="input-field !py-2 !w-24"
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={pagoNequi}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'pago_nequi', e.target.value)}
                                />
                              </td>
                              <td className="table-cell">
                                <input
                                  className="input-field !py-2 !w-24"
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={pagoDaviplata}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'pago_daviplata', e.target.value)}
                                />
                              </td>
                              <td className="table-cell">
                                <input
                                  className="input-field !py-2 !w-24"
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={pagoOtros}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'pago_otros', e.target.value)}
                                />
                              </td>
                              <td className="table-cell">
                                <input
                                  className="input-field !py-2 !w-24"
                                  type="number"
                                  min="0"
                                  step="1"
                                  value={abonoPuesto}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'abono_puesto', e.target.value)}
                                />
                              </td>
                              <td className="table-cell">
                                <select
                                  className="input-field !py-2 !w-28"
                                  value={medioAbono}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'medio_abono_puesto', e.target.value)}
                                >
                                  {MEDIOS_PAGO_OPERACION.map((m) => (
                                    <option key={`${fechaDia}-${m.value}`} value={m.value}>{m.label}</option>
                                  ))}
                                </select>
                              </td>
                              <td className="table-cell">
                                <select
                                  className="input-field !py-2 !w-44"
                                  value={aplicaComisionVentasDia ? 'si' : 'no'}
                                  onChange={(e) => actualizarCuadreDiaCampo(estId, fechaDia, 'aplica_comision_ventas', e.target.value === 'si')}
                                >
                                  <option value="si">Sí aplica</option>
                                  <option value="no">No aplica</option>
                                </select>
                              </td>
                              <td className="table-cell">
                                <div className="space-y-1">
                                  <button
                                    type="button"
                                    className="btn-primary !py-2 !px-3"
                                    onClick={() => guardarCuadreDiario({ estilistaId: estId, fecha: fechaDia, netoDia })}
                                    disabled={!!savingCuadreDiaByKey[key] || !fechaDia}
                                  >
                                    {savingCuadreDiaByKey[key] ? 'Guardando...' : 'Guardar día'}
                                  </button>
                                  <p className={`text-[11px] ${excedido ? 'text-rose-700' : 'text-slate-500'}`}>
                                    Pagado: {formatMoney(totalPagoFila)}
                                  </p>
                                  {excedido && <p className="text-[11px] text-rose-700">Supera el neto del día</p>}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="card border border-slate-200 bg-white">
                  <h4 className="card-header mb-3">Liquidación integrada</h4>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                        <p className="text-sm font-semibold text-emerald-900">1) Pago al empleado</p>
                        <p className="text-xs text-emerald-800">Ingresa solo lo que realmente se le entrega a la empleada.</p>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        {['efectivo', 'nequi', 'daviplata', 'otros'].map((medio) => (
                          <div key={medio}>
                            <label className="block text-xs text-slate-600 mb-1 capitalize">Pago {medio}</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={pagosPorEstilista[estId]?.[medio] || ''}
                              onFocus={() => setNumericPadTarget({ estilistaId: estId, field: medio })}
                              onChange={(e) => actualizarPagoMedio(estId, medio, e.target.value)}
                            />
                          </div>
                        ))}
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Facturas de consumo a abonar (puedes elegir varias)</label>
                        <select
                          className="input-field"
                          multiple
                          size={Math.min(Math.max(deudasEmpleado.length, 3), 7)}
                          value={deudasConsumoSeleccionadas}
                          onChange={(e) => {
                            const seleccionadas = Array.from(e.target.selectedOptions || []).map((opt) => opt.value);
                            setDeudaConsumoSeleccionadasPorEstilista((prev) => ({ ...prev, [estId]: seleccionadas }));
                          }}
                        >
                          {deudasEmpleado.map((d) => (
                            <option key={d.deuda_id} value={String(d.deuda_id)}>
                              {(d.numero_factura || `Deuda ${d.deuda_id}`)} - Saldo {formatMoney(d.saldo_pendiente)}
                            </option>
                          ))}
                        </select>
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <p className="text-xs text-slate-500">
                            {deudasConsumoSeleccionadas.length > 0
                              ? `${deudasConsumoSeleccionadas.length} factura(s) seleccionada(s)`
                              : 'Si no seleccionas, el sistema distribuye automático (más antigua primero).'}
                          </p>
                          {deudasConsumoSeleccionadas.length > 0 && (
                            <button
                              type="button"
                              className="btn-secondary !py-1 !px-2 text-xs"
                              onClick={() => limpiarSeleccionDeudasConsumo(estId)}
                            >
                              Limpiar selección
                            </button>
                          )}
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Cobro consumo a aplicar</label>
                        <input
                          className="input-field"
                          type="number"
                          min="0"
                          step="1"
                          value={cobroConsumoPorEstilista[estId] || ''}
                          onFocus={() => setNumericPadTarget({ estilistaId: estId, field: 'cobro_consumo' })}
                          onChange={(e) => setCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                        />
                        <p className="text-xs text-slate-500 mt-1">Aplicado: {formatMoney(cobroConsumoAplicado)} de {formatMoney(consumoPendiente)}</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Medio cobro consumo</label>
                        <select
                          className="input-field"
                          value={medioCobroConsumoPorEstilista[estId] || 'efectivo'}
                          onChange={(e) => setMedioCobroConsumoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </div>

                    </div>

                    <div className="space-y-3">
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                        <p className="text-sm font-semibold text-amber-900">2) Abonos y deducciones</p>
                        <p className="text-xs text-amber-800">Estos valores descuentan o cubren deuda, no son pago directo a la empleada.</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Tipo de cobro puesto</label>
                        <select
                          className="input-field"
                          value={modoCobroPuesto}
                          onChange={(e) => setModoCobroPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          <option value="fijo">Valor fijo</option>
                          <option value="porcentaje">Porcentaje del generado del día</option>
                        </select>
                        {modoCobroPuesto === 'porcentaje' ? (
                          <>
                            <label className="block text-xs text-slate-600 mt-2 mb-1">Porcentaje (%)</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="0.1"
                              value={porcentajePuestoPorEstilista[estId] || ''}
                              onChange={(e) => setPorcentajePuestoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                            />
                            <p className="text-xs text-slate-500 mt-1">Base del día: {formatMoney(Math.max(generadoEmpleadoSimple, 0))}</p>
                            <p className="text-xs text-amber-700 mt-1">Abono calculado por porcentaje: {formatMoney(abonoPuestoAvanzadoCalculado)}</p>
                          </>
                        ) : (
                          <>
                            <label className="block text-xs text-slate-600 mt-2 mb-1">Abono puesto (esta operación)</label>
                            <input
                              className="input-field"
                              type="number"
                              min="0"
                              step="1"
                              value={abonoPuestoPorEstilista[estId] || ''}
                              onFocus={() => setNumericPadTarget({ estilistaId: estId, field: 'abono_puesto' })}
                              onChange={(e) => setAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: String(e.target.value || '').replace(/[^\d.]/g, '') }))}
                            />
                          </>
                        )}
                        <p className="text-xs text-slate-500 mt-1">Acumulado del día antes de guardar: {formatMoney(abonoPuestoAcumuladoPorEstilista[estId] || 0)}</p>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Medio abono puesto</label>
                        <select
                          className="input-field"
                          value={medioAbonoPuestoPorEstilista[estId] || 'efectivo'}
                          onChange={(e) => setMedioAbonoPuestoPorEstilista((prev) => ({ ...prev, [estId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs text-slate-600 mb-1">Comisión de ventas al empleado</label>
                        <select
                          className="input-field"
                          value={Boolean(aplicaComisionVentasPorEstilista[estId] ?? true) ? 'si' : 'no'}
                          onChange={(e) => setAplicaComisionVentasPorEstilista((prev) => ({ ...prev, [estId]: e.target.value === 'si' }))}
                        >
                          <option value="si">Sí, aplicar</option>
                          <option value="no">No, ingreso establecimiento</option>
                        </select>
                      </div>

                      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                        <p className="text-sm text-slate-700">Objetivo pago al empleado</p>
                        <p className="text-3xl font-black text-indigo-900 mt-1">{formatMoney(netoEstimado)}</p>
                        <p className="text-xs text-slate-600 mt-2">Pagado digitado: {formatMoney(pagoDigitado)}</p>
                        <p className="text-xs text-amber-700">Saldo pendiente: {formatMoney(saldoPorPagar)}</p>
                      </div>

                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                        <p className="text-sm font-semibold text-slate-800">Resumen claro de movimientos</p>
                        <div className="mt-2 space-y-1 text-xs text-slate-700">
                          <p>Total a pagar al empleado (día): <b>{formatMoney(pendientePagoEmpleado)}</b></p>
                          <p>(-) Pagado digitado por medios: <b>{formatMoney(pagoDigitado)}</b></p>
                          <p className="pt-1 text-amber-800">(=) Saldo pendiente de pago al empleado: <b>{formatMoney(saldoPorPagar)}</b></p>
                          <p className="pt-2 text-slate-600">Abono a puesto (se registra aparte, no descuenta el pago al empleado): <b>{formatMoney(abonoPuestoAvanzadoCalculado)}</b></p>
                          <p className="text-slate-600">Cobro consumo aplicado (se registra aparte): <b>{formatMoney(cobroConsumoAplicado)}</b></p>
                        </div>
                      </div>

                      <button
                        className="btn-primary !w-full !py-3"
                        onClick={() => aplicarEstadoLiquidacion(empleado)}
                        disabled={!!savingEstadoByEstilista[estId]}
                      >
                        {savingEstadoByEstilista[estId] ? 'Procesando...' : 'Liquidar y registrar movimientos'}
                      </button>
                      {Boolean(modoCorreccionPorEstilista[estId]) && (
                        <p className="text-xs text-amber-700">Modo corrección activo: al guardar se reemplazan los valores de ese día.</p>
                      )}
                    </div>
                  </div>
                </div>

                {!vistaSimpleLiquidacion && (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <div className="card border border-amber-200 bg-amber-50">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <h4 className="card-header">Facturas de consumo pendientes</h4>
                      {deudasEmpleado.length > 0 && (
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            className="btn-secondary !py-1 !px-2 text-xs"
                            onClick={() => seleccionarTodasDeudasConsumo(estId, deudasEmpleado)}
                          >
                            Seleccionar todas
                          </button>
                          <button
                            type="button"
                            className="btn-secondary !py-1 !px-2 text-xs"
                            onClick={() => limpiarSeleccionDeudasConsumo(estId)}
                          >
                            Limpiar
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                      {deudasEmpleado.length === 0 && <p className="text-sm text-slate-500">No tiene consumo pendiente.</p>}
                      {deudasEmpleado.map((d) => (
                        <div key={d.deuda_id} className="rounded-xl border border-amber-200 bg-white p-3">
                          <label className="flex items-start gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              className="mt-1"
                              checked={deudasConsumoSeleccionadas.includes(String(d.deuda_id))}
                              onChange={() => toggleDeudaConsumoSeleccion(estId, d.deuda_id)}
                            />
                            <span className="text-sm font-semibold text-slate-900">{d.numero_factura || `Deuda ${d.deuda_id}`}</span>
                          </label>
                          <p className="text-xs text-slate-500">{d.fecha_hora || '-'}</p>
                          <p className="text-xs text-rose-700 mt-1">Saldo: {formatMoney(d.saldo_pendiente)}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="card border border-sky-200 bg-sky-50">
                    <h4 className="card-header mb-2">Historico de deuda de puesto (por dia)</h4>
                    <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                      {historialDiarioLiquidacion.length === 0 && <p className="text-sm text-slate-500">Sin movimientos registrados.</p>}
                      {historialDiarioLiquidacion.map((h) => {
                        const porcentajePuestoActual = Math.max(Number(porcentajePuestoPorEstilista[estId] || 0), 0);
                        const baseDiaHist = Math.max(Number(generadoPorFecha[String(h.fecha || '')] || 0), 0);
                        const cobroPuestoDia = modoCobroPuestoPorEstilista[estId] === 'porcentaje'
                          ? Math.max(Math.round((baseDiaHist * porcentajePuestoActual) / 100), 0)
                          : Math.max(Number(h.descuento_dia || 0), 0);
                        const abonadoPuestoDia = Math.max(Number(h.abono_aplicado_dia || 0), 0);
                        const saldoPuestoCierre = Math.max(Number(h.saldo_puesto_cierre || 0), 0);
                        const usaPuestoPorcentaje = modoCobroPuestoPorEstilista[estId] === 'porcentaje';
                        const saldoPuestoMostrado = usaPuestoPorcentaje
                          ? Math.max(cobroPuestoDia - abonadoPuestoDia, 0)
                          : saldoPuestoCierre;
                        const estadoPuesto = saldoPuestoCierre > 0 ? 'Debe' : 'Liquidado';
                        const pagoEmpleadoDia = Math.max(Number(h.pago_empleado_dia || 0), 0);
                        const pagoConsumoDia = Math.max(Number(pagoConsumoPorFecha[String(h.fecha || '')] || 0), 0);

                        return (
                          <div key={`hist-dia-${h.fecha}`} className="rounded-xl border border-sky-200 bg-white p-3">
                            <div className="flex justify-between gap-2 items-center">
                              <p className="text-sm font-semibold text-slate-900">{h.fecha || '-'}</p>
                              <div className="flex gap-1 items-center flex-wrap justify-end">
                                {h.skip_descuento_puesto && (
                                  <span className="text-xs font-semibold px-2 py-1 rounded-full border bg-purple-100 text-purple-700 border-purple-200">
                                    📌 Sin puesto
                                  </span>
                                )}
                                <span className={`text-xs font-semibold px-2 py-1 rounded-full border ${estadoPuesto === 'Debe' ? 'bg-rose-100 text-rose-700 border-rose-200' : 'bg-emerald-100 text-emerald-700 border-emerald-200'}`}>
                                  {estadoPuesto}
                                </span>
                              </div>
                            </div>
                            <p className="text-xs text-slate-500">{h.fecha_cambio || '-'}</p>
                            <p className="text-xs text-emerald-700 mt-1">Pago Empleado: {formatMoney(pagoEmpleadoDia)}</p>
                            <p className="text-xs text-slate-700 mt-1">Cobro puesto del día: {formatMoney(cobroPuestoDia)}</p>
                            <p className="text-xs text-sky-700">Cancelado de puesto: {formatMoney(abonadoPuestoDia)}</p>
                            <p className="text-xs text-amber-700">Saldo acumulado pendiente: {formatMoney(saldoPuestoMostrado)}</p>
                            <p className="text-xs text-slate-600">Medio abono: {h.medio_abono_puesto || 'efectivo'}</p>
                            <p className="text-xs text-violet-700">Pago consumo: {formatMoney(pagoConsumoDia)}</p>
                            <p className="text-xs text-violet-700">Valor acumulado pendiente: {formatMoney(consumoPendiente)}</p>
                            {h.notas && h.notas.includes('Carga manual') && (
                              <p className="text-xs text-blue-700 mt-1">📝 {h.notas}</p>
                            )}
                            <p className="text-xs text-slate-500">Usuario: {h.usuario_nombre || 'Sistema'}</p>
                            {puedeCorregirLiquidacion && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  className="btn-secondary !py-1 !px-2 text-xs"
                                  onClick={() => precargarCorreccionLiquidacion(empleado, h)}
                                >
                                  Cargar para corregir
                                </button>
                                <button
                                  type="button"
                                  className="btn-danger !py-1 !px-2 text-xs"
                                  onClick={() => eliminarRegistroHistorial({
                                    id: h.historial_id,
                                    estilista_nombre: empleado.estilista_nombre,
                                    fecha: h.fecha,
                                  })}
                                  disabled={!h.historial_id}
                                >
                                  Eliminar día
                                </button>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
                )}

                {!vistaSimpleLiquidacion && (
                <div className="card border border-violet-200 bg-violet-50">
                  <h4 className="card-header mb-2">Historial de abonos de consumo del empleado</h4>
                  <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                    {historialAbonosConsumo.length === 0 && <p className="text-sm text-slate-500">Sin abonos de consumo registrados.</p>}
                    {historialAbonosConsumo.map((a) => (
                      <div key={a.abono_id} className="rounded-xl border border-violet-200 bg-white p-3">
                        <div className="flex justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">{a.numero_factura || '-'}</p>
                          <p className="text-sm font-bold text-violet-700">{formatMoney(a.monto)}</p>
                        </div>
                        <p className="text-xs text-slate-500">{a.fecha_hora || '-'}</p>
                        <p className="text-xs text-slate-600 mt-1">Medio: {a.medio_pago || '-'}</p>
                        <p className="text-xs text-slate-600">{a.notas || 'Sin notas'}</p>
                      </div>
                    ))}
                  </div>
                </div>
                )}

              </>
            );
          })()}
        </section>
      </div>

      <NumericPad
        visible={!!numericPadTarget}
        value={getNumericPadValue()}
        onChange={setNumericPadValue}
        onClose={() => setNumericPadTarget(null)}
      />
    </div>
  );

  const renderModuloCartera = () => (
    <div className="space-y-6">
      <div className="card border border-amber-200 bg-amber-50">
        <h2 className="card-header">Cartera Empleado</h2>
        <p className="text-sm text-slate-600">Filtra por empleado, revisa facturas y controla saldos pendientes. Selecciona una fila para ver su histórico.</p>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
          <div className="rounded-xl border border-amber-200 bg-white p-3">
            <p className="text-xs text-slate-500">Facturas visibles</p>
            <p className="text-xl font-black text-slate-900">{resumenCarteraVisible.facturas}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-white p-3">
            <p className="text-xs text-slate-500">Total facturado</p>
            <p className="text-xl font-black text-slate-900">{formatMoney(resumenCarteraVisible.totalCargado)}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-white p-3">
            <p className="text-xs text-slate-500">Total abonado</p>
            <p className="text-xl font-black text-sky-700">{formatMoney(resumenCarteraVisible.totalAbonado)}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-white p-3">
            <p className="text-xs text-slate-500">Saldo pendiente</p>
            <p className="text-xl font-black text-rose-700">{formatMoney(resumenCarteraVisible.totalPendiente)}</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-white p-3">
            <p className="text-xs text-slate-500">Facturas con deuda</p>
            <p className="text-xl font-black text-rose-700">{resumenCarteraVisible.facturasPendientes}</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-slate-600 mb-1">Empleado</label>
            <select
              className="input-field !py-2 min-w-[240px]"
              value={filtroCarteraEstilistaId}
              onChange={(e) => setFiltroCarteraEstilistaId(e.target.value)}
            >
              <option value="todos">Todos los empleados</option>
              {opcionesEstilistaCartera.map((item) => (
                <option key={`cartera-est-${item.estilista_id}`} value={String(item.estilista_id)}>
                  {item.estilista_nombre}
                </option>
              ))}
            </select>
          </div>

          <label className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={mostrarFacturasSaldadas}
              onChange={(e) => setMostrarFacturasSaldadas(e.target.checked)}
            />
            Mostrar facturas saldadas
          </label>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Empleado</th>
                <th className="px-4 py-3 text-left">Estado</th>
                <th className="px-4 py-3 text-left">Fecha factura</th>
                <th className="px-4 py-3 text-left">Ultimo abono</th>
                <th className="px-4 py-3 text-left">Factura</th>
                <th className="px-4 py-3 text-left">Valor total</th>
                <th className="px-4 py-3 text-left">Valor abonado</th>
                <th className="px-4 py-3 text-left">Saldo pendiente</th>
                <th className="px-4 py-3 text-left">Total empleado</th>
                <th className="px-4 py-3 text-left">Abonar</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {deudasCarteraFiltradas.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={10}>No hay facturas para los filtros actuales.</td>
                </tr>
              )}
              {deudasCarteraFiltradas.map((deuda) => {
                const deudaId = Number(deuda.deuda_id);
                const resumenEmpleado = resumenPorEstilista[deuda.estilista_id] || {};
                const saving = !!savingAbonoByDeuda[deudaId];
                const ultimoAbono = (deuda.abonos || [])[0];
                const saldoFactura = Number(deuda.saldo_pendiente || 0);
                const estado = saldoFactura <= 0.5 ? 'cancelado' : Number(deuda.total_abonado || 0) > 0 ? 'parcial' : 'pendiente';
                const estadoClass = estado === 'cancelado'
                  ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                  : estado === 'parcial'
                  ? 'bg-amber-100 text-amber-700 border-amber-200'
                  : 'bg-rose-100 text-rose-700 border-rose-200';
                return (
                  <tr
                    key={deudaId}
                    className={`cursor-pointer ${Number(deudaActivaHistorial) === deudaId ? 'bg-amber-100' : 'hover:bg-slate-50'}`}
                    onClick={() => setDeudaActivaHistorial(deudaId)}
                  >
                    <td className="table-cell font-medium">{deuda.estilista_nombre || '-'}</td>
                    <td className="table-cell">
                      <span className={`inline-flex items-center rounded-full border px-2 py-1 text-xs font-semibold uppercase ${estadoClass}`}>
                        {estado}
                      </span>
                    </td>
                    <td className="table-cell">{(deuda.fecha_hora || '').slice(0, 10) || '-'}</td>
                    <td className="table-cell">{(ultimoAbono?.fecha_hora || '').slice(0, 10) || '-'}</td>
                    <td className="table-cell font-semibold">{deuda.numero_factura || '-'}</td>
                    <td className="table-cell">{formatMoney(deuda.total_cargo)}</td>
                    <td className="table-cell text-sky-700 font-semibold">{formatMoney(deuda.total_abonado)}</td>
                    <td className="table-cell text-rose-700 font-semibold">{formatMoney(saldoFactura)}</td>
                    <td className="table-cell">
                      <div className="text-xs text-slate-700">Saldo: <b>{formatMoney(resumenEmpleado.saldo_pendiente)}</b></div>
                      <div className="text-xs text-slate-500">Facturas: {resumenEmpleado.facturas || 0}</div>
                    </td>
                    <td className="table-cell" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        <select
                          className="input-field !py-2 !w-28"
                          value={medioAbonoPorDeuda[deudaId] || 'efectivo'}
                          onChange={(e) => setMedioAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        <input
                          type="number"
                          min="0"
                          step="100"
                          className="input-field !py-2 !w-28"
                          placeholder="Valor"
                          value={abonoPorDeuda[deudaId] || ''}
                          onChange={(e) => setAbonoPorDeuda((prev) => ({ ...prev, [deudaId]: e.target.value }))}
                        />
                        <button
                          className="btn-primary !px-3 !py-2"
                          onClick={() => abonarFacturaCartera(deuda)}
                          disabled={saving}
                        >
                          {saving ? 'Abonando...' : 'Abonar'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card border border-sky-200 bg-sky-50">
        <h2 className="card-header">Historico de abonos de la deuda seleccionada</h2>
        <p className="text-sm text-slate-600">
          {deudaSeleccionada
            ? `Factura ${deudaSeleccionada.numero_factura || '-'} - ${deudaSeleccionada.estilista_nombre || '-'}`
            : 'Selecciona una factura en la tabla superior para ver su histórico.'}
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="table-header">
              <tr>
                <th className="px-4 py-3 text-left">Fecha</th>
                <th className="px-4 py-3 text-left">Medio</th>
                <th className="px-4 py-3 text-left">Valor abonado</th>
                <th className="px-4 py-3 text-left">Editar datos del abono</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {!deudaSeleccionada && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={4}>Sin deuda seleccionada.</td>
                </tr>
              )}
              {deudaSeleccionada && (deudaSeleccionada.abonos || []).length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={4}>Esta factura no tiene abonos registrados.</td>
                </tr>
              )}
              {deudaSeleccionada && (deudaSeleccionada.abonos || []).map((abono) => {
                const abonoId = Number(abono.abono_id);
                const savingEdit = !!savingEditByAbono[abonoId];
                const editValue = editMontoByAbono[abonoId] ?? String(Number(abono.monto || 0));
                const editMedio = editMedioByAbono[abonoId] ?? (abono.medio_pago || 'efectivo');
                const editFecha = editFechaByAbono[abonoId] ?? String(abono.fecha_hora || '').slice(0, 10);
                const editNotas = editNotasByAbono[abonoId] ?? (abono.notas || '');
                return (
                  <tr key={abonoId}>
                    <td className="table-cell">{abono.fecha_hora || '-'}</td>
                    <td className="table-cell capitalize">{abono.medio_pago || '-'}</td>
                    <td className="table-cell text-sky-700 font-semibold">{formatMoney(abono.monto)}</td>
                    <td className="table-cell">
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          type="number"
                          min="0"
                          step="100"
                          className="input-field !py-2 !w-28"
                          value={editValue}
                          onChange={(e) => setEditMontoByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        />
                        <select
                          className="input-field !py-2 !w-28"
                          value={editMedio}
                          onChange={(e) => setEditMedioByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        >
                          {MEDIOS_PAGO_OPERACION.map((m) => (
                            <option key={m.value} value={m.value}>{m.label}</option>
                          ))}
                        </select>
                        <input
                          type="date"
                          className="input-field !py-2 !w-40"
                          value={editFecha}
                          onChange={(e) => setEditFechaByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        />
                        <input
                          type="text"
                          className="input-field !py-2 min-w-[220px]"
                          placeholder="Notas"
                          value={editNotas}
                          onChange={(e) => setEditNotasByAbono((prev) => ({ ...prev, [abonoId]: e.target.value }))}
                        />
                        <button
                          className="btn-secondary !px-3 !py-2"
                          onClick={() => editarAbonoCartera(abono, deudaSeleccionada)}
                          disabled={savingEdit}
                        >
                          {savingEdit ? 'Guardando...' : 'Guardar'}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  const renderModuloAjusteDiario = () => (
    <div className="space-y-6">
      {esRecepcion && (
        <div className="card border border-amber-200 bg-amber-50">
          <h3 className="card-header">Ajuste Diario Unificado</h3>
          <p className="text-sm text-slate-700">Este módulo está visible para consulta, pero la edición requiere rol administrador o gerente.</p>
        </div>
      )}
      <section className="rounded-3xl bg-gradient-to-br from-emerald-900 via-teal-800 to-slate-900 p-6 text-white shadow-2xl">
        <h2 className="text-2xl font-black tracking-tight">Ajuste Diario Unificado</h2>
        <p className="mt-2 text-sm text-emerald-100">
          Una sola tabla para ajustar por día y empleado: pagos al empleado, abono de puesto y cobro de consumo.
        </p>
      </section>

      <div className="card border border-emerald-200 bg-emerald-50">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3 mb-3">
          <div>
            <h3 className="card-header mb-0">Tabla diaria consolidada</h3>
            <p className="text-xs text-slate-600 mt-1">Filtra por empleado o fecha y visualiza cuántas filas tienen cambios sin guardar.</p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <input
              type="text"
              className="input-field !py-2 !w-56"
              placeholder="Buscar empleado o fecha..."
              value={filtroAjusteTexto}
              onChange={(e) => setFiltroAjusteTexto(e.target.value)}
            />
            <label className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={soloPendientesAjuste}
                onChange={(e) => setSoloPendientesAjuste(e.target.checked)}
              />
              Solo pendientes
            </label>
            <button
              type="button"
              className="btn-secondary"
              onClick={cargarAjusteDiarioUnificado}
              disabled={loadingAjusteDiario}
            >
              {loadingAjusteDiario ? 'Actualizando...' : 'Actualizar tabla'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3 mb-4">
          <div className="rounded-xl border border-emerald-200 bg-white p-3">
            <p className="text-xs text-slate-500">Filas visibles</p>
            <p className="text-xl font-black text-slate-900">{ajusteDiarioRowsFiltradas.length}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-3">
            <p className="text-xs text-slate-500">Generado (visible)</p>
            <p className="text-xl font-black text-slate-900">{formatMoney(resumenAjusteDiario.generado)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-3">
            <p className="text-xs text-slate-500">Consumo cobrado (visible)</p>
            <p className="text-xl font-black text-indigo-700">{formatMoney(resumenAjusteDiario.consumo)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-3">
            <p className="text-xs text-slate-500">Abono puesto (visible)</p>
            <p className="text-xl font-black text-emerald-700">{formatMoney(resumenAjusteDiario.abonoPuesto)}</p>
          </div>
          <div className="rounded-xl border border-emerald-200 bg-white p-3">
            <p className="text-xs text-slate-500">Filas modificadas</p>
            <p className="text-xl font-black text-amber-700">{resumenAjusteDiario.filasModificadas}</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-emerald-200">
            <thead className="bg-emerald-100 text-emerald-900 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2 text-left">Fecha</th>
                <th className="px-3 py-2 text-left">Empleado</th>
                <th className="px-3 py-2 text-left">Generado</th>
                <th className="px-3 py-2 text-left">Desc. puesto</th>
                <th className="px-3 py-2 text-left">Efectivo</th>
                <th className="px-3 py-2 text-left">Nequi</th>
                <th className="px-3 py-2 text-left">Daviplata</th>
                <th className="px-3 py-2 text-left">Otros</th>
                <th className="px-3 py-2 text-left">Abono puesto</th>
                <th className="px-3 py-2 text-left">Medio abono</th>
                <th className="px-3 py-2 text-left">Comisión ventas</th>
                <th className="px-3 py-2 text-left">Consumo día</th>
                <th className="px-3 py-2 text-left">Medio consumo</th>
                <th className="px-3 py-2 text-left">Pendiente</th>
                <th className="px-3 py-2 text-left">Acción</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-emerald-100">
              {!loadingAjusteDiario && ajusteDiarioRowsFiltradas.length === 0 && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={15}>No hay filas para el rango seleccionado.</td>
                </tr>
              )}
              {loadingAjusteDiario && (
                <tr>
                  <td className="table-cell text-slate-500" colSpan={15}>Cargando ajuste diario...</td>
                </tr>
              )}
              {ajusteDiarioRowsFiltradas.map((fila) => {
                const key = `${fila.estilista_id}|${fila.fecha}`;
                const edit = ajusteDiarioEditsByKey[key] || {};
                const aplicaComisionRow = Boolean(edit.aplica_comision_ventas ?? true);
                const totalPago =
                  toMontoNoNegativo(edit.pago_efectivo) +
                  toMontoNoNegativo(edit.pago_nequi) +
                  toMontoNoNegativo(edit.pago_daviplata) +
                  toMontoNoNegativo(edit.pago_otros);
                const generadoConComision = Number((fila.generado_total_con_comision ?? fila.generado_total) || 0);
                const generadoSinComision = Number((fila.generado_total_sin_comision ?? fila.generado_total) || 0);
                const generado = Math.max(aplicaComisionRow ? generadoConComision : generadoSinComision, 0);
                const pendientePreview = Math.max(generado - totalPago, 0);
                return (
                  <tr key={`ajuste-${key}`}>
                    <td className="table-cell font-semibold">{fila.fecha}</td>
                    <td className="table-cell">{fila.estilista_nombre}</td>
                    <td className="table-cell font-semibold text-slate-900">{formatMoney(generado)}</td>
                    <td className="table-cell text-amber-700">{formatMoney(fila.descuento_puesto)}</td>
                    <td className="table-cell"><input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.pago_efectivo || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'pago_efectivo', e.target.value)} /></td>
                    <td className="table-cell"><input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.pago_nequi || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'pago_nequi', e.target.value)} /></td>
                    <td className="table-cell"><input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.pago_daviplata || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'pago_daviplata', e.target.value)} /></td>
                    <td className="table-cell"><input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.pago_otros || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'pago_otros', e.target.value)} /></td>
                    <td className="table-cell"><input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.abono_puesto || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'abono_puesto', e.target.value)} /></td>
                    <td className="table-cell">
                      <select className="input-field !py-2 !w-28" value={edit.medio_abono_puesto || 'efectivo'} onChange={(e) => actualizarAjusteDiarioCampo(key, 'medio_abono_puesto', e.target.value)}>
                        {MEDIOS_PAGO_OPERACION.map((m) => (<option key={`aj-ab-${key}-${m.value}`} value={m.value}>{m.label}</option>))}
                      </select>
                    </td>
                    <td className="table-cell">
                      <select className="input-field !py-2 !w-44" value={Boolean(edit.aplica_comision_ventas ?? true) ? 'si' : 'no'} onChange={(e) => actualizarAjusteDiarioCampo(key, 'aplica_comision_ventas', e.target.value === 'si')}>
                        <option value="si">Sí aplica</option>
                        <option value="no">No aplica</option>
                      </select>
                    </td>
                    <td className="table-cell">
                      <input className="input-field !h-11 !py-2 !w-24 !font-semibold" value={edit.cobro_consumo_objetivo || ''} onChange={(e) => actualizarAjusteDiarioCampo(key, 'cobro_consumo_objetivo', e.target.value)} />
                      <p className="text-[11px] text-slate-500 mt-1">Actual: {formatMoney(fila.cobro_consumo_dia)}</p>
                    </td>
                    <td className="table-cell">
                      <select className="input-field !py-2 !w-28" value={edit.medio_cobro_consumo || 'efectivo'} onChange={(e) => actualizarAjusteDiarioCampo(key, 'medio_cobro_consumo', e.target.value)}>
                        {MEDIOS_PAGO_OPERACION.map((m) => (<option key={`aj-co-${key}-${m.value}`} value={m.value}>{m.label}</option>))}
                      </select>
                    </td>
                    <td className="table-cell font-semibold text-emerald-700">{formatMoney(pendientePreview)}</td>
                    <td className="table-cell">
                      <button
                        type="button"
                        className="btn-primary !py-2 !px-3"
                        onClick={() => guardarAjusteDiarioFila(fila)}
                        disabled={!!savingAjusteDiarioByKey[key]}
                      >
                        {savingAjusteDiarioByKey[key] ? 'Guardando...' : 'Guardar'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  const renderModuloAgotarse = () => (
    <div className="card">
      <h2 className="card-header">Productos por Agotarse</h2>
      <p className="text-sm text-slate-600">Listado de productos con stock igual o menor al minimo configurado. Puedes reabastecer desde aqui mismo.</p>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="table-header">
            <tr>
              <th className="px-4 py-3 text-left">Marca</th>
              <th className="px-4 py-3 text-left">Producto</th>
              <th className="px-4 py-3 text-left">Stock</th>
              <th className="px-4 py-3 text-left">Stock minimo</th>
              <th className="px-4 py-3 text-left">Precio venta</th>
              <th className="px-4 py-3 text-left">Reabastecer</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {(biData?.productos_bajo_stock || []).length === 0 && (
              <tr>
                <td className="table-cell text-slate-500" colSpan={6}>No hay productos en riesgo para el rango seleccionado.</td>
              </tr>
            )}
            {(biData?.productos_bajo_stock || []).map((item) => (
              <tr key={item.id}>
                <td className="table-cell">{item.marca || '-'}</td>
                <td className="table-cell font-medium">{item.nombre}</td>
                <td className="table-cell">{item.stock}</td>
                <td className="table-cell">{item.stock_minimo}</td>
                <td className="table-cell">{formatMoney(item.precio_venta)}</td>
                <td className="table-cell">
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min="1"
                      className="input-field w-24"
                      value={reabastecerByProductoId[item.id] ?? ''}
                      onChange={(e) => {
                        const val = e.target.value;
                        setReabastecerByProductoId((prev) => ({ ...prev, [item.id]: val }));
                      }}
                      placeholder="Cant."
                    />
                    <button
                      className="btn-primary whitespace-nowrap"
                      onClick={() => reabastecerProducto(item)}
                      disabled={!!savingStockByProductoId[item.id]}
                    >
                      {savingStockByProductoId[item.id] ? 'Guardando...' : 'Sumar stock'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="space-y-6 fade-in">
      <section className="relative overflow-hidden rounded-[30px] border border-slate-800 bg-[radial-gradient(circle_at_15%_20%,rgba(14,165,233,0.22),transparent_30%),radial-gradient(circle_at_85%_15%,rgba(16,185,129,0.22),transparent_34%),linear-gradient(120deg,#020617_0%,#0f172a_45%,#111827_100%)] p-7 text-white shadow-2xl">
        <div className="absolute -right-14 -top-14 h-44 w-44 rounded-full bg-white/5 blur-3xl" />
        <div className="absolute -left-12 bottom-0 h-40 w-40 rounded-full bg-cyan-300/10 blur-3xl" />
        <div className="relative z-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-3xl md:text-4xl font-black tracking-tight">Centro de Reportes</h1>
              <p className="text-slate-300 mt-2 max-w-3xl">Todo el control diario en un solo lugar: cierre, ajustes, liquidación y cartera con una interfaz más clara para operación real.</p>
            </div>
            <span className="inline-flex rounded-full bg-white/15 border border-white/30 px-3 py-1 text-xs font-semibold tracking-wide">UI {REPORTES_UI_VERSION}</span>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-white/25 bg-white/10 px-3 py-1">Rango: {fechaInicio} a {fechaFin}</span>
            <span className="rounded-full border border-white/25 bg-white/10 px-3 py-1">Medio: {MEDIOS_PAGO.find((m) => m.value === medioPago)?.label || 'Todos'}</span>
            <span className="rounded-full border border-emerald-200/40 bg-emerald-300/10 px-3 py-1">Vista activa: {(MODULOS.find((m) => m.key === moduloActivo)?.label || moduloActivo)}</span>
          </div>
        </div>
      </section>

      <div className="rounded-3xl border border-slate-200 bg-white/95 p-5 shadow-xl backdrop-blur-sm">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-2">
            <label className="block text-xs font-semibold tracking-wide text-slate-500 mb-1 uppercase">Periodo</label>
            <select className="input-field" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
              <option value="semana">Semana</option>
              <option value="mes">Mes</option>
              <option value="personalizado">Personalizado</option>
            </select>
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs font-semibold tracking-wide text-slate-500 mb-1 uppercase">Fecha inicio</label>
            <input type="date" className="input-field" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} />
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs font-semibold tracking-wide text-slate-500 mb-1 uppercase">Fecha fin</label>
            <input type="date" className="input-field" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} />
          </div>
          <div className="lg:col-span-2">
            <label className="block text-xs font-semibold tracking-wide text-slate-500 mb-1 uppercase">Medio de pago</label>
            <select className="input-field" value={medioPago} onChange={(e) => setMedioPago(e.target.value)}>
              {MEDIOS_PAGO.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="lg:col-span-4 flex flex-wrap items-end gap-2">
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('ayer')}>Ayer</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('hoy')}>Hoy</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('7dias')}>7 dias</button>
            <button className="btn-secondary" onClick={() => aplicarRangoRapido('mes')}>Mes</button>
            <button className="btn-primary" onClick={cargarTodo} disabled={loading}>{loading ? 'Consultando...' : 'Actualizar Datos'}</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
        {modulosVisibles.map((mod) => {
          const meta = MODULO_META[mod.key] || {};
          const activo = moduloActivo === mod.key;
          return (
            <button
              key={mod.key}
              className={`rounded-2xl border p-4 text-left transition-all duration-200 ${activo ? `${meta.border || 'border-slate-300'} bg-gradient-to-br ${meta.accent || 'from-slate-200 to-slate-100'} shadow-lg scale-[1.01]` : 'border-slate-200 bg-white hover:border-slate-300 hover:shadow-md'}`}
              onClick={() => setModuloActivo(mod.key)}
            >
              <p className={`text-sm font-black ${activo ? 'text-slate-900' : 'text-slate-800'}`}>{mod.label}</p>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">{meta.subtitle || 'Módulo operativo'}</p>
            </button>
          );
        })}
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-4 md:p-5 shadow-xl">
        {moduloActivo === 'cierre' && renderModuloCierreCaja()}
        {moduloActivo === 'ajuste' && renderModuloAjusteDiario()}
        {moduloActivo === 'liquidacion' && renderModuloLiquidacion()}
        {moduloActivo === 'cartera' && renderModuloCartera()}
        {moduloActivo === 'agotarse' && renderModuloAgotarse()}
      </div>
    </div>
  );
};

export default Reportes;
