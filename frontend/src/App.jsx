import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Usuarios from './pages/Usuarios';
import Estilistas from './pages/Estilistas';
import Servicios from './pages/Servicios';
import Productos from './pages/Productos';
import Ventas from './pages/Ventas';
import Reportes from './pages/Reportes';
import PantallaCliente from './pages/PantallaCliente';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import useAuthStore from './store/authStore';
import { isManagerRole } from './utils/roles';

const AdminRoute = ({ children }) => {
  const { user, isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isManagerRole(user?.rol)) return <Navigate to="/dashboard" replace />;
  return children;
};

function App() {
  const { checkAuth } = useAuthStore();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/pantalla-cliente" element={<PantallaCliente />} />
        
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="usuarios" element={<AdminRoute><Usuarios /></AdminRoute>} />
          <Route path="estilistas" element={<AdminRoute><Estilistas /></AdminRoute>} />
          <Route path="servicios" element={<Servicios />} />
          <Route path="productos" element={<Productos />} />
          <Route path="ventas" element={<Ventas />} />
          <Route path="reportes" element={<Reportes />} />
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
