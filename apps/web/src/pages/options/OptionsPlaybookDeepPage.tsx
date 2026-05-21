// Options Playbook deep dive — Phase F.5.
//
// Per-strategy educational page composed from /playbooks/{rule_id}/live:
//   * hero (rule + bias + risk profile + executive summary)
//   * when to use / when NOT to use
//   * market environment fit table
//   * IV regime fit table
//   * theta / vega / delta behavior
//   * typical DTE range
//   * lifecycle expectations
//   * beginner ↔ advanced overlay toggle
//   * live candidates + open positions on this rule
//   * cross-links to Opportunities / Positions / Research

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cn } from "@/lib/cn";
import OptionsBiasChip, { OptionsBias } from
  "@/components/options/copilot/OptionsBiasChip";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";


interface PlaybookFull {
  rule_id: string;
  executive_summary: string;
  when_to_use: Array<{ condition: string; explanation: string; example?: string }>;
  when_not_to_use: Array<{ condition: string; explanation: string; example?: string }>;
  market_environment_fit: Record<string, string>;
  iv_regime_fit: Record<string, { fit?: string; reason?: string }>;
  theta_behavior: string | null;
  vega_behavior: string | null;
  delta_behavior: string | null;
  typical_dte_range: { min?: number; max?: number; ideal?: number; reason?: string };
  lifecycle_expectations: {
    entry?: string; management?: string; exit?: string;
    typical_hold_days?: number;
  };
  risk_summary: string | null;
  educational_overlay_basic: string | null;
  educational_overlay_advanced: string | null;
  related_concepts: string[];
  source: string;
  is_stub: boolean;
  bias: string;
  directional_view: string;
  risk_profile: string;
  bias_notes: string | null;
  live: {
    candidates: Array<{
      candidate_id: number; underlying: string;
      run_date: string | null; composite_score: number | null;
      why_emitted: string; option_symbol: string;
      expiry: string | null; strike: number | null;
      option_type: string;
      earliest_event_type: string | null;
      earliest_event_date: string | null;
      event_days_away: number | null;
    }>;
    open_trades: Array<{
      trade_id: number; underlying: string;
      status: string; opened_at: string | null;
      max_loss_dollars: number | null;
      max_profit_dollars: number | null;
    }>;
  };
}


function strategyDisplayName(s: string): string {
  return s.replace(/_/g, " ").toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase());
}


export default function OptionsPlaybookDeepPage() {
  const { rule_id = "" } = useParams<{ rule_id: string }>();
  const [data, setData] = useState<PlaybookFull | null>(null);
  const [loading, setLoading] = useState(true);
  const [overlay, setOverlay] = useState<"basic" | "advanced">("basic");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/options/playbooks/${encodeURIComponent(rule_id)}/live`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setData(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rule_id]);

  if (loading) {
    return (
      <div className="opt-playbook-deep">
        <p className="opt-caption-muted">Loading playbook…</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="opt-playbook-deep">
        <p className="opt-caption-muted">Playbook not found for {rule_id}.</p>
      </div>
    );
  }

  return (
    <div className="opt-playbook-deep" data-test={`opt-playbook-deep-${rule_id}`}>
      <div className="opt-research-deep-crumbs">
        <Link to="/options/learn">← All playbooks</Link>
      </div>

      {/* Hero */}
      <section className={cn("opt-playbook-hero", `opt-playbook-bias-${data.bias}`)}>
        <div className="opt-playbook-hero-row">
          <div>
            <span className="opt-research-eyebrow">
              AI strategist · playbook
            </span>
            <h2 className="opt-playbook-deep-title">
              {strategyDisplayName(data.rule_id)}
            </h2>
            <div className="opt-playbook-hero-chips">
              <OptionsBiasChip bias={data.bias as OptionsBias} size="sm" />
              <span className="opt-caption-muted">
                {data.risk_profile} risk
              </span>
              {data.is_stub && (
                <span className="opt-playbook-stub-tag">stub playbook</span>
              )}
            </div>
          </div>
          <OptionsLiveStateChip />
        </div>
        <p className="opt-playbook-summary-large">
          {data.executive_summary}
        </p>
        {data.directional_view && (
          <p className="opt-caption-muted">{data.directional_view}</p>
        )}
      </section>

      {/* When to use / not to use */}
      {(data.when_to_use.length > 0 || data.when_not_to_use.length > 0) && (
        <div className="opt-research-deep-grid-2">
          <section className="opt-research-deep-block opt-playbook-when">
            <h3 className="opt-research-deep-block-title">When to use</h3>
            {data.when_to_use.length === 0 ? (
              <p className="opt-caption-muted">
                Not yet captured for this stub.
              </p>
            ) : (
              <ul className="opt-playbook-when-list">
                {data.when_to_use.map((w, i) => (
                  <li key={i}>
                    <strong>{w.condition}</strong>
                    <p className="opt-caption-muted">{w.explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="opt-research-deep-block opt-playbook-whennot">
            <h3 className="opt-research-deep-block-title">When NOT to use</h3>
            {data.when_not_to_use.length === 0 ? (
              <p className="opt-caption-muted">
                Not yet captured for this stub.
              </p>
            ) : (
              <ul className="opt-playbook-when-list">
                {data.when_not_to_use.map((w, i) => (
                  <li key={i}>
                    <strong>{w.condition}</strong>
                    <p className="opt-caption-muted">{w.explanation}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {/* Environment + IV fit */}
      <div className="opt-research-deep-grid-2">
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">Market environment fit</h3>
          {Object.keys(data.market_environment_fit).length === 0 ? (
            <p className="opt-caption-muted">Not captured.</p>
          ) : (
            <table className="opt-playbook-fit-table">
              <tbody>
                {Object.entries(data.market_environment_fit).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k.replace(/_/g, " ")}</td>
                    <td className={`opt-playbook-fit-${String(v).toLowerCase()}`}>
                      {String(v)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">IV regime fit</h3>
          {Object.keys(data.iv_regime_fit).length === 0 ? (
            <p className="opt-caption-muted">Not captured.</p>
          ) : (
            <ul className="opt-playbook-when-list">
              {Object.entries(data.iv_regime_fit).map(([k, v]) => (
                <li key={k}>
                  <strong>{k.replace(/_/g, " ")}: {v.fit ?? "—"}</strong>
                  {v.reason && (
                    <p className="opt-caption-muted">{v.reason}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* Greeks behavior */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Theta / Vega / Delta behavior
        </h3>
        <div className="opt-playbook-greeks">
          <div>
            <span className="opt-research-em-label">Theta</span>
            <p>{data.theta_behavior ?? "Not captured."}</p>
          </div>
          <div>
            <span className="opt-research-em-label">Vega</span>
            <p>{data.vega_behavior ?? "Not captured."}</p>
          </div>
          <div>
            <span className="opt-research-em-label">Delta</span>
            <p>{data.delta_behavior ?? "Not captured."}</p>
          </div>
        </div>
      </section>

      {/* DTE + lifecycle */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Typical DTE + lifecycle
        </h3>
        {data.typical_dte_range.min != null && (
          <p>
            <strong>DTE range:</strong> {data.typical_dte_range.min}-
            {data.typical_dte_range.max}d
            {data.typical_dte_range.ideal != null && (
              <> · ideal {data.typical_dte_range.ideal}d</>
            )}
            {data.typical_dte_range.reason && (
              <span className="opt-caption-muted">
                {" "}· {data.typical_dte_range.reason}
              </span>
            )}
          </p>
        )}
        {data.lifecycle_expectations.entry && (
          <p><strong>Entry:</strong> {data.lifecycle_expectations.entry}</p>
        )}
        {data.lifecycle_expectations.management && (
          <p><strong>Management:</strong> {data.lifecycle_expectations.management}</p>
        )}
        {data.lifecycle_expectations.exit && (
          <p><strong>Exit:</strong> {data.lifecycle_expectations.exit}</p>
        )}
        {data.lifecycle_expectations.typical_hold_days != null && (
          <p className="opt-caption-muted">
            Typical hold: {data.lifecycle_expectations.typical_hold_days} days.
          </p>
        )}
      </section>

      {/* Risk summary */}
      {data.risk_summary && (
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">Risk</h3>
          <p>{data.risk_summary}</p>
        </section>
      )}

      {/* Beginner ↔ advanced overlay */}
      {(data.educational_overlay_basic || data.educational_overlay_advanced) && (
        <section className="opt-research-deep-block">
          <header className="opt-playbook-overlay-header">
            <h3 className="opt-research-deep-block-title">Explanation</h3>
            <div className="opt-playbook-overlay-toggle">
              <button
                type="button"
                className={
                  "opt-action-pill"
                  + (overlay === "basic" ? " opt-action-pill-active" : "")
                }
                onClick={() => setOverlay("basic")}
              >Basic</button>
              <button
                type="button"
                className={
                  "opt-action-pill"
                  + (overlay === "advanced" ? " opt-action-pill-active" : "")
                }
                onClick={() => setOverlay("advanced")}
              >Advanced</button>
            </div>
          </header>
          <p className="opt-playbook-overlay-text">
            {overlay === "basic"
              ? (data.educational_overlay_basic ?? "Not captured.")
              : (data.educational_overlay_advanced ?? "Not captured.")}
          </p>
        </section>
      )}

      {/* Related concepts */}
      {data.related_concepts.length > 0 && (
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">Related concepts</h3>
          <div className="opt-playbook-concept-list">
            {data.related_concepts.map(c => (
              <span key={c} className="opt-playbook-concept-chip">
                {c.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Live overlay — candidates + open trades */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Live: candidates ({data.live.candidates.length})
        </h3>
        {data.live.candidates.length === 0 ? (
          <p className="opt-caption-muted">
            No live candidates for this rule in the last 7 days.
          </p>
        ) : (
          <ul className="opt-research-opp-list">
            {data.live.candidates.map(c => (
              <li key={c.candidate_id} className="opt-research-opp">
                <div className="opt-research-opp-head">
                  <Link to={`/options/research/${c.underlying}`}
                        className="opt-research-opp-rule">
                    {c.underlying}
                  </Link>
                  {c.composite_score != null && (
                    <span className="opt-research-opp-score">
                      composite {c.composite_score.toFixed(3)}
                    </span>
                  )}
                </div>
                <p className="opt-caption-muted">{c.why_emitted}</p>
                <p className="opt-research-opp-meta">
                  {c.option_type.toUpperCase()} @ ${c.strike} ·
                  expiry {c.expiry} · <code>{c.option_symbol}</code>
                </p>
              </li>
            ))}
          </ul>
        )}
        <Link to="/options/opportunities" className="opt-research-link">
          View all opportunities →
        </Link>
      </section>

      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          Open positions on this strategy ({data.live.open_trades.length})
        </h3>
        {data.live.open_trades.length === 0 ? (
          <p className="opt-caption-muted">
            No open paper trades currently use this strategy.
          </p>
        ) : (
          <ul className="opt-research-opp-list">
            {data.live.open_trades.map(t => (
              <li key={t.trade_id} className="opt-research-opp">
                <div className="opt-research-opp-head">
                  <Link to={`/options/research/${t.underlying}`}
                        className="opt-research-opp-rule">
                    {t.underlying}
                  </Link>
                  <span className="opt-caption-muted">{t.status}</span>
                </div>
                <p className="opt-research-opp-meta">
                  opened {t.opened_at?.slice(0, 16)}
                </p>
              </li>
            ))}
          </ul>
        )}
        <Link to="/options/positions" className="opt-research-link">
          View all positions →
        </Link>
      </section>
    </div>
  );
}
