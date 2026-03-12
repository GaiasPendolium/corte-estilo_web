import { create } from 'zustand';
import { authService } from '../services/api';

const useAuthStore = create((set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      login: async (username, password) => {
        try {
          const response = await authService.login(username, password);
          
          // Guardar tokens en localStorage
          localStorage.setItem('access_token', response.access);
          localStorage.setItem('refresh_token', response.refresh);
          
          // Obtener información del usuario
          const user = await authService.getCurrentUser();
          
          set({
            user,
            accessToken: response.access,
            refreshToken: response.refresh,
            isAuthenticated: true,
          });
          
          return { success: true };
        } catch (error) {
          return {
            success: false,
            error: error.response?.data?.detail || 'Error al iniciar sesión',
          };
        }
      },

      logout: () => {
        authService.logout();
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        });
      },

      checkAuth: async () => {
        const token = localStorage.getItem('access_token');
        if (token) {
          try {
            const user = await authService.getCurrentUser();
            set({
              user,
              accessToken: token,
              refreshToken: localStorage.getItem('refresh_token'),
              isAuthenticated: true,
            });
            return true;
          } catch (error) {
            set({
              user: null,
              accessToken: null,
              refreshToken: null,
              isAuthenticated: false,
            });
            return false;
          }
        }
        return false;
      },
    }));

export default useAuthStore;
