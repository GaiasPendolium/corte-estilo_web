import api from "./api";

const BASE_URL = "/creditos/";
const ABONOS_URL = "/abonos-credito/";

const creditosService = {
    // ==========================
    // CREDITOS
    // ==========================

    async getCreditos(params = {}) {
        const response = await api.get(BASE_URL, { params });
        return response.data;
    },

    async getCredito(id) {
        const response = await api.get(`${BASE_URL}${id}/`);
        return response.data;
    },

    async crearCredito(data) {
        const response = await api.post(BASE_URL, data);
        return response.data;
    },

    async actualizarCredito(id, data) {
        const response = await api.put(`${BASE_URL}${id}/`, data);
        return response.data;
    },

    async eliminarCredito(id) {
        const response = await api.delete(`${BASE_URL}${id}/`);
        return response.data;
    },

    // ==========================
    // RESUMEN
    // ==========================

    async getResumen() {
        const response = await api.get(`${BASE_URL}resumen/`);
        return response.data;
    },

    async getPorEmpleado(estilistaId) {
        const response = await api.get(`${BASE_URL}por_empleado/`, {
            params: {
                estilista_id: estilistaId,
            },
        });

        return response.data;
    },

    // ==========================
    // ABONOS
    // ==========================

    async getAbonos(creditoId) {
        const response = await api.get(`${ABONOS_URL}por_credito/`, {
            params: {
                credito_id: creditoId,
            },
        });

        return response.data;
    },

    async getAbonosPorEstilista(estilistaId) {
        // Todos los abonos de TODOS los créditos (activos y cancelados) de un
        // empleado, para el historial de pagos permanente.
        const response = await api.get(ABONOS_URL, {
            params: {
                credito__estilista: estilistaId,
                ordering: '-fecha',
            },
        });
        const data = response.data;
        return Array.isArray(data) ? data : (data?.results || []);
    },

    async crearAbono(data) {
        const response = await api.post(ABONOS_URL, data);
        return response.data;
    },

    async editarAbono(id, data) {
        const response = await api.put(`${ABONOS_URL}${id}/`, data);
        return response.data;
    },

    async eliminarAbono(id) {
        const response = await api.delete(`${ABONOS_URL}${id}/`);
        return response.data;
    },

    // ==========================
    // HISTORIAL Y REPORTES
    // ==========================

    async getHistorial(estilistaId) {
        const response = await api.get(`${BASE_URL}historial/`, {
            params: estilistaId ? { estilista_id: estilistaId } : {},
        });
        return response.data;
    },

    async exportarExcel(estilistaId) {
        const response = await api.get(`${BASE_URL}exportar-excel/`, {
            params: estilistaId ? { estilista_id: estilistaId } : {},
            responseType: 'blob',
        });
        if (response.data.type === 'application/json') {
            const text = await response.data.text();
            const error = JSON.parse(text);
            throw new Error(error.error || 'Error al exportar Excel');
        }
        return response.data;
    },

    async exportarPdf(estilistaId) {
        const response = await api.get(`${BASE_URL}exportar-pdf/`, {
            params: estilistaId ? { estilista_id: estilistaId } : {},
            responseType: 'blob',
        });
        if (response.data.type === 'application/json') {
            const text = await response.data.text();
            const error = JSON.parse(text);
            throw new Error(error.error || 'Error al exportar PDF');
        }
        return response.data;
    },

    // ==========================
    // UTILIDADES
    // ==========================

    formatearMoneda(valor) {
        return new Intl.NumberFormat("es-CO", {
            style: "currency",
            currency: "COP",
            minimumFractionDigits: 0,
        }).format(valor || 0);
    },

    obtenerColorEstado(estado) {
        switch (estado) {
            case "activo":
                return "success";

            case "cancelado":
                return "primary";

            case "vencido":
                return "danger";

            case "proximo_vencer":
                return "warning";

            default:
                return "secondary";
        }
    },

    obtenerTextoEstado(estado) {
        switch (estado) {
            case "activo":
                return "Activo";

            case "cancelado":
                return "Cancelado";

            case "vencido":
                return "Vencido";

            case "proximo_vencer":
                return "Próximo a vencer";

            default:
                return estado;
        }
    },

    calcularInteres(valorPrestado, porcentaje) {
        const interes =
            (parseFloat(valorPrestado || 0) *
                parseFloat(porcentaje || 0)) /
            100;

        return interes;
    },

    calcularTotal(valorPrestado, porcentaje) {
        const prestado = parseFloat(valorPrestado || 0);

        return (
            prestado +
            this.calcularInteres(prestado, porcentaje)
        );
    },
};

export default creditosService;