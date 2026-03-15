import { useEffect, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiTrash2 } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { estilistasService } from '../services/api';
import ModalForm from '../components/ModalForm';

const INITIAL_FORM = {
  nombre: '',
  telefono: '',
  email: '',
  comision_porcentaje: '0',
  tipo_cobro_espacio: 'sin_cobro',
  valor_cobro_espacio: '0',
  comision_ventas_productos: '0',
  fecha_ingreso: '',
  activo: true,
};

const extractRows = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const getApiErrorMessage = (error, fallback) => {
  const data = error?.response?.data;
  if (typeof data === 'string' && data.trim()) return data;
  if (data?.detail) return String(data.detail);
  if (data?.mensaje) return String(data.mensaje);
  if (typeof data === 'object' && data !== null) {
    const firstError = Object.values(data)[0];
    if (Array.isArray(firstError) && firstError[0]) return String(firstError[0]);
    if (firstError) return String(firstError);
  }
  return fallback;
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
      const payload = await estilistasService.getAll({ activo: true });
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

    if (saving) {
      return;
    }

    if (!form.nombre.trim()) {
      toast.warning('El nombre es obligatorio');
      return;
    }

    try {
      setSaving(true);
      const payload = {
        nombre: form.nombre.trim(),
        telefono: form.telefono.trim() || null,
        email: form.email.trim() || null,
        comision_porcentaje: Number(form.comision_porcentaje || 0),
        tipo_cobro_espacio: form.tipo_cobro_espacio,
        valor_cobro_espacio: Number(form.valor_cobro_espacio || 0),
        comision_ventas_productos: Number(form.comision_ventas_productos || 0),
        fecha_ingreso: form.fecha_ingreso || null,
      };

      let estilistaGuardado = null;

      if (editingId) {
        estilistaGuardado = await estilistasService.update(editingId, payload);
        toast.success('Empleado actualizado');
      } else {
        estilistaGuardado = await estilistasService.create(payload);
        toast.success('Empleado creado correctamente');
      }

      setEstilistas((prev) => {
        if (!estilistaGuardado?.id) {
          return prev;
        }

        const filtered = prev.filter((item) => item.id !== estilistaGuardado.id);
        return [...filtered, estilistaGuardado].sort((a, b) => String(a.nombre || '').localeCompare(String(b.nombre || '')));
      });

      setForm(INITIAL_FORM);
      setEditingId(null);
      setShowForm(false);

      try {
        await cargarEstilistas();
      } catch (refreshError) {
        toast.warning('El empleado se guardó, pero no se pudo refrescar el listado en este momento');
      }
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'No se pudo guardar el empleado'));
    } finally {
      setSaving(false);
    }
  };

  const editarEstilista = (item) => {
    setEditingId(item.id);
    setForm({
      nombre: item.nombre || '',
      telefono: item.telefono || '',
      email: item.email || '',
      comision_porcentaje: String(item.comision_porcentaje ?? 0),
      tipo_cobro_espacio: item.tipo_cobro_espacio || 'sin_cobro',
      valor_cobro_espacio: String(item.valor_cobro_espacio ?? 0),
      comision_ventas_productos: String(item.comision_ventas_productos ?? 0),
      fecha_ingreso: item.fecha_ingreso || '',
      activo: item.activo ?? true,
    });
    setShowForm(true);
  };

  const eliminarEstilista = async (item) => {
    const ok = window.confirm(`¿Eliminar empleado "${item.nombre}"?\nSi tiene historial de servicios será desactivado en lugar de eliminado, preservando sus registros.`);
    if (!ok) return;

    try {
      const response = await estilistasService.delete(item.id);
      if (response?.desactivado) {
        toast.info('Empleado desactivado (tiene historial de servicios preservado)');
      } else {
        toast.success('Empleado eliminado');
      }
      await cargarEstilistas();
    } catch (error) {
      toast.error('No se pudo eliminar el empleado');
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Empleados</h1>
          <p className="text-gray-600 mt-1">Configura forma de cobro de espacio y comisión por ventas de productos</p>
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
            <FiPlus /> Nuevo empleado
          </button>
        </div>
      </div>

      <ModalForm
        isOpen={showForm}
        onClose={() => setShowForm(false)}
        title={editingId ? 'Editar empleado' : 'Nuevo empleado'}
        subtitle="Configura datos de contacto y condiciones de pago"
        size="md"
      >
      <form onSubmit={guardarEstilista} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-600 mb-1">Nombre</label>
          <input
            className="input-field"
            value={form.nombre}
            onChange={(e) => onInputChange('nombre', e.target.value)}
            placeholder="Nombre del empleado"
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

        <div>
          <label className="block text-sm text-gray-600 mb-1">Email</label>
          <input
            className="input-field"
            type="email"
            value={form.email}
            onChange={(e) => onInputChange('email', e.target.value)}
            placeholder="correo@ejemplo.com"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Fecha de ingreso</label>
          <input
            className="input-field"
            type="date"
            value={form.fecha_ingreso}
            onChange={(e) => onInputChange('fecha_ingreso', e.target.value)}
          />
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Comisión por servicio (%)</label>
          <input
            className="input-field"
            type="number"
            min="0"
            step="0.01"
            value={form.comision_porcentaje}
            onChange={(e) => onInputChange('comision_porcentaje', e.target.value)}
            placeholder="% que recibe el empleado por servicio"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Comisión por venta de productos (%)</label>
          <input
            className="input-field"
            type="number"
            min="0"
            step="0.01"
            value={form.comision_ventas_productos}
            onChange={(e) => onInputChange('comision_ventas_productos', e.target.value)}
            placeholder="Aplica solo para productos"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-600 mb-1">Cobro por espacio</label>
          <select
            className="input-field"
            value={form.tipo_cobro_espacio}
            onChange={(e) => onInputChange('tipo_cobro_espacio', e.target.value)}
          >
            <option value="sin_cobro">Sin cobro (100% empleado)</option>
            <option value="porcentaje_neto">% sobre neto</option>
            <option value="costo_fijo_neto">Costo fijo sobre neto</option>
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
            placeholder={form.tipo_cobro_espacio === 'porcentaje_neto' ? 'Porcentaje %' : 'Monto'}
          />
        </div>

        <div className="md:col-span-2 flex items-end gap-2">
          <button type="submit" className="btn-primary w-full inline-flex items-center justify-center gap-2" disabled={saving}>
            <FiPlus />
            {saving ? 'Guardando...' : editingId ? 'Guardar cambios' : 'Crear empleado'}
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
            <h2 className="text-lg font-semibold text-gray-800">Sin empleados registrados</h2>
            <p className="text-gray-600 mt-1">Crea el primero con el formulario de arriba.</p>
          </div>
        )}

        {!loading && estilistas.length > 0 && (
          <div className="overflow-x-scroll">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Telefono</th>
                  <th className="px-6 py-3 text-left">Email</th>
                  <th className="px-6 py-3 text-left">Comision</th>
                  <th className="px-6 py-3 text-left">Cobro espacio</th>
                  <th className="px-6 py-3 text-left">Comisión ventas</th>
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
                    <td className="table-cell">{item.tipo_cobro_espacio || 'sin_cobro'} ({Number(item.valor_cobro_espacio || 0).toFixed(2)})</td>
                    <td className="table-cell">{Number(item.comision_ventas_productos || 0).toFixed(2)}%</td>
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
