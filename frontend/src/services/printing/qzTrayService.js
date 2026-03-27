import qz from 'qz-tray';

const PRINTER_STORAGE_KEY = 'pos.selectedPrinter';
const DRAWER_CONFIG_STORAGE_KEY = 'pos.drawerConfig';

const DEFAULT_DRAWER_PIN = Number(import.meta.env.VITE_QZ_DRAWER_PIN || 0);
const DEFAULT_DRAWER_ON_MS = Number(import.meta.env.VITE_QZ_DRAWER_ON_MS || 25);
const DEFAULT_DRAWER_OFF_MS = Number(import.meta.env.VITE_QZ_DRAWER_OFF_MS || 250);

const DEFAULT_WS_HOST = (import.meta.env.VITE_QZ_WS_HOST || 'localhost').trim();
const DEFAULT_WS_PORT_SECURE = Number(import.meta.env.VITE_QZ_WS_PORT_SECURE || 8181);
const DEFAULT_WS_PORT_INSECURE = Number(import.meta.env.VITE_QZ_WS_PORT_INSECURE || 8282);

const DEFAULT_PRINTER_NAME = (import.meta.env.VITE_QZ_DEFAULT_PRINTER || '').trim();
const QZ_CERT_PEM = (import.meta.env.VITE_QZ_CERT_PEM || '').trim();
const API_URL = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');
const QZ_SIGN_ENDPOINT = (
  import.meta.env.VITE_QZ_SIGN_ENDPOINT
  || (API_URL ? `${API_URL}/qz` : '')
).trim().replace(/\/$/, '');

let securityConfigured = false;

const toByte = (value, fallback = 0) => {
  const n = Number(value);
  if (Number.isNaN(n)) return fallback;
  return Math.max(0, Math.min(255, Math.trunc(n)));
};

// Construye bytes exactos ESC p pin t1 t2 y los codifica en base64
// para evitar que el texto plano corrompa el byte \x00 del pin y otros binarios.
const buildDrawerBase64 = ({ pin, onMs, offMs }) => {
  const p = toByte(pin, DEFAULT_DRAWER_PIN);
  const t1 = toByte(onMs, DEFAULT_DRAWER_ON_MS);
  const t2 = toByte(offMs, DEFAULT_DRAWER_OFF_MS);
  // ESC(0x1B) p(0x70) pin t1 t2
  const bytes = [0x1B, 0x70, p, t1, t2];
  return btoa(bytes.map((b) => String.fromCharCode(b)).join(''));
};

const normalizeError = (error, fallbackMessage) => {
  const message = String(error?.message || error || '').toLowerCase();

  if (message.includes('unable to establish connection') || message.includes('websocket')) {
    return 'No se pudo conectar con QZ Tray. Verifica que este ejecutandose en Windows.';
  }
  if (message.includes('not found') || message.includes('printer')) {
    return 'No se encontro la impresora seleccionada. Revisa el nombre configurado.';
  }

  return fallbackMessage || 'No se pudo completar la operacion de impresion';
};

const configureSecurity = () => {
  if (securityConfigured) return;

  if (!QZ_CERT_PEM && !QZ_SIGN_ENDPOINT) {
    throw new Error('Falta configurar firma QZ: define VITE_QZ_SIGN_ENDPOINT (o VITE_API_URL) en frontend.');
  }

  qz.security.setCertificatePromise((resolve, reject) => {
    if (QZ_CERT_PEM) {
      resolve(QZ_CERT_PEM);
      return;
    }

    if (!QZ_SIGN_ENDPOINT) {
      resolve();
      return;
    }

    fetch(`${QZ_SIGN_ENDPOINT}/certificate`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('No se pudo obtener certificado de firma de QZ');
        return response.text();
      })
      .then(resolve)
      .catch(reject);
  });

  qz.security.setSignatureAlgorithm('SHA256');
  qz.security.setSignaturePromise((toSign) => (resolve, reject) => {
    if (!QZ_SIGN_ENDPOINT) {
      resolve();
      return;
    }

    fetch(`${QZ_SIGN_ENDPOINT}/sign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ toSign }),
    })
      .then((response) => {
        if (!response.ok) throw new Error('No se pudo firmar la solicitud para QZ Tray');
        return response.text();
      })
      .then(resolve)
      .catch(reject);
  });

  securityConfigured = true;
};

const connectIfNeeded = async () => {
  configureSecurity();

  if (qz.websocket.isActive()) {
    return;
  }

  await qz.websocket.connect({
    host: DEFAULT_WS_HOST,
    usingSecure: true,
    port: {
      secure: [DEFAULT_WS_PORT_SECURE],
      insecure: [DEFAULT_WS_PORT_INSECURE],
    },
  });
};

const getStoredPrinter = () => localStorage.getItem(PRINTER_STORAGE_KEY) || '';

const setStoredPrinter = (printerName) => {
  if (!printerName) {
    localStorage.removeItem(PRINTER_STORAGE_KEY);
    return;
  }
  localStorage.setItem(PRINTER_STORAGE_KEY, printerName);
};

const getStoredDrawerConfig = () => {
  try {
    const raw = localStorage.getItem(DRAWER_CONFIG_STORAGE_KEY);
    if (!raw) {
      return {
        pin: DEFAULT_DRAWER_PIN,
        onMs: DEFAULT_DRAWER_ON_MS,
        offMs: DEFAULT_DRAWER_OFF_MS,
      };
    }
    const parsed = JSON.parse(raw);
    return {
      pin: toByte(parsed?.pin, DEFAULT_DRAWER_PIN),
      onMs: toByte(parsed?.onMs, DEFAULT_DRAWER_ON_MS),
      offMs: toByte(parsed?.offMs, DEFAULT_DRAWER_OFF_MS),
    };
  } catch (_error) {
    return {
      pin: DEFAULT_DRAWER_PIN,
      onMs: DEFAULT_DRAWER_ON_MS,
      offMs: DEFAULT_DRAWER_OFF_MS,
    };
  }
};

const setStoredDrawerConfig = (drawerConfig) => {
  const normalized = {
    pin: toByte(drawerConfig?.pin, DEFAULT_DRAWER_PIN),
    onMs: toByte(drawerConfig?.onMs, DEFAULT_DRAWER_ON_MS),
    offMs: toByte(drawerConfig?.offMs, DEFAULT_DRAWER_OFF_MS),
  };
  localStorage.setItem(DRAWER_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  return normalized;
};

const resolvePrinterName = async (preferredName) => {
  const printers = await qz.printers.find();
  const requestedName = (preferredName || getStoredPrinter() || DEFAULT_PRINTER_NAME || '').trim();

  if (!requestedName) {
    return printers[0] || null;
  }

  const exact = printers.find((p) => p === requestedName);
  if (exact) return exact;

  const contains = printers.find((p) => p.toLowerCase().includes(requestedName.toLowerCase()));
  return contains || null;
};

// Imprime texto ESC/POS (ticket). Permite adjuntar datos extra en formato base64
// (ej: comando de cajón) en el mismo trabajo para evitar que la impresora
// ignore el comando cuando llega en un trabajo separado.
const printRaw = async (rawData, printerName, extraBase64Items = []) => {
  try {
    await connectIfNeeded();
    const resolvedPrinter = await resolvePrinterName(printerName);

    if (!resolvedPrinter) {
      throw new Error('No printer found');
    }

    const config = qz.configs.create(resolvedPrinter, {
      copies: 1,
      encoding: 'CP437',
    });

    const dataItems = [
      { type: 'raw', format: 'plain', data: rawData },
      ...extraBase64Items.map((b64) => ({ type: 'raw', format: 'base64', data: b64 })),
    ];

    await qz.print(config, dataItems);
    return { printer: resolvedPrinter };
  } catch (error) {
    throw new Error(normalizeError(error));
  }
};

// Abre cajón solo, usando base64 para preservar bytes binarios exactos.
const openDrawerRaw = async (printerName, drawerBase64) => {
  try {
    await connectIfNeeded();
    const resolvedPrinter = await resolvePrinterName(printerName);

    if (!resolvedPrinter) {
      throw new Error('No printer found');
    }

    const config = qz.configs.create(resolvedPrinter, { copies: 1 });
    await qz.print(config, [{ type: 'raw', format: 'base64', data: drawerBase64 }]);
    return { printer: resolvedPrinter };
  } catch (error) {
    throw new Error(normalizeError(error));
  }
};

export const qzTrayService = {
  isConnected: () => qz.websocket.isActive(),

  getSelectedPrinter: () => getStoredPrinter(),

  setSelectedPrinter: (printerName) => {
    setStoredPrinter((printerName || '').trim());
  },

  getDrawerConfig: () => getStoredDrawerConfig(),

  setDrawerConfig: (drawerConfig) => setStoredDrawerConfig(drawerConfig),

  getDrawerCommand: () => buildDrawerBase64(getStoredDrawerConfig()),

  listPrinters: async () => {
    try {
      await connectIfNeeded();
      return await qz.printers.find();
    } catch (error) {
      throw new Error(normalizeError(error, 'No se pudo consultar la lista de impresoras'));
    }
  },

  printTicket: async (ticketData, options = {}) => {
    const { printerName } = options;
    return printRaw(ticketData, printerName);
  },

  // Abre el cajón enviando el comando ESC/POS en base64 para preservar
  // bytes binarios exactos (evita corrupción de \x00 con format:'plain').
  openDrawer: async (options = {}) => {
    const { printerName } = options;
    const b64 = buildDrawerBase64(getStoredDrawerConfig());
    return openDrawerRaw(printerName, b64);
  },

  // Envía ticket y comando de cajón en UN SOLO trabajo de impresión.
  // Muchas impresoras ignoran el segundo trabajo si llega muy rápido;
  // combinarlos evita ese problema y garantiza la apertura.
  printTicketAndOpenDrawer: async (ticketData, options = {}) => {
    const { printerName } = options;
    const drawerB64 = buildDrawerBase64(getStoredDrawerConfig());
    return printRaw(ticketData, printerName, [drawerB64]);
  },
};
