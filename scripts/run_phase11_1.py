"""Phase 11.1 — disciplined single-source ingestion + validation.

Sources (STRICT — no stitching):
  * FMP           -> consensus only (EPS + Revenue estimates)
  * SEC EDGAR     -> actuals only   (EPS Diluted + RevenueFromContract...)
  * iShares IWV   -> Russell 3000 universe (point-in-time)

Phase 10.6 guarantees maintained:
  * source_timezone=America/New_York (FMP)
  * value_unit explicit per metric (usd_per_share / usd_raw)
  * content_hash dedupe
  * NO silent TZ / unit inference
  * filing_date PIT semantics on actuals

STOPS at validation. Backtests deferred until validation passes.

Usage:
    python -m scripts.run_phase11_1                 # full pipeline
    python -m scripts.run_phase11_1 --top 50        # restrict universe
    python -m scripts.run_phase11_1 --skip-fetch    # reuse cached FMP+EDGAR
    python -m scripts.run_phase11_1 --skip-ingest   # just rerun validation
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset
from apps.api.src.ingestion.adapters.edgar_actuals import fetch_actual_records
from apps.api.src.ingestion.adapters.et_earnings import normalize_et_records
from apps.api.src.ingestion.adapters.fmp_consensus import fetch_consensus_records
from apps.api.src.ingestion.consensus import ingest_consensus
from apps.api.src.ingestion.earnings import ingest_earnings
from apps.api.src.ingestion.validation import run_validation

ET = ZoneInfo("America/New_York")
OUT_DIR = Path("artifacts/phase11_1")
OUT_DIR.mkdir(parents=True, exist_ok=True)
UNIVERSE_CSV = OUT_DIR / "iwv_universe_latest.csv"
CACHE_DIR = OUT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
EDGAR_IDENTITY = os.environ.get("EDGAR_IDENTITY", "kunalkhurana1@gmail.com kunal")

# Validation pass thresholds
MIN_USABLE_EPS_CONSENSUS_PCT   = 0.80
MIN_USABLE_EPS_ACTUAL_PCT      = 0.80
MIN_USABLE_REV_CONSENSUS_PCT   = 0.70
MIN_USABLE_REV_ACTUAL_PCT      = 0.70
MAX_ORPHAN_EVENTS_PCT          = 0.25
MAX_QUARANTINE_RATE_PCT        = 0.05
FORWARD_EVENT_CUTOFF_DAYS      = 7    # events newer than this excluded from actual coverage


def load_universe(top_n: int) -> list[dict]:
    if not UNIVERSE_CSV.exists():
        raise FileNotFoundError(
            f"{UNIVERSE_CSV} missing — run `python -m scripts.fetch_iwv_universe` first"
        )
    with UNIVERSE_CSV.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["market_value_usd"] = float(r["market_value_usd"])
        r["weight_pct"] = float(r["weight_pct"])
    rows.sort(key=lambda r: r["market_value_usd"], reverse=True)
    if top_n > 0:
        rows = rows[:top_n]
    return rows


def ensure_assets(session, symbols: list[str]) -> dict[str, str]:
    existing = session.execute(
        select(Asset).where(Asset.symbol.in_(symbols))
    ).scalars().all()
    have = {a.symbol: a.id for a in existing}
    for sym in symbols:
        if sym not in have:
            a = Asset(
                id=str(uuid.uuid4()), symbol=sym, asset_class="equity",
                currency="USD", is_active=True,
            )
            session.add(a); session.flush()
            have[sym] = a.id
    session.commit()
    return have


def _cache_path(kind: str) -> Path:
    return CACHE_DIR / f"{kind}.jsonl"


def _write_cache(kind: str, records: list[dict]) -> None:
    with _cache_path(kind).open("w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


def _read_cache(kind: str) -> list[dict]:
    p = _cache_path(kind)
    if not p.exists():
        return []
    with p.open() as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def run_fetch(symbol_asset_pairs: list[tuple[str, str]]) -> dict:
    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY not set in env")
    logger.info("[p11.1] FMP fetch — {} symbols...", len(symbol_asset_pairs))
    t0 = time.time()
    earnings, consensus, fmp_errs = fetch_consensus_records(
        symbol_asset_pairs, api_key=FMP_API_KEY,
    )
    logger.info(
        "[p11.1] FMP done in {:.1f}s: {} earnings, {} consensus, {} errs",
        time.time() - t0, len(earnings), len(consensus), len(fmp_errs),
    )
    _write_cache("fmp_earnings", earnings)
    _write_cache("fmp_consensus", consensus)
    _write_cache("fmp_errors", [{"err": e} for e in fmp_errs])

    # Restrict EDGAR universe to FMP-supported symbols (discipline: never
    # fetch actuals for a symbol we have no consensus for — prevents orphans).
    supported_syms = {e["symbol"] for e in earnings}
    supported_pairs = [(s, aid) for s, aid in symbol_asset_pairs if s in supported_syms]
    skipped = [s for s, _ in symbol_asset_pairs if s not in supported_syms]
    logger.info(
        "[p11.1] FMP-supported universe: {}/{} symbols (skipped: {})",
        len(supported_pairs), len(symbol_asset_pairs), skipped,
    )
    _write_cache("fmp_supported_symbols", [{"symbol": s} for s, _ in supported_pairs])

    # Build event_dates_by_symbol for EDGAR matching
    ev_by_sym: dict[str, list[dt.date]] = {}
    for e in earnings:
        ev_by_sym.setdefault(e["symbol"], []).append(
            dt.date.fromisoformat(e["event_date"])
        )

    logger.info("[p11.1] EDGAR fetch — {} supported symbols...", len(supported_pairs))
    t1 = time.time()
    actuals, edgar_errs, concept_mapping = fetch_actual_records(
        supported_pairs, ev_by_sym, identity=EDGAR_IDENTITY,
    )
    logger.info(
        "[p11.1] EDGAR done in {:.1f}s: {} actuals, {} concepts mapped, {} errs",
        time.time() - t1, len(actuals), len(concept_mapping), len(edgar_errs),
    )
    _write_cache("edgar_actuals", actuals)
    _write_cache("edgar_errors", [{"err": e} for e in edgar_errs])
    _write_cache("edgar_concept_mapping", concept_mapping)

    return {
        "fmp_earnings": earnings,
        "fmp_consensus": consensus,
        "fmp_errors": fmp_errs,
        "edgar_actuals": actuals,
        "edgar_errors": edgar_errs,
        "edgar_concept_mapping": concept_mapping,
        "fmp_supported_symbols": sorted(supported_syms),
        "fmp_skipped_symbols": skipped,
    }


def load_from_cache() -> dict:
    return {
        "fmp_earnings": _read_cache("fmp_earnings"),
        "fmp_consensus": _read_cache("fmp_consensus"),
        "fmp_errors": [r["err"] for r in _read_cache("fmp_errors")],
        "edgar_actuals": _read_cache("edgar_actuals"),
        "edgar_errors": [r["err"] for r in _read_cache("edgar_errors")],
        "edgar_concept_mapping": _read_cache("edgar_concept_mapping"),
    }


def run_ingest(session, data: dict) -> dict:
    # Earnings — FMP announcement-date events, ET-naive TS → UTC via Phase 10.6
    earn_norm = normalize_et_records(data["fmp_earnings"])
    res_e = ingest_earnings(session, earn_norm, source_timezone=ET)

    # Consensus — FMP ESTIMATES ONLY (estimate_type=consensus)
    res_c_fmp = ingest_consensus(session, data["fmp_consensus"])

    # Actuals — EDGAR ONLY (estimate_type=actual)
    res_c_edg = ingest_consensus(session, data["edgar_actuals"])

    return {
        "earnings_fmp": res_e.as_dict(),
        "consensus_fmp": res_c_fmp.as_dict(),
        "actuals_edgar": res_c_edg.as_dict(),
    }


def compute_eligible_completeness(session, *, cutoff_days: int) -> dict:
    """Recompute actual-coverage metrics restricted to ELIGIBLE events
    (event_date < today - cutoff_days). Pre-filter forward events from
    denominator so actuals are judged only on events that SHOULD have filed.
    """
    from sqlalchemy import text
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=cutoff_days)
    row = session.execute(text("""
        WITH events AS (
          SELECT id, asset_id, event_date,
                 (event_date < :cutoff) AS is_eligible
          FROM earnings_event
        )
        SELECT
          COUNT(*)                                            AS raw_events,
          SUM(CASE WHEN NOT is_eligible THEN 1 ELSE 0 END)    AS forward_excluded,
          SUM(CASE WHEN is_eligible THEN 1 ELSE 0 END)        AS eligible_events
        FROM events
    """), {"cutoff": cutoff}).one()
    raw_events, forward_excluded, eligible_events = row
    eligible_events = eligible_events or 0

    # Count actuals matched per eligible event
    r2 = session.execute(text("""
        SELECT
          SUM(CASE WHEN EXISTS (SELECT 1 FROM consensus_estimate ce
                  WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
                  AND ce.metric='eps' AND ce.estimate_type='actual')
              THEN 1 ELSE 0 END) AS has_eps_act,
          SUM(CASE WHEN EXISTS (SELECT 1 FROM consensus_estimate ce
                  WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
                  AND ce.metric='revenue' AND ce.estimate_type='actual')
              THEN 1 ELSE 0 END) AS has_rev_act,
          SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM consensus_estimate ce
                  WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
                  AND ce.estimate_type='actual')
              THEN 1 ELSE 0 END) AS orphan_no_actual
        FROM earnings_event ee
        WHERE ee.event_date < :cutoff
    """), {"cutoff": cutoff}).one()
    has_eps_act = r2[0] or 0
    has_rev_act = r2[1] or 0
    orphan      = r2[2] or 0

    def _pct(n, d):
        return round(n / d, 4) if d else 0.0

    return {
        "raw_events": int(raw_events or 0),
        "forward_excluded_events": int(forward_excluded or 0),
        "eligible_actual_events": int(eligible_events or 0),
        "eligible_eps_actual_pct": _pct(has_eps_act, eligible_events),
        "eligible_rev_actual_pct": _pct(has_rev_act, eligible_events),
        "eligible_orphan_ratio":   _pct(orphan,      eligible_events),
        "eligible_has_eps_actual": int(has_eps_act),
        "eligible_has_rev_actual": int(has_rev_act),
        "eligible_orphan_count":   int(orphan),
    }


def validation_verdict(val: dict, eligible: dict) -> tuple[str, list[str]]:
    """Apply Phase 11.1 gate thresholds.

    Consensus thresholds apply to ALL events (denominator includes forward
    events — consensus should always exist). Actual thresholds use eligible-
    events denominator (forward events excluded).
    """
    failures: list[str] = []
    comp = val.get("completeness_pct", {})

    eps_c = comp.get("eps_consensus", 0)
    rev_c = comp.get("revenue_consensus", 0)

    if eps_c < MIN_USABLE_EPS_CONSENSUS_PCT:
        failures.append(f"eps_consensus completeness {eps_c:.3f} < {MIN_USABLE_EPS_CONSENSUS_PCT}")
    if rev_c < MIN_USABLE_REV_CONSENSUS_PCT:
        failures.append(f"revenue_consensus completeness {rev_c:.3f} < {MIN_USABLE_REV_CONSENSUS_PCT}")

    eps_a_e = eligible["eligible_eps_actual_pct"]
    rev_a_e = eligible["eligible_rev_actual_pct"]
    orphan_r = eligible["eligible_orphan_ratio"]
    eligible_n = eligible["eligible_actual_events"]

    if eligible_n == 0:
        failures.append("no eligible events (denominator=0)")
    else:
        if eps_a_e < MIN_USABLE_EPS_ACTUAL_PCT:
            failures.append(
                f"eps_actual (eligible) {eps_a_e:.3f} < {MIN_USABLE_EPS_ACTUAL_PCT}"
            )
        if rev_a_e < MIN_USABLE_REV_ACTUAL_PCT:
            failures.append(
                f"revenue_actual (eligible) {rev_a_e:.3f} < {MIN_USABLE_REV_ACTUAL_PCT}"
            )
        if orphan_r > MAX_ORPHAN_EVENTS_PCT:
            failures.append(
                f"orphan_events (eligible) {orphan_r:.3f} > {MAX_ORPHAN_EVENTS_PCT}"
            )

    qbr = val.get("quarantine_by_reason") or {}
    total_quarantine = sum(qbr.values())
    events = val.get("earnings_events", 0) or 1
    if (total_quarantine / events) > MAX_QUARANTINE_RATE_PCT:
        failures.append(
            f"quarantine_rate {total_quarantine}/{events} > {MAX_QUARANTINE_RATE_PCT}"
        )

    hard_fail_reasons = {"naive_timestamp", "ambiguous_unit", "unit_metric_mismatch"}
    for reason in hard_fail_reasons:
        n = qbr.get(reason, 0)
        if n > 0:
            failures.append(f"hard-reject reason '{reason}' = {n} (must be 0)")

    return ("PASS" if not failures else "FAIL"), failures


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50,
                   help="Top-N universe members by market value")
    p.add_argument("--skip-fetch", action="store_true")
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args()

    # Universe
    universe = load_universe(args.top)
    symbols = [u["ticker"] for u in universe]
    logger.info("[p11.1] universe: {} symbols (top-{})", len(symbols), args.top)

    # Ensure asset rows — one DB round trip
    with SessionLocal() as session:
        sym_to_aid = ensure_assets(session, symbols)

    pairs = [(s, sym_to_aid[s]) for s in symbols if s in sym_to_aid]
    logger.info("[p11.1] asset resolution: {}/{}", len(pairs), len(symbols))

    # Fetch
    if args.skip_fetch:
        data = load_from_cache()
        logger.info(
            "[p11.1] cached: {} earnings, {} consensus, {} actuals",
            len(data["fmp_earnings"]), len(data["fmp_consensus"]),
            len(data["edgar_actuals"]),
        )
    else:
        data = run_fetch(pairs)

    # Ingest
    with SessionLocal() as session:
        if not args.skip_ingest:
            ing = run_ingest(session, data)
            logger.info("[p11.1] ingestion: {}", json.dumps(ing, default=str))
        else:
            ing = {}

        # Validate
        val_obj = run_validation(session)
        val = val_obj.as_dict() if hasattr(val_obj, "as_dict") else val_obj.__dict__
        eligible = compute_eligible_completeness(
            session, cutoff_days=FORWARD_EVENT_CUTOFF_DAYS,
        )

    verdict, failures = validation_verdict(val, eligible)

    # Concept-mapping summary by metric
    mapping_rows = data.get("edgar_concept_mapping", [])
    concept_summary: dict[str, dict[str, int]] = {"revenue": {}, "eps": {}}
    unresolved_symbols: dict[str, list[str]] = {"revenue": [], "eps": []}
    for m in mapping_rows:
        metric = m["metric"]
        sel = m.get("selected_concept") or "NONE"
        concept_summary.setdefault(metric, {})
        concept_summary[metric][sel] = concept_summary[metric].get(sel, 0) + 1
        if sel == "NONE":
            unresolved_symbols[metric].append(m["symbol"])

    # Persist concept mapping
    (OUT_DIR / "concept_mapping.jsonl").write_text(
        "\n".join(json.dumps(m, default=str) for m in mapping_rows)
    )

    report = {
        "phase": "11.1_passB",
        "today": dt.date.today().isoformat(),
        "universe_top_n": args.top,
        "universe_size": len(symbols),
        "fetch": {
            "fmp_earnings_count": len(data["fmp_earnings"]),
            "fmp_consensus_count": len(data["fmp_consensus"]),
            "fmp_error_count": len(data["fmp_errors"]),
            "edgar_actuals_count": len(data["edgar_actuals"]),
            "edgar_error_count": len(data["edgar_errors"]),
        },
        "ingest": ing,
        "validation": val,
        "eligibility": eligible,
        "concept_mapping_summary": concept_summary,
        "unresolved_concept_symbols": unresolved_symbols,
        "verdict": verdict,
        "failures": failures,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    print("=" * 78)
    print(f"PHASE 11.1 — INGEST + VALIDATION REPORT ({dt.date.today()})")
    print("=" * 78)
    print(f"Universe: top-{args.top} IWV ({len(symbols)} symbols)")
    print(f"Fetch: FMP={len(data['fmp_earnings'])} earn / {len(data['fmp_consensus'])} consensus / "
          f"{len(data['fmp_errors'])} err")
    print(f"       EDGAR={len(data['edgar_actuals'])} actuals / {len(data['edgar_errors'])} err")
    print(f"Events ingested (earnings_event rows):     {val.get('earnings_events')}")
    print(f"Consensus rows (est+actual merged):         {val.get('consensus_records')}")
    print()
    print("--- Consensus coverage (all events) ---")
    print(f"  eps_cons={val['completeness_pct']['eps_consensus']:.3f}  "
          f"rev_cons={val['completeness_pct']['revenue_consensus']:.3f}")
    print()
    print("--- Eligibility-adjusted ACTUAL coverage ---")
    print(f"  raw_events                = {eligible['raw_events']}")
    print(f"  forward_excluded_events   = {eligible['forward_excluded_events']} "
          f"(event_date >= today - {FORWARD_EVENT_CUTOFF_DAYS}d)")
    print(f"  eligible_actual_events    = {eligible['eligible_actual_events']}")
    print(f"  eps_actual (eligible)     = {eligible['eligible_eps_actual_pct']:.3f}  "
          f"({eligible['eligible_has_eps_actual']}/{eligible['eligible_actual_events']})")
    print(f"  rev_actual (eligible)     = {eligible['eligible_rev_actual_pct']:.3f}  "
          f"({eligible['eligible_has_rev_actual']}/{eligible['eligible_actual_events']})")
    print(f"  orphan_ratio (eligible)   = {eligible['eligible_orphan_ratio']:.3f}  "
          f"({eligible['eligible_orphan_count']}/{eligible['eligible_actual_events']})")
    print()
    print("--- Hard-rejects / integrity ---")
    print(f"  naive_ts={val['integrity']['events_naive_timestamp_rejected']}  "
          f"ambig_unit={val['integrity']['events_ambiguous_unit_rejected']}  "
          f"unit_mismatch={val['integrity']['events_unit_metric_mismatch']}  "
          f"impossible_timing={val['integrity']['events_impossible_timing']}")
    print(f"Sources: earnings={val['distinct_sources']['earnings']}  "
          f"consensus={val['distinct_sources']['consensus']}")
    print()
    print("--- Concept-mapping summary ---")
    for metric, ccnt in concept_summary.items():
        for c, n in sorted(ccnt.items(), key=lambda x: -x[1]):
            print(f"  {metric:<10}  {c:<65} {n}")
    if unresolved_symbols.get("revenue") or unresolved_symbols.get("eps"):
        print(f"  UNRESOLVED revenue symbols: {unresolved_symbols['revenue']}")
        print(f"  UNRESOLVED eps symbols:     {unresolved_symbols['eps']}")
    print("-" * 78)
    print(f"VERDICT: {verdict}")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
    print("=" * 78)
    print(f"Report: {OUT_DIR / 'report.json'}")
    print("=" * 78)
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
