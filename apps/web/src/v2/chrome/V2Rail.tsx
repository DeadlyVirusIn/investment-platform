// V2 Rail — wraps legacy TopStrip + MarketTicker + StatusRail in a
// V2-scoped container so the ArthOS market cockpit coexists with the
// Lovable shell per vision-lock #9.
//
// The three legacy components are imported unchanged; their classes
// (.topstrip-root / .u-market-ticker / .u-status-rail) are re-themed
// by v2-rail.css under the .v2-rail-root scope.
//
// Mobile collapse: TopStrip cells P&L / Return / Regime / Engine
// hide < 768px (data-slot CSS). StatusRail collapses to NOW only.
// The hidden cells move into V2RailDisclosure which is opened by the
// `▾` trigger rendered inline at the end of the TopStrip row.

import { useState } from 'react';
import TopStrip from '@/components/shell/TopStrip';
import MarketTicker from '@/components/shell/MarketTicker';
import StatusRail from '@/components/shell/StatusRail';
import { V2RailDisclosure } from './V2RailDisclosure';
import '../styles/v2-rail.css';

export function V2Rail() {
  const [open, setOpen] = useState(false);

  return (
    <div className="v2-rail-root">
      <div className="relative flex items-stretch">
        <div className="flex-1 min-w-0">
          <TopStrip />
        </div>
        <button
          type="button"
          className="v2-rail-disclosure-trigger"
          aria-expanded={open}
          aria-controls="v2-rail-disclosure-sheet"
          aria-label={open ? 'Hide rail detail' : 'Show rail detail'}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? '▴' : '▾'}
        </button>
      </div>
      <MarketTicker mode="compact" kind="combined" />
      <StatusRail />
      {open && (
        <div id="v2-rail-disclosure-sheet">
          <V2RailDisclosure onClose={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}
