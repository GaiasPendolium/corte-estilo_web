export const ROLES = [
  { value: 'administrador', label: 'Administrador' },
  { value: 'gerente', label: 'Gerente' },
  { value: 'recepcion', label: 'Recepción' },
];

export const canManageCatalog = (user) => ['administrador', 'gerente'].includes(user?.rol);

export const canManageInvoices = (user) => ['administrador', 'gerente'].includes(user?.rol);

export const roleLabel = (rol) => {
  const match = ROLES.find((item) => item.value === rol);
  return match?.label || rol || '-';
};
