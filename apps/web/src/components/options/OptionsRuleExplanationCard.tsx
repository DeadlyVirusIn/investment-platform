// Phase 11G — Strategy rule definition card.
// Read-only. Shows criteria + plain-English descriptions.
// No "recommended" or "best" wording.

import type { StrategyDef } from '@/lib/options/optionsApi';

export default function OptionsRuleExplanationCard({
  rule,
}: { rule: StrategyDef }) {
  return (
    <article className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3">
      <header className="mb-2">
        <h3 className="text-sm font-semibold text-zinc-100">{rule.name}</h3>
        <p className="mt-1 text-xs text-zinc-400">{rule.summary}</p>
      </header>
      <div className="text-xs uppercase tracking-wide text-zinc-500">
        Eligibility criteria (observation only)
      </div>
      <ul className="mt-1 space-y-1">
        {rule.criteria.map((c) => (
          <li
            key={c.code}
            className="rounded border border-zinc-800/60 bg-zinc-900/30 p-2"
          >
            <div className="text-xs font-semibold text-zinc-200">
              {c.label}
              <span className="ml-2 font-mono text-[10px] text-zinc-500">
                {c.code}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-zinc-400">{c.description}</p>
          </li>
        ))}
      </ul>
    </article>
  );
}
