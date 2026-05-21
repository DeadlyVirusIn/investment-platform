"""Phase 11.2B — Broad-Universe Messy Beat Scale-Up.

Pure scale-up of Phase 11.2. Same definition, same entry timing, same
windows, same costs. Only the universe changes (top-50 → top-150 IWV).

FMP free tier: 250 req/day. Cache-aware fetch reuses Phase 11.1 pass B
results (50 probed symbols) and only queries the NEW 100 symbols.

No definition changes. No threshold tuning. No new sources. No regime/guidance
overlays. Stops at backtest reporting.

Usage:
    python -m scripts.run_phase11_2b --top 150
    python -m scripts.run_phase11_2b --top 150 --skip-fetch   (re-use all cache)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import random
import statistics as st
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import Asset
from apps.api.src.ingestion.adapters.edgar_actuals import fetch_actual_records
from apps.api.src.ingestion.adapters.et_earnings import normalize_et_records
from apps.api.src.ingestion.adapters.fmp_consensus import fetch_consensus_records
from apps.api.src.ingestion.consensus import ingest_consensus
from apps.api.src.ingestion.earnings import ingest_earnings
from apps.api.src.ingestion.validation import run_validation

ET = ZoneInfo("America/New_York")

# --- Frozen config (identical to Phase 11.2) -------------------------------
HOLD_WINDOWS = (1, 3, 5, 10, 20)
COST_BPS     = (10, 20)
FORWARD_CUTOFF_DAYS = 7

# --- Universe + cache paths -------------------------------------------------
IWV_CSV  = Path("artifacts/phase11_1/iwv_universe_latest.csv")
CACHE_DIR_OLD = Path("artifacts/phase11_1/cache")   # reuse Phase 11.1 cache
OUT_DIR = Path("artifacts/phase11_2b")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = OUT_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
EDGAR_IDENTITY = os.environ.get(
    "EDGAR_IDENTITY", "kunalkhurana1@gmail.com kunal",
)

# Phase 11.1 thresholds (for ingestion health only; not Messy-Beat gate)
MIN_EPS_CONS = 0.80
MIN_EPS_ACT  = 0.80
MIN_REV_CONS = 0.70
MIN_REV_ACT  = 0.70
MAX_ORPHAN   = 0.25
MAX_QUARANT  = 0.05


# ---------------------------------------------------------------------------
# Universe + cache loaders
# ---------------------------------------------------------------------------
def load_universe(top_n: int) -> list[dict]:
    with IWV_CSV.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["market_value_usd"] = float(r["market_value_usd"])
    rows.sort(key=lambda r: r["market_value_usd"], reverse=True)
    return rows[:top_n]


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open() as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def load_cached_fmp() -> tuple[list[dict], list[dict], list[str], list[dict]]:
    """Load previous FMP cache. Returns (earnings, consensus, errors,
    concept_mapping) — concept mapping stored separately in edgar cache."""
    earnings = _read_jsonl(CACHE_DIR_OLD / "fmp_earnings.jsonl")
    consensus = _read_jsonl(CACHE_DIR_OLD / "fmp_consensus.jsonl")
    errors_raw = _read_jsonl(CACHE_DIR_OLD / "fmp_errors.jsonl")
    errors = [r["err"] for r in errors_raw]
    return earnings, consensus, errors, []


def load_cached_edgar() -> tuple[list[dict], list[str], list[dict]]:
    actuals = _read_jsonl(CACHE_DIR_OLD / "edgar_actuals.jsonl")
    errs_raw = _read_jsonl(CACHE_DIR_OLD / "edgar_errors.jsonl")
    errs = [r["err"] for r in errs_raw]
    mapping = _read_jsonl(CACHE_DIR_OLD / "edgar_concept_mapping.jsonl")
    return actuals, errs, mapping


# ---------------------------------------------------------------------------
# Asset resolution (idempotent)
# ---------------------------------------------------------------------------
def ensure_assets(session: Session, symbols: list[str]) -> dict[str, str]:
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


# ---------------------------------------------------------------------------
# Cache-aware fetch
# ---------------------------------------------------------------------------
def fetch_incremental(
    universe_symbols: list[str],
    sym_to_aid: dict[str, str],
    *, old_earnings: list[dict], old_consensus: list[dict],
    old_errors: list[str], old_actuals: list[dict],
    old_edgar_errors: list[str], old_concept_map: list[dict],
) -> dict:
    """Fetch FMP + EDGAR for symbols not already in Phase 11.1 cache.
    Merge new results with old cache — returns unified dataset."""
    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY not set")

    # Derive already-probed symbols (supported + errored)
    already_supported = {e["symbol"] for e in old_earnings}
    already_errored = {err.split(":")[0] for err in old_errors}
    already_probed = already_supported | already_errored
    new_syms = [s for s in universe_symbols if s not in already_probed]
    logger.info(
        "[p11.2b] FMP cache reuse: {} probed ({} supported, {} errored), "
        "{} NEW to fetch",
        len(already_probed), len(already_supported),
        len(already_errored), len(new_syms),
    )

    # Fetch new FMP
    new_pairs = [(s, sym_to_aid[s]) for s in new_syms if s in sym_to_aid]
    t0 = time.time()
    new_earnings, new_consensus, new_errors = fetch_consensus_records(
        new_pairs, api_key=FMP_API_KEY,
    )
    logger.info(
        "[p11.2b] FMP new fetch: {} symbols, {}s: {} earnings, {} consensus, {} errs",
        len(new_pairs), int(time.time() - t0),
        len(new_earnings), len(new_consensus), len(new_errors),
    )

    # Merged FMP data
    all_earnings = old_earnings + new_earnings
    all_consensus = old_consensus + new_consensus
    all_errors = old_errors + new_errors

    # Derive current FMP-supported set across merged data
    supported_syms = {e["symbol"] for e in all_earnings}
    supported_pairs = [(s, sym_to_aid[s]) for s in sorted(supported_syms)
                       if s in sym_to_aid]

    # Cache new-only fetch for idempotent re-runs
    _write_jsonl(CACHE_DIR / "fmp_earnings_new.jsonl", new_earnings)
    _write_jsonl(CACHE_DIR / "fmp_consensus_new.jsonl", new_consensus)
    _write_jsonl(CACHE_DIR / "fmp_errors_new.jsonl",
                 [{"err": e} for e in new_errors])

    # EDGAR — re-fetch only for newly-supported symbols (old_supported already
    # in cache). Concept scoring is deterministic → re-fetching cached symbols
    # would yield identical output.
    old_actual_syms = {a["symbol"] for a in old_actuals}
    newly_supported = [s for s in supported_syms if s not in old_actual_syms]
    newly_supported_pairs = [(s, sym_to_aid[s]) for s in newly_supported
                             if s in sym_to_aid]

    # Build event_dates_by_symbol for newly-supported symbols only
    ev_by_sym: dict[str, list[dt.date]] = {}
    for e in all_earnings:
        if e["symbol"] not in newly_supported:
            continue
        ev_by_sym.setdefault(e["symbol"], []).append(
            dt.date.fromisoformat(e["event_date"])
        )

    t1 = time.time()
    new_actuals, new_edgar_errs, new_concept_map = fetch_actual_records(
        newly_supported_pairs, ev_by_sym, identity=EDGAR_IDENTITY,
    )
    logger.info(
        "[p11.2b] EDGAR new fetch: {} symbols, {}s: {} actuals, {} concepts, {} errs",
        len(newly_supported_pairs), int(time.time() - t1),
        len(new_actuals), len(new_concept_map), len(new_edgar_errs),
    )

    all_actuals = old_actuals + new_actuals
    all_edgar_errors = old_edgar_errors + new_edgar_errs
    all_concept_map = old_concept_map + new_concept_map

    # Cache new-only EDGAR
    _write_jsonl(CACHE_DIR / "edgar_actuals_new.jsonl", new_actuals)
    _write_jsonl(CACHE_DIR / "edgar_concept_mapping_new.jsonl", new_concept_map)
    _write_jsonl(CACHE_DIR / "edgar_errors_new.jsonl",
                 [{"err": e} for e in new_edgar_errs])
    _write_jsonl(CACHE_DIR / "merged_all_earnings.jsonl", all_earnings)
    _write_jsonl(CACHE_DIR / "merged_all_consensus.jsonl", all_consensus)
    _write_jsonl(CACHE_DIR / "merged_all_actuals.jsonl", all_actuals)
    _write_jsonl(CACHE_DIR / "merged_all_concept_map.jsonl", all_concept_map)

    return {
        "earnings": all_earnings,
        "consensus": all_consensus,
        "errors": all_errors,
        "actuals": all_actuals,
        "edgar_errors": all_edgar_errors,
        "concept_mapping": all_concept_map,
        "supported_symbols": sorted(supported_syms),
        "new_supported_count": len(newly_supported),
        "new_fmp_call_count": len(new_pairs),
    }


def load_from_merged_cache() -> dict:
    return {
        "earnings": _read_jsonl(CACHE_DIR / "merged_all_earnings.jsonl"),
        "consensus": _read_jsonl(CACHE_DIR / "merged_all_consensus.jsonl"),
        "errors": [],
        "actuals": _read_jsonl(CACHE_DIR / "merged_all_actuals.jsonl"),
        "edgar_errors": [],
        "concept_mapping": _read_jsonl(CACHE_DIR / "merged_all_concept_map.jsonl"),
        "supported_symbols": sorted({e["symbol"] for e in
                                     _read_jsonl(CACHE_DIR / "merged_all_earnings.jsonl")}),
        "new_supported_count": 0,
        "new_fmp_call_count": 0,
    }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def run_ingest(session: Session, data: dict) -> dict:
    earn_norm = normalize_et_records(data["earnings"])
    res_e = ingest_earnings(session, earn_norm, source_timezone=ET)
    res_c_fmp = ingest_consensus(session, data["consensus"])
    res_c_edg = ingest_consensus(session, data["actuals"])
    return {
        "earnings_fmp": res_e.as_dict(),
        "consensus_fmp": res_c_fmp.as_dict(),
        "actuals_edgar": res_c_edg.as_dict(),
    }


def compute_eligible_metrics(session: Session) -> dict:
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=FORWARD_CUTOFF_DAYS)
    row = session.execute(text("""
      WITH events AS (
        SELECT asset_id, event_date, (event_date < :c) AS eligible
        FROM earnings_event WHERE source='fmp'
      )
      SELECT COUNT(*),
             SUM(CASE WHEN NOT eligible THEN 1 ELSE 0 END),
             SUM(CASE WHEN eligible THEN 1 ELSE 0 END)
      FROM events
    """), {"c": cutoff}).one()
    raw, fwd, eligible = row
    r2 = session.execute(text("""
      SELECT
        SUM(CASE WHEN EXISTS(SELECT 1 FROM consensus_estimate ce
              WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
              AND ce.metric='eps' AND ce.estimate_type='actual') THEN 1 ELSE 0 END),
        SUM(CASE WHEN EXISTS(SELECT 1 FROM consensus_estimate ce
              WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
              AND ce.metric='revenue' AND ce.estimate_type='actual') THEN 1 ELSE 0 END),
        SUM(CASE WHEN NOT EXISTS(SELECT 1 FROM consensus_estimate ce
              WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
              AND ce.estimate_type='actual') THEN 1 ELSE 0 END)
      FROM earnings_event ee
      WHERE ee.event_date < :c AND ee.source='fmp'
    """), {"c": cutoff}).one()
    eps_a = r2[0] or 0; rev_a = r2[1] or 0; orph = r2[2] or 0
    return {
        "raw_events": int(raw or 0),
        "forward_excluded": int(fwd or 0),
        "eligible": int(eligible or 0),
        "eps_actual_count": int(eps_a),
        "rev_actual_count": int(rev_a),
        "orphan_count": int(orph),
        "eps_actual_pct": round(eps_a / max(eligible or 1, 1), 4),
        "rev_actual_pct": round(rev_a / max(eligible or 1, 1), 4),
        "orphan_ratio":   round(orph / max(eligible or 1, 1), 4),
    }


# ---------------------------------------------------------------------------
# Messy-Beat backtest — IDENTICAL to Phase 11.2
# ---------------------------------------------------------------------------
def load_eligible_events(session: Session) -> list[dict]:
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=FORWARD_CUTOFF_DAYS)
    rows = session.execute(text("""
        SELECT
          ee.symbol, ee.asset_id, ee.event_date, ee.event_time, ee.fiscal_period,
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='consensus' AND ce.source='fmp'
             ORDER BY ce.as_of_date DESC LIMIT 1),
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1),
          (SELECT ce.as_of_date FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1),
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='consensus' AND ce.source='fmp'
             ORDER BY ce.as_of_date DESC LIMIT 1),
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1),
          (SELECT ce.as_of_date FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1)
        FROM earnings_event ee
        WHERE ee.event_date < :c AND ee.source='fmp'
        ORDER BY ee.event_date
    """), {"c": cutoff}).all()
    return [{
        "symbol": r[0], "asset_id": r[1], "event_date": r[2],
        "event_time": r[3], "fiscal_period": r[4],
        "eps_cons": float(r[5]) if r[5] is not None else None,
        "eps_act":  float(r[6]) if r[6] is not None else None,
        "eps_act_asof": r[7],
        "rev_cons": float(r[8]) if r[8] is not None else None,
        "rev_act":  float(r[9]) if r[9] is not None else None,
        "rev_act_asof": r[10],
    } for r in rows]


def load_price_frames(session: Session, symbols: set[str]) -> dict[str, list]:
    frames: dict[str, list] = {}
    rows = session.execute(text("""
        SELECT a.symbol, pb.ts, pb.close
        FROM price_bar pb JOIN asset a ON a.id=pb.asset_id
        WHERE pb.timeframe='1d' AND a.symbol = ANY(:syms)
        ORDER BY a.symbol, pb.ts
    """), {"syms": list(symbols)}).all()
    for sym, ts, close in rows:
        d = ts.date() if hasattr(ts, "date") else ts
        frames.setdefault(sym, []).append((d, float(close)))
    for sym in list(frames.keys()):
        seen = {}
        for d, c in frames[sym]:
            seen[d] = c
        frames[sym] = sorted(seen.items())
    return frames


def first_idx_after(frame, d):
    for i, (bd, _) in enumerate(frame):
        if bd > d:
            return i
    return None


def classify(ev):
    ec, ea, rc, ra = ev["eps_cons"], ev["eps_act"], ev["rev_cons"], ev["rev_act"]
    if None in (ec, ea, rc, ra):
        return None
    eps_beat = ea > ec
    rev_beat = ra > rc
    if eps_beat and not rev_beat:  return "messy_beat"
    if eps_beat and rev_beat:      return "both_beat"
    if not eps_beat and rev_beat:  return "eps_miss_rev_beat"
    return "both_miss"


def run_trades(events, frames):
    trades = []
    for ev in events:
        if classify(ev) != "messy_beat":
            continue
        fr = frames.get(ev["symbol"])
        if fr is None:
            continue
        entry_anchor = max(
            ev["event_date"], ev["eps_act_asof"], ev["rev_act_asof"],
        )
        i_entry = first_idx_after(fr, entry_anchor)
        if i_entry is None:
            continue
        entry_date, entry_close = fr[i_entry]
        pw = {}
        ok = True
        for N in HOLD_WINDOWS:
            ix = i_entry + N
            if ix >= len(fr):
                ok = False
                break
            pw[N] = {
                "exit_date": fr[ix][0].isoformat(),
                "exit_close": fr[ix][1],
                "return_raw": (fr[ix][1] - entry_close) / entry_close,
            }
        if not ok:
            continue
        eps_s = (ev["eps_act"] - ev["eps_cons"]) / max(abs(ev["eps_cons"]), 1e-9)
        rev_s = (ev["rev_act"] - ev["rev_cons"]) / max(abs(ev["rev_cons"]), 1e-9)
        trades.append({
            "symbol": ev["symbol"], "event_date": ev["event_date"].isoformat(),
            "fiscal_period": ev["fiscal_period"],
            "entry_anchor": entry_anchor.isoformat(),
            "entry_date": entry_date.isoformat(), "entry_close": entry_close,
            "eps_cons": ev["eps_cons"], "eps_act": ev["eps_act"],
            "rev_cons": ev["rev_cons"], "rev_act": ev["rev_act"],
            "eps_surprise_pct": eps_s, "rev_surprise_pct": rev_s,
            "windows": pw,
        })
    return trades


def _bootstrap_ci(xs, *, n_boot=5000, conf=0.95):
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n
             for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize_window(trades, N, bps):
    cost = bps / 1e4
    rg = [t["windows"][N]["return_raw"] for t in trades]
    rn = [r - cost for r in rg]
    n = len(rn)
    if n == 0:
        return {"N": N, "n": 0}
    mean = st.mean(rn); med = st.median(rn)
    sd = st.pstdev(rn) if n > 1 else 0.0
    wins = sum(1 for r in rn if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    lo, hi = _bootstrap_ci(rn)
    eq = 1.0; path = []
    for r in rn:
        eq *= (1 + r); path.append(eq)
    pk = path[0] if path else 1.0; maxdd = 0.0
    for v in path:
        pk = max(pk, v); maxdd = min(maxdd, (v - pk) / pk)
    return {
        "N": N, "n": n, "cost_bps": bps,
        "mean_pct": mean * 100, "median_pct": med * 100, "std_pct": sd * 100,
        "hit_rate": wins / n, "t_stat": t,
        "ci95_mean_pct": [lo * 100, hi * 100],
        "mean_gross_pct": st.mean(rg) * 100,
        "cumulative_ret_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_drawdown_pct": maxdd * 100,
    }


def bucketed(trades, N, bps, key_fn):
    groups: dict[str, list[float]] = defaultdict(list)
    cost = bps / 1e4
    for t in trades:
        groups[key_fn(t)].append(t["windows"][N]["return_raw"] - cost)
    out = {}
    for g, rs in groups.items():
        n = len(rs); m = st.mean(rs) if rs else 0.0
        sd = st.pstdev(rs) if n > 1 else 0.0
        out[g] = {
            "n": n, "mean_pct": m * 100,
            "hit_rate": sum(1 for r in rs if r > 0) / n,
            "t_stat": m / (sd / math.sqrt(n)) if sd > 0 and n > 1 else 0.0,
        }
    return out


def surprise_bucket(eps_pct, rev_pct):
    mag = abs(eps_pct) + abs(rev_pct)
    if mag < 0.02: return "minor"
    if mag < 0.08: return "moderate"
    return "large"


def load_sector_map():
    if not IWV_CSV.exists():
        return {}
    with IWV_CSV.open() as f:
        return {row["ticker"]: row.get("sector", "")
                for row in csv.DictReader(f)}


def load_concept_map_dict():
    rows = _read_jsonl(CACHE_DIR / "merged_all_concept_map.jsonl")
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["symbol"], {})[r["metric"]] = (
            r.get("selected_concept") or "NONE"
        )
    return out


def verdict_gate(summaries):
    s = summaries.get("10_20bps")
    if not s or s.get("n", 0) == 0:
        return ("FAIL", ["no trades"])
    n = s["n"]; t = s["t_stat"]; m = s["mean_pct"]
    lo, hi = s["ci95_mean_pct"]
    if n >= 30 and t > 2.0 and m > 0 and lo > 0:
        return ("PASS", [f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"])
    if n >= 15 and (t > 1.0 or (m > 0 and hi > 0)):
        return ("WEAK", [f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"])
    return ("FAIL", [f"n={n} t={t:.2f} mean={m:.3f}% CI=[{lo:.3f},{hi:.3f}]"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=150)
    p.add_argument("--skip-fetch", action="store_true")
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args()

    # --- Universe ---
    universe_rows = load_universe(args.top)
    universe_symbols = [u["ticker"] for u in universe_rows]
    logger.info("[p11.2b] universe top-{}: {} symbols", args.top, len(universe_symbols))

    with SessionLocal() as session:
        sym_to_aid = ensure_assets(session, universe_symbols)

    # --- Fetch ---
    if args.skip_fetch:
        data = load_from_merged_cache()
        logger.info("[p11.2b] using merged cache: {} earnings, {} consensus, {} actuals",
                    len(data["earnings"]), len(data["consensus"]), len(data["actuals"]))
    else:
        old_e, old_c, old_err, _ = load_cached_fmp()
        old_a, old_eerr, old_cm = load_cached_edgar()
        data = fetch_incremental(
            universe_symbols, sym_to_aid,
            old_earnings=old_e, old_consensus=old_c, old_errors=old_err,
            old_actuals=old_a, old_edgar_errors=old_eerr,
            old_concept_map=old_cm,
        )

    # --- Ingest ---
    with SessionLocal() as session:
        if not args.skip_ingest:
            ing = run_ingest(session, data)
            logger.info("[p11.2b] ingestion: {}", json.dumps(ing, default=str))
        else:
            ing = {}
        val_obj = run_validation(session)
        val = val_obj.as_dict() if hasattr(val_obj, "as_dict") else val_obj.__dict__
        eligible = compute_eligible_metrics(session)
        events = load_eligible_events(session)
        syms = {e["symbol"] for e in events}
        frames = load_price_frames(session, syms)

    # --- Backtest ---
    labels = Counter(classify(e) or "missing_metric" for e in events)
    trades = run_trades(events, frames)
    n_trades = len(trades)
    logger.info("[p11.2b] eligible events={} labels={} messy-beat trades={}",
                len(events), dict(labels), n_trades)

    summaries = {}
    for N in HOLD_WINDOWS:
        for bps in COST_BPS:
            summaries[f"{N}_{bps}bps"] = summarize_window(trades, N, bps)

    ranked = sorted(trades, key=lambda t: t["windows"][10]["return_raw"])
    top_losers = [{
        "symbol": t["symbol"], "event_date": t["event_date"],
        "ret_10d_pct": t["windows"][10]["return_raw"] * 100,
        "eps_surp_pct": t["eps_surprise_pct"] * 100,
        "rev_surp_pct": t["rev_surprise_pct"] * 100,
    } for t in ranked[:5]]
    top_winners = [{
        "symbol": t["symbol"], "event_date": t["event_date"],
        "ret_10d_pct": t["windows"][10]["return_raw"] * 100,
        "eps_surp_pct": t["eps_surprise_pct"] * 100,
        "rev_surp_pct": t["rev_surprise_pct"] * 100,
    } for t in ranked[-5:][::-1]]

    sector_map = load_sector_map()
    concept_map = load_concept_map_dict()
    sector_split = bucketed(trades, 10, 20.0,
                            key_fn=lambda t: sector_map.get(t["symbol"], "Unknown"))
    surprise_split = bucketed(trades, 10, 20.0,
                              key_fn=lambda t: surprise_bucket(
                                  t["eps_surprise_pct"], t["rev_surprise_pct"]))
    concept_split = bucketed(trades, 10, 20.0,
                             key_fn=lambda t: concept_map.get(t["symbol"], {})
                                              .get("revenue", "UNKNOWN")
                                              .split(":")[-1])

    verdict, vreasons = verdict_gate(summaries)

    # --- Comparison vs top-50 baseline ---
    top50_report_path = Path("artifacts/phase11_2/report.json")
    top50 = {}
    if top50_report_path.exists():
        top50 = json.loads(top50_report_path.read_text())

    report = {
        "phase": "11.2b_messy_beat_broad_universe",
        "today": dt.date.today().isoformat(),
        "universe_top_n": args.top,
        "universe_size": len(universe_symbols),
        "supported_symbols_count": len(data["supported_symbols"]),
        "new_fmp_call_count": data.get("new_fmp_call_count", 0),
        "new_supported_count": data.get("new_supported_count", 0),
        "eligibility": eligible,
        "label_counts": dict(labels),
        "messy_beat_prevalence_pct": round(
            100 * labels.get("messy_beat", 0) / max(eligible.get("eligible", 1), 1), 2
        ),
        "n_messy_beat_trades": n_trades,
        "sample_confidence": (
            "credible (n>=30)"     if n_trades >= 30 else
            "suggestive (15<=n<30)" if n_trades >= 15 else
            "too_thin (n<15)"
        ),
        "per_window_summaries": summaries,
        "top_winners_10d": top_winners,
        "top_losers_10d": top_losers,
        "sector_split_10d_20bps": sector_split,
        "surprise_magnitude_split_10d_20bps": surprise_split,
        "concept_family_split_10d_20bps": concept_split,
        "comparison_vs_top50": {
            "top50_n_messy_beat": top50.get("n_messy_beat_trades"),
            "top50_verdict": top50.get("verdict"),
            "top50_eligible_events": top50.get("universe", {}).get("eligible_events"),
        },
        "verdict": verdict,
        "verdict_reasons": vreasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))
    _write_jsonl(OUT_DIR / "trades.jsonl", trades)

    # Print
    print("=" * 78)
    print(f"PHASE 11.2B - MESSY BEAT BROAD UNIVERSE SCALE-UP ({dt.date.today()})")
    print("=" * 78)
    print(f"Universe: top-{args.top} IWV ({len(universe_symbols)} symbols)")
    print(f"FMP-supported: {len(data['supported_symbols'])} "
          f"(+{data.get('new_supported_count',0)} new this run)")
    print(f"New FMP calls: {data.get('new_fmp_call_count',0)}")
    print()
    print("--- Eligibility ---")
    print(f"  raw_events            = {eligible['raw_events']}")
    print(f"  forward_excluded      = {eligible['forward_excluded']}")
    print(f"  eligible              = {eligible['eligible']}")
    print(f"  eps_actual %  (elig)  = {eligible['eps_actual_pct']:.3f}")
    print(f"  rev_actual %  (elig)  = {eligible['rev_actual_pct']:.3f}")
    print(f"  orphan_ratio (elig)   = {eligible['orphan_ratio']:.3f}")
    print()
    print(f"--- Label distribution ---  {dict(labels)}")
    mb_prev = report["messy_beat_prevalence_pct"]
    print(f"Messy-beat prevalence: {mb_prev}% of eligible events")
    print(f"Messy-beat tradable (full 20D forward): n={n_trades}")
    print(f"Sample confidence: {report['sample_confidence']}")
    print()
    if n_trades:
        print(f"{'N':>3} {'n':>4} {'gross%':>8} {'net10%':>8} {'net20%':>8} "
              f"{'hit':>5} {'t':>6} {'CI95% 20bps':<28} {'maxDD%':>7}")
        for N in HOLD_WINDOWS:
            s20 = summaries[f"{N}_20bps"]
            s10 = summaries[f"{N}_10bps"]
            if s20["n"] == 0: continue
            print(f"{N:>3} {s20['n']:>4} {s20['mean_gross_pct']:>+8.3f} "
                  f"{s10['mean_pct']:>+8.3f} {s20['mean_pct']:>+8.3f} "
                  f"{s20['hit_rate']:>5.3f} {s20['t_stat']:>+6.2f} "
                  f"[{s20['ci95_mean_pct'][0]:+.3f},{s20['ci95_mean_pct'][1]:+.3f}] "
                  f"{s20['max_drawdown_pct']:>+7.2f}")
        print()
        print("--- Top winners (10D gross) ---")
        for t in top_winners:
            print(f"  {t['symbol']:6} {t['event_date']} ret={t['ret_10d_pct']:+.2f}% "
                  f"eps_surp={t['eps_surp_pct']:+.2f}% rev_surp={t['rev_surp_pct']:+.2f}%")
        print("--- Top losers (10D gross) ---")
        for t in top_losers:
            print(f"  {t['symbol']:6} {t['event_date']} ret={t['ret_10d_pct']:+.2f}% "
                  f"eps_surp={t['eps_surp_pct']:+.2f}% rev_surp={t['rev_surp_pct']:+.2f}%")
        print()
        print("--- Sector split (10D @ 20bps) ---")
        for sec, s in sorted(sector_split.items(), key=lambda x: -x[1]["n"]):
            print(f"  {sec:<32} n={s['n']:>3} mean={s['mean_pct']:+.3f}% "
                  f"hit={s['hit_rate']:.3f} t={s['t_stat']:+.2f}")
        print("--- Surprise magnitude (10D @ 20bps) ---")
        for mag, s in sorted(surprise_split.items()):
            print(f"  {mag:<10} n={s['n']:>3} mean={s['mean_pct']:+.3f}% "
                  f"hit={s['hit_rate']:.3f} t={s['t_stat']:+.2f}")
        print("--- Revenue-concept family (sanity, 10D @ 20bps) ---")
        for cf, s in sorted(concept_split.items(), key=lambda x: -x[1]["n"]):
            print(f"  {cf:<45} n={s['n']:>3} mean={s['mean_pct']:+.3f}% t={s['t_stat']:+.2f}")
    print()
    print("--- Comparison vs top-50 ---")
    print(f"  top-50 messy-beat trades: {top50.get('n_messy_beat_trades')}")
    print(f"  top-50 verdict:           {top50.get('verdict')}")
    print(f"  top-50 eligible events:   {top50.get('universe',{}).get('eligible_events')}")
    print(f"  broad  messy-beat trades: {n_trades}")
    print(f"  broad  eligible events:   {eligible['eligible']}")
    print(f"  broad  prevalence:        {mb_prev}%")
    print()
    print("-" * 78)
    print(f"VERDICT: {verdict}")
    for r in vreasons:
        print(f"  reason: {r}")
    print("=" * 78)
    print(f"Report: {OUT_DIR / 'report.json'}")
    print(f"Trades: {OUT_DIR / 'trades.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
