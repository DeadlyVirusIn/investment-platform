// Phase 11W (Phase B) - Research Job Health card on the existing
// JobsHealth page (extends, does NOT replace). Phase B = static
// "subsystem disabled" notice. Internal-ops surface only.

import ResearchBanner from './ResearchBanner';

export default function ResearchJobHealthCard() {
  return (
    <div
      className="research-job-health-card"
      style={{
        background: '#fff',
        border: '1px solid #e0e0e0',
        borderRadius: 4,
        padding: 16,
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14 }}>
        Research Intelligence Job Health
      </h3>
      <ResearchBanner context="jobs-health" />
      <div style={{ color: '#616161', fontSize: 13 }}>
        Research subsystem: <strong>disabled (Phase B)</strong>.
        <div style={{ fontSize: 12, marginTop: 4, color: '#9e9e9e' }}>
          Schema + API + UI shell present; no orchestrator wired.
        </div>
      </div>
    </div>
  );
}
