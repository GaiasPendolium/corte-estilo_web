import { useEffect, useMemo, useState } from 'react';
import { FiEdit2, FiPlus, FiRefreshCw, FiTrash2, FiX } from 'react-icons/fi';
import { toast } from 'react-toastify';
import { usuariosService } from '../services/api';
import useAuthStore from '../store/authStore';
import ModalForm from '../components/ModalForm';

const INITIAL_FORM = {
  username: '',
  nombre_completo: '',
  rol: 'empleado',
  activo: true,
  password: '',
};

const ROLES = [
  { value: 'administrador', label: 'Administrador' },
  { value: 'recepcionista', label: 'Recepcionista' },
  { value: 'empleado', label: 'Empleado' },
  { value: 'visualizador', label: 'Visualizador' },
];

const extractRows = (payload) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
};

const Usuarios = () => {
  const { user: currentUser } = useAuthStore();

  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);

  const isEditing = useMemo(() => editingId !== null, [editingId]);

  const cargarUsuarios = async () => {
    try {
      setLoading(true);
      const payload = await usuariosService.getAll();
      setUsuarios(extractRows(payload));
    } catch (error) {
      toast.error('No se pudieron cargar los usuarios');
      setUsuarios([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargarUsuarios();
  }, []);

  const resetForm = () => {
    setForm(INITIAL_FORM);
    setEditingId(null);
    setShowForm(false);
  };

  const onInputChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validarFormulario = () => {
    if (!form.username.trim()) return 'El usuario es obligatorio';
    if (!form.nombre_completo.trim()) return 'El nombre completo es obligatorio';
    if (!form.rol) return 'Debes seleccionar un rol';
    if (!isEditing && !form.password.trim()) return 'La contraseña es obligatoria al crear';
    return null;
  };

  const onSubmit = async (e) => {
    e.preventDefault();

    const error = validarFormulario();
    if (error) {
      toast.warning(error);
      return;
    }

    const payload = {
      username: form.username.trim(),
      nombre_completo: form.nombre_completo.trim(),
      rol: form.rol,
      activo: form.activo,
    };

    if (form.password.trim()) {
      payload.password = form.password;
    }

    try {
      setSaving(true);

      if (isEditing) {
        await usuariosService.update(editingId, payload);
        toast.success('Usuario actualizado');
      } else {
        await usuariosService.create(payload);
        toast.success('Usuario creado');
      }

      resetForm();
      await cargarUsuarios();
    } catch (err) {
      const backendErrors = err?.response?.data;
      const firstError = typeof backendErrors === 'object' ? Object.values(backendErrors)[0] : null;
      const msg = Array.isArray(firstError)
        ? firstError[0]
        : firstError || 'No se pudo guardar el usuario';
      toast.error(String(msg));
    } finally {
      setSaving(false);
    }
  };

  const iniciarEdicion = (usuario) => {
    setEditingId(usuario.id);
    setShowForm(true);
    setForm({
      username: usuario.username || '',
      nombre_completo: usuario.nombre_completo || '',
      rol: usuario.rol || 'empleado',
      activo: Boolean(usuario.activo),
      password: '',
    });
  };

  const eliminarUsuario = async (usuario) => {
    if (usuario.id === currentUser?.id) {
      toast.warning('No puedes eliminar tu propio usuario');
      return;
    }

    const ok = window.confirm(`¿Eliminar al usuario "${usuario.username}"?`);
    if (!ok) return;

    try {
      await usuariosService.delete(usuario.id);
      toast.success('Usuario eliminado');
      await cargarUsuarios();
    } catch (error) {
      toast.error('No se pudo eliminar el usuario');
    }
  };

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Usuarios</h1>
          <p className="text-gray-600 mt-1">Crear, editar, eliminar y asignar rol</p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={cargarUsuarios}
            className="btn-secondary inline-flex items-center gap-2"
            disabled={loading}
          >
            <FiRefreshCw className={loading ? 'animate-spin' : ''} />
            Actualizar
          </button>
          <button
            onClick={() => {
              if (showForm && !isEditing) {
                resetForm();
              } else {
                setShowForm(true);
                setEditingId(null);
                setForm(INITIAL_FORM);
              }
            }}
            className="btn-primary inline-flex items-center gap-2"
          >
            {showForm && !isEditing ? <FiX /> : <FiPlus />}
            {showForm && !isEditing ? 'Cerrar' : 'Nuevo usuario'}
          </button>
        </div>
      </div>

      <ModalForm
        isOpen={showForm}
        onClose={resetForm}
        title={isEditing ? 'Editar usuario' : 'Nuevo usuario'}
        subtitle="Completa los datos y guarda cambios"
      >
        <form onSubmit={onSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Usuario</label>
            <input
              className="input-field"
              value={form.username}
              onChange={(e) => onInputChange('username', e.target.value)}
              placeholder="usuario"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Nombre completo</label>
            <input
              className="input-field"
              value={form.nombre_completo}
              onChange={(e) => onInputChange('nombre_completo', e.target.value)}
              placeholder="Nombre y apellido"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Rol</label>
            <select
              className="input-field"
              value={form.rol}
              onChange={(e) => onInputChange('rol', e.target.value)}
            >
              {ROLES.map((rol) => (
                <option key={rol.value} value={rol.value}>
                  {rol.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1">
              {isEditing ? 'Nueva contraseña (opcional)' : 'Contraseña'}
            </label>
            <input
              type="password"
              className="input-field"
              value={form.password}
              onChange={(e) => onInputChange('password', e.target.value)}
              placeholder={isEditing ? 'Dejar vacío para no cambiar' : 'Mínimo 8 caracteres'}
            />
          </div>

          <div className="md:col-span-2 flex items-center gap-2">
            <input
              id="activo"
              type="checkbox"
              checked={form.activo}
              onChange={(e) => onInputChange('activo', e.target.checked)}
            />
            <label htmlFor="activo" className="text-sm text-gray-700">
              Usuario activo
            </label>
          </div>

          <div className="md:col-span-2 flex gap-2">
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Guardando...' : isEditing ? 'Actualizar usuario' : 'Crear usuario'}
            </button>
            <button type="button" className="btn-secondary" onClick={resetForm}>
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

        {!loading && usuarios.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-800">No hay usuarios registrados</h2>
            <p className="text-gray-600 mt-1">Crea el primero con el boton "Nuevo usuario".</p>
          </div>
        )}

        {!loading && usuarios.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  <th className="px-6 py-3 text-left">Usuario</th>
                  <th className="px-6 py-3 text-left">Nombre</th>
                  <th className="px-6 py-3 text-left">Rol</th>
                  <th className="px-6 py-3 text-left">Estado</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {usuarios.map((usuario) => (
                  <tr key={usuario.id} className="hover:bg-gray-50">
                    <td className="table-cell font-medium">{usuario.username}</td>
                    <td className="table-cell">{usuario.nombre_completo}</td>
                    <td className="table-cell capitalize">{usuario.rol}</td>
                    <td className="table-cell">
                      {usuario.activo ? (
                        <span className="px-2 py-1 rounded-full text-xs bg-green-100 text-green-800">Activo</span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-xs bg-red-100 text-red-800">Inactivo</span>
                      )}
                    </td>
                    <td className="table-cell">
                      <div className="flex justify-end gap-2">
                        <button
                          className="btn-secondary !px-3 !py-2 inline-flex items-center gap-1"
                          onClick={() => iniciarEdicion(usuario)}
                        >
                          <FiEdit2 size={14} /> Editar
                        </button>
                        <button
                          className="btn-danger !px-3 !py-2 inline-flex items-center gap-1"
                          onClick={() => eliminarUsuario(usuario)}
                          disabled={usuario.id === currentUser?.id}
                          title={usuario.id === currentUser?.id ? 'No puedes eliminar tu propio usuario' : 'Eliminar usuario'}
                        >
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

export default Usuarios;
