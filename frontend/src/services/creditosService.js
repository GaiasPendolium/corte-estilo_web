import api from "./api";

const BASE_URL = "/creditos/";
const ABONOS_URL = "/abonos-credito/";
const PERSONAS_URL = "/personas-credito/";

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

    async getPorTitular() {
        // Lista combinada: empleados activos + personas externas activas,
        // cada item con 'tipo': 'empleado' | 'persona'.
        const response = await api.get(`${BASE_URL}por-titular/`);
        return response.data;
    },

    // ==========================
    // PERSONAS EXTERNAS (titulares de crédito que no son empleados)
    // ==========================

    async crearPersona(data) {
        const response = await api.post(PERSONAS_URL, data);
        return response.data;
    },

    async actualizarPersona(id, data) {
        const response = await api.put(`${PERSONAS_URL}${id}/`, data);
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

    async getAbonosPorTitular(tipo, id) {
        // Todos los abonos de TODOS los créditos (activos y cancelados) de un
        // titular (empleado o persona externa), para el historial de pagos permanente.
        const filtroTitular = tipo === 'persona' ? { credito__persona_credito: id } : { credito__estilista: id };
        const response = await api.get(ABONOS_URL, {
            params: {
                ...filtroTitular,
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

    _paramsTitular(tipo, id) {
        if (!id) return {};
        return tipo === 'persona' ? { persona_credito_id: id } : { estilista_id: id };
    },

    async getHistorial(tipo, id) {
        const response = await api.get(`${BASE_URL}historial/`, {
            params: this._paramsTitular(tipo, id),
        });
        return response.data;
    },

    async exportarExcel(tipo, id) {
        const response = await api.get(`${BASE_URL}exportar-excel/`, {
            params: this._paramsTitular(tipo, id),
            responseType: 'blob',
        });
        if (response.data.type === 'application/json') {
            const text = await response.data.text();
            const error = JSON.parse(text);
            throw new Error(error.error || 'Error al exportar Excel');
        }
        return response.data;
    },

    async exportarPdf(tipo, id) {
        const response = await api.get(`${BASE_URL}exportar-pdf/`, {
            params: this._paramsTitular(tipo, id),
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