// Phase Opt-C1 Step 7 — Rejected Candidates workflow group.
//
// Collapsible list of failed candidates with PASS/FAIL evidence
// per row. Sits inside the tracker workflow (Checkpoint 3 will
// fold this into the grouped tracker; for now renders standalone
// for verification).
//
// Discipline:
//   - Real shadow_log rows only (no synthetic rejections)
//   - Per-row PASS/FAIL chips for all 7 filters
//   - Default collapsed; click to expand

import { useState } from "react";

import { cn } from "@/lib/cn";
import {
  FILTER_LABELS,
  daysSince,
  isRunFromToday,
  useShadowRunDetail,
  useShadowRunsList,
  type ShadowDecision,
} from "@/lib/options/researchCandidates";


function _RejectionRow({ d }: { d: ShadowDecision }) {
  const [open, setOpen] = useState(false);
  const passes = Object.entries(d.filters);
  const failed = passes.filter(([, p]) => !p);
  return (
    <li className="opt-rejected-row">
      <button
        type="button"
        className="opt-rejected-head"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        <span className="opt-rejected-toggle">{open ? "▾" : "▸"}</span>
        <span className="opt-rejected-ticker">{d.underlying_symbol}</span>
        <span className="opt-rejected-strategy">{d.strategy_name}</span>
        <span className="opt-rejected-failures">
          {failed.length === 0
            ? "—"
            : failed.map(([name]) => FILTER_LABELS[name] ?? name).join(", ")}
        </span>
      </button>
      {open && (
        <div className="opt-rejected-detail">
          <ul className="opt-suggestion-why-list">
            {passes.map(([code, passed]) => (
              <li
                key={code}
                className={cn("opt-suggestion-why-row",
                              passed ? "is-pos" : "is-neg")}
              >
                <span className="opt-suggestion-why-mark">
                  {passed ? "✓" : "✗"}
                </span>
                <span>{FILTER_LABELS[code] ?? code}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}


export default function OptionsRejectedCandidatesGroup() {
  const [open, setOpen] = useState(false);
  const runsQ = useShadowRunsList();
  const latestDate = runsQ.data?.runs?.[0]?.run_date ?? null;
  const detailQ = useShadowRunDetail(latestDate);
  const decisions = detailQ.data?.decisions ?? [];
  const todayHasRun = isRunFromToday(latestDate);
  const lastAge = daysSince(latestDate);
  const rejected = decisions.filter(d => !d.would_trade);

  return (
    <section className="u-card opt-card" data-test="options-rejected-candidates">
      <button
        type="button"
        className="opt-rejected-section-head"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
      >
        <span className="opt-rejected-toggle">{open ? "▾" : "▸"}</span>
        <span className="opt-card-eyebrow">Rejected candidates</span>
        <span className="opt-card-meta" style={{ marginLeft: "auto" }}>
          {todayHasRun
            ? `${rejected.length} rejected today`
            : latestDate
              ? `${rejected.length} rejected ${lastAge}d ago`
              : "no runs"}
        </span>
      </button>

      {open && (
        <>
          {rejected.length === 0 && (
            <p className="opt-empty-body" style={{ marginTop: 8 }}>
              {todayHasRun
                ? "No rejections today."
                : "Rejected candidates appear here when shadow evaluation runs daily (Phase Opt-B3)."}
            </p>
          )}
          {rejected.length > 0 && (
            <ul className="opt-rejected-list">
              {rejected.map((d, i) => (
                <_RejectionRow key={`${d.option_symbol}-${i}`} d={d} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
