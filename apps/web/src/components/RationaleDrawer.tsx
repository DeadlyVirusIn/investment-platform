import { useEffect } from 'react';
import { useAction } from '@/lib/hooks';
import Badge from './Badge';
import { ErrorState, LoadingState } from './States';

interface Props {
  actionId: string;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <h3 className="text-[11px] uppercase tracking-wider text-text-secondary font-semibold mb-2">
        {title}
      </h3>
      <div className="text-sm">{children}</div>
    </section>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between py-1 border-b border-surface-border/50 text-xs">
      <span className="text-text-secondary">{k}</span>
      <span className="font-mono text-text-primary">{v}</span>
    </div>
  );
}

export default function RationaleDrawer({ actionId, onClose }: Props) {
  const q = useAction(actionId);

  // Escape to close
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-label="Action detail"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60" />
      <aside
        className="relative w-full max-w-[480px] h-full bg-surface-card border-l border-surface-border p-6 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 text-text-secondary hover:text-text-primary"
          aria-label="Close drawer"
        >
          ✕
        </button>
        {q.isLoading && <LoadingState />}
        {q.error && <ErrorState message={String(q.error)} />}
        {q.data && (
          <>
            <div className="flex items-center gap-2 mb-1">
              <Badge tone={q.data.priority_tier === 'CRT' ? 'negative' : q.data.priority_tier === 'HIGH' ? 'warning' : 'muted'}>
                {q.data.priority_tier}
              </Badge>
              <Badge tone="info">{q.data.kind}</Badge>
              <span className="font-mono font-semibold text-lg">{q.data.symbol}</span>
            </div>
            <p className="text-text-secondary text-sm mb-4">{q.data.rationale_short}</p>

            <Section title="Signal">
              <KV k="priority" v={q.data.priority} />
              <KV k="confidence" v={q.data.confidence ?? '—'} />
              <KV k="composite_score" v={q.data.composite_score ?? '—'} />
              <KV k="urgency" v={q.data.urgency} />
              <KV k="origin" v={q.data.origin} />
              <KV k="status" v={q.data.status} />
              {q.data.decay_at && <KV k="decay_at" v={q.data.decay_at} />}
            </Section>

            <Section title="Factor contributions">
              {q.data.factor_top && q.data.factor_top.length > 0 ? (
                <ul className="space-y-1 font-mono text-xs">
                  {q.data.factor_top.map((f) => (
                    <li key={f.key} className="flex justify-between items-center py-1 border-b border-surface-border/50">
                      <span className="text-text-secondary">{f.key}</span>
                      <span className="text-text-muted">
                        value={f.value ?? '—'}
                      </span>
                      <span className={f.contribution >= 0 ? 'text-success' : 'text-danger'}>
                        {f.contribution >= 0 ? '+' : ''}
                        {f.contribution.toFixed(3)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-text-muted text-xs">No factor breakdown.</span>
              )}
            </Section>

            <Section title="Impact">
              {q.data.impact_estimate ? (
                <div className="space-y-1">
                  {Object.entries(q.data.impact_estimate).map(([k, v]) => (
                    <KV key={k} k={k} v={String(v)} />
                  ))}
                </div>
              ) : (
                <span className="text-text-muted text-xs">—</span>
              )}
            </Section>

            <Section title="Dependencies">
              {q.data.dependencies ? (
                <div className="space-y-1">
                  {q.data.dependencies.requires_cash != null && (
                    <KV k="requires_cash" v={`$${q.data.dependencies.requires_cash.toFixed(2)}`} />
                  )}
                  {q.data.dependencies.conflicts_with && q.data.dependencies.conflicts_with.length > 0 && (
                    <KV k="conflicts_with" v={q.data.dependencies.conflicts_with.length} />
                  )}
                  {q.data.dependencies.blocks_on && q.data.dependencies.blocks_on.length > 0 && (
                    <KV k="blocks_on" v={q.data.dependencies.blocks_on.join(', ')} />
                  )}
                </div>
              ) : (
                <span className="text-text-muted text-xs">—</span>
              )}
            </Section>

            {q.data.acted_trade_id && (
              <Section title="Trade">
                <KV k="trade_id" v={<span className="text-[10px]">{q.data.acted_trade_id}</span>} />
                <KV k="acted_at" v={q.data.acted_at ?? '—'} />
              </Section>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
