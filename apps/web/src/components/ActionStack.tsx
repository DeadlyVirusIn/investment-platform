import { useCallback, useEffect, useMemo, useState } from 'react';
import { useActions, useAct, useDismiss } from '@/lib/hooks';
import ActionCard from './ActionCard';
import RationaleDrawer from './RationaleDrawer';
import { EmptyState, ErrorState, LoadingState } from './States';

const MAX_VISIBLE = 10;

export default function ActionStack({ compact = false }: { compact?: boolean }) {
  const q = useActions('pending', MAX_VISIBLE);
  const act = useAct();
  const dismiss = useDismiss();
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [focusIdx, setFocusIdx] = useState(0);

  const actions = useMemo(() => (q.data?.actions ?? []).slice(0, MAX_VISIBLE), [q.data]);
  const conflictSymbols = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of q.data?.actions ?? []) m[a.id] = a.symbol;
    return m;
  }, [q.data]);

  // Clamp focus when list shrinks (e.g. after act/dismiss)
  useEffect(() => {
    if (focusIdx >= actions.length && actions.length > 0) {
      setFocusIdx(actions.length - 1);
    }
  }, [actions.length, focusIdx]);

  const focusedAction = actions[focusIdx];

  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (drawerId) return;
      if (actions.length === 0) return;
      // Ignore when typing in inputs
      const target = e.target as HTMLElement | null;
      if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusIdx((i) => Math.min(i + 1, actions.length - 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === 'a' && focusedAction) {
        e.preventDefault();
        if (focusedAction.status === 'pending') act.mutate(focusedAction.id);
      } else if (e.key === 'd' && focusedAction) {
        e.preventDefault();
        if (focusedAction.status === 'pending') {
          dismiss.mutate({ id: focusedAction.id, reason: 'keyboard_dismiss' });
        }
      } else if ((e.key === 'Enter' || e.key === '.') && focusedAction) {
        e.preventDefault();
        setDrawerId(focusedAction.id);
      } else if (e.key === 'Escape') {
        setDrawerId(null);
      }
    },
    [drawerId, actions, focusedAction, act, dismiss],
  );

  useEffect(() => {
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onKey]);

  if (q.isLoading) return <LoadingState />;
  if (q.error) return <ErrorState message={String(q.error)} />;

  if (actions.length === 0) {
    return (
      <EmptyState
        title="No actions right now"
        hint="Engine paused for regime or all candidates blocked. Check Jobs Health if stale."
      />
    );
  }

  return (
    <>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] uppercase tracking-wider text-text-secondary font-semibold">
          Actions ({actions.length})
        </span>
        <span className="text-[10px] text-text-muted font-mono hidden md:block">
          j/k nav · a act · d dismiss · Enter detail
        </span>
      </div>
      <ul
        role="list"
        aria-label="Pending actions"
        className={`space-y-2 ${compact ? 'max-h-[480px] overflow-y-auto' : ''}`}
      >
        {actions.map((a, i) => (
          <ActionCard
            key={a.id}
            action={a}
            focused={i === focusIdx}
            pending={act.isPending && act.variables === a.id}
            conflictSymbols={conflictSymbols}
            onAct={(id) => act.mutate(id)}
            onDismiss={(id) => dismiss.mutate({ id, reason: 'user_dismiss' })}
            onDetail={(id) => setDrawerId(id)}
          />
        ))}
      </ul>
      {drawerId && <RationaleDrawer actionId={drawerId} onClose={() => setDrawerId(null)} />}
    </>
  );
}
