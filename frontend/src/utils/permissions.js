const ACTION_KEYS = ['view', 'create', 'edit', 'delete'];

export const ACTION_LABELS = {
  view: 'Ingresar',
  create: 'Crear',
  edit: 'Editar',
  delete: 'Eliminar',
};

export const MENU_PERMISSION_DEFINITIONS = [
  { key: 'dashboard', label: 'Dashboard', path: '/dashboard', actions: ['view'] },
  { key: 'estilistas', label: 'Empleados', path: '/estilistas', actions: ACTION_KEYS },
  { key: 'impresion_pos', label: 'Impresión POS', path: '/impresion-pos', actions: ['view'] },
  {
    key: 'servicios',
    label: 'Operación diaria',
    path: '/servicios',
    actions: ['view'],
    submenus: [
      { key: 'servicios', label: 'Servicios', actions: ACTION_KEYS },
      { key: 'ventas', label: 'Ventas', actions: ACTION_KEYS },
      { key: 'consumo_empleado', label: 'Consumo empleado', actions: ACTION_KEYS },
    ],
  },
  {
    key: 'productos',
    label: 'Inventario y Servicio',
    path: '/productos',
    actions: ['view'],
    submenus: [
      { key: 'inventario', label: 'Inventario', actions: ACTION_KEYS },
      { key: 'servicios', label: 'Servicios catálogo', actions: ACTION_KEYS },
    ],
  },
  {
    key: 'ventas',
    label: 'Histórico de ventas',
    path: '/ventas',
    actions: ['view'],
    submenus: [
      { key: 'ventas', label: 'Ventas', actions: ACTION_KEYS },
      { key: 'servicios', label: 'Servicios facturados', actions: ACTION_KEYS },
      { key: 'consumo_empleado', label: 'Consumo empleado', actions: ACTION_KEYS },
    ],
  },
  {
    key: 'reportes',
    label: 'Reportes',
    path: '/reportes',
    actions: ['view'],
    submenus: [
      { key: 'cierre', label: 'Cierre de caja', actions: ['view'] },
      { key: 'liquidacion', label: 'Liquidación empleado', actions: ['view', 'edit'] },
      { key: 'cartera', label: 'Cartera empleado', actions: ['view', 'edit', 'delete'] },
      { key: 'ajuste', label: 'Ajuste diario', actions: ['view', 'edit'] },
      { key: 'agotarse', label: 'Productos por agotarse', actions: ['view'] },
    ],
  },
];

const clone = (value) => JSON.parse(JSON.stringify(value));

const buildActions = (actions = ACTION_KEYS, enabled = false) => Object.fromEntries(actions.map((key) => [key, Boolean(enabled)]));

const buildFromSchema = (enabledResolver) => {
  const result = {};
  MENU_PERMISSION_DEFINITIONS.forEach((menu) => {
    result[menu.key] = {
      ...buildActions(menu.actions || ['view'], enabledResolver(menu.key, null, null)),
    };
    if (menu.submenus?.length) {
      result[menu.key].submenus = {};
      menu.submenus.forEach((submenu) => {
        result[menu.key].submenus[submenu.key] = buildActions(
          submenu.actions || ACTION_KEYS,
          enabledResolver(menu.key, submenu.key, null)
        );
      });
    }
  });
  return result;
};

const normalizeRole = (rol) => String(rol || '').trim().toLowerCase();

export const isAdminRole = (rol) => normalizeRole(rol) === 'administrador';
export const isManagerRole = (rol) => ['administrador', 'gerente'].includes(normalizeRole(rol));

export const getDefaultPermissionsForRole = (rol) => {
  const normalized = normalizeRole(rol);

  if (normalized === 'administrador' || normalized === 'gerente') {
    return buildFromSchema(() => true);
  }

  return {
    ...buildFromSchema(() => false),
    dashboard: { view: true },
    servicios: {
      view: true,
      submenus: {
        servicios: { view: true, create: true, edit: false, delete: false },
        ventas: { view: true, create: true, edit: false, delete: false },
        consumo_empleado: { view: true, create: true, edit: false, delete: false },
      },
    },
    productos: {
      view: true,
      submenus: {
        inventario: { view: true, create: false, edit: false, delete: false },
        servicios: { view: true, create: false, edit: false, delete: false },
      },
    },
    ventas: {
      view: true,
      submenus: {
        ventas: { view: true, create: false, edit: false, delete: false },
        servicios: { view: true, create: false, edit: false, delete: false },
        consumo_empleado: { view: true, create: false, edit: false, delete: false },
      },
    },
    reportes: {
      view: true,
      submenus: {
        cierre: { view: true },
        liquidacion: { view: true, edit: false },
        cartera: { view: false, edit: false, delete: false },
        ajuste: { view: true, edit: false },
        agotarse: { view: false },
      },
    },
  };
};

export const sanitizePermissionsForSave = (value, rol) => {
  const defaults = getDefaultPermissionsForRole(rol);
  const next = clone(defaults);
  const input = value && typeof value === 'object' ? value : {};

  MENU_PERMISSION_DEFINITIONS.forEach((menu) => {
    const sourceMenu = input[menu.key] || {};
    (menu.actions || ['view']).forEach((action) => {
      if (action in sourceMenu) next[menu.key][action] = Boolean(sourceMenu[action]);
    });
    if (menu.submenus?.length) {
      menu.submenus.forEach((submenu) => {
        const sourceSubmenu = sourceMenu?.submenus?.[submenu.key] || {};
        (submenu.actions || ACTION_KEYS).forEach((action) => {
          if (action in sourceSubmenu) next[menu.key].submenus[submenu.key][action] = Boolean(sourceSubmenu[action]);
        });
      });
    }
  });

  return next;
};

export const getEffectivePermissions = (user) => {
  if (isAdminRole(user?.rol)) {
    return getDefaultPermissionsForRole('administrador');
  }
  return sanitizePermissionsForSave(user?.permisos_ui || {}, user?.rol);
};

export const hasMenuPermission = (user, menuKey, action = 'view') => {
  const menu = getEffectivePermissions(user)?.[menuKey];
  return Boolean(menu?.[action]);
};

export const hasSubmenuPermission = (user, menuKey, submenuKey, action = 'view') => {
  const menu = getEffectivePermissions(user)?.[menuKey];
  return Boolean(menu?.view && menu?.submenus?.[submenuKey]?.[action]);
};

export const getFirstAllowedPath = (user) => {
  const found = MENU_PERMISSION_DEFINITIONS.find((menu) => hasMenuPermission(user, menu.key, 'view') && menu.path);
  return found?.path || '/dashboard';
};

export const getAllowedSubmenuKey = (user, menuKey, fallbackKey) => {
  const menuDef = MENU_PERMISSION_DEFINITIONS.find((menu) => menu.key === menuKey);
  if (!menuDef?.submenus?.length) return fallbackKey;
  if (fallbackKey && hasSubmenuPermission(user, menuKey, fallbackKey, 'view')) return fallbackKey;
  return menuDef.submenus.find((submenu) => hasSubmenuPermission(user, menuKey, submenu.key, 'view'))?.key || null;
};