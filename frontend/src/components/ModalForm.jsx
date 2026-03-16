import { FiX } from 'react-icons/fi';

const ModalForm = ({ isOpen, title, subtitle, onClose, children, size = 'lg' }) => {
  if (!isOpen) return null;

  const maxWidthClass = size === 'xl' ? 'max-w-5xl' : size === 'md' ? 'max-w-2xl' : 'max-w-4xl';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className={`relative w-full ${maxWidthClass} rounded-2xl bg-white shadow-2xl max-h-[90vh] flex flex-col`}>
        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4 flex-shrink-0">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
            {subtitle && <p className="mt-1 text-sm text-gray-600">{subtitle}</p>}
          </div>
          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            onClick={onClose}
            aria-label="Cerrar"
          >
            <FiX size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-6 flex-1">{children}</div>
      </div>
    </div>
  );
};

export default ModalForm;
