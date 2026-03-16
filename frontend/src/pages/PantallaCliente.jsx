import { useEffect, useMemo, useState } from 'react';
import { FiClock, FiCreditCard, FiUser } from 'react-icons/fi';
import { customerDisplayService } from '../services/customerDisplayService';

const BUSINESS_NAME = import.meta.env.VITE_TICKET_BUSINESS_NAME || 'CORTE Y ESTILO';

const pad = (n) => String(n).padStart(2, '0');

const formatClock = (date) => `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

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

const money = (value) => `$${Number(value || 0).toFixed(2)}`;

const PantallaCliente = () => {
  const [clock, setClock] = useState(formatClock(new Date()));
  const [data, setData] = useState(() => customerDisplayService.getCurrent());

  useEffect(() => {
    const timer = setInterval(() => setClock(formatClock(new Date())), 1000);
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

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6 md:p-10">
      <div className="mx-auto max-w-5xl">
        <header className="rounded-3xl bg-gradient-to-r from-cyan-700 via-sky-700 to-blue-700 px-6 py-5 shadow-2xl">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-3xl md:text-4xl font-black tracking-wide">{BUSINESS_NAME}</h1>
              <p className="text-cyan-100 text-lg">Pantalla de atencion al cliente</p>
            </div>
            <div className="rounded-2xl bg-white/15 px-4 py-3 text-right">
              <div className="text-4xl font-extrabold tabular-nums">{clock}</div>
              <div className="text-cyan-100">Gracias por visitarnos</div>
            </div>
          </div>
        </header>

        <section className="mt-6 rounded-3xl bg-white/10 backdrop-blur-md border border-white/20 p-6 md:p-8 shadow-xl">
          {!data && (
            <div className="min-h-[320px] flex flex-col items-center justify-center text-center">
              <FiClock className="text-6xl text-cyan-300 mb-4" />
              <h2 className="text-3xl font-bold">Listos para atenderte</h2>
              <p className="text-cyan-100 mt-2 text-lg">Tu resumen de compra aparecera aqui al finalizar.</p>
            </div>
          )}

          {data && (
            <div className="space-y-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-3xl font-extrabold">{data.title || 'Resumen'}</h2>
                  <p className="text-cyan-100 text-lg">{data.subtitle || ''}</p>
                </div>
                <div className="text-left md:text-right text-cyan-100">
                  <p>Factura: #{data.id || '-'}</p>
                  <p>{formatDateTime(data.createdAt)}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="rounded-2xl bg-slate-950/40 border border-white/20 px-4 py-3">
                  <div className="flex items-center gap-2 text-cyan-200"><FiUser /> Cliente</div>
                  <p className="text-2xl font-bold mt-1">{data.customerName || 'Cliente'}</p>
                </div>
                <div className="rounded-2xl bg-slate-950/40 border border-white/20 px-4 py-3">
                  <div className="flex items-center gap-2 text-cyan-200"><FiUser /> Atendido por</div>
                  <p className="text-2xl font-bold mt-1">{data.employeeName || 'Equipo'}</p>
                </div>
                <div className="rounded-2xl bg-slate-950/40 border border-white/20 px-4 py-3">
                  <div className="flex items-center gap-2 text-cyan-200"><FiCreditCard /> Pago</div>
                  <p className="text-2xl font-bold mt-1">{paymentLabel(data.paymentMethod)}</p>
                </div>
              </div>

              <div className="rounded-2xl overflow-hidden border border-white/20">
                <table className="w-full text-lg">
                  <thead className="bg-cyan-900/60 text-cyan-100">
                    <tr>
                      <th className="px-4 py-3 text-left">Detalle</th>
                      <th className="px-4 py-3 text-center">Cant.</th>
                      <th className="px-4 py-3 text-right">Vlr unit.</th>
                      <th className="px-4 py-3 text-right">Subtotal</th>
                    </tr>
                  </thead>
                  <tbody className="bg-slate-950/25">
                    {totalLines.map((line, index) => (
                      <tr key={`${line.name}-${index}`} className="border-t border-white/10">
                        <td className="px-4 py-3 font-medium">{line.name}</td>
                        <td className="px-4 py-3 text-center">{line.qty}</td>
                        <td className="px-4 py-3 text-right">{money(line.unitPrice)}</td>
                        <td className="px-4 py-3 text-right">{money(line.lineTotal)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded-2xl bg-emerald-500/20 border border-emerald-300/40 p-5 flex items-center justify-between">
                <p className="text-2xl md:text-3xl font-semibold">Total pagado</p>
                <p className="text-4xl md:text-5xl font-black text-emerald-200">{money(data.total)}</p>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default PantallaCliente;
