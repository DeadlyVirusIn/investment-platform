import { useEffect, useState } from 'react';

const SHORTCUTS: Array<{ keys: string; desc: string }> = [
  { keys: 'j  /  ↓', desc: 'Focus next action' },
  { keys: 'k  /  ↑', desc: 'Focus previous action' },
  { keys: 'a', desc: 'Act on focused action' },
  { keys: 'd', desc: 'Dismiss focused action' },
  { keys: 'Enter  /  .', desc: 'Open rationale drawer' },
  { keys: 'Esc', desc: 'Close drawer / overlay' },
  { keys: '?', desc: 'Toggle this help overlay' },
];

export default function KeyboardHelpOverlay() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
      if (e.key === '?') {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === 'Escape' && open) {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 z-[60] flex items-center justify-center"
      onClick={() => setOpen(false)}
    >
      <div className="absolute inset-0 bg-black/60" />
      <div
        className="relative bg-surface-card border border-surface-border rounded-md shadow-lg p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">
          Keyboard Shortcuts
        </h2>
        <ul className="space-y-2">
          {SHORTCUTS.map(({ keys, desc }) => (
            <li key={keys} className="flex items-center justify-between text-sm">
              <kbd className="font-mono text-xs px-2 py-0.5 rounded bg-surface-hover border border-surface-border text-text-primary">
                {keys}
              </kbd>
              <span className="text-text-secondary">{desc}</span>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="mt-5 text-xs text-text-muted hover:text-text-primary"
        >
          Press Esc to close
        </button>
      </div>
    </div>
  );
}
