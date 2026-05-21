// AI Approach deep dive — Phase G.
//
// Per-approach educational + live regime-fit view.
// Sections:
//   1. Hero (name + fit label + transparency note)
//   2. Live regime fit panel (calm)
//   3. When it fits / When it doesn't
//   4. Suitability + risk character
//   5. Typical strategies (links to /options/learn/{rule_id})
//   6. Theta + IV behavior
//   7. Risk expansion scenarios
//   8. Beginner ↔ advanced overlay toggle
//   9. Upcoming calendar events
//  10. Matched live candidates
//  11. Transparency note (locked footer)

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cn } from "@/lib/cn";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsCatalystChip from
  "@/components/options/copilot/OptionsCatalystChip";


interface ApproachFull {
  slug: string; name: string;
  one_liner: string; thematic_summary: string;
  when_it_fits: Array<{ signal: string; explanation: string }>;
  when_it_doesnt: Array<{ signal: string; explanation: string }>;
  suitability: string[];
  typical_strategies: string[];
  iv_regime_preference: string;
  typical_dte_range: { min?: number; max?: number; ideal?: number; reason?: string };
  risk_character: string;
  profit_taking_guidance: string | null;
  theta_expectations: string | null;
  iv_behavior_explainer: string | null;
  risk_expansion_scenarios: Array<{ scenario: string; explanation: string }>;
  educational_overlay_basic: string | null;
  educational_overlay_advanced: string | null;
  regime_signals: string[];
  transparency_note: string;
  live: {
    fit_label: "fits_now" | "fits_with_caveat" | "doesnt_fit_now" | "uncertain";
    fit_reason: string;
    iv_universe_mean: number | null;
    iv_universe_tier: string;
    iv_underlying_count: number;
    upcoming_events: Array<{
      event_type: string; event_date: string;
      importance: string; title: string; days_away: number;
    }>;
    high_importance_events_in_window: number;
    matched_candidates: Array<{
      candidate_id: number; rule_id: string; underlying: string;
      composite_score: number | null; bias: string;
      why_emitted: string;
      earliest_event_type: string | null;
      earliest_event_date: string | null;
      event_days_away: number | null;
    }>;
  };
}


function fitTone(label: string): "pos" | "warn" | "neg" | "neutral" {
  if (label === "fits_now")         return "pos";
  if (label === "fits_with_caveat") return "warn";
  if (label === "doesnt_fit_now")   return "neg";
  return "neutral";
}


function strategyDisplayName(s: string): string {
  return s.replace(/_/g, " ").toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}


export default function OptionsApproachDeepPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const [data, setData] = useState<ApproachFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [overlay, setOverlay] = useState<"basic" | "advanced">("basic");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/options/approaches/${encodeURIComponent(slug)}/live`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setData(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [slug]);

  if (loading) return <p className="opt-caption-muted">Loading approach…</p>;
  if (!data)   return <p className="opt-caption-muted">Approach not found.</p>;

  const tone = fitTone(data.live.fit_label);

  return (
    <div className="opt-approach-deep" data-test={`opt-approach-deep-${slug}`}>
      <div className="opt-research-deep-crumbs">
        <Link to="/options/approaches">← All approaches</Link>
      </div>

      {/* Hero */}
      <section className={cn("opt-approach-hero", `opt-approach-tone-${tone}`)}>
        <div className="opt-approach-hero-row">
          <div>
            <span className="opt-research-eyebrow">
              AI strategist · approach
            </span>
            <h2 className="opt-approach-deep-title">{data.name}</h2>
            <p className="opt-approach-oneliner">{data.one_liner}</p>
          </div>
          <OptionsLiveStateChip />
        </div>
        <p className="opt-approach-summary">{data.thematic_summary}</p>
      </section>

      {/* H.7 hero — fit verdict at display scale.
          H-refine: when verdict is "uncertain" AND universe IV is null,
          we render a calm "waiting for data" badge instead. Repeated
          "uncertain" across seven approaches reads broken; the data
          gap is real and should be named, not papered over. */}
      {(() => {
        const ivMissing = data.live.iv_universe_mean == null;
        const isWaitingForData =
          data.live.fit_label === "uncertain" && ivMissing;
        const badgeLabel = isWaitingForData
          ? "waiting for data"
          : data.live.fit_label.replace(/_/g, " ");
        const badgeTone = isWaitingForData
          ? "opt-approach-fit-badge-waiting"
          : `opt-approach-fit-badge-${data.live.fit_label}`;
        return (
      <section className={cn("opt-research-deep-block",
                              `opt-approach-fit-${tone}`)}>
        <div className="opt-narrative-eyebrow">Does it fit right now?</div>
        <div className="opt-approach-fit-hero">
          <span className={`opt-approach-fit-badge ${badgeTone}`}>
            {badgeLabel}
          </span>
        </div>
        <p className="opt-approach-fit-reason">
          {isWaitingForData
            ? "Universe IV hasn't landed yet. We don't classify regime fit on incomplete data — we'll tell you the moment it's ready."
            : data.live.fit_reason}
        </p>
        <div className="opt-approach-fit-meta">
          <span className="opt-caption-muted">
            Universe IV mean:{" "}
            {data.live.iv_universe_mean != null
              ? data.live.iv_universe_mean.toFixed(1)
              : "unavailable"}{" "}
            · tier {data.live.iv_universe_tier}{" "}
            · {data.live.iv_underlying_count} underlying
            {data.live.iv_underlying_count === 1 ? "" : "s"} with data
          </span>
        </div>
      </section>
        );
      })()}

      {/* When fits / when doesn't */}
      <div className="opt-research-deep-grid-2">
        <section className="opt-research-deep-block opt-playbook-when">
          <h3 className="opt-research-deep-block-title">When it fits</h3>
          <ul className="opt-playbook-when-list">
            {data.when_it_fits.map((w, i) => (
              <li key={i}>
                <strong>{w.signal}</strong>
                <p className="opt-caption-muted">{w.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
        <section className="opt-research-deep-block opt-playbook-whennot">
          <h3 className="opt-research-deep-block-title">When it doesn't</h3>
          <ul className="opt-playbook-when-list">
            {data.when_it_doesnt.map((w, i) => (
              <li key={i}>
                <strong>{w.signal}</strong>
                <p className="opt-caption-muted">{w.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* Suitability + DTE + risk */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Suitability + scope</h3>
        <div className="opt-approach-scope">
          <div>
            <span className="opt-research-em-label">Suitability</span>
            <div className="opt-approach-tags">
              {data.suitability.map(s => (
                <span key={s} className="opt-approach-suit-chip">
                  {s.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
          <div>
            <span className="opt-research-em-label">Risk character</span>
            <p className="opt-approach-scope-value">{data.risk_character}</p>
          </div>
          <div>
            <span className="opt-research-em-label">IV regime</span>
            <p className="opt-approach-scope-value">
              {data.iv_regime_preference.replace(/_/g, " ")}
            </p>
          </div>
          <div>
            <span className="opt-research-em-label">Typical DTE</span>
            <p className="opt-approach-scope-value">
              {data.typical_dte_range.min}-{data.typical_dte_range.max}d
              {data.typical_dte_range.ideal != null
                && <> · ideal {data.typical_dte_range.ideal}d</>}
            </p>
          </div>
        </div>
      </section>

      {/* Typical strategies */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Typical strategies in this approach
        </h3>
        <div className="opt-approach-strategy-list">
          {data.typical_strategies.map(r => (
            <Link
              key={r}
              to={`/options/learn/${r}`}
              className="opt-approach-strategy-chip"
            >
              {strategyDisplayName(r)}
            </Link>
          ))}
        </div>
      </section>

      {/* Theta + IV behavior + profit-taking */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Theta + IV behavior
        </h3>
        {data.theta_expectations && (
          <p><strong>Theta:</strong> {data.theta_expectations}</p>
        )}
        {data.iv_behavior_explainer && (
          <p><strong>Vega / IV:</strong> {data.iv_behavior_explainer}</p>
        )}
        {data.profit_taking_guidance && (
          <p><strong>Profit-taking:</strong> {data.profit_taking_guidance}</p>
        )}
      </section>

      {/* Risk expansion scenarios */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Risk expansion scenarios
        </h3>
        <ul className="opt-playbook-when-list">
          {data.risk_expansion_scenarios.map((s, i) => (
            <li key={i}>
              <strong>{s.scenario}</strong>
              <p className="opt-caption-muted">{s.explanation}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* Beginner ↔ advanced overlay */}
      <section className="opt-research-deep-block">
        <header className="opt-playbook-overlay-header">
          <h3 className="opt-research-deep-block-title">Explanation</h3>
          <div className="opt-playbook-overlay-toggle">
            <button type="button"
                    className={"opt-action-pill" + (overlay === "basic" ? " opt-action-pill-active" : "")}
                    onClick={() => setOverlay("basic")}>Basic</button>
            <button type="button"
                    className={"opt-action-pill" + (overlay === "advanced" ? " opt-action-pill-active" : "")}
                    onClick={() => setOverlay("advanced")}>Advanced</button>
          </div>
        </header>
        <p className="opt-playbook-overlay-text">
          {overlay === "basic"
            ? (data.educational_overlay_basic ?? "Not captured.")
            : (data.educational_overlay_advanced ?? "Not captured.")}
        </p>
      </section>

      {/* Regime signals */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Regime signals to confirm fit</h3>
        <ul className="opt-approach-signal-list">
          {data.regime_signals.map((s, i) => (
            <li key={i} className="opt-approach-signal">{s}</li>
          ))}
        </ul>
      </section>

      {/* Upcoming events */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Upcoming events in DTE window
        </h3>
        {data.live.upcoming_events.length === 0 ? (
          <p className="opt-caption-muted">
            No catalysts in the typical DTE window for this approach.
          </p>
        ) : (
          <ul className="opt-approach-events-list">
            {data.live.upcoming_events.map(e => (
              <li key={`${e.event_type}-${e.event_date}`}>
                <OptionsCatalystChip
                  eventType={e.event_type}
                  eventDate={e.event_date}
                  daysAway={e.days_away}
                  importance={e.importance}
                  title={e.title} />
                <span className="opt-caption-muted">{e.title}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Matched live candidates */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Live candidates in this approach ({data.live.matched_candidates.length})
        </h3>
        {data.live.matched_candidates.length === 0 ? (
          <p className="opt-caption-muted">
            No active candidates currently match the approach's
            typical strategies. Refresh after the next shadow run.
          </p>
        ) : (
          <ul className="opt-research-opp-list">
            {data.live.matched_candidates.map(c => (
              <li key={c.candidate_id} className="opt-research-opp">
                <div className="opt-research-opp-head">
                  <Link to={`/options/research/${c.underlying}`}
                        className="opt-research-opp-rule">
                    {c.underlying}
                  </Link>
                  <Link to={`/options/learn/${c.rule_id}`}
                        className="opt-approach-strategy-chip"
                        style={{ marginLeft: 6 }}>
                    {strategyDisplayName(c.rule_id)}
                  </Link>
                  {c.composite_score != null && (
                    <span className="opt-research-opp-score">
                      composite {c.composite_score.toFixed(3)}
                    </span>
                  )}
                </div>
                <p className="opt-caption-muted">{c.why_emitted}</p>
              </li>
            ))}
          </ul>
        )}
        <Link to="/options/opportunities" className="opt-research-link">
          View all opportunities →
        </Link>
      </section>

      {/* Transparency note — locked footer */}
      <section className="opt-approach-transparency">
        <header className="opt-approach-transparency-head">
          <span className="opt-approach-transparency-eyebrow">
            Honest disclosure
          </span>
        </header>
        <p className="opt-approach-transparency-body">
          {data.transparency_note}
        </p>
      </section>
    </div>
  );
}
