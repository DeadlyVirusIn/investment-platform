// Options Opportunities page — Phase B.
//
// Six lanes: Bullish / Bearish / Neutral / Event-driven /
// Developing / High conviction. Each lane shows up to N cards
// composed from /api/options/opportunities/lanes (one HTTP fetch).
//
// Above the lanes: a calm regime banner pulled from
// /api/options/opportunities/regime — strategist's market read in
// one sentence + the headline IV-rank mean + today's
// would-trade count.
//
// Read-only. No execution. Watermarked. Aligned with the canonical
// terminology lock established in the trust-infra patch.

import { useEffect, useState } from "react";

import OpportunityLane, { LaneName } from
  "@/components/options/copilot/OpportunityLane";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import { OpportunityPayload } from
  "@/components/options/copilot/OptionsOpportunityCard";


interface LaneBucket {
  count: number;
  items: OpportunityPayload[];
}

interface LanesResponse {
  lookback_days: number;
  conviction_floor: number;
  lanes: Record<LaneName, LaneBucket>;
}

interface RegimeResponse {
  iv_rank: {
    underlyings_with_data: number;
    mean: number | null;
    min:  number | null;
    max:  number | null;
  };
  shadow: {
    latest_run: string | null;
    would_trade_today: number;
    evaluated_today: number;
  };
}


const LANE_ORDER: LaneName[] = [
  "conviction", "bullish", "bearish",
  "neutral", "event", "developing",
];


function describeRegime(regime: RegimeResponse | null): string {
  if (!regime) return "We're reading today's setups…";
  const mean = regime.iv_rank.mean;
  const wt = regime.shadow.would_trade_today;
  if (mean == null) {
    return wt > 0
      ? `We've found ${wt} setup${wt === 1 ? "" : "s"} worth watching today.`
      : "We've found nothing worth a strong recommendation today.";
  }
  const tone =
    mean >= 75 ? "rich" :
    mean >= 50 ? "elevated" :
    mean >= 25 ? "average" : "cheap";
  if (wt === 0) {
    return `Premium is ${tone}, but nothing has cleared conviction today. Patience.`;
  }
  return `${wt} setup${wt === 1 ? "" : "s"} look${wt === 1 ? "s" : ""} worth a look. Premium environment is ${tone}.`;
}


export default function OptionsOpportunitiesPage() {
  const [lanes, setLanes] = useState<LanesResponse | null>(null);
  const [regime, setRegime] = useState<RegimeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  // H-refine: collapse empty lanes by default. Toggle exposes them so
  // power users still see honest "nothing in bullish today" copy when
  // they want it.
  const [showEmpty, setShowEmpty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/options/opportunities/lanes?limit_per_lane=6")
        .then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/api/options/opportunities/regime")
        .then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([l, r]) => {
      if (cancelled) return;
      setLanes(l as LanesResponse | null);
      setRegime(r as RegimeResponse | null);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="opt-opportunities-page"
         data-test="options-opportunities-page">

      {/* H.6 — first-visit orientation. Dismisses permanently. */}
      <OptionsOrientationCard surface="opportunities" />

      {/* H.2 narrative hero — first-person plural strategist voice.
          Weights + thresholds collapsed into a single quiet footnote. */}
      <section className="opt-opp-regime-banner">
        <div className="opt-opp-regime-row">
          <span className="opt-narrative-eyebrow">
            Opportunities · today's read
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          {describeRegime(regime)}
        </h1>
        {lanes && (
          <p className="opt-caption-muted">
            Ranking weighs score, freshness, liquidity, IV fit, and
            catalyst proximity. Conviction lane requires composite ≥{" "}
            {lanes.conviction_floor.toFixed(2)}.
          </p>
        )}
      </section>

      {loading && (
        <div className="opt-caption-muted opt-opp-loading"
             data-test="opt-opportunities-loading">
          Loading lanes…
        </div>
      )}

      {!loading && lanes && (() => {
        const nonEmpty = LANE_ORDER.filter(
          name => (lanes.lanes[name]?.items?.length ?? 0) > 0,
        );
        const empty = LANE_ORDER.filter(
          name => (lanes.lanes[name]?.items?.length ?? 0) === 0,
        );
        const visible = showEmpty ? LANE_ORDER : nonEmpty;
        return (
          <div className="opt-lane-stack" data-test="opt-lane-stack">
            {visible.map(name => (
              <OpportunityLane
                key={name}
                lane={name}
                items={lanes.lanes[name]?.items ?? []}
                canaryEnabled={false}
                limit={6} />
            ))}
            {/* Honest empty-lane disclosure: when every lane is empty,
                we surface a single calm sentence rather than six. */}
            {nonEmpty.length === 0 && (
              <p
                className="opt-caption-muted opt-lane-allempty"
                data-test="opt-lane-allempty"
              >
                Nothing has cleared any lane today. {showEmpty ? "" : "All lanes are empty — you can expand below to read each lane's calm empty-state line."}
              </p>
            )}
            {empty.length > 0 && (
              <button
                type="button"
                className="opt-lane-toggle"
                data-test="opt-lane-toggle"
                onClick={() => setShowEmpty(v => !v)}
              >
                {showEmpty
                  ? `Hide ${empty.length} empty lane${empty.length === 1 ? "" : "s"}`
                  : `${empty.length} lane${empty.length === 1 ? "" : "s"} empty · show all`}
              </button>
            )}
          </div>
        );
      })()}
    </div>
  );
}
