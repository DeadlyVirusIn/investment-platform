// MarketEvents — Market Events & Catalysts section.
// Fetches /api/market/events for the active symbol set. Empty/not-
// connected states are first-class.

import { useEffect, useState } from "react";

import {
  fetchMarketEvents, type EventsState, type SymbolEvents,
} from "@/lib/portfolio/events";


export interface MarketEventsProps {
  symbols: string[];
}


function fmtRel(iso: string): string {
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 0) {
    const futureH = -hours;
    if (futureH < 24) return `in ${Math.round(futureH)}h`;
    return `in ${Math.round(futureH / 24)}d`;
  }
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


function totalsPerSymbol(events: SymbolEvents): { earnings: number; news: number; filings: number; expir: number } {
  return {
    earnings: events.earnings.length,
    news: events.news.length,
    filings: events.filings.length,
    expir: events.options_expirations.length,
  };
}


export default function MarketEvents({ symbols }: MarketEventsProps) {
  const [state, setState] = useState<EventsState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchMarketEvents(symbols).then(s => {
      if (!cancelled) setState(s);
    });
    return () => { cancelled = true; };
  }, [symbols.join(",")]);

  if (state.status === "loading") {
    return (
      <section className="me-section" data-test="me-loading">
        <header className="pi-section-header">
          <h3>Market Events &amp; Catalysts</h3>
          <span className="pi-section-sub">Loading…</span>
        </header>
      </section>
    );
  }

  if (state.status === "not-connected") {
    return (
      <section className="me-section" data-test="me-not-connected">
        <header className="pi-section-header">
          <h3>Market Events &amp; Catalysts</h3>
          <span className="pi-section-sub">Not connected</span>
        </header>
        <div className="pi-empty-state">
          <h4>News and earnings feed not connected yet</h4>
          <p>
            Connect a Polygon, Benzinga, or SEC EDGAR provider to activate
            this section. Once wired, this surface shows upcoming earnings,
            recent SEC filings, news catalysts, and options expirations for
            every symbol in your watchlist and recommendations.
          </p>
          <p className="me-contract-hint">
            Expected endpoint: <code>GET /api/market/events?symbols=…</code>
          </p>
        </div>
      </section>
    );
  }

  if (state.status === "empty") {
    return (
      <section className="me-section" data-test="me-empty">
        <header className="pi-section-header">
          <h3>Market Events &amp; Catalysts</h3>
          <span className="pi-section-sub">No fresh catalysts</span>
        </header>
        <div className="pi-empty-state">
          <h4>No fresh news, earnings, or filings right now</h4>
          <p>
            Provider is connected but no events match your current symbol set.
            Check back during market hours or earnings weeks.
          </p>
        </div>
      </section>
    );
  }

  // Ready
  const { data } = state;
  const entries = Object.entries(data.symbols);

  return (
    <section className="me-section" data-test="me-ready">
      <header className="pi-section-header">
        <h3>Market Events &amp; Catalysts</h3>
        <span className="pi-section-sub">
          {entries.length} symbol{entries.length === 1 ? "" : "s"} · refreshed {fmtRel(data.generated_at)}
        </span>
      </header>

      <div className="me-grid">
        {entries.map(([sym, events]) => {
          const totals = totalsPerSymbol(events);
          const earnUpcoming = events.earnings.find(e => e.status === "upcoming");
          const topNews = events.news.slice(0, 2);
          const topFiling = events.filings[0];
          const nextExpir = events.options_expirations[0];

          return (
            <article key={sym} className="me-card">
              <header className="me-card-header">
                <h4 className="me-card-symbol">{sym}</h4>
                <div className="me-card-counts">
                  {totals.earnings > 0 && (
                    <span className="me-pill" data-tone="info" title="Upcoming + recent earnings events">
                      {totals.earnings} earnings
                    </span>
                  )}
                  {totals.news > 0 && (
                    <span className="me-pill" data-tone="default" title="Recent news items">
                      {totals.news} news
                    </span>
                  )}
                  {totals.filings > 0 && (
                    <span className="me-pill" data-tone="info" title="Recent SEC filings">
                      {totals.filings} filings
                    </span>
                  )}
                  {totals.expir > 0 && (
                    <span className="me-pill" data-tone="warn" title="Upcoming options expirations">
                      {totals.expir} expirations
                    </span>
                  )}
                </div>
              </header>

              {earnUpcoming && (
                <div className="me-row">
                  <span className="me-row-label">Earnings</span>
                  <span className="me-row-value">{earnUpcoming.date} · {earnUpcoming.type}</span>
                </div>
              )}
              {nextExpir && (
                <div className="me-row">
                  <span className="me-row-label">Next expiry</span>
                  <span className="me-row-value">{nextExpir.expiration}</span>
                </div>
              )}
              {topFiling && (
                <div className="me-row">
                  <span className="me-row-label">Filing</span>
                  <a href={topFiling.url} target="_blank" rel="noopener noreferrer" className="me-row-link">
                    {topFiling.form} · {fmtRel(topFiling.filed_at)}
                  </a>
                </div>
              )}
              {topNews.length > 0 && (
                <ul className="me-news">
                  {topNews.map((n, i) => (
                    <li key={i} className="me-news-item" data-sentiment={n.sentiment ?? "neutral"}>
                      <a href={n.url} target="_blank" rel="noopener noreferrer">{n.title}</a>
                      <span className="me-news-meta">{n.source} · {fmtRel(n.published_at)}</span>
                    </li>
                  ))}
                </ul>
              )}

              {totals.earnings === 0 && totals.news === 0 && totals.filings === 0 && (
                <div className="me-empty-line">No fresh catalyst</div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
