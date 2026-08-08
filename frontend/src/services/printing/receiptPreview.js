import { buildLiquidacionTicketPayload } from './escposTicket';

const money = (amount) => {
  const n = Number(amount || 0);
  return `$${Math.round(n).toLocaleString('es-CO')}`;
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}[ch]));

const buildHtml = (payload) => {
  const itemsHtml = (payload.items || []).map((item) => `
    <div class="item">
      <div class="item-row">
        <span>${escapeHtml(item.nombre)}</span>
        <span>${money(item.total)}</span>
      </div>
      ${(item.infoLines || []).map((l) => `<div class="item-info">${escapeHtml(l)}</div>`).join('')}
    </div>
  `).join('');

  const summaryHtml = (payload.summaryRows || []).map((row) => `
    <div class="summary-row">
      <span>${escapeHtml(row.label)}</span>
      <span>${escapeHtml(row.value)}</span>
    </div>
  `).join('');

  const footerHtml = (payload.footerLines || []).map((l, idx) => `
    <div class="footer-line ${idx === 0 ? 'footer-main' : 'footer-note'}">${escapeHtml(l)}</div>
  `).join('');

  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(payload.ticketTitle || 'Recibo')}</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #f1f5f9;
    margin: 0;
    padding: 24px;
    color: #0f172a;
  }
  .receipt {
    max-width: 380px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 20px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.15);
    padding: 24px;
  }
  .header { text-align: center; margin-bottom: 16px; }
  .header .title { font-size: 12px; font-weight: 800; letter-spacing: 0.15em; text-transform: uppercase; color: #64748b; }
  .header .name { font-size: 22px; font-weight: 900; margin-top: 4px; }
  .header .meta { font-size: 12px; color: #64748b; margin-top: 4px; }
  .divider { border-top: 1px dashed #cbd5e1; margin: 14px 0; }
  .item { margin-bottom: 8px; }
  .item-row { display: flex; justify-content: space-between; font-weight: 700; font-size: 14px; }
  .item-info { font-size: 11px; color: #64748b; }
  .summary-row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; }
  .footer-line { text-align: center; border-radius: 12px; padding: 10px; margin-top: 6px; font-weight: 800; }
  .footer-main { background: #f1f5f9; font-size: 18px; }
  .footer-note { background: #fef3c7; color: #92400e; font-size: 12px; }
  .actions { max-width: 380px; margin: 16px auto 0; text-align: center; }
  .actions button {
    background: #0f172a; color: #fff; border: none; border-radius: 10px;
    padding: 10px 18px; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  @media print {
    body { background: #fff; padding: 0; }
    .receipt { box-shadow: none; }
    .actions { display: none; }
  }
</style>
</head>
<body>
  <div class="receipt">
    <div class="header">
      <div class="title">${escapeHtml(payload.ticketTitle || 'Recibo')}</div>
      <div class="name">${escapeHtml(payload.empleado_nombre || '')}</div>
      <div class="meta">${escapeHtml(payload.numero_factura || '')} · ${escapeHtml(payload.fecha_hora || '')}</div>
    </div>
    <div class="divider"></div>
    ${itemsHtml || '<p style="text-align:center;color:#94a3b8;font-size:12px;">Sin servicios registrados este día.</p>'}
    <div class="divider"></div>
    ${summaryHtml}
    <div class="divider"></div>
    ${footerHtml}
  </div>
  <div class="actions">
    <button onclick="window.print()">Imprimir esta vista</button>
  </div>
</body>
</html>`;
};

export const openLiquidacionPreview = (recibo) => {
  const payload = buildLiquidacionTicketPayload(recibo);
  const html = buildHtml(payload);
  const popup = window.open('', 'previsualizar_liquidacion', 'width=460,height=760,scrollbars=yes');
  if (!popup) {
    throw new Error('El navegador bloqueó la ventana emergente. Habilita los popups para este sitio.');
  }
  popup.document.open();
  popup.document.write(html);
  popup.document.close();
  popup.focus();
};
