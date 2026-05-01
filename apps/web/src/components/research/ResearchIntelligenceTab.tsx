// Phase 11W (Phase B) - Research Intelligence tab on the
// Recommendations page. Phase B = empty state only. No data fetched
// (the API stub returns empty list anyway). No action buttons. No
// recommendation iconography.

import ResearchBanner from './ResearchBanner';

export default function ResearchIntelligenceTab() {
  return (
    <div className="research-intelligence-tab">
      <ResearchBanner context="tab" />
      <div
        style={{
          color: '#616161',
          fontSize: 14,
          padding: '32px 16px',
          textAlign: 'center',
        }}
      >
        No research runs yet for this asset.
        <div style={{ fontSize: 12, marginTop: 8, color: '#9e9e9e' }}>
          Phase B scaffold — research orchestration is not enabled.
        </div>
      </div>
    </div>
  );
}
