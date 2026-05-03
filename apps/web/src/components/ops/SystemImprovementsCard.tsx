// Phase SYSTEM-ALPHA-3 — top suggestions + apply/ignore buttons.

import {
  useApplySuggestion, useIgnoreSuggestion, useRollbackRule,
  useRuleSuggestions, useActiveRules,
} from "@/lib/alpha/rules";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

export default function SystemImprovementsCard() {
  const { data } = useRuleSuggestions("pending");
  const { data: active } = useActiveRules();
  const apply = useApplySuggestion();
  const ignore = useIgnoreSuggestion();
  const rollback = useRollbackRule();

  const sugs = (data?.suggestions ?? []).slice(0, 3);
  const rules = (active?.rules ?? []).slice(0, 3);

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-3">
        <div>
          <Label>System Improvements</Label>
          <div className="u-caption-2 mt-0.5">
            Deterministic rule suggestions · SYSTEM-ALPHA-3
          </div>
        </div>
        <span className={cn("u-chip",
          sugs.length > 0 ? "u-chip-accent" : "u-chip-neutral")}>
          {sugs.length} pending
        </span>
      </div>

      {sugs.length === 0 ? (
        <div className="u-caption-2 italic mb-3">
          No pending suggestions. Run{" "}
          <code className="u-mono-sm">POST /api/alpha/rules/refresh</code>.
        </div>
      ) : (
        <ul className="divide-y divide-b1 mb-3">
          {sugs.map(s => (
            <li key={s.id} className="py-2.5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={cn("u-chip", riskTone(s.risk_level))}>
                    {s.risk_level}
                  </span>
                  <span className="u-mono-sm text-fg-3">{s.rule_type}</span>
                </div>
                <span className="u-mono-sm text-fg-2">
                  n={s.sample_size} · {Math.round(s.confidence * 100)}%
                </span>
              </div>
              <div className="u-caption text-fg-2 mb-2">
                {s.description}
              </div>
              <div className="flex gap-2">
                <button
                  className={cn("u-chip",
                    s.auto_applicable ? "u-chip-success" : "u-chip-warning")}
                  disabled={apply.isPending}
                  onClick={() => apply.mutate({
                    suggestion_id: s.id,
                    force: !s.auto_applicable,
                  })}
                  title={s.auto_applicable ? "safe auto-apply"
                    : "force apply (medium-risk)"}>
                  apply
                </button>
                <button
                  className="u-chip u-chip-neutral"
                  disabled={ignore.isPending}
                  onClick={() => ignore.mutate({
                    suggestion_id: s.id, reason: "operator ignored",
                  })}>
                  ignore
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {rules.length > 0 && (
        <div className="pt-3 border-t border-b1">
          <div className="u-label-sm mb-2">Active rules</div>
          <ul className="space-y-1">
            {rules.map((r: any) => (
              <li key={r.rule_id}
                  className="flex items-center justify-between u-caption-2">
                <span className="u-mono-sm text-fg-2 truncate">
                  {r.rule_id}
                </span>
                <button className="u-chip u-chip-neutral"
                        disabled={rollback.isPending}
                        onClick={() => rollback.mutate({
                          rule_id: r.rule_id,
                          reason: "operator rollback",
                        })}>
                  rollback
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function riskTone(level: string) {
  if (level === "low")    return "u-chip-success";
  if (level === "medium") return "u-chip-warning";
  return "u-chip-danger";
}
