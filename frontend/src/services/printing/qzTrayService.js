import qz from 'qz-tray';

const PRINTER_STORAGE_KEY = 'pos.selectedPrinter';

const DEFAULT_DRAWER_COMMAND = '\x1Bp\x00\x19\xFA'; // ESC p 0 25 250

const DEFAULT_WS_HOST = (import.meta.env.VITE_QZ_WS_HOST || 'localhost').trim();
const DEFAULT_WS_PORT_SECURE = Number(import.meta.env.VITE_QZ_WS_PORT_SECURE || 8181);
const DEFAULT_WS_PORT_INSECURE = Number(import.meta.env.VITE_QZ_WS_PORT_INSECURE || 8282);

const DEFAULT_PRINTER_NAME = (import.meta.env.VITE_QZ_DEFAULT_PRINTER || '').trim();
const QZ_CERT_PEM = (import.meta.env.VITE_QZ_CERT_PEM || '').trim();
const QZ_SIGN_ENDPOINT = (import.meta.env.VITE_QZ_SIGN_ENDPOINT || '').trim();

let securityConfigured = false;

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

  qz.security.setCertificatePromise((resolve, reject) => {
    if (QZ_CERT_PEM) {
      resolve(QZ_CERT_PEM);
      return;
    }

    if (!QZ_SIGN_ENDPOINT) {
      resolve();
      return;
    }

    fetch(`${QZ_SIGN_ENDPOINT.replace(/\/$/, '')}/certificate`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('No se pudo obtener certificado de firma de QZ');
        return response.text();
      })
      .then(resolve)
      .catch(reject);
  });

  qz.security.setSignatureAlgorithm('SHA512');
  qz.security.setSignaturePromise((toSign) => (resolve, reject) => {
    if (!QZ_SIGN_ENDPOINT) {
      resolve();
      return;
    }

    fetch(`${QZ_SIGN_ENDPOINT.replace(/\/$/, '')}/sign`, {
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

const printRaw = async (rawData, printerName) => {
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

    await qz.print(config, [{ type: 'raw', format: 'plain', data: rawData }]);
    return { printer: resolvedPrinter };
  } catch (error) {
    throw new Error(normalizeError(error));
  }
};

export const qzTrayService = {
  drawerCommand: DEFAULT_DRAWER_COMMAND,

  isConnected: () => qz.websocket.isActive(),

  getSelectedPrinter: () => getStoredPrinter(),

  setSelectedPrinter: (printerName) => {
    setStoredPrinter((printerName || '').trim());
  },

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

  openDrawer: async (options = {}) => {
    const { printerName, command = DEFAULT_DRAWER_COMMAND } = options;
    return printRaw(command, printerName);
  },

  printTicketAndOpenDrawer: async (ticketData, options = {}) => {
    const printResult = await qzTrayService.printTicket(ticketData, options);
    await qzTrayService.openDrawer(options);
    return printResult;
  },
};
