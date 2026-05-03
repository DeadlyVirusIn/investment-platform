// Phase SYSTEM-ALPHA-7 — "Context Adjustments" card for Ops.

import {
  useActiveContexts, useApplyContext, useContextRecs,
  useRevertContext,
} from "@/lib/alpha/context";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function ContextAdjustmentsCard() {
  const { data: recs } = useContextRecs();
  const { data: active } = useActiveContexts();
  const apply = useApplyContext();
  const revert = useRevertContext();

  const recList = recs?.recommendations ?? [];
  const activeRows = active?.rows ?? [];

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>Context Adjustments</Label>
          <div className="u-caption-2 mt-0.5">
            Per-bucket multipliers · engine × regime × mode
          </div>
        </div>
        <span className={cn("u-chip",
          recList.length ? "u-chip-accent" : "u-chip-neutral")}>
          {recList.length} rec
        </span>
      </div>

      {recList.length === 0 ? (
        <div className="u-caption-2 italic mb-3">
          No context adjustments pending. Run{" "}
          <code className="u-mono-sm">
            POST /api/alpha/context/refresh
          </code>.
        </div>
      ) : (
        <ul className="divide-y divide-b1 mb-3">
          {recList.map(r => (
            <li key={r.context_key} className="py-2.5">
              <div className="flex items-center justify-between mb-1">
                <span className="u-mono-sm text-fg font-semibold">
                  Engine {r.context.engine} · {r.context.regime} ·{" "}
                  {r.context.mode}
                </span>
                <span className={cn("u-chip",
                  r.auto_applicable ? "u-chip-success" : "u-chip-warning")}>
                  {r.auto_applicable ? "auto-safe" : "review"}
                </span>
              </div>
              <div className="u-caption text-fg-2 mb-1">
                {r.reason}
              </div>
              <div className="u-caption-2 flex items-center gap-3 mb-2">
                <span>
                  <span className="text-danger">
                    {r.current_multiplier}
                  </span>
                  {" → "}
                  <span className="text-success">
                    {r.proposed_multiplier}
                  </span>
                </span>
                <span>n={r.stats.sample_size}</span>
                <span>conf {(r.confidence * 100).toFixed(0)}%</span>
              </div>
              <button
                className="u-chip u-chip-accent"
                disabled={apply.isPending}
                onClick={() => apply.mutate(r)}>
                apply
              </button>
            </li>
          ))}
        </ul>
      )}

      {activeRows.length > 0 && (
        <div className="pt-2 border-t border-b1">
          <div className="u-label-sm mb-2">Active contexts</div>
          <ul className="space-y-1">
            {activeRows.map(r => (
              <li key={r.context_key}
                  className="flex items-center justify-between u-caption-2">
                <span className="u-mono-sm text-fg-2">
                  {r.context?.engine} · {r.context?.regime} ·{" "}
                  {r.context?.mode}
                </span>
                <span className="flex items-center gap-2">
                  <span className="u-mono-sm text-fg">{r.multiplier}</span>
                  <button className="u-chip u-chip-neutral"
                          disabled={revert.isPending}
                          onClick={() => revert.mutate(r.context_key)}>
                    revert
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
