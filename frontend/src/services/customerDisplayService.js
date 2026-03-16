const CUSTOMER_DISPLAY_KEY = 'pos.customerDisplay.current';

const money = (value) => Number(value || 0).toFixed(2);

const emitUpdate = (payload) => {
  localStorage.setItem(CUSTOMER_DISPLAY_KEY, JSON.stringify(payload));
  window.dispatchEvent(new CustomEvent('customer-display-update', { detail: payload }));
};

const nowIso = () => new Date().toISOString();

export const customerDisplayService = {
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

  publishServiceSale: (serviceSale) => {
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
      createdAt: nowIso(),
    };

    emitUpdate(payload);
    return payload;
  },
};
