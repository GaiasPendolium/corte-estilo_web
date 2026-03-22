const DEFAULT_URL = (import.meta.env.VITE_LOCAL_DRAWER_URL || 'http://127.0.0.1:5000/abrir-cajon').trim();
const DEFAULT_TIMEOUT_MS = Number(import.meta.env.VITE_LOCAL_DRAWER_TIMEOUT_MS || 1500);

const withTimeout = async (url, timeoutMs) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: 'GET',
      mode: 'cors',
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timer);
  }
};

export const localDrawerService = {
  openDrawer: async () => {
    try {
      const response = await withTimeout(DEFAULT_URL, DEFAULT_TIMEOUT_MS);
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || 'No se pudo abrir el cajon por servicio local');
      }
      return true;
    } catch (error) {
      // No bloqueamos la venta/factura si el cajon no responde.
      console.warn('[localDrawerService] Fallo apertura de cajon:', error);
      return false;
    }
  },
};
