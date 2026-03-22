import {
  buildEscPosTicket,
  buildProductSaleTicketPayload,
  buildServiceSaleTicketPayload,
} from './escposTicket';
import { qzTrayService } from './qzTrayService';
import { localDrawerService } from './localDrawerService';
import { localPosBridgeService } from './localPosBridgeService';

const BUSINESS_NAME = (import.meta.env.VITE_TICKET_BUSINESS_NAME || 'CORTE Y ESTILO').trim();
const PRINT_MODE = (import.meta.env.VITE_PRINT_MODE || 'qz').trim().toLowerCase();
const DRAWER_MODE = (import.meta.env.VITE_DRAWER_MODE || 'serial').trim().toLowerCase();

const printTicket = async (ticket) => {
  if (PRINT_MODE === 'bridge') {
    return localPosBridgeService.printTicket(ticket);
  }
  return qzTrayService.printTicket(ticket);
};

const openDrawerSafely = async () => {
  try {
    if (DRAWER_MODE === 'qz') {
      await qzTrayService.openDrawer();
      return;
    }
    if (DRAWER_MODE === 'bridge') {
      await localPosBridgeService.openDrawer();
      return;
    }
    await localDrawerService.openDrawer();
  } catch (error) {
    // Nunca interrumpir el flujo de cobro por falla de apertura de cajon.
    console.warn('[ticketPrintService] Fallo apertura de cajon:', error);
  }
};

const withBusinessData = (payload) => ({
  businessName: BUSINESS_NAME,
  ...payload,
});

export const ticketPrintService = {
  buildFromProductSale: (sale) => buildEscPosTicket(withBusinessData(buildProductSaleTicketPayload(sale))),

  buildFromServiceSale: (service) => buildEscPosTicket(withBusinessData(buildServiceSaleTicketPayload(service))),

  printProductSaleAndOpenDrawer: async (sale) => {
    const ticket = ticketPrintService.buildFromProductSale(sale);
    await printTicket(ticket);
    await openDrawerSafely();
    return { ok: true };
  },

  printServiceSaleAndOpenDrawer: async (service) => {
    const ticket = ticketPrintService.buildFromServiceSale(service);
    await printTicket(ticket);
    await openDrawerSafely();
    return { ok: true };
  },

  reprintProductSale: async (sale) => {
    const ticket = ticketPrintService.buildFromProductSale(sale);
    return qzTrayService.printTicket(ticket);
  },

  reprintServiceSale: async (service) => {
    const ticket = ticketPrintService.buildFromServiceSale(service);
    return qzTrayService.printTicket(ticket);
  },
};
