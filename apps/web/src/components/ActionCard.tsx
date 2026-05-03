import type { ActionItem, ActionKind, ActionTier } from '@/types';
import Badge from './Badge';

interface Props {
  action: ActionItem;
  onAct: (id: string) => void;
  onDismiss: (id: string) => void;
  onDetail: (id: string) => void;
  pending?: boolean;
  focused?: boolean;
  /** Map of action_id → symbol (from the current list) to resolve conflict refs. */
  conflictSymbols?: Record<string, string>;
}

const KIND_TONE: Record<ActionKind, 'positive' | 'negative' | 'warning' | 'info' | 'muted'> = {
  BUY: 'positive',
  EXIT: 'negative',
  TRIM: 'warning',
  WATCH: 'info',
  HOLD: 'muted',
  RESOLVE_ALERT: 'warning',
};

const TIER_TONE: Record<ActionTier, 'negative' | 'warning' | 'muted'> = {
  CRT: 'negative',
  HIGH: 'warning',
  NRM: 'muted',
};

function fmtContribution(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}`;
}

function fmtImpact(a: ActionItem): string {
  if (!a.impact_estimate) return '';
  const delta = a.impact_estimate.position_delta_pct;
  const notional = a.impact_estimate.notional_usd;
  if (delta != null) {
    const sign = delta >= 0 ? '+' : '';
    const notPart = notional != null ? ` · $${notional.toFixed(0)}` : '';
    return `impact: ${sign}${delta.toFixed(1)}%${notPart}`;
  }
  if (notional != null) return `notional: $${notional.toFixed(0)}`;
  return '';
}

function DecayDot({ at }: { at: string }) {
  const msLeft = new Date(at).getTime() - Date.now();
  if (msLeft <= 0) return <span className="ml-2 text-[10px] text-danger">expired</span>;
  const critical = msLeft < 3_600_000;
  return (
    <span
      aria-label={`decays at ${at}`}
      title={`decays at ${at}`}
      className={`ml-2 inline-block w-2 h-2 rounded-full ${
        critical ? 'bg-danger animate-pulse' : 'bg-warning'
      }`}
    />
  );
}

export default function ActionCard({
  action: a,
  onAct,
  onDismiss,
  onDetail,
  pending,
  focused,
  conflictSymbols,
}: Props) {
  const blocked = a.status === 'blocked';
  const disabled = pending || blocked || a.status !== 'pending';
  const conflictIds = a.dependencies?.conflicts_with ?? [];
  const conflictLabels = conflictSymbols
    ? conflictIds.map((cid) => conflictSymbols[cid]).filter(Boolean)
    : [];
  const conflictTitle =
    conflictLabels.length > 0
      ? `conflicts: ${conflictLabels.join(', ')}`
      : conflictIds.length > 0
      ? `${conflictIds.length} conflict${conflictIds.length > 1 ? 's' : ''}`
      : '';
  const decayExpired =
    !!a.decay_at && new Date(a.decay_at).getTime() <= Date.now();

  return (
    <div
      role="listitem"
      tabIndex={0}
      data-action-id={a.id}
      aria-disabled={disabled}
      className={[
        'rounded-[10px] border bg-surface-card px-4 py-3 flex flex-col gap-1.5',
        blocked ? 'border-l-[3px] border-l-danger border-surface-border' : 'border-surface-border',
        focused ? 'ring-1 ring-accent' : '',
      ].join(' ')}
    >
      {/* Row 1: tier/kind/symbol/rationale */}
      <div className="flex items-center gap-2">
        <Badge tone={TIER_TONE[a.priority_tier]}>{a.priority_tier}</Badge>
        <Badge tone={KIND_TONE[a.kind]}>{a.kind}</Badge>
        <span className="font-mono font-medium text-sm text-text-primary">{a.symbol}</span>
        <span className="text-text-secondary text-xs truncate flex-1" title={a.rationale_short}>
          — {a.rationale_short}
        </span>
        {a.decay_at && <DecayDot at={a.decay_at} />}
      </div>

      {/* Row 2: factor top-3 inline */}
      {a.factor_top && a.factor_top.length > 0 && (
        <div className="text-[11px] text-text-muted font-mono">
          {a.factor_top.slice(0, 3).map((f) => (
            <span key={f.key} className="mr-3">
              {f.key}{' '}
              <span className={f.contribution >= 0 ? 'text-success' : 'text-danger'}>
                {fmtContribution(f.contribution)}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Row 3: impact + actions */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-text-muted">
          {fmtImpact(a)}
          {conflictIds.length > 0 && (
            <span
              className="ml-3 text-warning"
              title={conflictTitle}
            >
              conflict: {conflictLabels.length > 0 ? conflictLabels.join(', ') : conflictIds.length}
            </span>
          )}
          {blocked && (
            <span className="ml-3 text-danger" title={a.dependencies?.blocks_on?.join(', ')}>
              blocked{a.dependencies?.blocks_on?.length ? `: ${a.dependencies.blocks_on.join(', ')}` : ''}
            </span>
          )}
          {decayExpired && <span className="ml-3 text-danger">expired</span>}
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => onAct(a.id)}
            disabled={disabled}
            className="px-3 py-1 rounded-md bg-accent hover:bg-accent-hover text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label={`Act on ${a.kind} ${a.symbol}`}
          >
            {pending ? '…' : 'Act'}
          </button>
          <button
            type="button"
            onClick={() => onDetail(a.id)}
            className="px-2 py-1 text-xs text-text-secondary hover:text-text-primary"
            aria-label={`Open detail for ${a.symbol}`}
          >
            Detail
          </button>
          <button
            type="button"
            onClick={() => onDismiss(a.id)}
            disabled={a.status !== 'pending'}
            className="px-2 py-1 text-xs text-text-muted hover:text-text-primary disabled:opacity-40"
            aria-label={`Dismiss action ${a.symbol}`}
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
