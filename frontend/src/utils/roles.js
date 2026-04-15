import { hasSubmenuPermission, isAdminRole, isManagerRole } from './permissions';

export const ROLES = [
  { value: 'administrador', label: 'Administrador' },
  { value: 'gerente', label: 'Gerente' },
  { value: 'recepcion', label: 'Recepción' },
];

const normalizeRole = (rol) => String(rol || '').trim().toLowerCase();

export { isAdminRole, isManagerRole };

export const canManageCatalog = (user) => (
  hasSubmenuPermission(user, 'productos', 'inventario', 'create')
  || hasSubmenuPermission(user, 'productos', 'inventario', 'edit')
  || hasSubmenuPermission(user, 'productos', 'inventario', 'delete')
  || hasSubmenuPermission(user, 'productos', 'servicios', 'create')
  || hasSubmenuPermission(user, 'productos', 'servicios', 'edit')
  || hasSubmenuPermission(user, 'productos', 'servicios', 'delete')
);

export const canManageInvoices = (user) => (
  hasSubmenuPermission(user, 'ventas', 'ventas', 'edit')
  || hasSubmenuPermission(user, 'ventas', 'ventas', 'delete')
  || hasSubmenuPermission(user, 'ventas', 'servicios', 'edit')
  || hasSubmenuPermission(user, 'ventas', 'servicios', 'delete')
  || hasSubmenuPermission(user, 'ventas', 'consumo_empleado', 'edit')
  || hasSubmenuPermission(user, 'ventas', 'consumo_empleado', 'delete')
);

export const roleLabel = (rol) => {
  const match = ROLES.find((item) => item.value === normalizeRole(rol));
  return match?.label || rol || '-';
};
