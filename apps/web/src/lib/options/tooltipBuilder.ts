// Phase 11M — Standardised tooltip builder.
//
// All tooltips on options pages should follow this 3-part structure:
//   description → limitation → non-action clarification
//
// `buildTooltip(...)` joins the parts with " · " so screen readers
// + browser tooltips render a consistent rhythm. Frontend-only;
// pure helper.

export interface TooltipParts {
  description: string;
  limitation?: string;
  nonAction?: string;
}

export const NON_ACTION_DEFAULT =
  'This is review context only — not advice, recommendation, or '
  + 'execution guidance.';

export function buildTooltip({
  description,
  limitation,
  nonAction,
}: TooltipParts): string {
  const parts: string[] = [description.trim()];
  if (limitation && limitation.trim()) {
    parts.push(limitation.trim());
  }
  parts.push((nonAction ?? NON_ACTION_DEFAULT).trim());
  return parts.join(' · ');
}
