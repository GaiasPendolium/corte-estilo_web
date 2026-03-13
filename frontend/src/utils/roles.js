export const ROLES = [
  { value: 'administrador', label: 'Administrador' },
  { value: 'gerente', label: 'Gerente' },
  { value: 'recepcion', label: 'Recepción' },
];

const normalizeRole = (rol) => String(rol || '').trim().toLowerCase();

const isManagerRole = (rol) => {
  const normalized = normalizeRole(rol);
  return normalized === 'administrador' || normalized === 'gerente';
};

export const canManageCatalog = (user) => isManagerRole(user?.rol);

export const canManageInvoices = (user) => isManagerRole(user?.rol);

export const roleLabel = (rol) => {
  const match = ROLES.find((item) => item.value === normalizeRole(rol));
  return match?.label || rol || '-';
};
