import { useState } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  FiHome, FiUsers, FiScissors, FiPackage, FiDollarSign,
  FiBarChart2, FiSettings, FiLogOut, FiMenu, FiX
} from 'react-icons/fi';
import useAuthStore from '../store/authStore';
import { toast } from 'react-toastify';

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

  const menuItems = [
    { path: '/dashboard', icon: FiHome, label: 'Dashboard' },
    { path: '/usuarios', icon: FiUsers, label: 'Usuarios' },
    { path: '/estilistas', icon: FiScissors, label: 'Estilistas' },
    { path: '/servicios', icon: FiPackage, label: 'Servicios' },
    { path: '/productos', icon: FiPackage, label: 'Productos' },
    { path: '/ventas', icon: FiDollarSign, label: 'Ventas' },
    { path: '/reportes', icon: FiBarChart2, label: 'Reportes' },
  ];

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? 'w-64' : 'w-20'
        } bg-gradient-to-b from-gray-900 to-gray-800 text-white transition-all duration-300 ease-in-out flex flex-col`}
      >
        {/* Logo y toggle */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          {sidebarOpen && (
            <div className="flex items-center space-x-3">
              {!logoError ? (
                <img
                  src={logoSalon}
                  alt="Corte y Estilo"
                  className="h-12 w-auto max-w-[120px] rounded-lg object-contain bg-white p-1.5"
                  onError={() => setLogoError(true)}
                />
              ) : (
                <span className="text-3xl">✂️</span>
              )}
              <div>
                <span className="block font-bold text-lg leading-tight">Corte y Estilo</span>
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
                    className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200
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
          <div className={`flex items-center ${sidebarOpen ? 'space-x-3' : 'justify-center'} mb-3`}>
            <div className="w-10 h-10 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full flex items-center justify-center font-bold">
              {user?.nombre_completo?.charAt(0) || 'U'}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{user?.nombre_completo}</p>
                <p className="text-xs text-gray-400 truncate">{user?.rol}</p>
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            className={`w-full flex items-center ${sidebarOpen ? 'space-x-3' : 'justify-center'} px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 transition-colors`}
          >
            <FiLogOut size={20} />
            {sidebarOpen && <span>Cerrar Sesión</span>}
          </button>
        </div>
      </aside>

      {/* Contenido principal */}
      <main className="flex-1 overflow-y-auto">
        <div className="container mx-auto px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
