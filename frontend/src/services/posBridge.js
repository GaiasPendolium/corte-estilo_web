import axios from 'axios';

const POS_BRIDGE_URL = (import.meta.env.VITE_POS_BRIDGE_URL || '').trim();

const bridgeClient = POS_BRIDGE_URL
  ? axios.create({
      baseURL: POS_BRIDGE_URL,
      headers: { 'Content-Type': 'application/json' },
      timeout: 7000,
    })
  : null;

export const posBridgeService = {
  isEnabled: () => Boolean(bridgeClient),

  status: async () => {
    if (!bridgeClient) throw new Error('POS bridge no configurado');
    const res = await bridgeClient.get('/status');
    return res.data;
  },

  printTicket: async (text) => {
    if (!bridgeClient) throw new Error('POS bridge no configurado');
    const res = await bridgeClient.post('/print-ticket', { text });
    return res.data;
  },

  openDrawer: async () => {
    if (!bridgeClient) throw new Error('POS bridge no configurado');
    const res = await bridgeClient.post('/open-drawer', {});
    return res.data;
  },
};
