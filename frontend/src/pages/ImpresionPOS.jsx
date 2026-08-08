import PrinterPanel from '../components/PrinterPanel';

const ImpresionPOS = () => {
  return (
    <div className="space-y-4 fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Impresora y caja registradora</h1>
        <p className="text-gray-600 mt-1">
          Configura la impresora de tickets y la apertura de la caja registradora.
        </p>
      </div>

      <PrinterPanel />
    </div>
  );
};

export default ImpresionPOS;
