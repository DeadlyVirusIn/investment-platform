"""EDGAR actuals adapter — Phase 11.1 (remediation pass B).

Single-source discipline: this adapter emits ACTUAL records only
(EPS + Revenue). It NEVER emits consensus. Consensus comes from `fmp_consensus`.

Semantics (PIT):
- `as_of_date` = SEC `filing_date` — the date the 10-Q/10-K facts became public.
  Strict `<=` is enforced by Phase 10.6 consensus PIT logic at backtest time.
- `event_date` for the actual estimate = the FMP announcement date MATCHED by
  `period_of_report` (fiscal quarter end). Match rule: for each quarter end Q,
  the earliest FMP event_date e such that Q <= e <= Q + 90 days.

Units:
    EPS      -> usd_per_share  (XBRL native; us-gaap:EarningsPerShare*)
    Revenue  -> usd_raw         (XBRL native; us-gaap:Revenue*)

Concept selection (pass B):
    Deterministic per-symbol best-concept selection across a CANDIDATE list.
    Rejection of "first non-empty wins" in favor of a scored pick:
      score = (# quarterly rows in last 3 calendar years)
              + 5  if at least one annual-coherent Q4 derivable
              - 10 if no FY matching any Q1/Q2/Q3 (orphan annuals)
      tiebreak: lower concept-index in CANDIDATE list (stable)

    One concept per (symbol, metric). No silent union across concepts.

Q4 derivation:
    Q4 = FY − (Q1+Q2+Q3) only when:
      * all four inputs are same concept (same XBRL tag → same unit/scale)
      * all have same fiscal_year
      * annual 10-K filing_date is the PIT anchor for derived Q4 as_of_date
      * otherwise skip (logged).
"""

from __future__ import annotations

import datetime as dt
import warnings
from typing import Iterable

from loguru import logger

SOURCE = "sec_edgar"

# Candidate revenue concepts — ordered by preference for industrials/tech.
# Per-symbol scoring picks the actual winner (banks/energy use different tags).
REV_CONCEPT_CANDIDATES = (
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",   # post-2019 industrials/tech
    "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap:Revenues",                                              # banks/energy/pharma/legacy
    "us-gaap:RevenuesNetOfInterestExpense",                          # large banks (JPM/GS/WFC)
    "us-gaap:SalesRevenueNet",                                       # pre-2018
)

# Candidate EPS concepts — Diluted preferred, fall back to BasicAndDiluted
# (single-line filers) then Basic. Pro-forma and anti-dilutive concepts never
# used — those are not the reported EPS.
EPS_CONCEPT_CANDIDATES = (
    "us-gaap:EarningsPerShareDiluted",
    "us-gaap:EarningsPerShareBasicAndDiluted",
    "us-gaap:EarningsPerShareBasic",
)

_ANNUAL_DURATION_RANGE = (300, 380)   # 10-K fiscal-year duration
_QUARTERLY_DURATION_RANGE = (75, 105)  # 10-Q 3-month duration
_SCORING_WINDOW_YEARS = 3


# ---------------------------------------------------------------------------
# Low-level fact filtering
# ---------------------------------------------------------------------------

def _filter_rows(
    all_facts, concept_local_name: str,
    *, forms: set[str], duration_range: tuple[int, int],
) -> list[dict]:
    """Filter flat fact list by concept + form + period-duration.

    Dedup on period_end keeping EARLIEST filing (original, not amendment).
    """
    d_min, d_max = duration_range
    rows: list[dict] = []
    for fact in all_facts:
        concept = getattr(fact, "concept", "") or ""
        local = concept.split(":", 1)[-1] if ":" in concept else concept
        if local != concept_local_name:
            continue
        form = getattr(fact, "form_type", None) or getattr(fact, "form", None)
        if form not in forms:
            continue
        pend = getattr(fact, "period_end", None)
        pstart = getattr(fact, "period_start", None)
        fdate = getattr(fact, "filing_date", None)
        val = getattr(fact, "numeric_value", None)
        if val is None:
            val = getattr(fact, "value", None)
        if pend is None or pstart is None or fdate is None or val is None:
            continue
        if isinstance(pend, str):
            pend = dt.date.fromisoformat(pend[:10])
        if isinstance(pstart, str):
            pstart = dt.date.fromisoformat(pstart[:10])
        if isinstance(fdate, str):
            fdate = dt.date.fromisoformat(fdate[:10])
        dur_days = (pend - pstart).days
        if not (d_min <= dur_days <= d_max):
            continue
        rows.append({
            "period_end": pend, "period_start": pstart,
            "filing_date": fdate,
            "value": float(val),
            "fiscal_year": getattr(fact, "fiscal_year", None),
            "fiscal_period": getattr(fact, "fiscal_period", None),
            "form": form, "concept": local,
        })
    # Dedup on period_end — earliest filing wins (original, not /A)
    dedup: dict[dt.date, dict] = {}
    for r in sorted(rows, key=lambda x: x["filing_date"]):
        if r["period_end"] not in dedup:
            dedup[r["period_end"]] = r
    return sorted(dedup.values(), key=lambda x: x["period_end"])


def _filter_quarterly_rows(all_facts, concept_local: str) -> list[dict]:
    return _filter_rows(
        all_facts, concept_local,
        forms={"10-Q", "10-Q/A"},
        duration_range=_QUARTERLY_DURATION_RANGE,
    )


def _filter_annual_rows(all_facts, concept_local: str) -> list[dict]:
    return _filter_rows(
        all_facts, concept_local,
        forms={"10-K", "10-K/A"},
        duration_range=_ANNUAL_DURATION_RANGE,
    )


# ---------------------------------------------------------------------------
# Concept scoring
# ---------------------------------------------------------------------------

def _score_concept(all_facts, full_concept: str) -> dict:
    """Return a scoring dict for a concept on a symbol's fact set.

    Components:
      - quarterly_recent: #quarterly rows with period_end within last N years
      - annual_coherent:  #annual rows where Q1/Q2/Q3 of same fiscal_year exist
                           (Q4 derivable — signals clean annual/quarterly alignment)
      - orphan_annuals:   #annual rows with NO matching Q1/Q2/Q3 (penalized)
    """
    local = full_concept.split(":", 1)[1] if ":" in full_concept else full_concept
    q_rows = _filter_quarterly_rows(all_facts, local)
    a_rows = _filter_annual_rows(all_facts, local)

    cutoff = dt.date.today() - dt.timedelta(days=365 * _SCORING_WINDOW_YEARS)
    q_recent = [r for r in q_rows if r["period_end"] >= cutoff]

    # Annual coherence: how many FY facts have matching Q1+Q2+Q3
    fy_to_qs: dict[int, set[str]] = {}
    for q in q_rows:
        fy = q.get("fiscal_year")
        fp = q.get("fiscal_period")
        if fy is None or fp not in {"Q1", "Q2", "Q3"}:
            continue
        fy_to_qs.setdefault(fy, set()).add(fp)

    coherent = 0
    orphan = 0
    for a in a_rows:
        fy = a.get("fiscal_year")
        if fy is None:
            continue
        qset = fy_to_qs.get(fy, set())
        if {"Q1", "Q2", "Q3"}.issubset(qset):
            coherent += 1
        elif not qset:
            orphan += 1

    score = len(q_recent) + 5 * coherent - 10 * orphan
    return {
        "concept": full_concept,
        "quarterly_recent": len(q_recent),
        "quarterly_total": len(q_rows),
        "annual_total": len(a_rows),
        "annual_coherent": coherent,
        "orphan_annuals": orphan,
        "score": score,
        "q_rows": q_rows,
        "a_rows": a_rows,
    }


def _select_concept(
    all_facts, candidates: tuple[str, ...],
) -> tuple[str | None, list[dict], list[dict], list[dict]]:
    """Return (selected_concept, q_rows, a_rows, all_scores)."""
    scored = [_score_concept(all_facts, c) for c in candidates]
    # Ordered by (score desc, candidate_idx asc) — stable tiebreak
    scored_with_idx = [(s["score"], -i, s) for i, s in enumerate(scored)]
    scored_with_idx.sort(reverse=True)
    top = scored_with_idx[0][2]
    if top["score"] <= 0:
        return None, [], [], scored
    return top["concept"], top["q_rows"], top["a_rows"], scored


# ---------------------------------------------------------------------------
# Q4 derivation
# ---------------------------------------------------------------------------

def _derive_q4_rows(
    quarterly_rows: list[dict], annual_rows: list[dict],
    *, skipped_log: list[str], symbol: str, concept_label: str,
) -> list[dict]:
    """Q4 = FY − (Q1+Q2+Q3). Same-concept guard (_select_concept ensures this).
    Fiscal-year + same-concept preconditions enforced.
    """
    qidx: dict[tuple, dict] = {}
    for q in quarterly_rows:
        fy = q.get("fiscal_year")
        fp = q.get("fiscal_period")
        if fy is None or fp not in {"Q1", "Q2", "Q3"}:
            continue
        qidx[(fy, fp, q["concept"])] = q

    out: list[dict] = []
    for a in annual_rows:
        fy = a.get("fiscal_year")
        concept = a["concept"]
        if fy is None:
            skipped_log.append(
                f"{symbol}: Q4-derive skip {concept_label} FY-end={a['period_end']} "
                f"(annual missing fiscal_year)"
            )
            continue
        q1 = qidx.get((fy, "Q1", concept))
        q2 = qidx.get((fy, "Q2", concept))
        q3 = qidx.get((fy, "Q3", concept))
        missing = [lbl for lbl, v in [("Q1", q1), ("Q2", q2), ("Q3", q3)] if v is None]
        if missing:
            skipped_log.append(
                f"{symbol}: Q4-derive skip {concept_label} FY={fy} "
                f"(missing {missing} in same concept/fiscal_year)"
            )
            continue
        q4_val = a["value"] - q1["value"] - q2["value"] - q3["value"]
        out.append({
            "period_end": a["period_end"],
            "period_start": q3["period_end"] + dt.timedelta(days=1),
            "filing_date": a["filing_date"],
            "value": float(q4_val),
            "fiscal_year": fy,
            "fiscal_period": "Q4",
            "form": a["form"] + "_derived_q4",
            "concept": concept,
        })
    return out


# ---------------------------------------------------------------------------
# Period matching
# ---------------------------------------------------------------------------

def _match_period_to_event(
    period_end: dt.date, events: list[dt.date], max_gap_days: int = 100,
) -> dt.date | None:
    cand = [
        e for e in events
        if period_end <= e <= period_end + dt.timedelta(days=max_gap_days)
    ]
    return min(cand) if cand else None


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def fetch_actual_records(
    symbols: Iterable[tuple[str, str]],
    event_dates_by_symbol: dict[str, list[dt.date]],
    *, identity: str,
) -> tuple[list[dict], list[str], list[dict]]:
    """Fetch EDGAR actuals for each symbol.

    Returns:
        records: actual consensus-estimate rows for ingest_consensus
        errors:  human-readable skip/error notes
        concept_mapping: per-(symbol,metric) selected concept + score telemetry
    """
    from edgar import Company, set_identity
    set_identity(identity)

    records: list[dict] = []
    errors: list[str] = []
    concept_mapping: list[dict] = []
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    for sym, aid in symbols:
        events = sorted(event_dates_by_symbol.get(sym, []))
        if not events:
            errors.append(f"{sym}: no FMP events to match")
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                comp = Company(sym)
                facts = comp.get_facts()
        except Exception as exc:
            errors.append(f"{sym}: edgar fetch fail: {exc}")
            continue
        if facts is None:
            errors.append(f"{sym}: no facts")
            continue

        all_facts = facts.get_all_facts()

        # Per-symbol concept selection with full scoring
        rev_sel, rev_q, rev_a, rev_scores = _select_concept(
            all_facts, REV_CONCEPT_CANDIDATES,
        )
        eps_sel, eps_q, eps_a, eps_scores = _select_concept(
            all_facts, EPS_CONCEPT_CANDIDATES,
        )

        concept_mapping.append({
            "symbol": sym, "metric": "revenue",
            "selected_concept": rev_sel,
            "candidate_count": len(REV_CONCEPT_CANDIDATES),
            "selection_reason":
                "max_score_score_gt_zero" if rev_sel else "no_viable_concept",
            "scores": [{"concept": s["concept"],
                        "quarterly_recent": s["quarterly_recent"],
                        "annual_coherent": s["annual_coherent"],
                        "orphan_annuals": s["orphan_annuals"],
                        "score": s["score"]} for s in rev_scores],
            "selected_at": now_iso,
        })
        concept_mapping.append({
            "symbol": sym, "metric": "eps",
            "selected_concept": eps_sel,
            "candidate_count": len(EPS_CONCEPT_CANDIDATES),
            "selection_reason":
                "max_score_score_gt_zero" if eps_sel else "no_viable_concept",
            "scores": [{"concept": s["concept"],
                        "quarterly_recent": s["quarterly_recent"],
                        "annual_coherent": s["annual_coherent"],
                        "orphan_annuals": s["orphan_annuals"],
                        "score": s["score"]} for s in eps_scores],
            "selected_at": now_iso,
        })

        if rev_sel is None:
            errors.append(f"{sym}: no revenue concept scored > 0")
        if eps_sel is None:
            errors.append(f"{sym}: no EPS concept scored > 0")

        # Q4 derivation (same-concept guard — rev_sel and eps_sel are stable)
        q4_log: list[str] = []
        if rev_sel:
            q4_rev = _derive_q4_rows(
                rev_q, rev_a,
                skipped_log=q4_log, symbol=sym, concept_label="revenue",
            )
        else:
            q4_rev = []
        if eps_sel:
            q4_eps = _derive_q4_rows(
                eps_q, eps_a,
                skipped_log=q4_log, symbol=sym, concept_label="eps",
            )
        else:
            q4_eps = []
        if q4_log:
            for msg in q4_log:
                logger.debug("[edgar.act] {}", msg)
            errors.extend(q4_log)

        rev_rows = sorted(rev_q + q4_rev, key=lambda r: r["period_end"])
        eps_rows = sorted(eps_q + q4_eps, key=lambda r: r["period_end"])

        rev_by_pe = {r["period_end"]: r for r in rev_rows}
        eps_by_pe = {r["period_end"]: r for r in eps_rows}
        all_periods = sorted(set(rev_by_pe.keys()) | set(eps_by_pe.keys()))

        for pe in all_periods:
            ev = _match_period_to_event(pe, events)
            if ev is None:
                continue

            rev = rev_by_pe.get(pe)
            eps = eps_by_pe.get(pe)

            if rev is not None:
                records.append({
                    "asset_id": aid, "symbol": sym,
                    "event_date": ev.isoformat(), "metric": "revenue",
                    "estimate_type": "actual",
                    "value": rev["value"],
                    "value_unit": "usd_raw",
                    "as_of_date": rev["filing_date"].isoformat(),
                    "source": SOURCE,
                    "external_id": (
                        f"edgar:{sym}:pe={pe.isoformat()}:"
                        f"filed={rev['filing_date'].isoformat()}:rev"
                    ),
                })
            if eps is not None:
                records.append({
                    "asset_id": aid, "symbol": sym,
                    "event_date": ev.isoformat(), "metric": "eps",
                    "estimate_type": "actual",
                    "value": eps["value"],
                    "value_unit": "usd_per_share",
                    "as_of_date": eps["filing_date"].isoformat(),
                    "source": SOURCE,
                    "external_id": (
                        f"edgar:{sym}:pe={pe.isoformat()}:"
                        f"filed={eps['filing_date'].isoformat()}:eps"
                    ),
                })

    return records, errors, concept_mapping
