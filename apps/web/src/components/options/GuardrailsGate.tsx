// Phase 11L — Visual gate for 11K interpretation panels.
// When toggle is OFF, panel renders dimmed but stays mounted so
// expandable details remain accessible. When ON (default), panel
// gets a subtle accent border to highlight 11K guardrail surfaces.

import { useGuardrailsToggle } from '@/lib/options/guardrailsToggle';

export default function GuardrailsGate({
  children,
  hideWhenOff = false,
}: {
  children: React.ReactNode;
  /** When true, returns null while toggle is OFF (use sparingly —
   * 11K mandates the universal "What this does NOT mean" remain
   * always visible). */
  hideWhenOff?: boolean;
}) {
  const { on } = useGuardrailsToggle();
  if (!on && hideWhenOff) return null;
  if (!on) {
    return (
      <div className="opacity-60 transition-opacity duration-200">
        {children}
      </div>
    );
  }
  return (
    <div
      className="transition-all duration-200"
      style={{
        boxShadow: 'var(--shadow-soft)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      {children}
    </div>
  );
}
