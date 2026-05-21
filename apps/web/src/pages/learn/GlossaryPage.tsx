// Glossary page — PR-5A Phase A.
// Search + filter chips + alphabetical list. With only 2 terms in
// Phase A, the alphabetical grouping is mostly a placeholder for
// PR-5B's 25+ additional terms; the layout is correct now.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import TodayNav from "@/components/today/TodayNav";

import { getAllTermsAlphabetical, type Term } from "@/lib/learn/curriculum";

import "../today/today.css";
import "@/styles/primitives.css";
import "./learn.css";


type Filter = "all" | "ai" | "portfolio" | "risk";


export default function GlossaryPage() {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    const all = getAllTermsAlphabetical();
    const q = search.trim().toLowerCase();
    return all.filter(t => {
      if (filter !== "all") {
        if (filter === "ai" && t.category !== "ai") return false;
        if (filter === "portfolio" && t.category !== "portfolio") return false;
        if (filter === "risk" && t.category !== "risk") return false;
      }
      if (!q) return true;
      return t.term.toLowerCase().includes(q)
        || t.definition.toLowerCase().includes(q);
    });
  }, [search, filter]);

  // Group by first letter
  const byLetter: Record<string, Term[]> = {};
  for (const t of filtered) {
    const letter = t.term.charAt(0).toUpperCase();
    if (!byLetter[letter]) byLetter[letter] = [];
    byLetter[letter].push(t);
  }
  const letters = Object.keys(byLetter).sort();

  return (
    <div className="today-root">
      <TodayNav />
      <main className="learn-page">

        <Link to="/learn" className="learn-back">&larr; Back to Learn</Link>

        <header className="mp-page-header">
          <div className="mp-eyebrow">Reference</div>
          <h1 className="mp-page-title learn-page-title">Glossary</h1>
          <p className="mp-page-subtitle">
            Definitions across investing, the engine, and your portfolio.
            More terms arrive in the next release.
          </p>
        </header>

        <section className="learn-section" style={{ borderTop: "none" }}>
          <input
            type="search"
            className="learn-glossary-search"
            placeholder="Search terms…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="learn-glossary-filters">
            {(["all", "ai", "portfolio", "risk"] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                className="learn-glossary-filter"
                data-active={filter === f ? "true" : undefined}
                onClick={() => setFilter(f)}
              >
                {f === "all" ? "All"
                  : f === "ai" ? "Engine"
                  : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </section>

        {filtered.length === 0 ? (
          <p className="today-empty">No terms match.</p>
        ) : (
          letters.map(letter => (
            <section key={letter}>
              <h2 className="learn-glossary-letter">{letter}</h2>
              <ul className="learn-glossary-list">
                {byLetter[letter]!.map((t: Term) => (
                  <li className="learn-glossary-row" key={t.slug}>
                    <Link to={`/learn/term/${t.slug}`}>
                      <span className="learn-glossary-name">{t.term}</span>
                      <span className="learn-glossary-def">{t.definition}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}

      </main>
    </div>
  );
}
