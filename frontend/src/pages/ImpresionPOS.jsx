import PrinterPanel from '../components/PrinterPanel';

const ImpresionPOS = () => {
  return (
    <div className="space-y-4 fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Impresion POS</h1>
        <p className="text-gray-600 mt-1">
          Configuracion de impresora, cajon RJ11 y pruebas de QZ Tray.
        </p>
      </div>

      <PrinterPanel />
    </div>
  );
};

export default ImpresionPOS;
