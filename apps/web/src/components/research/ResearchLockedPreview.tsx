// Phase 11W (Phase F.1) — locked-state card for the free tier.
//
// Renders the upgrade prompt copy. NEVER renders any
// recommendation, signal, target-price, or "trade now" wording.
// NEVER includes a button that POSTs.

import { RESEARCH_LOCKED_COPY } from '../../lib/research/tier';

export interface ResearchLockedPreviewProps {
  variant?: 'full_note' | 'history' | 'enterprise';
}

export default function ResearchLockedPreview({
  variant = 'full_note',
}: ResearchLockedPreviewProps) {
  const copy = RESEARCH_LOCKED_COPY[variant] ?? RESEARCH_LOCKED_COPY.full_note;
  return (
    <div
      className={`research-locked-preview research-locked-${variant}`}
      role="note"
      aria-label="Research locked preview"
      style={{
        background: '#fafafa',
        border: '1px dashed #bdbdbd',
        borderRadius: 4,
        color: '#424242',
        fontSize: 13,
        padding: '16px 20px',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 12, color: '#9e9e9e', marginBottom: 6 }}>
        🔒 Locked
      </div>
      {copy}
    </div>
  );
}
