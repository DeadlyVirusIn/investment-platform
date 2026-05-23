// Local-first reflection capture. Renders prompt + textarea; persists
// to localStorage on save. No network, no grading, no notifications.
//
// Ported (Phase 5) from wise-start-bloom-31433ca8.
// Adaptations from upstream:
//   - cn from '@/lib/cn' (was '@/lib/utils')
//   - PillButton from V2 path (was Lovable primitives)
//   - Token classes (text-ink, bg-sage-light, etc.) → V2 CSS vars
//     used inside .v2-root scope.

import { useEffect, useState } from 'react';
import { Check, NotebookPen, Trash2 } from 'lucide-react';
import {
  saveReflection,
  deleteReflection,
  useReflection,
  type ReflectionKind,
} from '../lib/reflections';
import { PillButton } from './ui/PillButton';
import { cn } from '@/lib/cn';

export function ReflectionCapture({
  kind,
  targetId,
  prompt,
  placeholder = 'Write whatever comes — nothing is saved or graded.',
  className,
  compact,
}: {
  kind: ReflectionKind;
  targetId: string;
  prompt: string;
  placeholder?: string;
  className?: string;
  compact?: boolean;
}) {
  const existing = useReflection(kind, targetId);
  const [body, setBody] = useState(existing?.body ?? '');
  const [saved, setSaved] = useState(false);

  // Hydrate from store when route changes.
  useEffect(() => {
    setBody(existing?.body ?? '');
  }, [existing?.id, existing?.body]);

  function handleSave() {
    if (!body.trim()) return;
    saveReflection({ kind, targetId, prompt, body: body.trim() });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  function handleDelete() {
    if (!existing) return;
    deleteReflection(existing.id);
    setBody('');
  }

  return (
    <div
      className={cn(
        'rounded-xl border surface-drawer p-4 lg:p-5',
        'border-hairline',
        className,
      )}
    >
      <div className="flex items-center gap-2 mb-2">
        <NotebookPen className="size-3.5 ink-muted" aria-hidden />
        <p className="text-meta ink-muted">Reflection</p>
        {existing && (
          <span className="ml-auto text-[11px] ink-fainter">
            Saved {new Date(existing.createdAt).toLocaleDateString()}
          </span>
        )}
      </div>
      <p className="text-[13.5px] ink-muted leading-relaxed italic mb-3">
        "{prompt}"
      </p>
      <label htmlFor={`reflection-${kind}-${targetId}`} className="sr-only">
        Reflection on {prompt}
      </label>
      <textarea
        id={`reflection-${kind}-${targetId}`}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={compact ? 3 : 4}
        className="w-full p-3 rounded-lg surface-elevated border border-hairline text-[14px] ink-primary leading-relaxed font-sans focus:outline-none focus:ring-2 focus:ring-[var(--ink-muted)] resize-none placeholder:ink-fainter"
        placeholder={placeholder}
      />
      <div className="flex items-center justify-between gap-3 mt-3">
        <p className="text-[11.5px] ink-fainter leading-snug">
          Stored on this device only. Never sent anywhere.
        </p>
        <div className="flex items-center gap-2">
          {existing && (
            <button
              type="button"
              onClick={handleDelete}
              className="inline-flex items-center gap-1 text-[12px] font-semibold ink-fainter hover:ink-muted transition-colors h-9 px-3 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ink-muted)]"
              aria-label="Delete reflection"
            >
              <Trash2 className="size-3.5" aria-hidden /> Clear
            </button>
          )}
          <PillButton
            type="button"
            onClick={handleSave}
            disabled={!body.trim()}
            className="disabled:opacity-40 disabled:cursor-not-allowed h-10 px-4 text-[12.5px]"
          >
            {saved ? (
              <>
                <Check className="size-3.5" aria-hidden /> Saved
              </>
            ) : existing ? (
              'Update'
            ) : (
              'Save reflection'
            )}
          </PillButton>
        </div>
      </div>
    </div>
  );
}
