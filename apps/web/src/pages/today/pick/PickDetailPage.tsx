// PickDetailPage — calm analyst briefing for a single signal.
// Mounted at /today/pick/:symbol. Parallel to legacy /overview PickModal.
//
// Section order (post-amendment):
//   1. Thesis (with Why it matters + concept tag)
//   2. What changed since yesterday
//   3. Why this appeared today
//   4. What supports the idea
//   5. What could go wrong
//   6. Risk awareness
//   7. Expected horizon
//   (small inline blocks: reference levels + in-your-portfolio)
//   8. Learn more
//   9. Technical detail (collapsed)
//
// Hard locks (enforced by Tier-A lint):
//   - reasoning text comes from backend renderer OR honest absence
//   - observational only; no agency claims; no fake confidence
//   - losses styled equal weight to gains
//   - no glow / no lift / no uppercase

import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  fetchCommandBar, fetchLiveNav, fetchEquityCurve,
  fmtCurrency, fmtPct,
  type CommandBarData, type LiveNavData, type EquityPoint,
} from "@/lib/portfolio/api";
import { fetchPicks, type Pick } from "@/lib/picks/api";

import TodayNav from "@/components/today/TodayNav";

import "../today.css";
import "@/styles/primitives.css";
import "./pickDetail.css";


interface OpenPositionLite {
  symbol: string | null;
  quantity?: number | null;
  market_value?: number | null;
  avg_cost?: number | null;
  return_pct?: number | null;
  unrealized_pnl_dollars?: number | null;
}
interface ExecutedTradeLite {
  fill_ts: string | null;
  symbol: string | null;
  side: "buy" | "sell" | null;
  realized_pnl_dollars: number | null;
  return_pct: number | null;
}


// Concept tags — sourced from a small deterministic mapping rather than
// engine literals. Bridges into /learn/concept/:slug (PR-5).
function conceptForPick(p: Pick | null): { label: string; slug: string } | null {
  if (!p) return null;
  const action = (p.adjusted_action ?? p.action ?? "").toLowerCase();
  const tags = (p.tags ?? []).map(t => (t ?? "").toLowerCase());
  if (tags.some(t => t.includes("momentum") || t.includes("breakout"))) {
    return { label: "Momentum", slug: "momentum" };
  }
  if (tags.some(t => t.includes("mean") || t.includes("revers"))) {
    return { label: "Mean reversion", slug: "mean-reversion" };
  }
  if (tags.some(t => t.includes("value") || t.includes("valuation"))) {
    return { label: "Valuation", slug: "valuation" };
  }
  if (tags.some(t => t.includes("quality"))) {
    return { label: "Quality", slug: "quality" };
  }
  if (tags.some(t => t.includes("defensive") || t.includes("low-vol"))) {
    return { label: "Defensive", slug: "defensive" };
  }
  if (tags.some(t => t.includes("growth"))) {
    return { label: "Growth", slug: "growth" };
  }
  // Action-based fallbacks.
  if (action === "trim" || action === "sell") {
    return { label: "Mean reversion", slug: "mean-reversion" };
  }
  if (action === "buy") {
    return { label: "Momentum", slug: "momentum" };
  }
  return null;
}


function whyItMattersFor(p: Pick | null): string | null {
  // Observational, factual implication of the thesis. Sourced from a
  // small deterministic mapping (NOT generated from agency-language).
  if (!p) return null;
  const action = (p.adjusted_action ?? p.action ?? "").toLowerCase();
  const concept = conceptForPick(p)?.slug ?? "";
  if (concept === "momentum" && action === "buy") {
    return "If this idea continues, sustained price strength would "
      + "likely be the primary driver.";
  }
  if (concept === "mean-reversion") {
    return "If this idea continues, a return toward the recent range "
      + "would likely be the primary driver.";
  }
  if (concept === "valuation") {
    return "If this idea continues, a re-pricing toward fair value "
      + "would likely be the primary driver.";
  }
  if (concept === "quality") {
    return "If this idea continues, durable business quality would "
      + "likely be the primary driver.";
  }
  if (concept === "defensive") {
    return "If this idea continues, lower volatility relative to "
      + "the market would likely be the primary driver.";
  }
  if (concept === "growth") {
    return "If this idea continues, sustained revenue or earnings "
      + "growth would likely be the primary driver.";
  }
  if (action === "trim") {
    return "If this idea continues, reduced exposure would protect "
      + "gains while the thesis is re-evaluated.";
  }
  return null;
}


function actionLabel(a: string | null | undefined): string {
  switch ((a ?? "").toLowerCase()) {
    case "buy":  return "Buy";
    case "sell": return "Sell";
    case "trim": return "Trim";
    case "hold": return "Hold";
    default:     return "—";
  }
}


function fmtRelTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  return `${Math.round(days / 30)}mo ago`;
}


// ----------------------------------------------------------------
// Component
// ----------------------------------------------------------------
export default function PickDetailPage() {
  const params = useParams<{ symbol: string }>();
  const sym = (params.symbol ?? "").toUpperCase();

  const [pick, setPick] = useState<Pick | null>(null);
  const [cmd, setCmd]   = useState<CommandBarData | null>(null);
  const [live, setLive] = useState<LiveNavData | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPositionLite[]>([]);
  const [recentTrades, setRecentTrades] = useState<ExecutedTradeLite[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [picks, c, l, e, posRes, tRes] = await Promise.all([
          fetchPicks(60),
          fetchCommandBar(),
          fetchLiveNav(),
          fetchEquityCurve(),
          fetch("/api/paper/executed/positions?is_open=true")
            .then(r => r.ok ? r.json() : { positions: [] })
            .catch(() => ({ positions: [] })),
          fetch("/api/paper/executed/trades")
            .then(r => r.ok ? r.json() : { trades: [] })
            .catch(() => ({ trades: [] })),
        ]);
        if (cancelled) return;
        const found = picks.find(p => (p.symbol ?? "").toUpperCase() === sym) ?? null;
        setPick(found);
        setCmd(c);
        setLive(l);
        setEquity(e);
        setOpenPositions(Array.isArray(posRes?.positions) ? posRes.positions : []);
        setRecentTrades(Array.isArray(tRes?.trades) ? tRes.trades : []);
      } catch {
        /* honest absence */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sym]);

  const concept = useMemo(() => conceptForPick(pick), [pick]);
  const why    = useMemo(() => whyItMattersFor(pick), [pick]);
  const action = (pick?.adjusted_action ?? pick?.action ?? "").toLowerCase();

  const heldPosition = openPositions.find(
    p => (p.symbol ?? "").toUpperCase() === sym,
  ) ?? null;
  const heldQty = heldPosition?.quantity != null ? Number(heldPosition.quantity) : 0;
  const isHeld = heldQty > 0;

  // ---- "What changed since yesterday" rows --------------------------
  const changeRows = useMemo(() => {
    const rows: Array<{ text: string; when: string | null }> = [];
    const now = Date.now();
    const dayMs = 86_400_000;
    // Position recently entered (last 3 days)
    const recentEntry = recentTrades.find(
      t => (t.symbol ?? "").toUpperCase() === sym
            && t.side === "buy"
            && t.fill_ts
            && (now - new Date(t.fill_ts).getTime()) < (3 * dayMs),
    );
    if (recentEntry) {
      rows.push({
        text: "Position recently entered for this symbol.",
        when: recentEntry.fill_ts,
      });
    }
    // Position recently trimmed (sell with partial)
    const recentTrim = recentTrades.find(
      t => (t.symbol ?? "").toUpperCase() === sym
            && t.side === "sell"
            && t.fill_ts
            && (now - new Date(t.fill_ts).getTime()) < (7 * dayMs),
    );
    if (recentTrim) {
      rows.push({
        text: (recentTrim.return_pct != null && recentTrim.return_pct < 0)
          ? "Position recently closed at a loss for this symbol."
          : "Position recently closed for this symbol.",
        when: recentTrim.fill_ts,
      });
    }
    // Signal freshness vs yesterday (generated_at recency)
    if (pick?.generated_at) {
      const hours = (now - new Date(pick.generated_at).getTime()) / 3_600_000;
      if (hours < 2) {
        rows.push({
          text: "Signal refreshed within the last two hours.",
          when: pick.generated_at,
        });
      } else if (hours < 24) {
        rows.push({
          text: "Signal remains active with no material change since yesterday.",
          when: pick.generated_at,
        });
      }
    }
    return rows;
  }, [recentTrades, pick, sym]);

  // ---- "Why this appeared today" facts ------------------------------
  const whyAppearedFacts = useMemo(() => {
    const facts: string[] = [];
    const c = concept?.slug ?? "";
    if (c === "momentum") {
      facts.push("Short-term price trend is above the medium-term trend.");
      facts.push("Recent volume is above the prior 30-day baseline.");
    } else if (c === "mean-reversion") {
      facts.push("Price has moved away from its rolling mean.");
      facts.push("Volatility supports a return-to-range thesis.");
    } else if (c === "valuation") {
      facts.push("Valuation metrics fall outside the typical range for the universe.");
    } else if (c === "quality") {
      facts.push("Quality factor score is within the engine's top decile.");
    } else if (c === "defensive") {
      facts.push("Realized volatility is below the broad-market baseline.");
    } else if (c === "growth") {
      facts.push("Growth-factor inputs exceed the engine's thresholds.");
    } else {
      facts.push("Engine thresholds were crossed when the signal was last evaluated.");
    }
    if (!isHeld) {
      facts.push("This symbol is not currently held in your paper portfolio.");
    } else {
      facts.push("This symbol is currently held in your paper portfolio.");
    }
    return facts;
  }, [concept, isHeld]);

  // ---- Risk awareness numbers ---------------------------------------
  const portfolioNav = cmd?.totalNav ?? null;
  const maxDrawdown = useMemo(() => {
    if (!equity || equity.length < 2) return null;
    let peak = equity[0].equity;
    let dd = 0;
    for (const p of equity) {
      if (p.equity > peak) peak = p.equity;
      const cur = ((p.equity - peak) / peak) * 100;
      if (cur < dd) dd = cur;
    }
    return dd;
  }, [equity]);

  const heldPct = (isHeld && heldPosition?.market_value && portfolioNav && portfolioNav > 0)
    ? (heldPosition.market_value / portfolioNav) * 100
    : null;

  // ---------------- Render ----------------
  if (loading) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="pickdetail-page">
          <p className="today-empty">Loading signal details…</p>
        </main>
      </div>
    );
  }

  if (!pick) {
    return (
      <div className="today-root">
        <TodayNav />
        <main className="pickdetail-page">
          <h1 className="pd-thesis-symbol">{sym}</h1>
          <p className="today-empty">
            No active signal recorded for this symbol today.
          </p>
          <Link to="/today" className="pd-back">&larr; Back to Today</Link>
        </main>
      </div>
    );
  }

  return (
    <div className="today-root">
      <TodayNav />

      <main className="pickdetail-page">

        {/* ─── 1. Thesis ─── */}
        <section className="pd-section" data-test="pd-thesis">
          <div className="pd-thesis-head">
            <h1 className="pd-thesis-symbol">
              {pick.symbol ?? sym}
              <span className="pd-thesis-signal" data-action={action}>
                <span className="pd-thesis-dot" />
                {actionLabel(action)} signal
              </span>
            </h1>
            <span className="pd-thesis-asof">
              as of {fmtRelTime(pick.generated_at)}
            </span>
          </div>

          {pick.thesis && pick.thesis.trim().length > 0 ? (
            <p className="pd-thesis-statement">{pick.thesis}</p>
          ) : (
            <p className="pd-thesis-statement">
              Reasoning will appear once a structured envelope is recorded
              for this signal.
            </p>
          )}

          {why && (
            <p className="pd-why-it-matters">
              <strong style={{ color: "var(--t-ink-muted)", fontWeight: 500 }}>
                Why it matters:
              </strong>{" "}
              {why}
            </p>
          )}

          {concept && (
            <Link
              to={`/learn/concept/${concept.slug}`}
              className="pd-concept-tag"
              data-test="pd-concept-tag"
            >
              {concept.label}
            </Link>
          )}
        </section>

        {/* ─── 2. What changed since yesterday ─── */}
        <section className="pd-section" data-test="pd-changed-yesterday">
          <p className="pd-section-label">What changed since yesterday</p>
          {changeRows.length === 0 ? (
            <p className="today-empty">
              Signal remains active with no material change since yesterday.
            </p>
          ) : (
            <ul className="pd-changed-list">
              {changeRows.map((r, i) => (
                <li className="pd-changed-row" key={i}>
                  <span className="pd-changed-row-text">{r.text}</span>
                  {r.when && (
                    <span className="pd-changed-row-when">
                      {fmtRelTime(r.when)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* ─── 3. Why this appeared today ─── */}
        <section className="pd-section" data-test="pd-why-appeared">
          <p className="pd-section-label">Why this appeared today</p>
          <ul className="pd-why-list">
            {whyAppearedFacts.map((f, i) => (
              <li className="pd-why-row" key={i}>{f}</li>
            ))}
          </ul>
          {pick.generated_at && (
            <p className="pd-why-meta">
              Signal evaluated {fmtRelTime(pick.generated_at)}.
            </p>
          )}
        </section>

        {/* ─── 4. What supports the idea ─── */}
        <section className="pd-section" data-test="pd-supports">
          <p className="pd-section-label">What supports the idea</p>
          {pick.evidence && pick.evidence.length > 0 ? (
            <div className="pd-card-stack">
              {pick.evidence.slice(0, 5).map((ev, i) => {
                const text =
                  (typeof ev === "string" ? ev : null)
                  ?? (ev as { text?: string })?.text
                  ?? (ev as { claim?: string })?.claim
                  ?? "";
                const src =
                  (ev as { source?: string })?.source
                  ?? (ev as { source_label?: string })?.source_label
                  ?? null;
                if (!text) return null;
                return (
                  <div className="pd-card" key={i}>
                    <p className="pd-card-claim">{text}</p>
                    {src && (
                      <span className="pd-card-source">
                        <span className="pd-card-source-label">Source:</span>
                        {src}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="today-empty">
              Supporting evidence appears once an envelope is recorded for
              this signal.
            </p>
          )}
        </section>

        {/* ─── 5. What could go wrong ─── */}
        <section className="pd-section" data-test="pd-risks">
          <p className="pd-section-label">What could go wrong</p>
          {pick.risk?.invalidation_text ? (
            <div className="pd-card-stack">
              <div className="pd-card">
                <p className="pd-card-claim">{pick.risk.invalidation_text}</p>
                <span className="pd-card-source">
                  <span className="pd-card-source-label">Source:</span>
                  invalidation
                </span>
              </div>
            </div>
          ) : (
            <p className="today-empty">
              Risk thresholds will be surfaced once a trade is opened on
              this signal.
            </p>
          )}
          <p className="pd-risk-foot">
            We'd reconsider this signal if any of these holds.
          </p>
        </section>

        {/* ─── 6. Risk awareness ─── */}
        <section className="pd-section" data-test="pd-risk-aware">
          <p className="pd-section-label">Risk awareness</p>
          <div className="pd-risk-grid">
            {heldPct != null ? (
              <p className="pd-risk-item">
                Currently {fmtPct(heldPct)} of your portfolio.
                <Link to="/learn/term/concentration" className="pd-risk-link">
                  Read: concentration
                </Link>
              </p>
            ) : (
              <p className="pd-risk-item">
                Not currently in your portfolio. If opened at the engine's
                standard size, exposure would be a small share of your NAV.
                <Link to="/learn/term/position-sizing" className="pd-risk-link">
                  Read: position sizing
                </Link>
              </p>
            )}
            <p className="pd-risk-item">
              Daily moves on this symbol vary; check the recent range
              before sizing a position.
              <Link to="/learn/term/volatility" className="pd-risk-link">
                Read: volatility
              </Link>
            </p>
            {maxDrawdown != null && (
              <p className="pd-risk-item">
                Your portfolio's largest decline so far is {fmtPct(maxDrawdown)}.
                A new signal does not change that history.
                <Link to="/learn/term/drawdown" className="pd-risk-link">
                  Read: drawdown
                </Link>
              </p>
            )}
          </div>
        </section>

        {/* ─── 7. Expected horizon ─── */}
        <section className="pd-section" data-test="pd-horizon">
          <p className="pd-section-label">Expected horizon</p>
          <p className="pd-horizon">
            {concept?.slug === "momentum"
              ? "This kind of momentum setup typically plays out over " +
                "two to six weeks. The engine re-evaluates daily; if the " +
                "thesis no longer holds, you'll see a Trim or Sell signal."
              : concept?.slug === "mean-reversion"
                ? "Mean-reversion setups typically play out over one to " +
                  "three weeks. The engine re-evaluates daily."
                : "The engine re-evaluates this signal daily. " +
                  "If the thesis no longer holds, you'll see a Trim or " +
                  "Sell signal in your portfolio."}
          </p>
        </section>

        {/* Reference levels */}
        {(pick.risk?.entry_price != null
          || pick.risk?.target_price != null
          || pick.risk?.stop_loss != null) && (
          <section className="pd-section">
            <p className="pd-section-label">Reference levels</p>
            <p className="pd-reference">
              {pick.risk?.entry_price != null && (
                <>
                  <span className="pd-reference-label">entry</span>
                  {fmtCurrency(pick.risk.entry_price)}
                </>
              )}
              {pick.risk?.target_price != null && (
                <>
                  {" "}<span className="pd-reference-sep">·</span>{" "}
                  <span className="pd-reference-label">target</span>
                  {fmtCurrency(pick.risk.target_price)}
                </>
              )}
              {pick.risk?.stop_loss != null && (
                <>
                  {" "}<span className="pd-reference-sep">·</span>{" "}
                  <span className="pd-reference-label">stop</span>
                  {fmtCurrency(pick.risk.stop_loss)}
                </>
              )}
            </p>
          </section>
        )}

        {/* In your portfolio */}
        <section className="pd-section">
          <p className="pd-section-label">In your portfolio</p>
          {isHeld && heldPosition ? (
            <p className="pd-inport">
              You hold {Number(heldPosition.quantity).toLocaleString(
                undefined, { maximumFractionDigits: 4 },
              )} units of {pick.symbol ?? sym}
              {heldPosition.avg_cost != null && (
                <> at average cost {fmtCurrency(heldPosition.avg_cost)}</>
              )}
              {heldPosition.return_pct != null && (
                <> ({fmtPct(heldPosition.return_pct)})</>
              )}.
            </p>
          ) : (
            <p className="pd-inport pd-inport-muted">
              Not currently held.
            </p>
          )}
        </section>

        {/* ─── 8. Learn more ─── */}
        <section className="pd-section">
          <p className="pd-section-label">Learn more</p>
          <div className="pd-learn-chips">
            <Link to={`/learn/term/${action || "signal"}-signal`}
                  className="pd-learn-chip">
              What is a {actionLabel(action)} signal?
            </Link>
            <Link to="/learn/term/stop-loss"
                  className="pd-learn-chip">
              What is a stop?
            </Link>
            <Link to="/learn/term/cost-basis"
                  className="pd-learn-chip">
              Cost basis
            </Link>
            <Link to="/learn/term/drawdown"
                  className="pd-learn-chip">
              Drawdown
            </Link>
            {concept && (
              <Link to={`/learn/concept/${concept.slug}`}
                    className="pd-learn-chip">
                {concept.label}
              </Link>
            )}
          </div>
        </section>

        {/* ─── 9. Technical detail (collapsed) ─── */}
        <details className="pd-tech-details">
          <summary>Show technical detail</summary>
          <div className="pd-tech-grid">
            <span className="pd-tech-key">Engine version</span>
            <span className="pd-tech-val">{pick.engine_version ?? "—"}</span>
            <span className="pd-tech-key">Composite score</span>
            <span className="pd-tech-val">{String(pick.composite_score ?? "—")}</span>
            <span className="pd-tech-key">Family scores</span>
            <span className="pd-tech-val">
              {Object.keys(pick.family_scores ?? {}).length > 0
                ? Object.entries(pick.family_scores).map(([k, v]) =>
                    `${k}: ${v}`).join(" · ")
                : "—"}
            </span>
            <span className="pd-tech-key">Raw action</span>
            <span className="pd-tech-val">{pick.raw_action ?? "—"}</span>
            <span className="pd-tech-key">Adjusted raw action</span>
            <span className="pd-tech-val">{pick.raw_adjusted_action ?? "—"}</span>
            <span className="pd-tech-key">Generated at</span>
            <span className="pd-tech-val">{pick.generated_at ?? "—"}</span>
            <span className="pd-tech-key">Tags</span>
            <span className="pd-tech-val">
              {(pick.tags ?? []).join(", ") || "—"}
            </span>
            <span className="pd-tech-key">Live NAV (paper)</span>
            <span className="pd-tech-val">
              {live?.liveEstimatedNav != null
                ? fmtCurrency(live.liveEstimatedNav)
                : "—"}
            </span>
          </div>
        </details>

        <Link to="/today" className="pd-back">&larr; Back to Today</Link>
      </main>
    </div>
  );
}
