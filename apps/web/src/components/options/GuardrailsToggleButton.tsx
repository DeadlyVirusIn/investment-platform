// Phase 11L — Guardrails ON/OFF toggle button.
// Default state: ON. Persists in localStorage. UI-only.

import { useGuardrailsToggle } from '@/lib/options/guardrailsToggle';

export default function GuardrailsToggleButton() {
  const { on, toggle } = useGuardrailsToggle();
  return (
    <button
      type="button"
      onClick={toggle}
      title={
        on
          ? 'Guardrails ON — 11K interpretation panels emphasised'
          : 'Guardrails OFF — interpretation panels dimmed (universal disclaimers stay visible)'
      }
      className={[
        'inline-flex items-center gap-2 rounded-md border px-3 py-1 text-xs',
        'transition-colors duration-150',
        on
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
          : 'border-zinc-700/60 bg-zinc-900/40 text-zinc-300',
      ].join(' ')}
      aria-pressed={on}
    >
      <span aria-hidden="true">{on ? '🛡' : '○'}</span>
      <span className="font-semibold">
        Guardrails {on ? 'ON' : 'OFF'}
      </span>
    </button>
  );
}
