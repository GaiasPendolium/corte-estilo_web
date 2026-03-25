import { useMemo, useState } from 'react';
import { FiImage, FiUpload, FiRefreshCw, FiDownload } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { iaService } from '../services/api';

const formatKB = (bytes) => `${(Number(bytes || 0) / 1024).toFixed(1)} KB`;

const MejoradorImagenIA = () => {
  const [imagenOriginal, setImagenOriginal] = useState(null);
  const [imagenOriginalUrl, setImagenOriginalUrl] = useState('');
  const [imagenMejoradaBlob, setImagenMejoradaBlob] = useState(null);
  const [imagenMejoradaUrl, setImagenMejoradaUrl] = useState('');
  const [intensidad, setIntensidad] = useState(55);
  const [upscale, setUpscale] = useState(true);
  const [loading, setLoading] = useState(false);

  const statsOriginal = useMemo(() => {
    if (!imagenOriginal) return null;
    return {
      nombre: imagenOriginal.name,
      tamano: formatKB(imagenOriginal.size),
      tipo: imagenOriginal.type || 'image/*',
    };
  }, [imagenOriginal]);

  const statsMejorada = useMemo(() => {
    if (!imagenMejoradaBlob) return null;
    return {
      tamano: formatKB(imagenMejoradaBlob.size),
      tipo: imagenMejoradaBlob.type || 'image/jpeg',
    };
  }, [imagenMejoradaBlob]);

  const limpiarResultado = () => {
    if (imagenMejoradaUrl) URL.revokeObjectURL(imagenMejoradaUrl);
    setImagenMejoradaBlob(null);
    setImagenMejoradaUrl('');
  };

  const manejarArchivo = (file) => {
    if (!file) return;
    if (!file.type?.startsWith('image/')) {
      toast.warning('Debes seleccionar un archivo de imagen válido.');
      return;
    }

    if (imagenOriginalUrl) URL.revokeObjectURL(imagenOriginalUrl);
    limpiarResultado();

    setImagenOriginal(file);
    setImagenOriginalUrl(URL.createObjectURL(file));
  };

  const onInputFile = (e) => {
    const file = e.target.files?.[0];
    manejarArchivo(file);
  };

  const mejorarImagen = async () => {
    if (!imagenOriginal) {
      toast.warning('Primero selecciona una imagen.');
      return;
    }

    try {
      setLoading(true);
      limpiarResultado();
      const blob = await iaService.mejorarImagen({
        imagenFile: imagenOriginal,
        intensidad,
        upscale,
      });
      const url = URL.createObjectURL(blob);
      setImagenMejoradaBlob(blob);
      setImagenMejoradaUrl(url);
      toast.success('Imagen mejorada correctamente.');
    } catch (error) {
      toast.error(error.message || 'No se pudo mejorar la imagen.');
    } finally {
      setLoading(false);
    }
  };

  const descargarResultado = () => {
    if (!imagenMejoradaBlob || !imagenMejoradaUrl) return;
    const a = document.createElement('a');
    a.href = imagenMejoradaUrl;
    a.download = `mejorada_${Date.now()}.jpg`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="space-y-6 fade-in">
      <section className="rounded-[28px] bg-[linear-gradient(140deg,#0f172a_0%,#1f2937_45%,#111827_100%)] p-6 text-white shadow-2xl">
        <div className="flex items-center gap-3">
          <FiImage className="text-cyan-300" size={30} />
          <div>
            <h1 className="text-3xl font-black tracking-tight">Mejorador IA de Imágenes</h1>
            <p className="text-slate-300 text-sm">Módulo exclusivo de administrador para mejorar fotos borrosas y embellecer detalles.</p>
          </div>
        </div>
      </section>

      <div className="card grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-3">
          <label className="block text-sm font-medium text-gray-700">Cargar imagen</label>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-cyan-300 bg-cyan-50 px-4 py-6 text-cyan-900 hover:bg-cyan-100 transition-colors">
            <FiUpload />
            <span>{imagenOriginal ? 'Cambiar imagen' : 'Seleccionar imagen'}</span>
            <input type="file" accept="image/*" className="hidden" onChange={onInputFile} />
          </label>
          {statsOriginal && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
              <p><strong>Archivo:</strong> {statsOriginal.nombre}</p>
              <p><strong>Tamaño:</strong> {statsOriginal.tamano}</p>
              <p><strong>Tipo:</strong> {statsOriginal.tipo}</p>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Intensidad de mejora: {intensidad}%</label>
            <input
              type="range"
              min="0"
              max="100"
              value={intensidad}
              onChange={(e) => setIntensidad(Number(e.target.value || 0))}
              className="w-full"
            />
          </div>

          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={upscale}
              onChange={(e) => setUpscale(e.target.checked)}
            />
            Reescalar automáticamente fotos pequeñas
          </label>

          <button className="btn-primary w-full inline-flex items-center justify-center gap-2" onClick={mejorarImagen} disabled={loading || !imagenOriginal}>
            {loading ? <FiRefreshCw className="animate-spin" /> : <FiImage />}
            {loading ? 'Procesando...' : 'Mejorar imagen'}
          </button>

          <button className="btn-secondary w-full inline-flex items-center justify-center gap-2" onClick={descargarResultado} disabled={!imagenMejoradaBlob}>
            <FiDownload /> Descargar resultado
          </button>

          {statsMejorada && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <p><strong>Resultado:</strong> {statsMejorada.tamano}</p>
              <p><strong>Tipo:</strong> {statsMejorada.tipo}</p>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="card-header">Antes</h2>
          <div className="rounded-xl border border-gray-200 bg-gray-50 min-h-[280px] flex items-center justify-center overflow-hidden">
            {imagenOriginalUrl ? (
              <img src={imagenOriginalUrl} alt="Original" className="max-h-[520px] w-auto object-contain" />
            ) : (
              <p className="text-gray-500 text-sm">Sin imagen cargada</p>
            )}
          </div>
        </div>

        <div className="card">
          <h2 className="card-header">Después</h2>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 min-h-[280px] flex items-center justify-center overflow-hidden">
            {imagenMejoradaUrl ? (
              <img src={imagenMejoradaUrl} alt="Mejorada" className="max-h-[520px] w-auto object-contain" />
            ) : (
              <p className="text-emerald-700 text-sm">El resultado aparecerá aquí</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MejoradorImagenIA;
