import { useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  FiHome, FiUsers, FiScissors, FiPackage, FiDollarSign,
  FiBarChart2, FiLogOut, FiMenu, FiX, FiMonitor, FiPrinter
} from 'react-icons/fi';
import useAuthStore from '../store/authStore';
import { toast } from 'react-toastify';
import { roleLabel, isManagerRole } from '../utils/roles';
import { hasMenuPermission } from '../utils/permissions';

const logoSalon = '/corte_estilo_logo.png';

const Layout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [logoError, setLogoError] = useState(false);

  const handleLogout = () => {
    logout();
    toast.info('Sesión cerrada');
    navigate('/login');
  };

  const abrirPantallaCliente = () => {
    window.open('/pantalla-cliente', 'pantalla_cliente', 'noopener,noreferrer');
  };

  const esAdmin = isManagerRole(user?.rol);
  const menuItems = [
    { path: '/dashboard', icon: FiHome, label: 'Dashboard', permissionKey: 'dashboard' },
    ...(esAdmin ? [
      { path: '/usuarios', icon: FiUsers, label: 'Usuarios' },
      { path: '/estilistas', icon: FiScissors, label: 'Empleados', permissionKey: 'estilistas' },
      { path: '/impresion-pos', icon: FiPrinter, label: 'Impresion POS', permissionKey: 'impresion_pos' },
    ] : []),
    { path: '/servicios', icon: FiPackage, label: 'Operación diaria', permissionKey: 'servicios' },
    { path: '/productos', icon: FiPackage, label: 'Inventario y Servicio', permissionKey: 'productos' },
    { path: '/ventas', icon: FiDollarSign, label: 'Histórico de ventas', permissionKey: 'ventas' },
    { path: '/reportes', icon: FiBarChart2, label: 'Reportes', permissionKey: 'reportes' },
  ].filter((item) => !item.permissionKey || hasMenuPermission(user, item.permissionKey, 'view'));

  return (
    <div className="flex h-screen bg-gray-100 touch-scroll">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? 'w-56' : 'w-16'
        } bg-gradient-to-b from-gray-900 to-gray-800 text-white transition-all duration-300 ease-in-out flex flex-col`}
      >
        {/* Logo y toggle */}
        <div className="flex items-center justify-between p-3 border-b border-gray-700 min-h-[64px]">
          {sidebarOpen && (
            <div className="flex items-center space-x-3">
              {!logoError ? (
                <img
                  src={logoSalon}
                  alt="Corte y Estilo"
                  className="h-10 w-auto max-w-[108px] rounded-lg object-contain bg-white p-1"
                  onError={() => setLogoError(true)}
                />
              ) : (
                <span className="text-3xl">✂️</span>
              )}
              <div>
                <span className="block font-bold text-base leading-tight">Corte y Estilo</span>
                <span className="block text-xs text-gray-300">Panel profesional</span>
              </div>
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 rounded-lg hover:bg-gray-700 transition-colors"
          >
            {sidebarOpen ? <FiX size={20} /> : <FiMenu size={20} />}
          </button>
        </div>

        {/* Menú de navegación */}
        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1 px-2">
            {menuItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className={`flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-all duration-200 text-sm
                      ${isActive 
                        ? 'bg-white text-gray-900 font-semibold shadow-lg' 
                        : 'hover:bg-gray-700 text-gray-300'
                      }`}
                  >
                    <Icon size={20} />
                    {sidebarOpen && <span>{item.label}</span>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Usuario y logout */}
        <div className="border-t border-gray-700 p-4">
          {sidebarOpen && (
            <button
              onClick={abrirPantallaCliente}
              className="w-full flex items-center space-x-3 px-4 py-3 rounded-lg bg-cyan-600 hover:bg-cyan-700 transition-colors mb-3"
            >
              <FiMonitor size={20} />
              <span>Pantalla cliente</span>
            </button>
          )}
          <div className={`flex items-center ${sidebarOpen ? 'space-x-3' : 'justify-center'} mb-3`}>
            <div className="w-10 h-10 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full flex items-center justify-center font-bold">
              {user?.nombre_completo?.charAt(0) || 'U'}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{user?.nombre_completo}</p>
                <p className="text-xs text-gray-400 truncate">{roleLabel(user?.rol)}</p>
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            className={`w-full flex items-center ${sidebarOpen ? 'space-x-3' : 'justify-center'} px-4 py-3 rounded-lg bg-red-600 hover:bg-red-700 transition-colors`}
          >
            <FiLogOut size={20} />
            {sidebarOpen && <span>Cerrar Sesión</span>}
          </button>
        </div>
      </aside>

      {/* Contenido principal */}
      <main className="flex-1 overflow-y-auto">
        <div className="container mx-auto px-3 md:px-4 py-4 md:py-5">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
