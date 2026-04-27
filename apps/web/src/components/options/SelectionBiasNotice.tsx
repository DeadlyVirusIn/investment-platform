// Phase 11K — Selection-bias notice.
// Renders a neutral banner when the current filter view is narrow
// enough to introduce review selection bias.
//
// Trigger states (mirror backend `safety.detect_selection_bias`):
//   * Only HIGH_REVIEW_PRIORITY bucket selected
//   * Score-descending sort active (default — always true under
//     the deterministic ranking)
//   * Only one bucket selected
//
// Component is purely presentational — frontend computes the trigger
// and passes the active state in. Banner copy is fetched from the
// backend page-context endpoint to keep wording centralised.

import { useOptionsGuardrailsPageContext } from '@/lib/options/hooks';
import {
  BUCKET_HIGH_REVIEW_PRIORITY,
} from '@/lib/options/optionsApi';

export interface SelectionBiasState {
  bucketFilter?: string;
  selectedBuckets?: string[];
  sortMode?: string;
}

export function detectSelectionBiasTriggers(
  state: SelectionBiasState,
): string[] {
  const triggers: string[] = [];
  const sel = state.selectedBuckets ?? [];
  const sortMode = state.sortMode ?? 'SCORE_DESC';
  if (state.bucketFilter === BUCKET_HIGH_REVIEW_PRIORITY) {
    triggers.push('ONLY_HIGH_REVIEW_PRIORITY_BUCKET');
  } else if (sel.length === 1 && sel[0] === BUCKET_HIGH_REVIEW_PRIORITY) {
    triggers.push('ONLY_HIGH_REVIEW_PRIORITY_BUCKET');
  }
  if (sortMode === 'SCORE_DESC') {
    triggers.push('SCORE_DESC_SORT_ACTIVE');
  }
  if (state.bucketFilter && state.bucketFilter !== 'ALL'
      && state.bucketFilter !== BUCKET_HIGH_REVIEW_PRIORITY) {
    triggers.push('ONLY_ONE_BUCKET_SELECTED');
  } else if (sel.length === 1 && sel[0] !== BUCKET_HIGH_REVIEW_PRIORITY) {
    triggers.push('ONLY_ONE_BUCKET_SELECTED');
  }
  return triggers;
}

export default function SelectionBiasNotice({
  state,
}: { state: SelectionBiasState }) {
  const ctx = useOptionsGuardrailsPageContext();
  const triggers = detectSelectionBiasTriggers(state);
  if (triggers.length === 0) return null;
  // Spec banner copy (frontend fallback; backend supplies same text)
  const fallbackText = 'Viewing only a subset of observations may create selection bias. Review context is observational only and does not indicate suitability, preference, or an action.';
  const text = ctx.data?.page_context.selection_bias_banner_default_text
    ?? fallbackText;
  return (
    <div
      role="status"
      className="mb-3 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
    >
      <span aria-hidden="true">⚠</span>
      <div>
        <span className="font-semibold">Selection bias notice:</span>{' '}
        {text}
        <div className="mt-1 text-[10px] font-mono text-amber-200/70">
          triggers: {triggers.join(' · ')}
        </div>
      </div>
    </div>
  );
}
