import { useEffect, useState } from 'react';
import { FiPrinter, FiRefreshCw } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { buildEscPosTicket } from '../services/printing/escposTicket';
import { qzTrayService } from '../services/printing/qzTrayService';

const PRUEBA_PAYLOAD = {
  businessName: 'CORTE Y ESTILO',
  ticketTitle: 'PRUEBA IMPRESORA',
  numero_factura: 'TEST-0001',
  fecha_hora: new Date().toISOString(),
  cliente_nombre: 'Prueba local',
  usuario_nombre: 'Sistema',
  medio_pago: 'efectivo',
  total: 1000,
  items: [
    {
      nombre: 'Prueba de impresion ESC/POS',
      cantidad: 1,
      precio_unitario: 1000,
      total: 1000,
    },
  ],
  footerLines: ['Si lees esto, QZ Tray esta integrado correctamente.'],
};

const PrinterPanel = () => {
  const [loading, setLoading] = useState(false);
  const [printers, setPrinters] = useState([]);
  const [selectedPrinter, setSelectedPrinter] = useState(qzTrayService.getSelectedPrinter());
  const [drawerConfig, setDrawerConfig] = useState(qzTrayService.getDrawerConfig());

  const cargarImpresoras = async () => {
    try {
      setLoading(true);
      const list = await qzTrayService.listPrinters();
      setPrinters(list);
      if (!selectedPrinter && list.length) {
        setSelectedPrinter(list[0]);
      }
    } catch (error) {
      toast.error(error.message || 'No se pudo consultar QZ Tray');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarImpresoras();
  }, []);

  const guardarImpresora = () => {
    qzTrayService.setSelectedPrinter(selectedPrinter);
    toast.success(selectedPrinter ? `Impresora guardada: ${selectedPrinter}` : 'Impresora predeterminada restablecida');
  };

  const guardarCajon = () => {
    const saved = qzTrayService.setDrawerConfig(drawerConfig);
    setDrawerConfig(saved);
    toast.success(`Configuracion cajon guardada (pin ${saved.pin}, on ${saved.onMs}, off ${saved.offMs})`);
  };

  const imprimirPrueba = async () => {
    try {
      const raw = buildEscPosTicket(PRUEBA_PAYLOAD);
      await qzTrayService.printTicket(raw);
      toast.success('Ticket de prueba enviado');
    } catch (error) {
      toast.error(error.message || 'No se pudo imprimir ticket de prueba');
    }
  };

  const probarCajon = async () => {
    try {
      await qzTrayService.openDrawer();
      toast.success('Comando de apertura enviado');
    } catch (error) {
      toast.error(error.message || 'No se pudo abrir el cajon');
    }
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="card-header mb-0 inline-flex items-center gap-2">
          <FiPrinter /> Impresion POS (QZ Tray)
        </h2>
        <button className="btn-secondary inline-flex items-center gap-2" onClick={cargarImpresoras} disabled={loading}>
          <FiRefreshCw className={loading ? 'animate-spin' : ''} /> Actualizar
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <select className="input-field md:col-span-2" value={selectedPrinter} onChange={(e) => setSelectedPrinter(e.target.value)}>
          <option value="">Impresora predeterminada del sistema</option>
          {printers.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>

        <button className="btn-secondary" type="button" onClick={guardarImpresora}>Guardar impresora</button>
        <button className="btn-secondary" type="button" onClick={imprimirPrueba}>Imprimir prueba</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <select
          className="input-field"
          value={String(drawerConfig.pin)}
          onChange={(e) => setDrawerConfig((prev) => ({ ...prev, pin: Number(e.target.value) }))}
        >
          <option value="0">Pin apertura: 0 (recomendado)</option>
          <option value="1">Pin apertura: 1</option>
        </select>

        <input
          className="input-field"
          type="number"
          min="1"
          max="255"
          value={drawerConfig.onMs}
          onChange={(e) => setDrawerConfig((prev) => ({ ...prev, onMs: Number(e.target.value || 0) }))}
          placeholder="Pulso ON (1-255)"
        />

        <input
          className="input-field"
          type="number"
          min="1"
          max="255"
          value={drawerConfig.offMs}
          onChange={(e) => setDrawerConfig((prev) => ({ ...prev, offMs: Number(e.target.value || 0) }))}
          placeholder="Pulso OFF (1-255)"
        />

        <button className="btn-secondary" type="button" onClick={guardarCajon}>Guardar cajon RJ11</button>
      </div>

      <div className="flex gap-2">
        <button className="btn-secondary" type="button" onClick={probarCajon}>Probar apertura de caja</button>
      </div>
    </div>
  );
};

export default PrinterPanel;
