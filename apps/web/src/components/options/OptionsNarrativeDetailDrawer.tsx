// Phase 11J — Narrative detail drawer.
// Read-only. Bundles narrative + caveats + flags + checklist
// + ranking context. NO act-on-this CTA.

import {
  useOptionsDecisionFramingContext,
  useOptionsDecisionFramingNarrativeDetail,
} from '@/lib/options/hooks';
import OptionsHumanReviewChecklist from './OptionsHumanReviewChecklist';
import OptionsContextCaveatsPanel from './OptionsContextCaveatsPanel';
import { OptionsFlagList } from './OptionsFlagChip';
// Phase 11K guardrail panels — append-only integration; do NOT
// modify any 11H / 11I / 11J wiring above.
import ScoreInterpretationPanel from './ScoreInterpretationPanel';
import BucketMeaningPanel from './BucketMeaningPanel';
import RankingGuardrailBanner from './RankingGuardrailBanner';
import WhatThisDoesNotMean from './WhatThisDoesNotMean';

export default function OptionsNarrativeDetailDrawer({
  observationId, onClose,
}: { observationId: string | null; onClose: () => void }) {
  const detail = useOptionsDecisionFramingNarrativeDetail(observationId ?? undefined);
  const ctx = useOptionsDecisionFramingContext(observationId ?? undefined);
  if (observationId === null) return null;
  return (
    <aside className="fixed inset-y-0 right-0 z-30 w-full max-w-xl overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-4 text-zinc-100 shadow-xl">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Review narrative</h2>
          <p className="text-[11px] text-zinc-500">{observationId}</p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md border border-zinc-700 px-2 py-1 text-xs hover:bg-zinc-900"
        >
          Close
        </button>
      </header>
      {detail.isLoading || ctx.isLoading ? (
        <p className="text-sm text-zinc-400">Loading…</p>
      ) : detail.error || ctx.error ? (
        <p className="text-sm text-red-400">Error loading narrative.</p>
      ) : detail.data && ctx.data ? (
        <div className="space-y-4 text-sm">
          <section className="rounded-md border border-zinc-800 bg-zinc-900/30 p-3">
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Why it appears
            </div>
            <p className="mt-1 text-[12px] text-zinc-200">
              {detail.data.narrative.why_it_appears}
            </p>
            <div className="mt-3 text-xs uppercase tracking-wide text-zinc-400">
              Why caution is still required
            </div>
            <p className="mt-1 text-[11px] text-zinc-300">
              {detail.data.narrative.caution_paragraph}
            </p>
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-zinc-400">
              Score context
            </div>
            <ul className="mt-1 text-[11px] text-zinc-300">
              <li>Score: {detail.data.narrative.total_score} / 100</li>
              <li>Bucket: {detail.data.narrative.bucket_label}</li>
              <li>Rank position: {detail.data.narrative.rank_position ?? 'Unavailable'}</li>
              <li>Inclusion reason: {detail.data.inclusion_reason}</li>
            </ul>
          </section>

          {detail.data.narrative.caveats.length > 0 ? (
            <section>
              <div className="text-xs uppercase tracking-wide text-zinc-400">
                Caveats
              </div>
              <ul className="mt-1 list-disc list-inside text-[11px] text-zinc-300">
                {detail.data.narrative.caveats.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </section>
          ) : null}

          {detail.data.narrative.flags.length > 0 ? (
            <section>
              <div className="text-xs uppercase tracking-wide text-zinc-400">
                Model limitation flags
              </div>
              <div className="mt-1">
                <OptionsFlagList flags={detail.data.narrative.flags} />
              </div>
            </section>
          ) : null}

          <OptionsHumanReviewChecklist items={ctx.data.checklist} />
          <OptionsContextCaveatsPanel caveats={ctx.data.context_caveats} />

          {/* Phase 11K guardrails — append-only */}
          <ScoreInterpretationPanel observationId={observationId ?? undefined} />
          <BucketMeaningPanel observationId={observationId ?? undefined} />
          <RankingGuardrailBanner observationId={observationId ?? undefined} />
          <WhatThisDoesNotMean />

          <section className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-3 text-[11px] text-zinc-200">
            {detail.data.narrative.non_action_footer}
          </section>
        </div>
      ) : null}
    </aside>
  );
}
