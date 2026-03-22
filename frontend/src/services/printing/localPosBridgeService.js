const BASE_URL = (import.meta.env.VITE_POS_BRIDGE_URL || 'http://127.0.0.1:8787').trim().replace(/\/$/, '');
const PRINTER_NAME = (import.meta.env.VITE_POS_BRIDGE_PRINTER || '').trim();
const TIMEOUT_MS = Number(import.meta.env.VITE_POS_BRIDGE_TIMEOUT_MS || 2500);

const requestJson = async (path, body) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(detail || `Bridge error ${response.status}`);
    }

    return response.json().catch(() => ({}));
  } finally {
    clearTimeout(timer);
  }
};

export const localPosBridgeService = {
  printTicket: async (text, printerName) => {
    if (!text) throw new Error('Ticket vacio');
    return requestJson('/print-ticket', {
      text,
      printer_name: (printerName || PRINTER_NAME || null),
    });
  },

  openDrawer: async (printerName) => {
    return requestJson('/open-drawer', {
      printer_name: (printerName || PRINTER_NAME || null),
    });
  },
};
