// Phase 11W (Phase B) - Research Pulse card on the Dashboard. Phase B
// = empty state only. Reads /api/research/runs (returns empty list);
// renders "0 runs in last 24h". No links to action surfaces.

import ResearchBanner from './ResearchBanner';

export default function ResearchPulseCard() {
  return (
    <div
      className="research-pulse-card"
      style={{
        background: '#fff',
        border: '1px solid #e0e0e0',
        borderRadius: 4,
        padding: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
        Research Pulse
      </h3>
      <ResearchBanner context="pulse" />
      <div style={{ color: '#616161', fontSize: 13 }}>
        0 research runs in last 24h.
        <div style={{ fontSize: 12, marginTop: 4, color: '#9e9e9e' }}>
          Phase B scaffold — research orchestration is not enabled.
        </div>
      </div>
    </div>
  );
}
