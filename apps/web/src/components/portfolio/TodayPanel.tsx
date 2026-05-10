// TodayPanel — composed "Today" command center.
// Left: AI summary (posture + body)
// Middle: Top action (uses PriorityAction styles inline)
// Right: mini cards (Risk / Income / Watchlist / Freshness)

import type { LatestPrice } from "@/lib/picks/api";
import {
  fmtConfidencePct, confidenceLabel, actionTitle,
} from "@/lib/picks/api";
import type { Briefing as BriefingT, PriorityResult, PicksFilter } from "@/lib/picks/copilot";


export interface TodayPanelProps {
  briefing: BriefingT;
  priority: PriorityResult | null;
  priorityPrice: LatestPrice | null | undefined;
  watchlistCount: number;
  riskCount: number;
  monthlyPremium: number | null;
  onOpenCockpit: (id: string) => void;
  onFilterChange: (f: PicksFilter) => void;
}


function fmtRel(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


function fmtPrice(p: number | null): string {
  if (p == null) return "—";
  if (p >= 1000) return `$${p.toFixed(0)}`;
  return `$${p.toFixed(2)}`;
}


function MiniCard({ label, value, tone, sub }: {
  label: string; value: string; tone?: "good" | "bad" | "warn" | "default"; sub?: string;
}) {
  return (
    <div className="today-mini" data-tone={tone ?? "default"}>
      <div className="today-mini-label">{label}</div>
      <div className="today-mini-value">{value}</div>
      {sub && <div className="today-mini-sub">{sub}</div>}
    </div>
  );
}


export default function TodayPanel({
  briefing, priority, priorityPrice, watchlistCount, riskCount,
  monthlyPremium, onOpenCockpit, onFilterChange,
}: TodayPanelProps) {
  return (
    <section className="today-panel" data-test="today-panel">
      {/* Left — AI summary */}
      <aside className="today-summary">
        <span className="today-eyebrow">AI summary</span>
        <div className="today-posture-row">
          <span className="today-posture" data-posture={briefing.posture}>
            <span className="today-posture-dot" />
            {briefing.postureLabel}
          </span>
        </div>
        <h2 className="today-headline">{briefing.headline}</h2>
        <p className="today-body">{briefing.body}</p>
      </aside>

      {/* Middle — Top action */}
      <div className="today-action">
        <span className="today-eyebrow">Top action today</span>
        {priority ? (
          <>
            <div className="today-action-row">
              <span className="today-action-pill" data-action={priority.pick.adjusted_action ?? priority.pick.action}>
                {priority.pick.adjusted_action ?? priority.pick.action}
              </span>
              <h2 className="today-action-symbol">{priority.pick.symbol ?? "—"}</h2>
              {priorityPrice && (
                <span className="today-action-price">{fmtPrice(priorityPrice.close)}</span>
              )}
            </div>
            <div className="today-action-title">{actionTitle(priority.pick.adjusted_action ?? priority.pick.action)}</div>
            <p className="today-action-why">{priority.reason}</p>
            <div className="today-action-meta">
              <span>{confidenceLabel(priority.pick.adjusted_confidence ?? priority.pick.confidence)} · {fmtConfidencePct(priority.pick.adjusted_confidence ?? priority.pick.confidence)}</span>
            </div>
            <div className="today-action-ctas">
              <button
                type="button"
                className="today-cta today-cta-primary"
                onClick={() => onOpenCockpit(priority.pick.id)}
              >
                Open research cockpit →
              </button>
              {priority.ctaSecondaryFilter && (
                <button
                  type="button"
                  className="today-cta today-cta-secondary"
                  onClick={() => onFilterChange(priority.ctaSecondaryFilter!)}
                >
                  {priority.ctaSecondary}
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="today-empty">No actionable picks right now.</div>
        )}
      </div>

      {/* Right — mini cards */}
      <div className="today-mini-grid">
        <MiniCard
          label="Posture risk"
          value={String(riskCount)}
          tone={riskCount > 0 ? "warn" : "default"}
          sub="Stale, thin, or sell"
        />
        <MiniCard
          label="Watchlist"
          value={String(watchlistCount)}
          tone="default"
          sub="Hold candidates"
        />
        <MiniCard
          label="Premium MTD"
          value={monthlyPremium != null && monthlyPremium > 0
            ? `$${monthlyPremium.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
            : "—"}
          tone={monthlyPremium != null && monthlyPremium > 0 ? "good" : "default"}
          sub={monthlyPremium != null && monthlyPremium > 0 ? "Options income" : "Not tracked yet"}
        />
        <MiniCard
          label="Latest signal"
          value={fmtRel(briefing.freshestAtIso)}
          tone="default"
          sub={briefing.staleCount > 0 ? `${briefing.staleCount} stale` : "Engine fresh"}
        />
      </div>
    </section>
  );
}
