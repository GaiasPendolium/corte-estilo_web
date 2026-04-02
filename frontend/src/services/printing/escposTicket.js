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
  return `$${Math.round(n).toLocaleString('es-CO')}`;
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

    if (Array.isArray(item.infoLines) && item.infoLines.length) {
      item.infoLines.forEach((infoLine) => {
        output += `${truncate(`  ${String(infoLine || '')}`, width)}\n`;
      });
    }
  });

  if (Array.isArray(payload.summaryRows) && payload.summaryRows.length) {
    output += divider(width);
    payload.summaryRows.forEach((row) => {
      output += line(row?.label || '', row?.value || '', width);
    });
  }

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

export const buildProductSaleTicketPayload = (sale) => {
  const rows = Array.isArray(sale?.items) && sale.items.length > 0
    ? sale.items
    : [sale];

  const items = rows.map((item) => {
    const qty = Number(item?.cantidad || 1);
    const unit = Number(item?.precio_unitario || 0);
    const total = Number(item?.total || (qty * unit));
    return {
      nombre: item?.producto_nombre || item?.nombre || sale?.producto_nombre || 'Producto',
      cantidad: qty,
      precio_unitario: unit,
      total,
    };
  });

  const total = items.reduce((acc, item) => acc + Number(item.total || 0), 0);

  return {
    ticketTitle: 'VENTA PRODUCTO',
    numero_factura: sale?.numero_factura || sale?.id || '-',
    fecha_hora: sale?.fecha_hora,
    cliente_nombre: sale?.cliente_nombre,
    empleado_nombre: sale?.estilista_nombre,
    usuario_nombre: sale?.usuario_nombre,
    medio_pago: sale?.medio_pago,
    total: Number(sale?.total || total),
    items,
  };
};

export const buildServiceSaleTicketPayload = (service) => {
  const principalValor = Number(service?.neto_servicio ?? service?.precio_cobrado ?? 0);
  const principalEmpleado = Number(service?.monto_estilista || 0);
  const principalEstablecimiento = Number(service?.monto_establecimiento || 0);

  const items = [
    {
      nombre: `${service?.servicio_nombre || 'Servicio'} - ${service?.estilista_nombre || '-'}`,
      cantidad: 1,
      precio_unitario: principalValor,
      total: principalValor,
      infoLines: [
        `Ganancia empleado: ${money(principalEmpleado)}`,
        `Ganancia establecimiento: ${money(principalEstablecimiento)}`,
      ],
    },
  ];

  const adicionales = Array.isArray(service?.adicionales_asignados)
    ? service.adicionales_asignados
    : [];

  let adicionalesEmpleado = 0;
  let adicionalesEstablecimiento = 0;

  adicionales.forEach((item) => {
    const valor = Number(item?.valor || 0);
    if (valor <= 0) return;

    const aplicaPct = Boolean(item?.aplica_porcentaje_establecimiento);
    const pctEstablecimiento = Number(item?.porcentaje_establecimiento || 0);
    const pctNormalizado = Math.max(0, Math.min(100, pctEstablecimiento));
    const comisionEmpleado = aplicaPct
      ? valor * (1 - (pctNormalizado / 100))
      : valor;
    const valorEstablecimiento = valor - comisionEmpleado;
    adicionalesEmpleado += comisionEmpleado;
    adicionalesEstablecimiento += valorEstablecimiento;

    items.push({
      nombre: `${item?.servicio_nombre || 'Servicio adicional'} - ${item?.estilista_nombre || '-'}`,
      cantidad: 1,
      precio_unitario: valor,
      total: valor,
      infoLines: [
        `Ganancia empleado: ${money(comisionEmpleado)}`,
        `Ganancia establecimiento: ${money(valorEstablecimiento)}`,
      ],
    });
  });

  let productoAdicionalTotal = 0;
  let productoAdicionalEmpleado = 0;
  let productoAdicionalEstablecimiento = 0;

  if (service?.adicional_otro_producto) {
    const qtyProductoAd = Number(service?.adicional_otro_cantidad || 1);
    const totalProductoAd = Number(service?.adicional_otro_total || 0);
    const unitProductoAd = qtyProductoAd > 0 ? totalProductoAd / qtyProductoAd : totalProductoAd;
    const comisionProductoAd = Number(service?.adicional_otro_comision_estilista || 0);
    const estilistaComisionProducto = service?.adicional_otro_estilista_nombre || service?.estilista_nombre || '-';
    productoAdicionalTotal = totalProductoAd;
    productoAdicionalEmpleado = comisionProductoAd;
    productoAdicionalEstablecimiento = totalProductoAd - comisionProductoAd;

    items.push({
      nombre: `${service?.adicional_otro_producto_nombre || 'Producto adicional'} - ${estilistaComisionProducto}`,
      cantidad: qtyProductoAd,
      precio_unitario: unitProductoAd,
      total: totalProductoAd,
      infoLines: [
        `Ganancia empleado: ${money(comisionProductoAd)}`,
        `Ganancia establecimiento: ${money(productoAdicionalEstablecimiento)}`,
      ],
    });
  }

  const valorAdicionalesTotal = Number(service?.valor_adicionales || 0);
  const valorAdicionalesAsignados = adicionales.reduce((acc, ad) => acc + Number(ad?.valor || 0), 0);
  const adicionalNoDesglosado = Math.max(0, valorAdicionalesTotal - valorAdicionalesAsignados - productoAdicionalTotal);
  if (adicionalNoDesglosado > 0) {
    adicionalesEstablecimiento += adicionalNoDesglosado;
    items.push({
      nombre: `Adicional no desglosado - ${service?.estilista_nombre || '-'}`,
      cantidad: 1,
      precio_unitario: adicionalNoDesglosado,
      total: adicionalNoDesglosado,
      infoLines: [
        `Ganancia empleado: ${money(0)}`,
        `Ganancia establecimiento: ${money(adicionalNoDesglosado)}`,
      ],
    });
  }

  const totalServicio = principalValor + valorAdicionalesTotal;
  const totalEmpleado = principalEmpleado + adicionalesEmpleado + productoAdicionalEmpleado;
  const totalEstablecimiento = principalEstablecimiento + adicionalesEstablecimiento + productoAdicionalEstablecimiento;

  return {
    ticketTitle: 'SOPORTE SERVICIO',
    numero_factura: service?.numero_factura || service?.id || '-',
    fecha_hora: service?.fecha_hora,
    cliente_nombre: service?.cliente_nombre || 'Cliente no registrado',
    empleado_nombre: service?.estilista_nombre,
    usuario_nombre: service?.usuario_nombre,
    medio_pago: service?.medio_pago,
    total: totalServicio,
    items,
    summaryRows: [
      { label: 'Total servicio', value: money(totalServicio) },
      { label: 'Empleado', value: money(totalEmpleado) },
      { label: 'Establecimiento', value: money(totalEstablecimiento) },
    ],
    footerLines: ['Uso interno empleado', ...(service?.notas ? [`Notas: ${service.notas}`] : [])],
  };
};
