import { useEffect, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { estilistasService } from '../services/api';
import ModalForm from '../components/ModalForm';

const INITIAL_FORM = {
  nombre: '',
  telefono: '',
  tipo_cobro_espacio: 'ninguno',
  valor_cobro_espacio: '0',
};

const extractRows = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const Estilistas = () => {
  const [form, setForm] = useState(INITIAL_FORM);
  const [estilistas, setEstilistas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);

  const cargarEstilistas = async () => {
    try {
      setLoading(true);
      const payload = await estilistasService.getAll();
      setEstilistas(extractRows(payload));
    } catch (error) {
      toast.error('No se pudo cargar el listado de estilistas');
      setEstilistas([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarEstilistas();
  }, []);

  const onInputChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const guardarEstilista = async (e) => {
    e.preventDefault();

    if (!form.nombre.trim()) {
      toast.warning('El nombre es obligatorio');
      return;
    }

    try {
      setSaving(true);
      const payload = {
        nombre: form.nombre.trim(),
        telefono: form.telefono.trim() || null,
        tipo_cobro_espacio: form.tipo_cobro_espacio,
        valor_cobro_espacio: Number(form.valor_cobro_espacio || 0),
      };

      if (editingId) {
        await estilistasService.update(editingId, payload);
        toast.success('Estilista actualizado');
      } else {
        await estilistasService.create(payload);
        toast.success('Estilista creado correctamente');
      }

      setForm(INITIAL_FORM);
      setEditingId(null);
      setShowForm(false);
      await cargarEstilistas();
    } catch (error) {
      const data = error?.response?.data;
      const firstError = typeof data === 'object' ? Object.values(data)[0] : null;
      const message = Array.isArray(firstError)
        ? firstError[0]
        : firstError || 'No se pudo crear el estilista';
      toast.error(String(message));
    } finally {
      setSaving(false);
    }
  };

  const editarEstilista = (item) => {
    setEditingId(item.id);
    setForm({
      nombre: item.nombre || '',
      telefono: item.telefono || '',
      tipo_cobro_espacio: item.tipo_cobro_espacio || 'ninguno',
      valor_cobro_espacio: String(item.valor_cobro_espacio ?? 0),
    });
    setShowForm(true);
  };

  const eliminarEstilista = async (item) => {
    const ok = window.confirm(`¿Eliminar estilista "${item.nombre}"?`);
    if (!ok) return;

    try {
      await estilistasService.delete(item.id);
      toast.success('Estilista eliminado');
      await cargarEstilistas();
    } catch (error) {
      toast.error('No se pudo eliminar el estilista');
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Estilistas</h1>
          <p className="text-gray-600 mt-1">Registra estilistas con nombre y numero de telefono</p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-secondary inline-flex items-center gap-2"
            onClick={cargarEstilistas}
            disabled={loading}
          >
            <FiRefreshCw className={loading ? 'animate-spin' : ''} />
            Actualizar
          </button>
          <button
            className="btn-primary inline-flex items-center gap-2"
            onClick={() => {
              setEditingId(null);
              setForm(INITIAL_FORM);
              setShowForm(true);
            }}
          >
            <FiPlus /> Nuevo estilista
          </button>
        </div>
      </div>

      <ModalForm
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title={editingId ? 'Editar estilista' : 'Nuevo estilista'}
        subtitle="Configura datos de contacto y tipo de cobro"
        size="md"
      >
      <form onSubmit={guardarEstilista} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Nombre</label>
          <input
            className="input-field"
            value={form.nombre}
            onChange={(e) => onInputChange('nombre', e.target.value)}
            placeholder="Nombre del estilista"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Numero de telefono</label>
          <input
            className="input-field"
            value={form.telefono}
            onChange={(e) => onInputChange('telefono', e.target.value)}
            placeholder="555-000-0000"
          />
        </div>

        <div className="md:col-span-2 flex items-end gap-2">
          <button type="submit" className="btn-primary w-full inline-flex items-center justify-center gap-2" disabled={saving}>
            <FiPlus />
            {saving ? 'Guardando...' : editingId ? 'Guardar cambios' : 'Crear estilista'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setShowForm(false);
              setEditingId(null);
              setForm(INITIAL_FORM);
            }}
          >
            Cancelar
          </button>
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Cobro por espacio</label>
          <select
            className="input-field"
            value={form.tipo_cobro_espacio}
            onChange={(e) => onInputChange('tipo_cobro_espacio', e.target.value)}
          >
            <option value="ninguno">Sin cobro</option>
            <option value="alquiler">Alquiler fijo</option>
            <option value="comision">Comisión sobre ganancias</option>
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Valor cobro espacio</label>
          <input
            className="input-field"
            type="number"
            min="0"
            step="0.01"
            value={form.valor_cobro_espacio}
            onChange={(e) => onInputChange('valor_cobro_espacio', e.target.value)}
            placeholder={form.tipo_cobro_espacio === 'comision' ? 'Porcentaje %' : 'Monto'}
          />
        </div>
      </form>
      </ModalForm>

      <div className="card">
        {loading && (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-gray-900"></div>
          </div>
        )}

        {!loading && estilistas.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-800">Sin estilistas registrados</h2>
            <p className="text-gray-600 mt-1">Crea el primero con el formulario de arriba.</p>
          </div>
        )}

        {!loading && estilistas.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Telefono</th>
                  <th className="px-6 py-3 text-left">Email</th>
                  <th className="px-6 py-3 text-left">Comision</th>
                  <th className="px-6 py-3 text-left">Cobro espacio</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {estilistas.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="table-cell font-medium">{item.nombre || '-'}</td>
                    <td className="table-cell">{item.telefono || '-'}</td>
                    <td className="table-cell">{item.email || '-'}</td>
                    <td className="table-cell">{item.comision_porcentaje ?? 0}%</td>
                    <td className="table-cell">{item.tipo_cobro_espacio || 'ninguno'} ({Number(item.valor_cobro_espacio || 0).toFixed(2)})</td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1" onClick={() => editarEstilista(item)}>
                          <FiEdit2 size={14} /> Editar
                        </button>
                        <button className="btn-danger !px-3 !py-2 inline-flex items-center gap-1" onClick={() => eliminarEstilista(item)}>
                          <FiTrash2 size={14} /> Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Estilistas;
