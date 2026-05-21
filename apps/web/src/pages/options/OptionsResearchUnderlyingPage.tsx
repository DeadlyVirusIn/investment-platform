// Options Research deep-dive — Phase D.
//
// Per-underlying AI conviction layer. Composition order:
//   1. Calm hero (posture + spot)
//   2. Volatility regime block
//   3. Expected move
//   4. Strategy-family fit (ranked)
//   5. Catalyst timeline
//   6. Top opportunities
//   7. Open positions
//   8. Thesis invalidators
//
// Read-only. Honest empty fields when data missing.

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { cn } from "@/lib/cn";
import { fmtUSD, fmtPct } from "@/components/ui/primitives";
import OptionsLiveStateChip from
  "@/components/options/copilot/OptionsLiveStateChip";
import OptionsBiasChip, { OptionsBias } from
  "@/components/options/copilot/OptionsBiasChip";
import OptionsCatalystChip from
  "@/components/options/copilot/OptionsCatalystChip";


interface ResearchUnderlying {
  symbol: string;
  spot: number | null;
  spot_as_of: string | null;
  calm_sentence: string;
  ai_posture: {
    label: string;
    reason: string;
    bias_mix: Record<string, number>;
  };
  volatility_regime: {
    premium_tier: string;
    iv_rank_252d: number | null;
    atm_iv: number | null;
    realized_vol_30d: number | null;
    vrp_30d: number | null;
    explanation: string;
  };
  expected_move: {
    one_week: number | null;
    one_month: number | null;
    explanation: string;
  };
  strategy_family_fit: Array<{
    rule_id: string;
    bias: string;
    risk_profile: string;
    directional_view: string;
    candidate_count: number;
    avg_composite: number | null;
    best_composite: number | null;
  }>;
  catalyst_timeline: Array<{
    event_type: string;
    event_date: string;
    event_time: string | null;
    title: string;
    importance: string;
    explanation: string;
    days_away: number;
  }>;
  top_opportunities: Array<{
    candidate_id: number;
    rule_id: string;
    bias: string;
    composite_score: number | null;
    directional_view: string;
    why_emitted: string;
    triggering_rule: string;
    option_symbol: string;
    expiry: string | null;
    strike: number | null;
    option_type: string;
    earliest_event_type: string | null;
    earliest_event_date: string | null;
    event_days_away: number | null;
  }>;
  open_positions: Array<{
    trade_id: number;
    strategy_name: string;
    status: string;
    opened_at: string | null;
    max_loss_dollars: number | null;
    max_profit_dollars: number | null;
    breakeven_lower: number | null;
    breakeven_upper: number | null;
  }>;
  thesis_invalidators: string[];
}


function postureTone(p: string): "pos" | "neg" | "warn" | "neutral" {
  if (p.startsWith("bullish")) return "pos";
  if (p.startsWith("bearish")) return "neg";
  if (p === "event-driven") return "warn";
  return "neutral";
}


export default function OptionsResearchUnderlyingPage() {
  const { symbol = "" } = useParams<{ symbol: string }>();
  const [data, setData] = useState<ResearchUnderlying | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/options/research/underlying/${encodeURIComponent(symbol)}`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setData(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  if (loading) {
    return (
      <div className="opt-research-deep">
        <p className="opt-caption-muted">Loading conviction view…</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="opt-research-deep">
        <p className="opt-caption-muted">
          Conviction view unavailable for {symbol}.
        </p>
      </div>
    );
  }

  const tone = postureTone(data.ai_posture.label);

  return (
    <div className="opt-research-deep" data-test={`opt-research-deep-${symbol}`}>
      {/* Breadcrumb */}
      <div className="opt-research-deep-crumbs">
        <Link to="/options/research">← All underlyings</Link>
      </div>

      {/* Hero */}
      <section className={cn("opt-research-deep-hero",
                              `opt-research-tone-${tone}`)}>
        <div className="opt-research-deep-hero-row">
          <div>
            <span className="opt-research-eyebrow">
              AI strategist · {symbol}
            </span>
            <h2 className="opt-research-deep-title">
              {symbol}
              {data.spot != null && (
                <span className="opt-research-deep-spot">
                  {" "}· {fmtUSD(data.spot, 2)}
                </span>
              )}
            </h2>
          </div>
          <OptionsLiveStateChip />
        </div>
        <p className="opt-research-deep-calm">{data.calm_sentence}</p>
        <p className="opt-caption-muted">{data.ai_posture.reason}</p>
      </section>

      {/* Volatility regime + expected move */}
      <div className="opt-research-deep-grid-2">
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">Volatility regime</h3>
          <div className="opt-research-vol-row">
            <span className="opt-research-vol-tier">
              {data.volatility_regime.premium_tier}
            </span>
            {data.volatility_regime.iv_rank_252d != null && (
              <span>IV rank {data.volatility_regime.iv_rank_252d.toFixed(0)}</span>
            )}
            {data.volatility_regime.atm_iv != null && (
              <span>ATM IV {(data.volatility_regime.atm_iv * 100).toFixed(1)}%</span>
            )}
          </div>
          <p className="opt-caption-muted">
            {data.volatility_regime.explanation}
          </p>
        </section>
        <section className="opt-research-deep-block">
          <h3 className="opt-research-deep-block-title">Expected move</h3>
          <div className="opt-research-em-row">
            <div>
              <span className="opt-research-em-label">1 week</span>
              <span className="opt-research-em-value">
                {data.expected_move.one_week != null
                  ? `±${fmtUSD(data.expected_move.one_week, 2)}`
                  : "—"}
              </span>
            </div>
            <div>
              <span className="opt-research-em-label">1 month</span>
              <span className="opt-research-em-value">
                {data.expected_move.one_month != null
                  ? `±${fmtUSD(data.expected_move.one_month, 2)}`
                  : "—"}
              </span>
            </div>
          </div>
          <p className="opt-caption-muted">{data.expected_move.explanation}</p>
        </section>
      </div>

      {/* Strategy family fit */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Strategy fit</h3>
        {data.strategy_family_fit.length === 0 ? (
          <p className="opt-caption-muted">
            No strategy candidates in last 7 days for this underlying.
          </p>
        ) : (
          <table className="opt-research-strategy-table">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Bias</th>
                <th>Risk</th>
                <th>Candidates</th>
                <th>Avg composite</th>
                <th>Best</th>
              </tr>
            </thead>
            <tbody>
              {data.strategy_family_fit.map(s => (
                <tr key={s.rule_id}>
                  <td>{s.rule_id.replace(/_/g, " ").toLowerCase()
                    .replace(/\b\w/g, c => c.toUpperCase())}</td>
                  <td>
                    <OptionsBiasChip
                      bias={s.bias as OptionsBias} size="xs" />
                  </td>
                  <td>{s.risk_profile}</td>
                  <td>{s.candidate_count}</td>
                  <td>{s.avg_composite != null
                    ? s.avg_composite.toFixed(3) : "—"}</td>
                  <td>{s.best_composite != null
                    ? s.best_composite.toFixed(3) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Catalyst timeline */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Catalyst timeline</h3>
        {data.catalyst_timeline.length === 0 ? (
          <p className="opt-caption-muted">
            No catalysts in next 90 days for this underlying.
          </p>
        ) : (
          <ul className="opt-research-catalyst-list">
            {data.catalyst_timeline.map(c => (
              <li key={`${c.event_type}-${c.event_date}`}>
                <div className="opt-research-catalyst-head">
                  <OptionsCatalystChip
                    eventType={c.event_type}
                    eventDate={c.event_date}
                    daysAway={c.days_away}
                    importance={c.importance}
                    title={c.title}
                    explanation={c.explanation} />
                  <span className="opt-research-catalyst-title">
                    {c.title}
                  </span>
                </div>
                <p className="opt-caption-muted">{c.explanation}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Top opportunities */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Top opportunities</h3>
        {data.top_opportunities.length === 0 ? (
          <p className="opt-caption-muted">
            No shadow signals on this underlying in last 7 days.
          </p>
        ) : (
          <ul className="opt-research-opp-list">
            {data.top_opportunities.map(o => (
              <li key={o.candidate_id} className="opt-research-opp">
                <div className="opt-research-opp-head">
                  <OptionsBiasChip bias={o.bias as OptionsBias} size="xs" />
                  <span className="opt-research-opp-rule">
                    {o.rule_id.replace(/_/g, " ").toLowerCase()
                      .replace(/\b\w/g, c => c.toUpperCase())}
                  </span>
                  {o.composite_score != null && (
                    <span className="opt-research-opp-score">
                      {fmtPct(o.composite_score * 100, 0)}
                    </span>
                  )}
                </div>
                <p className="opt-caption-muted">{o.why_emitted}</p>
                <p className="opt-research-opp-meta">
                  {o.option_type.toUpperCase()} @ ${o.strike} · expiry{" "}
                  {o.expiry} · <code>{o.option_symbol}</code>
                </p>
              </li>
            ))}
          </ul>
        )}
        <Link
          to="/options/opportunities"
          className="opt-research-link"
        >
          View all opportunities →
        </Link>
      </section>

      {/* Open positions */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">Open positions</h3>
        {data.open_positions.length === 0 ? (
          <p className="opt-caption-muted">
            No open paper positions on {symbol}.
          </p>
        ) : (
          <ul className="opt-research-opp-list">
            {data.open_positions.map(p => (
              <li key={p.trade_id} className="opt-research-opp">
                <div className="opt-research-opp-head">
                  <span className="opt-research-opp-rule">
                    {p.strategy_name.replace(/_/g, " ").toLowerCase()
                      .replace(/\b\w/g, c => c.toUpperCase())}
                  </span>
                  <span className="opt-caption-muted">{p.status}</span>
                </div>
                <p className="opt-research-opp-meta">
                  Max loss {p.max_loss_dollars != null
                    ? fmtUSD(p.max_loss_dollars) : "—"}
                  {" · "}
                  Max profit {p.max_profit_dollars != null
                    ? fmtUSD(p.max_profit_dollars) : "—"}
                  {p.breakeven_lower != null && (
                    <>{" · "}BE {fmtUSD(p.breakeven_lower, 2)}</>
                  )}
                  {p.breakeven_upper != null && (
                    <>{" / "}{fmtUSD(p.breakeven_upper, 2)}</>
                  )}
                </p>
              </li>
            ))}
          </ul>
        )}
        <Link
          to="/options/positions"
          className="opt-research-link"
        >
          View all positions →
        </Link>
      </section>

      {/* Thesis invalidators */}
      <section className="opt-research-deep-block">
        <h3 className="opt-research-deep-block-title">
          What invalidates the thesis
        </h3>
        <ul className="opt-research-invalidator-list">
          {data.thesis_invalidators.map((i, idx) => (
            <li key={idx}>{i}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
