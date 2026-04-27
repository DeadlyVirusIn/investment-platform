// Phase 11J — Human review checklist.
// Frozen list. Action-safe wording. NO buy/sell/execute/enter/exit.

import type { ChecklistItem } from '@/lib/options/optionsApi';

export default function OptionsHumanReviewChecklist({
  items,
}: { items: ChecklistItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section>
      <header className="mb-2">
        <h3 className="text-sm font-semibold text-zinc-100">
          Human review checklist
        </h3>
        <p className="text-[11px] text-zinc-500">
          Manual verification steps before any further inspection.
        </p>
      </header>
      <ul className="space-y-2">
        {items.map((it) => (
          <li
            key={it.code}
            className="rounded border border-zinc-800 bg-zinc-900/30 p-2"
          >
            <div className="flex items-center gap-2">
              <span aria-hidden="true">☐</span>
              <span className="text-sm font-semibold text-zinc-100">
                {it.label}
              </span>
              <span className="ml-auto font-mono text-[10px] text-zinc-500">
                {it.code}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-zinc-400">{it.description}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
