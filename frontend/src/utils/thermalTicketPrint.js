const TICKET_BUSINESS_NAME = (import.meta.env.VITE_TICKET_BUSINESS_NAME || 'CORTE Y ESTILO').trim();

const formatMoney = (value) => {
  const n = Number(value || 0);
  return `$${Math.round(n).toLocaleString('es-CO')}`;
};

const formatDate = (value) => {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value).replace('T', ' ').slice(0, 16);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const escapeHtml = (value) => String(value || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/\"/g, '&quot;')
  .replace(/'/g, '&#039;');

const renderSeparator = (heavy = false) => `<div class="sep ${heavy ? 'heavy' : ''}"></div>`;

const buildServiceItems = (data) => {
  const items = [];
  const principalValor = Number(data?.neto_servicio ?? data?.precio_cobrado ?? 0);

  items.push({
    servicio: data?.servicio_nombre || 'Servicio',
    estilista: data?.estilista_nombre || '-',
    valor: principalValor,
  });

  const adicionales = Array.isArray(data?.adicionales_asignados) ? data.adicionales_asignados : [];
  adicionales.forEach((ad) => {
    const valor = Number(ad?.valor || 0);
    if (valor <= 0) return;
    items.push({
      servicio: ad?.servicio_nombre || 'Servicio adicional',
      estilista: ad?.estilista_nombre || '-',
      valor,
    });
  });

  const totalServicio = Number(data?.precio_cobrado || 0) + Number(data?.valor_adicionales || 0);

  return {
    items,
    totalServicio,
    empleado: Number(data?.monto_estilista || 0),
    establecimiento: Number(data?.monto_establecimiento || 0),
  };
};

const buildProductItems = (data) => {
  const rows = Array.isArray(data?.items) && data.items.length > 0 ? data.items : [data];
  const items = rows.map((r) => ({
    servicio: r?.producto_nombre || r?.nombre || 'Producto',
    estilista: `x${Number(r?.cantidad || 1)}`,
    valor: Number(r?.total || (Number(r?.cantidad || 1) * Number(r?.precio_unitario || 0))),
  }));

  const total = items.reduce((acc, item) => acc + Number(item.valor || 0), 0);
  return {
    items,
    totalServicio: total,
    empleado: null,
    establecimiento: null,
  };
};

const buildTicketHtml = ({ type, data }) => {
  const isService = type === 'servicio';
  const factura = data?.numero_factura || data?.id || '-';
  const info = isService ? buildServiceItems(data) : buildProductItems(data);
  const logoSrc = `${window.location.origin}/corte_estilo_logo.png`;

  const detalleRows = info.items
    .map((item) => `
      <div class="item">
        <div class="name">${escapeHtml(item.servicio)}</div>
        <div class="subrow">
          <span>${escapeHtml(item.estilista)}</span>
          <span class="amount">${formatMoney(item.valor)}</span>
        </div>
      </div>
    `)
    .join('');

  const resumenExtra = isService
    ? `
      <div class="row"><span>Total servicio:</span><span>${formatMoney(info.totalServicio)}</span></div>
      <div class="row"><span>Empleado:</span><span>${formatMoney(info.empleado)}</span></div>
      <div class="row"><span>Establecimiento:</span><span>${formatMoney(info.establecimiento)}</span></div>
    `
    : `
      <div class="row"><span>Total productos:</span><span>${formatMoney(info.totalServicio)}</span></div>
    `;

  return `
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>Ticket ${escapeHtml(factura)}</title>
        <style>
          @page { size: 80mm auto; margin: 0; }
          html, body { margin: 0; padding: 0; background: #fff; color: #000; }
          body { font-family: "Courier New", Consolas, monospace; }
          .ticket {
            width: 72mm;
            margin: 0 auto;
            padding: 2mm 1.5mm 3mm;
            font-size: 11px;
            line-height: 1.35;
          }
          .center { text-align: center; }
          .logo {
            display: block;
            margin: 0 auto 1.5mm;
            height: 26mm;
            width: auto;
            max-width: 64mm;
            object-fit: contain;
          }
          .business {
            font-weight: 800;
            font-size: 14px;
            letter-spacing: .3px;
            margin-bottom: 1mm;
          }
          .meta { margin-bottom: 1mm; }
          .sep { border-top: 1px dashed #000; margin: 2.2mm 0; }
          .sep.heavy { border-top-style: solid; border-top-width: 2px; margin: 2.5mm 0; }
          .label { font-weight: 700; margin-bottom: .8mm; }
          .row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 2mm;
            margin: .4mm 0;
          }
          .item { margin-bottom: 1.8mm; }
          .name {
            font-weight: 700;
            white-space: normal;
            overflow-wrap: anywhere;
          }
          .subrow {
            display: flex;
            justify-content: space-between;
            gap: 2mm;
            margin-top: .3mm;
          }
          .amount { font-weight: 700; }
          .total {
            font-weight: 900;
            font-size: 14px;
            letter-spacing: .4px;
            text-transform: uppercase;
          }
          .footer {
            text-align: center;
            margin-top: 2mm;
            font-size: 11px;
          }
        </style>
      </head>
      <body>
        <section class="ticket">
          <div class="center">
            <img class="logo" src="${logoSrc}" alt="Logo" />
            <div class="business">${escapeHtml(TICKET_BUSINESS_NAME)}</div>
            <div class="meta">Factura: ${escapeHtml(factura)}</div>
            <div class="meta">Fecha: ${escapeHtml(formatDate(data?.fecha_hora))}</div>
            <div class="meta">Tipo: ${isService ? 'Servicio' : 'Producto'}</div>
          </div>

          ${renderSeparator()}

          <div><strong>Cliente:</strong> ${escapeHtml(data?.cliente_nombre || 'Cliente no registrado')}</div>
          <div><strong>Atendido por:</strong> ${escapeHtml(data?.estilista_nombre || data?.empleado_nombre || '-')}</div>

          ${renderSeparator()}

          <div class="label">Detalle</div>
          ${detalleRows}

          ${renderSeparator()}

          ${resumenExtra}

          ${renderSeparator(true)}

          <div class="row total">
            <span>TOTAL:</span>
            <span>${formatMoney(info.totalServicio)}</span>
          </div>

          ${renderSeparator()}

          <div><strong>Medio de pago:</strong> ${escapeHtml(String(data?.medio_pago || '-').toUpperCase())}</div>

          <div class="footer">Gracias por su visita</div>
        </section>
      </body>
    </html>
  `;
};

export const printThermalTicket = ({ type, data }) => {
  const html = buildTicketHtml({ type, data });
  const printWin = window.open('', '_blank', 'noopener,noreferrer,width=360,height=900');
  if (!printWin) {
    throw new Error('El navegador bloqueó la ventana de impresión. Habilita ventanas emergentes.');
  }

  printWin.document.open();
  printWin.document.write(html);
  printWin.document.close();
  printWin.focus();
  setTimeout(() => {
    printWin.print();
  }, 250);
};
