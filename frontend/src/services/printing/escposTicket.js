const ESC = '\x1B';
const GS = '\x1D';

const CMD = {
  INIT: `${ESC}@`,
  ALIGN_LEFT: `${ESC}a\x00`,
  ALIGN_CENTER: `${ESC}a\x01`,
  BOLD_ON: `${ESC}E\x01`,
  BOLD_OFF: `${ESC}E\x00`,
  DOUBLE_ON: `${GS}!\x11`,
  DOUBLE_OFF: `${GS}!\x00`,
  CUT: `${GS}V\x41\x10`,
};

const DEFAULT_PAPER_WIDTH = 42;

const PAYMENT_LABELS = {
  nequi: 'Nequi',
  daviplata: 'Daviplata',
  efectivo: 'Efectivo',
  otros: 'Otros',
};

const truncate = (value, maxLength) => {
  const text = String(value || '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3))}...`;
};

const money = (amount) => {
  const n = Number(amount || 0);
  return `$${n.toFixed(2)}`;
};

const formatDate = (value) => {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return String(value || '');
  return date.toLocaleString('es-CO', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const centerLine = (text, width) => {
  const line = String(text || '');
  if (line.length >= width) return `${line}\n`;
  const spaces = Math.floor((width - line.length) / 2);
  return `${' '.repeat(Math.max(0, spaces))}${line}\n`;
};

const line = (label, value, width) => {
  const left = String(label || '').trim();
  const right = String(value || '').trim();
  const gap = Math.max(1, width - left.length - right.length);
  return `${truncate(left, width - right.length - 1)}${' '.repeat(gap)}${right}\n`;
};

const divider = (width) => `${'-'.repeat(width)}\n`;

export const medioPagoLabel = (medioPago) => PAYMENT_LABELS[medioPago] || String(medioPago || '-');

export const buildEscPosTicket = (payload, options = {}) => {
  const width = Number(options.paperWidth || DEFAULT_PAPER_WIDTH);
  const businessName = payload.businessName || 'SALON DE BELLEZA';
  const ticketTitle = payload.ticketTitle || 'TICKET DE VENTA';
  const items = Array.isArray(payload.items) ? payload.items : [];

  let output = '';
  output += CMD.INIT;
  output += CMD.ALIGN_CENTER;
  output += CMD.BOLD_ON;
  output += centerLine(truncate(businessName, width), width);
  output += CMD.BOLD_OFF;
  output += centerLine(ticketTitle, width);
  output += divider(width);

  output += CMD.ALIGN_LEFT;
  output += `Fecha: ${formatDate(payload.fecha_hora)}\n`;
  output += `Factura: ${payload.numero_factura || '-'}\n`;
  output += `Cliente: ${payload.cliente_nombre || 'Consumidor final'}\n`;
  output += `Empleado: ${payload.empleado_nombre || '-'}\n`;
  output += `Cajero: ${payload.usuario_nombre || '-'}\n`;
  output += `Pago: ${medioPagoLabel(payload.medio_pago)}\n`;
  output += divider(width);

  output += 'Item\n';
  output += line('Cant x Unit', 'Total', width);
  output += divider(width);

  items.forEach((item) => {
    const qty = Number(item.cantidad || 1);
    const unit = Number(item.precio_unitario || 0);
    const total = Number(item.total || qty * unit);

    output += `${truncate(item.nombre || 'Producto/Servicio', width)}\n`;
    output += line(`${qty} x ${money(unit)}`, money(total), width);
  });

  output += divider(width);
  output += CMD.BOLD_ON;
  output += line('TOTAL', money(payload.total), width);
  output += CMD.BOLD_OFF;

  if (payload.footerLines?.length) {
    output += divider(width);
    output += CMD.ALIGN_CENTER;
    payload.footerLines.forEach((text) => {
      output += centerLine(truncate(text, width), width);
    });
    output += CMD.ALIGN_LEFT;
  }

  output += '\n\n';
  output += CMD.CUT;
  return output;
};

export const buildProductSaleTicketPayload = (sale) => ({
  ticketTitle: 'VENTA PRODUCTO',
  numero_factura: sale?.numero_factura || sale?.id || '-',
  fecha_hora: sale?.fecha_hora,
  cliente_nombre: sale?.cliente_nombre,
  empleado_nombre: sale?.estilista_nombre,
  usuario_nombre: sale?.usuario_nombre,
  medio_pago: sale?.medio_pago,
  total: Number(sale?.total || 0),
  items: [
    {
      nombre: sale?.producto_nombre || 'Producto',
      cantidad: Number(sale?.cantidad || 1),
      precio_unitario: Number(sale?.precio_unitario || sale?.total || 0),
      total: Number(sale?.total || 0),
    },
  ],
});

export const buildServiceSaleTicketPayload = (service) => {
  const total = Number(service?.precio_cobrado || 0);
  return {
    ticketTitle: 'VENTA SERVICIO',
    numero_factura: service?.numero_factura || service?.id || '-',
    fecha_hora: service?.fecha_hora,
    cliente_nombre: service?.cliente_nombre,
    empleado_nombre: service?.estilista_nombre,
    usuario_nombre: service?.usuario_nombre,
    medio_pago: service?.medio_pago,
    total,
    items: [
      {
        nombre: service?.servicio_nombre || 'Servicio',
        cantidad: 1,
        precio_unitario: total,
        total,
      },
    ],
    footerLines: service?.notas ? [`Notas: ${service.notas}`] : undefined,
  };
};
