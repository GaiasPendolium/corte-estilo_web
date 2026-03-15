import {
  buildEscPosTicket,
  buildProductSaleTicketPayload,
  buildServiceSaleTicketPayload,
} from './escposTicket';
import { qzTrayService } from './qzTrayService';

const BUSINESS_NAME = (import.meta.env.VITE_TICKET_BUSINESS_NAME || 'CORTE Y ESTILO').trim();

const withBusinessData = (payload) => ({
  businessName: BUSINESS_NAME,
  ...payload,
});

export const ticketPrintService = {
  buildFromProductSale: (sale) => buildEscPosTicket(withBusinessData(buildProductSaleTicketPayload(sale))),

  buildFromServiceSale: (service) => buildEscPosTicket(withBusinessData(buildServiceSaleTicketPayload(service))),

  printProductSaleAndOpenDrawer: async (sale) => {
    const ticket = ticketPrintService.buildFromProductSale(sale);
    return qzTrayService.printTicketAndOpenDrawer(ticket);
  },

  printServiceSaleAndOpenDrawer: async (service) => {
    const ticket = ticketPrintService.buildFromServiceSale(service);
    return qzTrayService.printTicketAndOpenDrawer(ticket);
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
