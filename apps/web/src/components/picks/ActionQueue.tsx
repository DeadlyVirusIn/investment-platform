// ActionQueue — picks grouped by action category.
// Renames "AI suggestions" framing into a Today's Action Queue.
// Each group has its own header + count, and shows a meaningful
// empty message when zero (e.g. "No buy setups passed today").

import type { Pick, LatestPrice } from "@/lib/picks/api";
import type { PicksFilter } from "@/lib/picks/copilot";
import { rankingLabel, applyFilter } from "@/lib/picks/copilot";
import type { SymbolEvents } from "@/lib/portfolio/events";
import { deriveBadge } from "@/lib/portfolio/events";

import PickBox from "./PickBox";


export interface ActionQueueProps {
  picks: Pick[];                                  // already excludes priority
  allPicks: Pick[];                               // for ranking context
  priceMap: Record<string, LatestPrice | null | undefined>;
  filter: PicksFilter;
  eventsBySymbol?: Record<string, SymbolEvents>;
  onPickClick: (id: string) => void;
  // Phase 15f.3 — set of pick IDs already opened in PickModal during
  // this/recent sessions. PickBox uses it to render data-visited.
  visited?: Set<string>;
}


interface Group {
  key: "buy" | "trim" | "hold" | "sell";
  label: string;
  emptyText: string;
}


const GROUPS: Group[] = [
  { key: "buy",  label: "Buy candidates",
    emptyText: "No buy setups passed today — waiting for cleaner entries." },
  { key: "trim", label: "Trim / Reduce",
    emptyText: "No positions are flagged for reduction today." },
  { key: "sell", label: "Avoid / Sell",
    emptyText: "No urgent exits today." },
  { key: "hold", label: "Watch / Hold",
    emptyText: "No watchlist holds currently." },
];


export default function ActionQueue({
  picks, allPicks, priceMap, filter, eventsBySymbol, onPickClick, visited,
}: ActionQueueProps) {
  const filtered = applyFilter(picks, filter);

  function badgeFor(p: Pick) {
    if (!eventsBySymbol || !p.symbol) return null;
    return deriveBadge(eventsBySymbol[p.symbol]);
  }

  // When a non-"all" filter is active, show a single flat list
  if (filter !== "all") {
    return (
      <div className="action-queue" data-test="action-queue">
        <div className="action-queue-grid">
          {filtered.map(p => (
            <PickBox
              key={p.id}
              pick={p}
              price={p.symbol ? priceMap[p.symbol] : null}
              rankingLabel={rankingLabel(p, allPicks)}
              eventBadge={badgeFor(p)}
              onClick={onPickClick}
              visited={visited?.has(p.id)}
            />
          ))}
          {filtered.length === 0 && (
            <div className="action-queue-empty">No picks match this filter.</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="action-queue" data-test="action-queue">
      {GROUPS.map(g => {
        const groupPicks = picks.filter(p => (p.adjusted_action ?? p.action) === g.key);
        return (
          <section key={g.key} className="action-group" data-action={g.key}>
            <header className="action-group-header">
              <h4 className="action-group-title">
                <span className="action-group-dot" data-action={g.key} />
                {g.label}
              </h4>
              <span className="action-group-count">
                {groupPicks.length}
              </span>
            </header>
            {groupPicks.length === 0 ? (
              <div className="action-group-empty">{g.emptyText}</div>
            ) : (
              <div className="action-group-grid">
                {groupPicks.map(p => (
                  <PickBox
                    key={p.id}
                    pick={p}
                    price={p.symbol ? priceMap[p.symbol] : null}
                    rankingLabel={rankingLabel(p, allPicks)}
                    eventBadge={badgeFor(p)}
                    onClick={onPickClick}
                    visited={visited?.has(p.id)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
