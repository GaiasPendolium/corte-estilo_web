import axios from 'axios';

const isLocalHost =
  typeof window !== 'undefined' && ['localhost', '127.0.0.1'].includes(window.location.hostname);
const envApiUrl = (import.meta.env.VITE_API_URL || '').trim();
const API_URL = isLocalHost
  ? (envApiUrl || 'http://localhost:8000/api')
  : '/api';

// Crear instancia de axios
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor para agregar token a las peticiones
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor para manejar respuestas y errores
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Si el token expiró, intentar refrescarlo
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = localStorage.getItem('refresh_token');
        const response = await axios.post(`${API_URL}/auth/refresh/`, {
          refresh: refreshToken,
        });

        const { access } = response.data;
        localStorage.setItem('access_token', access);

        originalRequest.headers.Authorization = `Bearer ${access}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Si falla el refresh, limpiar tokens y redirigir al login
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    if (!error.response) {
      error.message = 'No se pudo conectar al servidor. Verifica VITE_API_URL y CORS en backend.';
    }

    return Promise.reject(error);
  }
);

export default api;

// Servicios de autenticación
export const authService = {
  login: async (username, password) => {
    const response = await api.post('/auth/login/', { username, password });
    return response.data;
  },
  
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
  
  getCurrentUser: async () => {
    const response = await api.get('/usuarios/me/');
    return response.data;
  },
};

// Servicios de usuarios
export const usuariosService = {
  getAll: async (params) => {
    const response = await api.get('/usuarios/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/usuarios/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/usuarios/', data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/usuarios/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/usuarios/${id}/`);
    return response.data;
  },
  
  cambiarPassword: async (id, password) => {
    const response = await api.post(`/usuarios/${id}/cambiar_password/`, { password });
    return response.data;
  },
};

// Servicios de estilistas
export const estilistasService = {
  getAll: async (params) => {
    const response = await api.get('/estilistas/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/estilistas/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/estilistas/', data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/estilistas/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/estilistas/${id}/`);
    return response.data;
  },
  
  getEstadisticas: async (id, params) => {
    const response = await api.get(`/estilistas/${id}/estadisticas/`, { params });
    return response.data;
  },
};

// Servicios de servicios
export const serviciosService = {
  getAll: async (params) => {
    const response = await api.get('/servicios/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/servicios/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/servicios/', data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/servicios/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/servicios/${id}/`);
    return response.data;
  },
};

// Servicios de clientes
export const clientesService = {
  getAll: async (params) => {
    const response = await api.get('/clientes/', { params });
    return response.data;
  },

  create: async (data) => {
    const response = await api.post('/clientes/', data);
    return response.data;
  },
};

// Servicios de productos
export const productosService = {
  getAll: async (params) => {
    const response = await api.get('/productos/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/productos/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/productos/', data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/productos/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/productos/${id}/`);
    return response.data;
  },
  
  getBajoStock: async () => {
    const response = await api.get('/productos/bajo_stock/');
    return response.data;
  },
  
  ajustarStock: async (id, stock, descripcion) => {
    const response = await api.post(`/productos/${id}/ajustar_stock/`, { stock, descripcion });
    return response.data;
  },
};

// Servicios de servicios realizados
export const serviciosRealizadosService = {
  getAll: async (params) => {
    const response = await api.get('/servicios-realizados/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/servicios-realizados/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/servicios-realizados/', data);
    return response.data;
  },
  
  update: async (id, data) => {
    const response = await api.put(`/servicios-realizados/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/servicios-realizados/${id}/`);
    return response.data;
  },

  getEstadoEstilistas: async () => {
    const response = await api.get('/servicios-realizados/estado_estilistas/');
    return response.data;
  },

  finalizar: async (id, data) => {
    const response = await api.post(`/servicios-realizados/${id}/finalizar/`, data);
    return response.data;
  },
};

// Servicios de ventas
export const ventasService = {
  getAll: async (params) => {
    const response = await api.get('/ventas/', { params });
    return response.data;
  },
  
  getById: async (id) => {
    const response = await api.get(`/ventas/${id}/`);
    return response.data;
  },
  
  create: async (data) => {
    const response = await api.post('/ventas/', data);
    return response.data;
  },

  createTransaction: async (data) => {
    const response = await api.post('/ventas/transaccion/', data);
    return response.data;
  },

  update: async (id, data) => {
    const response = await api.put(`/ventas/${id}/`, data);
    return response.data;
  },
  
  delete: async (id) => {
    const response = await api.delete(`/ventas/${id}/`);
    return response.data;
  },

  cancelByInvoice: async (numeroFactura) => {
    const response = await api.post('/ventas/cancelar-factura/', {
      numero_factura: numeroFactura,
    });
    return response.data;
  },

  updateInvoiceTransaction: async (data) => {
    const response = await api.post('/ventas/editar-factura/', data);
    return response.data;
  },

  getFactura: async (id) => {
    const response = await api.get(`/ventas/${id}/factura/`);
    return response.data;
  },
};

// Servicios de reportes
export const reportesService = {
  getEstadisticasGenerales: async (params) => {
    const response = await api.get('/reportes/estadisticas/', { params });
    return response.data;
  },
  
  getReporteVentas: async (params) => {
    const response = await api.get('/reportes/ventas/', { params });
    return response.data;
  },
  
  getReporteServicios: async (params) => {
    const response = await api.get('/reportes/servicios/', { params });
    return response.data;
  },

  getBIResumen: async (params) => {
    const response = await api.get('/reportes/bi/', { params });
    return response.data;
  },

  getCierreCaja: async (params) => {
    try {
      const response = await api.get('/reportes/cierre-caja/', { params });
      return response.data;
    } catch (error) {
      // Reintento sobre la misma ruta proxied para evitar CORS en respuestas 503 cross-origin.
      if (error?.response?.status === 503) {
        const retry = await api.get('/reportes/cierre-caja/', { params });
        return retry.data;
      }
      throw error;
    }
  },

  exportBICsv: async (params) => {
    try {
      const response = await api.get('/reportes/bi/export/', {
        params,
        responseType: 'blob',
      });
      
      // Si el blob es en realidad un JSON con error, convertirlo
      if (response.data.type === 'application/json') {
        const text = await response.data.text();
        const error = JSON.parse(text);
        throw new Error(error.error || error.message || 'Error al exportar CSV');
      }
      
      return response.data;
    } catch (error) {
      console.error('Error exportando CSV:', error);
      throw error;
    }
  },

  exportBIPdf: async (params) => {
    try {
      const response = await api.get('/reportes/bi/export-pdf/', {
        params,
        responseType: 'blob',
      });
      
      // Si el blob es en realidad un JSON con error, convertirlo
      if (response.data.type === 'application/json') {
        const text = await response.data.text();
        const error = JSON.parse(text);
        throw new Error(error.error || error.message || 'Error al exportar PDF');
      }
      
      return response.data;
    } catch (error) {
      console.error('Error exportando PDF:', error);
      throw error;
    }
  },

  getResumenDiario: async () => {
    const response = await api.get('/reportes/bi/resumen-diario/');
    return response.data;
  },

  getEstadoPagoEstilistaDia: async (fecha) => {
    const response = await api.get('/reportes/estilistas/estado-pago-dia/', {
      params: { fecha },
    });
    return response.data;
  },

  getEstadoPagoHistorial: async (params) => {
    const response = await api.get('/reportes/estilistas/estado-pago-historial/', { params });
    return response.data;
  },

  deleteEstadoPagoHistorial: async (historialId) => {
    const response = await api.delete(`/reportes/estilistas/estado-pago-historial/${historialId}/`);
    return response.data;
  },

  setEstadoPagoEstilistaDia: async ({ estilista_id, fecha, fecha_inicio, fecha_fin, estado, notas, pagos_detalle, abono_puesto, medio_abono_puesto }) => {
    const response = await api.post('/reportes/estilistas/estado-pago-dia/', {
      estilista_id,
      fecha,
      fecha_inicio,
      fecha_fin,
      estado,
      notas,
      pagos_detalle,
      abono_puesto,
      medio_abono_puesto,
    });
    return response.data;
  },

  liquidarDiaV2: async ({ estilista_id, fecha, pago_efectivo, pago_nequi, pago_daviplata, pago_otros, abono_puesto, notas }) => {
    const payload = {
      estilista_id,
      fecha,
      pago_efectivo,
      pago_nequi,
      pago_daviplata,
      pago_otros,
      abono_puesto,
      notas,
    };

    const response = await api.post('/reportes/estilistas/liquidar-dia-v2/', payload);
    return response.data;
  },

  getConsumoEmpleadoDeudas: async (params) => {
    const response = await api.get('/reportes/consumo-empleado/deudas/', { params });
    return response.data;
  },

  abonarConsumoEmpleado: async ({ estilista_id, monto, medio_pago, notas }) => {
    const response = await api.post('/reportes/consumo-empleado/abonar/', {
      estilista_id,
      monto,
      medio_pago,
      notas,
    });
    return response.data;
  },
};
