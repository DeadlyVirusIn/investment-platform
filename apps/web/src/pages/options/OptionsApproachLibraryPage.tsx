// AI Strategy Approaches library — Phase G.
//
// Meta-layer above individual strategy playbooks. 7 thematic
// approaches; each lists typical strategies + suitability tags.
// Calm. Transparent. Anti-guru.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";


interface ApproachLibraryRow {
  slug: string;
  name: string;
  one_liner: string;
  thematic_summary: string;
  suitability: string[];
  typical_strategies: string[];
  iv_regime_preference: string;
  risk_character: string;
}


interface RegimeResponse {
  iv_rank: {
    underlyings_with_data: number;
    mean: number | null;
  };
}


export default function OptionsApproachLibraryPage() {
  const [rows, setRows] = useState<ApproachLibraryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [regime, setRegime] = useState<RegimeResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/options/approaches")
        .then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/api/options/opportunities/regime")
        .then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([j, r]) => {
      if (cancelled) return;
      setRows(j?.items ?? []);
      setRegime(r as RegimeResponse | null);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  // H-refine: when universe IV is null, surface ONE calm banner. The
  // per-approach "uncertain" verdict that fires under these conditions
  // would otherwise read seven times — manufactured pessimism.
  const ivUnavailable = regime != null && regime.iv_rank?.mean == null;

  return (
    <div className="opt-approach-page">
      <OptionsOrientationCard surface="approaches" />

      <section className="opt-research-banner">
        <div className="opt-research-banner-row">
          <span className="opt-narrative-eyebrow">
            Approaches · how to think about options
          </span>
          <OptionsLiveStateChip />
        </div>
        <h1 className="opt-narrative-sentence">
          Seven ways we think about the market.
        </h1>
        <p className="opt-narrative-supporting">
          Each approach matches a market regime to a family of
          strategies — and tells you when it doesn't fit. No
          win-rate marketing; honest about risk.
        </p>
      </section>

      {ivUnavailable && (
        <section
          className="opt-approach-iv-waiting"
          data-test="opt-approach-iv-waiting"
        >
          <p className="opt-narrative-supporting">
            Universe IV is still warming up. Until it lands, our fit
            verdicts inside each approach will read "waiting for data" —
            that's honesty, not pessimism.
          </p>
        </section>
      )}

      {loading && (
        <p className="opt-caption-muted">Loading approaches…</p>
      )}

      {!loading && rows.length === 0 && (
        <section className="opt-approach-empty">
          <h3>No approaches seeded</h3>
        </section>
      )}

      {!loading && rows.length > 0 && (
        <div className="opt-approach-grid">
          {rows.map(r => (
            <Link
              key={r.slug}
              to={`/options/approaches/${r.slug}`}
              className="opt-approach-card"
              data-test={`opt-approach-card-${r.slug}`}
            >
              <header className="opt-approach-card-head">
                <h3 className="opt-approach-card-title">{r.name}</h3>
                <span className="opt-approach-card-iv">
                  IV {r.iv_regime_preference.replace(/_/g, " ")}
                </span>
              </header>
              <p className="opt-approach-card-oneliner">{r.one_liner}</p>
              <p className="opt-approach-card-summary">{r.thematic_summary}</p>
              <div className="opt-approach-card-tags">
                {r.suitability.map(s => (
                  <span key={s} className="opt-approach-suit-chip">
                    {s.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
              <div className="opt-approach-card-strats">
                <span className="opt-caption-muted">
                  {r.typical_strategies.length} strategies ·{" "}
                  {r.risk_character} risk
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
