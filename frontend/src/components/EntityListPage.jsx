import { useEffect, useMemo, useState } from 'react';
import { FiRefreshCw } from 'react-icons/fi';
import { toast } from 'react-toastify';

function toRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.results)) return payload.results;
  return [];
}

const EntityListPage = ({ title, subtitle, service, columns }) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      setLoading(true);
      const payload = await service.getAll();
      setRows(toRows(payload));
    } catch (error) {
      toast.error(`Error cargando ${title.toLowerCase()}`);
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasRows = useMemo(() => rows.length > 0, [rows]);

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{title}</h1>
          <p className="text-gray-600 mt-1">{subtitle}</p>
        </div>
        <button
          onClick={loadData}
          className="btn-secondary inline-flex items-center justify-center gap-2"
          disabled={loading}
        >
          <FiRefreshCw className={loading ? 'animate-spin' : ''} />
          Actualizar
        </button>
      </div>

      <div className="card">
        {loading && (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-gray-900"></div>
          </div>
        )}

        {!loading && !hasRows && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8 text-center">
            <h2 className="text-lg font-semibold text-gray-800">Sin datos por ahora</h2>
            <p className="text-gray-600 mt-1">Cuando registres información, aparecerá en este módulo.</p>
          </div>
        )}

        {!loading && hasRows && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="table-header">
                <tr>
                  {columns.map((col) => (
                    <th key={col.key} className="px-6 py-3 text-left">
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {rows.map((row, idx) => (
                  <tr key={row.id || idx} className="hover:bg-gray-50">
                    {columns.map((col) => (
                      <td key={col.key} className="table-cell">
                        {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '-')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default EntityListPage;
