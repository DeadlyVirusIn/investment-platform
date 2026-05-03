import type { DecisionReviewAvB, IntelligenceSummary } from '@/types';

/**
 * Deterministic decision-quality verdict derived from Intelligence summary.
 *
 *   GREEN  — accepted_avg ≥ blocked_avg AND accepted_win_rate ≥ 0.50
 *   RED    — accepted_win_rate == 0 AND accepted_count ≥ 3
 *            OR blocked_avg_return ≥ accepted_avg + 2%
 *   YELLOW — otherwise / inconclusive
 *   UNKNOWN — insufficient sample
 */

export type Verdict = 'green' | 'yellow' | 'red' | 'unknown';


function num(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}


export function deriveVerdict(avb: DecisionReviewAvB | null): Verdict {
  if (!avb) return 'unknown';
  const acceptedAvg = num(avb.accepted_avg_return_pct);
  const blockedAvg = num(avb.blocked_avg_return_pct);
  const wr = num(avb.accepted_win_rate);
  const count = avb.accepted_count ?? 0;

  if (count === 0) return 'unknown';

  // RED conditions
  if (wr === 0 && count >= 3) return 'red';
  if (acceptedAvg !== null && blockedAvg !== null && blockedAvg - acceptedAvg > 0.02) {
    return 'red';
  }

  // GREEN conditions
  if (wr !== null && wr >= 0.5) {
    if (acceptedAvg === null || blockedAvg === null || acceptedAvg >= blockedAvg) {
      return 'green';
    }
  }

  return 'yellow';
}


const CONFIG: Record<Verdict, { label: string; box: string; dot: string }> = {
  green: {
    label: 'Decision quality: Strong',
    box: 'border-success/40 bg-success/10 text-success',
    dot: 'bg-success',
  },
  yellow: {
    label: 'Decision quality: Mixed',
    box: 'border-warning/40 bg-warning/10 text-warning',
    dot: 'bg-warning',
  },
  red: {
    label: 'Decision quality: Weak',
    box: 'border-danger/40 bg-danger/10 text-danger',
    dot: 'bg-danger',
  },
  unknown: {
    label: 'Decision quality: Insufficient sample',
    box: 'border-surface-border bg-surface-hover text-text-muted',
    dot: 'bg-text-muted',
  },
};


function verdictMessage(
  verdict: Verdict, avb: DecisionReviewAvB | null,
): string | null {
  if (!avb) return null;
  const acceptedAvg = num(avb.accepted_avg_return_pct);
  const blockedAvg = num(avb.blocked_avg_return_pct);
  const wr = num(avb.accepted_win_rate);
  const count = avb.accepted_count ?? 0;

  if (verdict === 'red') {
    if (wr === 0 && count >= 3) {
      return `${count} trades, 0 wins — signal quality deteriorating.`;
    }
    if (acceptedAvg !== null && blockedAvg !== null) {
      return `Blocked-alpha outperforming accepted by ${(100 * (blockedAvg - acceptedAvg)).toFixed(1)}%.`;
    }
  }
  if (verdict === 'yellow') {
    return `Mixed: ${count} trade(s), win rate ${wr !== null ? (wr * 100).toFixed(0) + '%' : '—'}.`;
  }
  if (verdict === 'green') {
    return `${count} trade(s), win rate ${wr !== null ? (wr * 100).toFixed(0) + '%' : '—'}.`;
  }
  return 'Too few trades to evaluate yet.';
}


export default function DecisionQualityRibbon({
  intelligence,
  className = '',
}: {
  intelligence: IntelligenceSummary | undefined;
  className?: string;
}) {
  const avb = intelligence?.decision_review?.accepted_vs_blocked ?? null;
  const verdict = deriveVerdict(avb);
  const cfg = CONFIG[verdict];
  const msg = verdictMessage(verdict, avb);

  return (
    <div
      className={`flex items-center gap-3 rounded-md border px-4 py-2 ${cfg.box} ${className}`}
      role="status"
    >
      <span className={`w-2 h-2 rounded-full ${cfg.dot}`} aria-hidden />
      <span className="text-sm font-semibold tracking-wide">{cfg.label}</span>
      {msg && (
        <span className="text-xs opacity-80 ml-2">{msg}</span>
      )}
    </div>
  );
}
