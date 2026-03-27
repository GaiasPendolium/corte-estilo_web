import { useRef, useState } from 'react';

const KEYBOARD_ROWS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'N', 'Ñ'],
  ['Z', 'X', 'C', 'V', 'B', 'N', 'M', 'Á', 'É', 'Í', 'Ó', 'Ú'],
];

const KeyboardIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="5" width="20" height="14" rx="2" ry="2" />
    <path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M10 13h.01M14 13h.01M18 13h.01" />
    <path d="M7 16h10" />
  </svg>
);

const DraggableSearchKeyboard = ({
  visible,
  value,
  onChange,
  onClose,
  title = 'Teclado de búsqueda',
}) => {
  const [upper, setUpper] = useState(false);
  const [position, setPosition] = useState({ x: 40, y: 90 });
  const dragRef = useRef({ active: false, offsetX: 0, offsetY: 0 });

  if (!visible) return null;

  const handlePointerDown = (event) => {
    const panel = event.currentTarget.parentElement;
    const rect = panel.getBoundingClientRect();
    dragRef.current = {
      active: true,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
  };

  const handlePointerMove = (event) => {
    if (!dragRef.current.active) return;
    const nextX = Math.max(8, event.clientX - dragRef.current.offsetX);
    const nextY = Math.max(8, event.clientY - dragRef.current.offsetY);
    setPosition({ x: nextX, y: nextY });
  };

  const stopDragging = () => {
    dragRef.current.active = false;
  };

  const press = (token) => {
    const current = String(value || '');

    if (token === 'SHIFT') {
      setUpper((prev) => !prev);
      return;
    }
    if (token === 'DEL') {
      onChange(current.slice(0, -1));
      return;
    }
    if (token === 'C') {
      onChange('');
      return;
    }
    if (token === 'SPACE') {
      onChange(`${current} `);
      return;
    }

    onChange(`${current}${upper ? token : token.toLowerCase()}`);
  };

  return (
    <div
      className="fixed inset-0 z-[70] pointer-events-none"
      onPointerMove={handlePointerMove}
      onPointerUp={stopDragging}
      onPointerCancel={stopDragging}
    >
      <div
        className="pointer-events-auto fixed w-[min(92vw,860px)] rounded-2xl border border-slate-300 bg-white shadow-2xl"
        style={{ left: position.x, top: position.y }}
      >
        <div
          className="flex cursor-move items-center justify-between rounded-t-2xl bg-slate-100 px-4 py-3 border-b border-slate-200"
          onPointerDown={handlePointerDown}
        >
          <div className="inline-flex items-center gap-2 text-slate-700 font-semibold">
            <KeyboardIcon size={20} />
            <span>{title}</span>
          </div>
          <button type="button" className="btn-secondary !px-3 !py-1" onClick={onClose}>Cerrar</button>
        </div>

        <div className="p-4">
          <p className="mb-3 min-h-[2rem] rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-lg font-semibold text-slate-900 break-words">
            {value || ' '}
          </p>

          <div className="space-y-2">
            {KEYBOARD_ROWS.map((row, idx) => (
              <div key={`kbd-row-${idx}`} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${row.length}, minmax(0, 1fr))` }}>
                {row.map((token) => (
                  <button
                    key={token}
                    type="button"
                    className="btn-secondary !py-3 !text-base"
                    onClick={() => press(token)}
                  >
                    {upper ? token : token.toLowerCase()}
                  </button>
                ))}
              </div>
            ))}
          </div>

          <div className="mt-3 grid grid-cols-4 gap-2">
            <button type="button" className="btn-secondary !py-3" onClick={() => press('SHIFT')}>
              {upper ? 'Minúsc' : 'Mayúsc'}
            </button>
            <button type="button" className="btn-secondary !py-3" onClick={() => press('SPACE')}>Espacio</button>
            <button type="button" className="btn-secondary !py-3" onClick={() => press('DEL')}>Borrar</button>
            <button type="button" className="btn-danger !py-3" onClick={() => press('C')}>Limpiar</button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DraggableSearchKeyboard;
