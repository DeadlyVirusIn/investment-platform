// Phase Opt-C2 Pre-Canary 0.5 — canary portfolio status block.
//
// Operator-grade. Calm-by-default. Surfaces:
//   * canary portfolio name + active flag
//   * cash deployed vs initial
//   * open trade count vs cap
//   * scope locks (universe, strategy family, capital cap)
//   * single-line funnel summary if any rows exist
//
// Discipline:
//   * Read-only (calls /api/options/canary/* GET endpoints).
//   * No mutation, no toggles, no forms.
//   * Honest empty state — no fabricated counts.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface CanaryPortfolioRow {
  id: string;
  name: string;
  cash_initial: string;
  cash_current: string;
  max_open_trades: number;
  max_capital_per_trade: string;
  active: boolean;
  universe: string;
  strategy_family: string;
  open_count: number;
}

interface PortfoliosResponse {
  count: number;
  rows: CanaryPortfolioRow[];
}

interface FunnelRecentResponse {
  count: number;
  days: number;
  rows: Array<{
    run_date: string;
    candidates_total: number;
    promoted: number;
    filled: number;
    closed_today: number;
  }>;
}


function _Money({ amount }: { amount: string | undefined }) {
  if (amount === undefined || amount === null) return <>—</>;
  const n = Number(amount);
  if (Number.isNaN(n)) return <>{amount}</>;
  return <>${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}</>;
}


export default function OptionsCanaryStatus() {
  const { data: portfolios } = useQuery<PortfoliosResponse>({
    queryKey: ["options", "canary", "portfolios"],
    queryFn: () => apiGet("/options/canary/portfolios"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const { data: funnel } = useQuery<FunnelRecentResponse>({
    queryKey: ["options", "canary", "funnel", "recent", 14],
    queryFn: () => apiGet("/options/canary/funnel/recent?days=14"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const rows = portfolios?.rows ?? [];

  if (portfolios !== undefined && rows.length === 0) {
    return (
      <section
        className="u-card opt-canary-status"
        data-test="options-canary-status"
      >
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Canary</span>
          <span className="opt-card-meta">no portfolios configured</span>
        </header>
        <p className="opt-card-empty">
          No canary portfolios have been declared. Promotion path is dormant.
        </p>
      </section>
    );
  }

  return (
    <section
      className="u-card opt-canary-status"
      data-test="options-canary-status"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Canary</span>
        <span className="opt-card-meta">
          {rows.length === 1 ? "1 portfolio" : `${rows.length} portfolios`}
          {" "}declared · read-only
        </span>
      </header>

      {rows.map((p) => {
        const slotsUsed = p.open_count;
        const slotsMax = p.max_open_trades;
        const cashDeployed =
          Number(p.cash_initial) - Number(p.cash_current);
        const stateLabel = p.active
          ? "active · accepting promotions"
          : "dormant · promotions gated off";
        return (
          <div
            key={p.id}
            className="opt-canary-portfolio"
            data-test={`options-canary-portfolio-${p.name}`}
          >
            <div className="opt-canary-row">
              <span className="opt-canary-name">{p.name}</span>
              <span className="opt-canary-state">{stateLabel}</span>
            </div>
            <div className="opt-canary-row opt-canary-row-meta">
              <span>
                Universe: <strong>{p.universe}</strong>
              </span>
              <span>
                Strategy: <strong>{p.strategy_family}</strong>
              </span>
              <span>
                Cap: <_Money amount={p.max_capital_per_trade} /> / trade
              </span>
            </div>
            <div className="opt-canary-row opt-canary-row-meta">
              <span>
                Slots used:{" "}
                <strong>
                  {slotsUsed} / {slotsMax}
                </strong>
              </span>
              <span>
                Cash deployed: <_Money amount={String(cashDeployed)} /> of{" "}
                <_Money amount={p.cash_initial} />
              </span>
            </div>
          </div>
        );
      })}

      <div
        className="opt-canary-funnel-line"
        data-test="options-canary-funnel-line"
      >
        {funnel === undefined ? (
          <>Loading funnel summary…</>
        ) : funnel.count === 0 ? (
          <>No funnel rows in the last 14 days. Promotion job has not yet executed.</>
        ) : (
          <>
            {funnel.count} funnel row{funnel.count === 1 ? "" : "s"} in last 14d
            {" · "}
            promoted{" "}
            <strong>
              {funnel.rows.reduce((s, r) => s + (r.promoted ?? 0), 0)}
            </strong>
            {" · "}
            filled{" "}
            <strong>
              {funnel.rows.reduce((s, r) => s + (r.filled ?? 0), 0)}
            </strong>
            {" · "}
            closed{" "}
            <strong>
              {funnel.rows.reduce((s, r) => s + (r.closed_today ?? 0), 0)}
            </strong>
          </>
        )}
      </div>
    </section>
  );
}
