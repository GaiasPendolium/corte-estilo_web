import { useEffect, useMemo, useState } from 'react';
import { FiCheckCircle, FiClock, FiCreditCard, FiScissors, FiSmartphone, FiUser } from 'react-icons/fi';
import { customerDisplayService } from '../services/customerDisplayService';

const BUSINESS_NAME = import.meta.env.VITE_TICKET_BUSINESS_NAME || 'CORTE Y ESTILO';

// Posiciones fijas de las partículas de la pantalla de espera, para que el
// layout no "salte" entre renders (evitar Math.random en cada render).
const IDLE_SPARKLES = [
  { left: '12%', top: '18%', size: '4px', delay: '0s' },
  { left: '22%', top: '68%', size: '3px', delay: '0.8s' },
  { left: '38%', top: '30%', size: '5px', delay: '1.6s' },
  { left: '62%', top: '22%', size: '3px', delay: '0.4s' },
  { left: '78%', top: '62%', size: '4px', delay: '1.2s' },
  { left: '85%', top: '32%', size: '3px', delay: '2s' },
  { left: '50%', top: '78%', size: '4px', delay: '0.2s' },
  { left: '30%', top: '82%', size: '3px', delay: '1.4s' },
];

const pad = (n) => String(n).padStart(2, '0');

const formatClock = (date) => `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

const formatDateLong = (date) => date.toLocaleDateString('es-CO', {
  weekday: 'long',
  day: '2-digit',
  month: 'long',
});

const formatDateTime = (isoString) => {
  if (!isoString) return '--';
  const d = new Date(isoString);
  return d.toLocaleString('es-CO', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const paymentLabel = (raw) => {
  const value = String(raw || '').toLowerCase();
  if (value === 'efectivo') return 'Efectivo';
  if (value === 'nequi') return 'Nequi';
  if (value === 'daviplata') return 'Daviplata';
  if (value === 'otros') return 'Otros';
  return raw || 'Sin definir';
};

// Formato de pesos colombianos: sin decimales, con separador de miles
// (ej. $45.000), consistente con el resto de la app y los recibos impresos.
const money = (value) => `$${Math.round(Number(value || 0)).toLocaleString('es-CO')}`;

const PantallaCliente = () => {
  const [clock, setClock] = useState(formatClock(new Date()));
  const [now, setNow] = useState(new Date());
  const [data, setData] = useState(() => customerDisplayService.getCurrent());

  useEffect(() => {
    const timer = setInterval(() => {
      const d = new Date();
      setClock(formatClock(d));
      setNow(d);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key !== 'pos.customerDisplay.current') return;
      try {
        setData(e.newValue ? JSON.parse(e.newValue) : null);
      } catch (_error) {
        setData(null);
      }
    };

    const onCustom = (e) => {
      setData(e.detail || null);
    };

    window.addEventListener('storage', onStorage);
    window.addEventListener('customer-display-update', onCustom);

    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('customer-display-update', onCustom);
    };
  }, []);

  const totalLines = useMemo(() => {
    if (!Array.isArray(data?.lines)) return [];
    return data.lines;
  }, [data]);

  const tienePago = Boolean(data?.qrImageUrl || data?.datosTransferencia);
  const esPreview = data?.type === 'servicio_preview';

  // Encabezado (título/subtítulo/factura) y las 3 tarjetas de resumen
  // (cliente/atendido por/pago) se reutilizan en ambos layouts -- con QR
  // (mitad izquierda) y sin QR (ancho completo) -- para no duplicar el JSX.
  const renderEncabezadoResumen = () => (
    <div className="shrink-0 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
      <div>
        <h2 className="text-2xl md:text-3xl font-extrabold">{data.title || 'Resumen de tu visita'}</h2>
        <p className="text-cyan-100">{data.subtitle || ''}</p>
      </div>
      <div className="text-left md:text-right text-cyan-100 text-sm">
        <p>Factura: #{data.id || '-'}</p>
        <p>{formatDateTime(data.createdAt)}</p>
      </div>
    </div>
  );

  const renderTarjetasResumen = () => (
    <div className="shrink-0 grid grid-cols-3 gap-2">
      <div className="rounded-xl bg-slate-950/40 border border-white/20 px-3 py-2">
        <div className="flex items-center gap-1.5 text-cyan-200 text-xs"><FiUser /> Cliente</div>
        <p className="text-lg font-bold mt-0.5 truncate">{data.customerName || 'Cliente'}</p>
      </div>
      <div className="rounded-xl bg-slate-950/40 border border-white/20 px-3 py-2">
        <div className="flex items-center gap-1.5 text-cyan-200 text-xs"><FiUser /> Atendido por</div>
        <p className="text-lg font-bold mt-0.5 truncate">{data.employeeName || 'Equipo'}</p>
      </div>
      <div className="rounded-xl bg-slate-950/40 border border-white/20 px-3 py-2">
        <div className="flex items-center gap-1.5 text-cyan-200 text-xs"><FiCreditCard /> Pago</div>
        <p className="text-lg font-bold mt-0.5">{paymentLabel(data.paymentMethod)}</p>
      </div>
    </div>
  );

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-[radial-gradient(circle_at_15%_20%,rgba(14,165,233,0.28),transparent_32%),radial-gradient(circle_at_85%_15%,rgba(16,185,129,0.22),transparent_36%),radial-gradient(circle_at_50%_100%,rgba(168,85,247,0.18),transparent_40%),linear-gradient(140deg,#020617_0%,#0f172a_50%,#111827_100%)] text-white p-4 md:p-6 flex flex-col gap-4">
      <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-cyan-400/10 blur-3xl animate-pulse" />
      <div className="pointer-events-none absolute -left-16 bottom-0 h-64 w-64 rounded-full bg-emerald-400/10 blur-3xl animate-pulse" />

      <header className="relative z-10 shrink-0 rounded-2xl bg-white/10 backdrop-blur-md border border-white/15 px-5 py-3 shadow-2xl">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 p-2.5 shadow-lg">
              <FiScissors className="text-xl" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-black tracking-wide">{BUSINESS_NAME}</h1>
              <p className="text-cyan-200 text-xs md:text-sm capitalize">{formatDateLong(now)}</p>
            </div>
          </div>
          <div className="rounded-xl bg-white/10 border border-white/15 px-4 py-2 text-right">
            <div className="text-2xl md:text-3xl font-extrabold tabular-nums tracking-wide">{clock}</div>
          </div>
        </div>
      </header>

      <section className="relative z-10 flex-1 min-h-0 rounded-2xl bg-white/[0.07] backdrop-blur-md border border-white/15 p-4 md:p-6 shadow-xl flex flex-col">
        {!data && (
          <div className="idle-stage relative flex-1 flex flex-col items-center justify-center text-center overflow-hidden">
            <div className="idle-conic" />
            <div className="idle-orb idle-orb-a" />
            <div className="idle-orb idle-orb-b" />
            <div className="idle-orb idle-orb-c" />
            {IDLE_SPARKLES.map((s, i) => (
              <span
                key={i}
                className="idle-sparkle"
                style={{ left: s.left, top: s.top, width: s.size, height: s.size, animationDelay: s.delay }}
              />
            ))}

            <div className="idle-logo-wrap relative z-10">
              <img src="/corte_estilo_logo.png" alt={BUSINESS_NAME} className="idle-logo" />
              <span className="idle-shimmer" />
            </div>

            <h2 className="relative z-10 mt-6 text-3xl md:text-4xl font-black">Listos para atenderte</h2>
            <p className="relative z-10 text-cyan-100 mt-2 text-lg">Tu resumen de compra aparecerá aquí al finalizar.</p>

            <div className="relative z-10 mt-8 flex gap-2">
              <span className="idle-dot" style={{ animationDelay: '0s' }} />
              <span className="idle-dot" style={{ animationDelay: '0.2s' }} />
              <span className="idle-dot" style={{ animationDelay: '0.4s' }} />
            </div>
          </div>
        )}

        {data && (
          <div className="flex-1 min-h-0 flex flex-col gap-3">
            {tienePago ? (
              // Con QR: la pantalla se divide en mitades -- toda la
              // información a la izquierda, el QR ocupando el alto completo
              // a la derecha, lo más grande posible (la pantalla física del
              // cliente suele ser pequeña, así que cada centímetro cuenta).
              <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="min-h-0 flex flex-col gap-3">
                  {renderEncabezadoResumen()}
                  {renderTarjetasResumen()}
                  <div className={`shrink-0 rounded-2xl border p-4 ${esPreview ? 'bg-amber-500/15 border-amber-300/40' : 'bg-gradient-to-br from-emerald-500/20 to-cyan-500/10 border-emerald-300/30'}`}>
                    <p className={`flex items-center gap-1.5 text-xs uppercase tracking-widest font-bold ${esPreview ? 'text-amber-200' : 'text-emerald-200'}`}>
                      {esPreview && <FiClock className="animate-pulse" />}
                      {esPreview ? 'Total a pagar (por confirmar)' : 'Total a pagar'}
                    </p>
                    <p className={`mt-1 text-4xl md:text-5xl font-black tabular-nums ${esPreview ? 'text-amber-300' : 'text-emerald-300'}`}>{money(data.total)}</p>
                    <p className="mt-2 text-sm text-cyan-100">Por {paymentLabel(data.paymentMethod)}{data.nombreCobrador ? ` · a nombre de ${data.nombreCobrador}` : ''}</p>
                  </div>
                  <div className="flex-1 min-h-0 rounded-2xl bg-slate-950/40 border border-white/15 overflow-hidden flex flex-col">
                    <p className="shrink-0 px-4 py-2 text-xs font-bold uppercase tracking-widest text-cyan-200 bg-white/5 border-b border-white/10">Detalle de lo que estás pagando</p>
                    <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-white/10">
                      {totalLines.length === 0 && (
                        <p className="px-4 py-3 text-sm text-cyan-100/70">{data.subtitle || 'Servicio realizado'}</p>
                      )}
                      {totalLines.map((line, index) => (
                        <div key={`${line.name}-${index}`} className="px-4 py-2.5 flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <p className="font-semibold truncate">{line.name}</p>
                            {Number(line.qty) > 1 && <p className="text-xs text-cyan-200/70">Cant. {line.qty} · {money(line.unitPrice)} c/u</p>}
                          </div>
                          <p className="font-bold shrink-0">{money(line.lineTotal)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="min-h-0 rounded-2xl bg-white text-slate-900 shadow-2xl p-4 md:p-6 flex flex-col items-center">
                  <div className="shrink-0 flex items-center gap-2 rounded-full bg-amber-100 text-amber-800 px-4 py-1.5 text-sm font-bold animate-pulse">
                    <FiSmartphone /> Escanea para pagar
                  </div>
                  <div className="mt-3 flex-1 min-h-0 w-full flex items-center justify-center">
                    {data.qrImageUrl && (
                      <img
                        src={data.qrImageUrl}
                        alt={`QR ${paymentLabel(data.paymentMethod)}`}
                        className="h-full max-h-full w-auto max-w-full rounded-2xl object-contain ring-4 ring-slate-200"
                      />
                    )}
                  </div>
                  {data.datosTransferencia && (
                    <div className="shrink-0 mt-3 w-full rounded-xl bg-slate-100 p-3 text-center">
                      <p className="text-xs uppercase tracking-wide text-slate-500 font-bold">O transfiere a</p>
                      <p className="mt-1 whitespace-pre-line text-base md:text-lg font-bold text-slate-800">{data.datosTransferencia}</p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <>
                {renderEncabezadoResumen()}
                {renderTarjetasResumen()}
                <div className="flex-1 min-h-0 rounded-xl overflow-hidden border border-white/20 overflow-y-auto">
                  <table className="w-full text-base">
                    <thead className="bg-cyan-900/60 text-cyan-100 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left">Detalle</th>
                        <th className="px-3 py-2 text-center">Cant.</th>
                        <th className="px-3 py-2 text-right">Vlr unit.</th>
                        <th className="px-3 py-2 text-right">Subtotal</th>
                      </tr>
                    </thead>
                    <tbody className="bg-slate-950/25">
                      {totalLines.map((line, index) => (
                        <tr key={`${line.name}-${index}`} className="border-t border-white/10">
                          <td className="px-3 py-2 font-medium">{line.name}</td>
                          <td className="px-3 py-2 text-center">{line.qty}</td>
                          <td className="px-3 py-2 text-right">{money(line.unitPrice)}</td>
                          <td className="px-3 py-2 text-right">{money(line.lineTotal)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className={`shrink-0 rounded-xl border p-4 flex items-center justify-between ${esPreview ? 'bg-amber-500/15 border-amber-300/40' : 'bg-gradient-to-r from-emerald-500/20 to-emerald-500/5 border-emerald-300/40'}`}>
                  <p className="flex items-center gap-2 text-xl md:text-2xl font-semibold">
                    {esPreview ? <FiClock className="text-amber-300 animate-pulse" /> : <FiCheckCircle className="text-emerald-300" />}
                    {esPreview ? 'Total a pagar' : 'Total pagado'}
                  </p>
                  <p className={`text-3xl md:text-4xl font-black tabular-nums ${esPreview ? 'text-amber-200' : 'text-emerald-200'}`}>{money(data.total)}</p>
                </div>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
};

export default PantallaCliente;
