const CUSTOMER_DISPLAY_KEY = 'pos.customerDisplay.current';
const CUSTOMER_DISPLAY_WINDOW_NAME = 'pantalla_cliente';

const money = (value) => Number(value || 0).toFixed(2);

const emitUpdate = (payload) => {
  localStorage.setItem(CUSTOMER_DISPLAY_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent('customer-display-update', { detail: payload }));
};

const nowIso = () => new Date().toISOString();

export const customerDisplayService = {
  // Abre (o reutiliza si ya está abierta, por el nombre de ventana) la
  // pantalla cliente, intentando ubicarla en el segundo monitor: parte del
  // ancho total de pantallas (window.screen.availWidth ya incluye todos los
  // monitores en la mayoría de navegadores con monitores extendidos) a la
  // derecha del monitor principal. Si el POS solo tiene un monitor, esto no
  // hace daño -- simplemente abre en el mismo monitor.
  abrirVentana: () => {
    try {
      const anchoMonitorPrincipal = window.screen.width || 1280;
      const altoMonitorPrincipal = window.screen.height || 800;
      const features = `noopener,noreferrer,left=${anchoMonitorPrincipal},top=0,width=${anchoMonitorPrincipal},height=${altoMonitorPrincipal}`;
      return window.open('/pantalla-cliente', CUSTOMER_DISPLAY_WINDOW_NAME, features);
    } catch (_error) {
      return null;
    }
  },

  getCurrent: () => {
    try {
      const raw = localStorage.getItem(CUSTOMER_DISPLAY_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (_error) {
      return null;
    }
  },

  clear: () => {
    localStorage.removeItem(CUSTOMER_DISPLAY_KEY);
    window.dispatchEvent(new CustomEvent('customer-display-update', { detail: null }));
  },

  publishProductSale: (sale) => {
    const payload = {
      id: sale?.id || null,
      type: 'venta_producto',
      title: 'Gracias por tu compra',
      subtitle: 'Tu factura ha sido registrada',
      customerName: sale?.cliente_nombre || 'Cliente',
      employeeName: sale?.estilista_nombre || 'Equipo Corte y Estilo',
      paymentMethod: sale?.medio_pago || 'efectivo',
      total: money(sale?.valor_total),
      lines: [
        {
          name: sale?.producto_nombre || 'Producto',
          qty: Number(sale?.cantidad || 1),
          unitPrice: money(sale?.precio_unitario),
          lineTotal: money(Number(sale?.cantidad || 1) * Number(sale?.precio_unitario || 0)),
        },
      ],
      createdAt: nowIso(),
    };

    emitUpdate(payload);
    return payload;
  },

  // Fase 1 del cobro: se muestra apenas el cajero abre la confirmación de
  // cobro, ANTES de guardar nada en el backend y ANTES de saber si hay QR
  // (eso llega despues, con publishServiceSale). Deja ver al cliente que su
  // servicio ya se está registrando, mientras el cajero confirma el monto.
  publishServicePreview: ({ servicioNombre, estilistaNombre, clienteNombre, total, medioPago }) => {
    const payload = {
      id: null,
      type: 'servicio_preview',
      title: 'Registrando tu servicio',
      subtitle: 'Un momento, estamos preparando tu cuenta...',
      customerName: clienteNombre || 'Cliente',
      employeeName: estilistaNombre || 'Equipo Corte y Estilo',
      paymentMethod: medioPago || 'efectivo',
      total: money(total),
      lines: [
        {
          name: servicioNombre || 'Servicio',
          qty: 1,
          unitPrice: money(total),
          lineTotal: money(total),
        },
      ],
      createdAt: nowIso(),
    };

    emitUpdate(payload);
    return payload;
  },

  // `datosPagoElectronico` (opcional): { qrImageUrl, datosTransferencia, nombreCobrador }
  // del empleado que realmente recibe el pago electrónico -- puede ser el
  // mismo que atendió o un compañero (ver campo cobrado_por), para servicios
  // cobrados en conjunto en una sola visita.
  publishServiceSale: (serviceSale, datosPagoElectronico = null) => {
    const esElectronico = (serviceSale?.medio_pago || 'efectivo') !== 'efectivo';
    const payload = {
      id: serviceSale?.id || null,
      type: 'servicio',
      title: 'Servicio finalizado',
      subtitle: 'Gracias por preferirnos',
      customerName: serviceSale?.cliente_nombre || 'Cliente',
      employeeName: serviceSale?.estilista_nombre || 'Equipo Corte y Estilo',
      paymentMethod: serviceSale?.medio_pago || 'efectivo',
      total: money(serviceSale?.precio_cobrado),
      lines: [
        {
          name: serviceSale?.servicio_nombre || 'Servicio',
          qty: 1,
          unitPrice: money(serviceSale?.precio_cobrado),
          lineTotal: money(serviceSale?.precio_cobrado),
        },
      ],
      qrImageUrl: esElectronico ? (datosPagoElectronico?.qrImageUrl || null) : null,
      datosTransferencia: esElectronico ? (datosPagoElectronico?.datosTransferencia || null) : null,
      nombreCobrador: esElectronico ? (datosPagoElectronico?.nombreCobrador || null) : null,
      createdAt: nowIso(),
    };

    emitUpdate(payload);
    return payload;
  },
};
