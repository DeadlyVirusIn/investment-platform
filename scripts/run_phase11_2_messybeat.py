"""Phase 11.2 — TRUE Messy Beat backtest on Phase 11.1 eligible events.

Canonical Messy Beat signal:
    eps_beat   := actual.eps     >  consensus.eps     (strict)
    rev_miss   := actual.revenue <  consensus.revenue (strict)
    messy_beat := eps_beat AND rev_miss

Universe (frozen from Phase 11.1 pass B):
    - 28 FMP-supported symbols (top-50 IWV intersect FMP free tier)
    - Earnings + consensus source = FMP only
    - Actuals source = SEC EDGAR only
    - Events eligible for actual-coverage (event_date < today - 7d)
    - Both EPS and Revenue actual present (else drop — cannot classify)

Tradable point (PIT-safe):
    entry_anchor = max(event_date, eps_actual.as_of_date, rev_actual.as_of_date)
    entry_idx    = first trading day whose date > entry_anchor
    exit_idx     = entry_idx + N trading days

Holding windows:  1D, 3D, 5D, 10D, 20D (trading days).
Costs:            10 bps and 20 bps round-trip (subtract from each trade return).

NO parameter tuning, NO regime filter, NO size sweep, NO cherry-picked window.

Outputs written to  artifacts/phase11_2/{report.json, trades.jsonl}.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal

# ---------------------------------------------------------------------------
# Config (frozen)
# ---------------------------------------------------------------------------
HOLD_WINDOWS = (1, 3, 5, 10, 20)
COST_BPS     = (10, 20)                 # round-trip basis points
FORWARD_CUTOFF_DAYS = 7
SECTOR_CSV = Path("artifacts/phase11_1/iwv_universe_latest.csv")
OUT_DIR = Path("artifacts/phase11_2")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Load eligible event records
# ---------------------------------------------------------------------------
def load_eligible_events(session: Session) -> list[dict]:
    """Join earnings_event + consensus+actual for eps and revenue.
    Filter to eligible (event_date < today - cutoff) AND both actuals present."""
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=FORWARD_CUTOFF_DAYS)

    rows = session.execute(text("""
        SELECT
          ee.symbol, ee.asset_id, ee.event_date,
          ee.event_time, ee.fiscal_period,
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='consensus' AND ce.source='fmp'
             ORDER BY ce.as_of_date DESC LIMIT 1)              AS eps_cons,
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1)               AS eps_act,
          (SELECT ce.as_of_date FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='eps' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1)               AS eps_act_asof,
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='consensus' AND ce.source='fmp'
             ORDER BY ce.as_of_date DESC LIMIT 1)              AS rev_cons,
          (SELECT ce.value FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1)               AS rev_act,
          (SELECT ce.as_of_date FROM consensus_estimate ce
             WHERE ce.asset_id=ee.asset_id AND ce.event_date=ee.event_date
             AND ce.metric='revenue' AND ce.estimate_type='actual' AND ce.source='sec_edgar'
             ORDER BY ce.as_of_date ASC LIMIT 1)               AS rev_act_asof
        FROM earnings_event ee
        WHERE ee.event_date < :cutoff
          AND ee.source='fmp'
        ORDER BY ee.event_date
    """), {"cutoff": cutoff}).all()

    out: list[dict] = []
    for r in rows:
        d = {
            "symbol": r[0], "asset_id": r[1], "event_date": r[2],
            "event_time": r[3], "fiscal_period": r[4],
            "eps_cons": float(r[5]) if r[5] is not None else None,
            "eps_act":  float(r[6]) if r[6] is not None else None,
            "eps_act_asof": r[7],
            "rev_cons": float(r[8]) if r[8] is not None else None,
            "rev_act":  float(r[9]) if r[9] is not None else None,
            "rev_act_asof": r[10],
        }
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Price-bar loader
# ---------------------------------------------------------------------------
def load_price_frames(session: Session, symbols: set[str]) -> dict[str, list[tuple[dt.date, float]]]:
    """symbol -> sorted list of (date, close)."""
    frames: dict[str, list[tuple[dt.date, float]]] = {}
    rows = session.execute(text("""
        SELECT a.symbol, pb.ts, pb.close
        FROM price_bar pb JOIN asset a ON a.id=pb.asset_id
        WHERE pb.timeframe='1d' AND a.symbol = ANY(:syms)
        ORDER BY a.symbol, pb.ts
    """), {"syms": list(symbols)}).all()
    for sym, ts, close in rows:
        d = ts.date() if hasattr(ts, "date") else ts
        frames.setdefault(sym, []).append((d, float(close)))
    # Dedupe dates (keep last)
    for sym in list(frames.keys()):
        seen: dict[dt.date, float] = {}
        for d, c in frames[sym]:
            seen[d] = c
        frames[sym] = sorted(seen.items())
    return frames


def first_idx_after(frame: list[tuple[dt.date, float]], d: dt.date) -> int | None:
    for i, (bd, _) in enumerate(frame):
        if bd > d:
            return i
    return None


# ---------------------------------------------------------------------------
# Label + backtest
# ---------------------------------------------------------------------------
def classify(ev: dict) -> str | None:
    """Canonical Messy Beat classification.
    Returns one of: 'messy_beat', 'both_beat', 'both_miss', 'eps_miss_rev_beat',
    or None if either metric missing."""
    ec, ea, rc, ra = ev["eps_cons"], ev["eps_act"], ev["rev_cons"], ev["rev_act"]
    if None in (ec, ea, rc, ra):
        return None
    eps_beat = ea > ec
    rev_beat = ra > rc
    if eps_beat and not rev_beat:
        return "messy_beat"
    if eps_beat and rev_beat:
        return "both_beat"
    if not eps_beat and rev_beat:
        return "eps_miss_rev_beat"
    return "both_miss"


def run_trades(events: list[dict], frames: dict) -> list[dict]:
    trades: list[dict] = []
    for ev in events:
        label = classify(ev)
        if label != "messy_beat":
            continue
        sym = ev["symbol"]
        fr = frames.get(sym)
        if fr is None:
            continue
        entry_anchor = max(
            ev["event_date"], ev["eps_act_asof"], ev["rev_act_asof"],
        )
        i_entry = first_idx_after(fr, entry_anchor)
        if i_entry is None:
            continue
        entry_date, entry_close = fr[i_entry]

        per_window: dict[int, dict] = {}
        ok_for_all = True
        for N in HOLD_WINDOWS:
            i_exit = i_entry + N
            if i_exit >= len(fr):
                ok_for_all = False
                break
            exit_date, exit_close = fr[i_exit]
            ret = (exit_close - entry_close) / entry_close
            per_window[N] = {
                "exit_date": exit_date.isoformat(),
                "exit_close": exit_close, "return_raw": ret,
            }
        if not ok_for_all:
            # Drop events without enough forward bars for longest window
            continue

        # Surprise magnitude proxies
        eps_surprise_pct = (ev["eps_act"] - ev["eps_cons"]) / max(abs(ev["eps_cons"]), 1e-9)
        rev_surprise_pct = (ev["rev_act"] - ev["rev_cons"]) / max(abs(ev["rev_cons"]), 1e-9)

        trades.append({
            "symbol": sym,
            "event_date": ev["event_date"].isoformat(),
            "fiscal_period": ev["fiscal_period"],
            "entry_anchor": entry_anchor.isoformat(),
            "entry_date": entry_date.isoformat(),
            "entry_close": entry_close,
            "eps_cons": ev["eps_cons"], "eps_act": ev["eps_act"],
            "rev_cons": ev["rev_cons"], "rev_act": ev["rev_act"],
            "eps_surprise_pct": eps_surprise_pct,
            "rev_surprise_pct": rev_surprise_pct,
            "windows": per_window,
        })
    return trades


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def _bootstrap_ci(xs: list[float], *, n_boot: int = 5000, conf: float = 0.95) -> tuple[float, float]:
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(xs)
    means = []
    for _ in range(n_boot):
        samp = [xs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(samp) / n)
    means.sort()
    lo = means[int((1 - conf) / 2 * n_boot)]
    hi = means[int((1 - (1 - conf) / 2) * n_boot) - 1]
    return (lo, hi)


def summarize_window(trades: list[dict], N: int, bps: float) -> dict:
    cost = bps / 1e4
    rets_gross = [t["windows"][N]["return_raw"] for t in trades]
    rets_net = [r - cost for r in rets_gross]
    n = len(rets_net)
    if n == 0:
        return {"N": N, "n": 0}
    mean = st.mean(rets_net)
    med  = st.median(rets_net)
    sd   = st.pstdev(rets_net) if n > 1 else 0.0
    wins = sum(1 for r in rets_net if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    ci_lo, ci_hi = _bootstrap_ci(rets_net)
    # Sequential equal-weight portfolio path (compounding) for DD
    path = []
    eq = 1.0
    for r in rets_net:
        eq *= (1 + r)
        path.append(eq)
    peak = 0.0
    max_dd = 0.0
    prev_peak = path[0] if path else 1.0
    for v in path:
        prev_peak = max(prev_peak, v)
        dd = (v - prev_peak) / prev_peak
        max_dd = min(max_dd, dd)
    return {
        "N": N, "n": n, "cost_bps": bps,
        "mean_pct": mean * 100,
        "median_pct": med * 100,
        "std_pct": sd * 100,
        "hit_rate": wins / n,
        "t_stat": t,
        "ci95_mean_pct": [ci_lo * 100, ci_hi * 100],
        "mean_gross_pct": st.mean(rets_gross) * 100,
        "cumulative_ret_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_drawdown_pct": max_dd * 100,
    }


def _avg_surprise(trades: list[dict], metric: str) -> dict:
    vals = [t[metric] for t in trades]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": st.mean(vals),
        "median": st.median(vals),
        "p10": sorted(vals)[max(0, int(0.1 * len(vals)) - 1)],
        "p90": sorted(vals)[int(0.9 * len(vals)) - 1] if len(vals) > 1 else vals[0],
    }


def surprise_bucket(eps_pct: float, rev_pct: float) -> str:
    mag = abs(eps_pct) + abs(rev_pct)
    if mag < 0.02:
        return "minor"
    if mag < 0.08:
        return "moderate"
    return "large"


def bucketed(trades: list[dict], N: int, bps: float, key_fn) -> dict:
    groups: dict[str, list[float]] = defaultdict(list)
    cost = bps / 1e4
    for t in trades:
        g = key_fn(t)
        groups[g].append(t["windows"][N]["return_raw"] - cost)
    out = {}
    for g, rs in groups.items():
        n = len(rs)
        m = st.mean(rs) if rs else 0.0
        sd = st.pstdev(rs) if n > 1 else 0.0
        out[g] = {
            "n": n,
            "mean_pct": m * 100,
            "hit_rate": sum(1 for r in rs if r > 0) / n,
            "t_stat": m / (sd / math.sqrt(n)) if sd > 0 and n > 1 else 0.0,
        }
    return out


def load_sector_map() -> dict[str, str]:
    if not SECTOR_CSV.exists():
        return {}
    import csv
    with SECTOR_CSV.open() as f:
        return {row["ticker"]: row.get("sector", "") for row in csv.DictReader(f)}


# ---------------------------------------------------------------------------
# Concept mapping for sanity split
# ---------------------------------------------------------------------------
def load_concept_mapping() -> dict[str, dict[str, str]]:
    """symbol -> {metric: selected_concept}."""
    p = Path("artifacts/phase11_1/concept_mapping.jsonl")
    if not p.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with p.open() as f:
        for ln in f:
            if not ln.strip():
                continue
            d = json.loads(ln)
            out.setdefault(d["symbol"], {})[d["metric"]] = (
                d.get("selected_concept") or "NONE"
            )
    return out


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
def verdict(summaries_20: dict[str, dict]) -> tuple[str, list[str]]:
    """Primary verdict gate on 10D window at 20bps net.
    PASS: n>=30 AND t>2 AND mean>0 AND CI lower bound > 0.
    WEAK: n>=15 AND (t>1 OR mean>0 with positive CI bias) — suggestive but thin.
    FAIL: otherwise.
    """
    # Use 10D window @ 20bps as primary gate (conservative realistic horizon+cost)
    if "10_20bps" not in summaries_20:
        return ("FAIL", ["no 10D 20bps summary"])
    s = summaries_20["10_20bps"]
    n = s["n"]
    reasons: list[str] = []
    if n == 0:
        return ("FAIL", ["no messy-beat trades"])
    tstat = s["t_stat"]
    mean = s["mean_pct"]
    ci_lo, ci_hi = s["ci95_mean_pct"]
    if n >= 30 and tstat > 2.0 and mean > 0 and ci_lo > 0:
        reasons.append(f"n={n} t={tstat:.2f} mean={mean:.3f}% CI=[{ci_lo:.3f},{ci_hi:.3f}]")
        return ("PASS", reasons)
    if n >= 15 and (tstat > 1.0 or (mean > 0 and ci_hi > 0)):
        reasons.append(f"suggestive n={n} t={tstat:.2f} mean={mean:.3f}% CI=[{ci_lo:.3f},{ci_hi:.3f}]")
        return ("WEAK", reasons)
    return ("FAIL", [f"no edge n={n} t={tstat:.2f} mean={mean:.3f}% CI=[{ci_lo:.3f},{ci_hi:.3f}]"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-db", action="store_true", help=argparse.SUPPRESS)
    _ = p.parse_args()

    with SessionLocal() as session:
        events = load_eligible_events(session)
        logger.info("[p11.2] eligible events loaded: {}", len(events))
        syms = {e["symbol"] for e in events}
        frames = load_price_frames(session, syms)
        logger.info("[p11.2] price frames: {}/{} symbols", len(frames), len(syms))

    # Classification audit
    labels = Counter(classify(e) or "missing_metric" for e in events)
    logger.info("[p11.2] label counts: {}", dict(labels))

    trades = run_trades(events, frames)
    n_trades = len(trades)
    logger.info("[p11.2] messy-beat trades with full 20D forward: {}", n_trades)

    # Per-window / per-cost summaries
    summaries: dict[str, dict] = {}
    for N in HOLD_WINDOWS:
        for bps in COST_BPS:
            k = f"{N}_{bps}bps"
            summaries[k] = summarize_window(trades, N, bps)

    # Sanity: surprise distributions
    eps_surp_stats = _avg_surprise(trades, "eps_surprise_pct")
    rev_surp_stats = _avg_surprise(trades, "rev_surprise_pct")

    # Top winners / losers at primary 10D window (gross)
    ranked = sorted(trades, key=lambda t: t["windows"][10]["return_raw"])
    top_losers = [{
        "symbol": t["symbol"], "event_date": t["event_date"],
        "ret_pct_10d": t["windows"][10]["return_raw"] * 100,
        "eps_surp_pct": t["eps_surprise_pct"] * 100,
        "rev_surp_pct": t["rev_surprise_pct"] * 100,
    } for t in ranked[:5]]
    top_winners = [{
        "symbol": t["symbol"], "event_date": t["event_date"],
        "ret_pct_10d": t["windows"][10]["return_raw"] * 100,
        "eps_surp_pct": t["eps_surprise_pct"] * 100,
        "rev_surp_pct": t["rev_surprise_pct"] * 100,
    } for t in ranked[-5:][::-1]]

    # Sector split (at 10D, 20bps)
    sector_map = load_sector_map()
    sector_split = bucketed(
        trades, 10, 20.0,
        key_fn=lambda t: sector_map.get(t["symbol"], "Unknown"),
    )

    # Surprise-magnitude split (at 10D, 20bps)
    surprise_split = bucketed(
        trades, 10, 20.0,
        key_fn=lambda t: surprise_bucket(
            t["eps_surprise_pct"], t["rev_surprise_pct"],
        ),
    )

    # Concept-family split (rev concept source) — sanity only
    concept_mapping = load_concept_mapping()
    concept_split = bucketed(
        trades, 10, 20.0,
        key_fn=lambda t: concept_mapping.get(t["symbol"], {}).get("revenue", "UNKNOWN")
                          .split(":")[-1],
    )

    v, v_reasons = verdict({f"10_20bps": summaries["10_20bps"]})

    thin_warning = (
        n_trades < 30
    )

    report = {
        "phase": "11.2_messy_beat_first_run",
        "today": dt.date.today().isoformat(),
        "universe": {
            "eligible_events": len(events),
            "eligible_symbols": sorted(syms),
            "price_frames_covered": len(frames),
        },
        "label_counts": dict(labels),
        "n_messy_beat_trades": n_trades,
        "sample_size_note": (
            "descriptive only — below 30 trades, stats not robust"
            if thin_warning else
            "credible sample size for robust stats"
        ),
        "surprise_distribution": {
            "eps_surprise_pct": eps_surp_stats,
            "rev_surprise_pct": rev_surp_stats,
        },
        "per_window_summaries": summaries,
        "top_winners_10d": top_winners,
        "top_losers_10d": top_losers,
        "sector_split_10d_20bps": sector_split,
        "surprise_magnitude_split_10d_20bps": surprise_split,
        "concept_family_split_10d_20bps": concept_split,
        "verdict": v,
        "verdict_reasons": v_reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (OUT_DIR / "trades.jsonl").write_text(
        "\n".join(json.dumps(t, default=str) for t in trades)
    )

    # Human-readable summary
    print("=" * 78)
    print(f"PHASE 11.2 — MESSY BEAT FIRST HONEST BACKTEST ({dt.date.today()})")
    print("=" * 78)
    print(f"Eligible events (Phase 11.1 validated): {len(events)}")
    print(f"Event-label split: {dict(labels)}")
    print(f"Messy-beat trades (full 20D forward avail): {n_trades}")
    print(f"Sample-size note: {'THIN — descriptive only' if thin_warning else 'CREDIBLE'}")
    print()
    if n_trades:
        print("--- Surprise distribution (messy-beat trades only) ---")
        print(f"  EPS surprise %:  mean={eps_surp_stats['mean']*100:+.2f}%  "
              f"median={eps_surp_stats['median']*100:+.2f}%  "
              f"p10={eps_surp_stats['p10']*100:+.2f}%  p90={eps_surp_stats['p90']*100:+.2f}%")
        print(f"  REV surprise %:  mean={rev_surp_stats['mean']*100:+.2f}%  "
              f"median={rev_surp_stats['median']*100:+.2f}%  "
              f"p10={rev_surp_stats['p10']*100:+.2f}%  p90={rev_surp_stats['p90']*100:+.2f}%")
        print()
        print(f"--- Per-window returns (gross | 10bps net | 20bps net) ---")
        print(f"{'N':>3}  {'n':>3}  {'gross%':>8}  {'net10%':>8}  {'net20%':>8}  "
              f"{'hit':>5}  {'t':>6}  {'CI95% (20bps)':<26}  {'maxDD%':>7}")
        for N in HOLD_WINDOWS:
            s10 = summaries[f"{N}_10bps"]
            s20 = summaries[f"{N}_20bps"]
            if s20["n"] == 0:
                continue
            print(f"{N:>3}  {s20['n']:>3}  {s20['mean_gross_pct']:>+8.3f}  "
                  f"{s10['mean_pct']:>+8.3f}  {s20['mean_pct']:>+8.3f}  "
                  f"{s20['hit_rate']:>5.3f}  {s20['t_stat']:>+6.2f}  "
                  f"[{s20['ci95_mean_pct'][0]:+.3f},{s20['ci95_mean_pct'][1]:+.3f}]  "
                  f"{s20['max_drawdown_pct']:>+7.2f}")
        print()
        print("--- Top winners at 10D (gross) ---")
        for t in top_winners:
            print(f"  {t['symbol']:6}  {t['event_date']}  "
                  f"ret10d={t['ret_pct_10d']:+.2f}%  "
                  f"eps_surp={t['eps_surp_pct']:+.2f}%  rev_surp={t['rev_surp_pct']:+.2f}%")
        print("--- Top losers at 10D (gross) ---")
        for t in top_losers:
            print(f"  {t['symbol']:6}  {t['event_date']}  "
                  f"ret10d={t['ret_pct_10d']:+.2f}%  "
                  f"eps_surp={t['eps_surp_pct']:+.2f}%  rev_surp={t['rev_surp_pct']:+.2f}%")
        print()
        print("--- Sector split (10D, 20bps) ---")
        for sec, s in sorted(sector_split.items(), key=lambda x: -x[1]["n"]):
            print(f"  {sec:<30}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
                  f"hit={s['hit_rate']:.3f}  t={s['t_stat']:+.2f}")
        print()
        print("--- Surprise-magnitude split (10D, 20bps) ---")
        for mag, s in sorted(surprise_split.items()):
            print(f"  {mag:<10}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
                  f"hit={s['hit_rate']:.3f}  t={s['t_stat']:+.2f}")
        print()
        print("--- Revenue-concept-family split (sanity only, 10D, 20bps) ---")
        for cf, s in sorted(concept_split.items(), key=lambda x: -x[1]["n"]):
            print(f"  {cf:<45}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
                  f"t={s['t_stat']:+.2f}")
    print()
    print("-" * 78)
    print(f"VERDICT: {v}")
    for r in v_reasons:
        print(f"  reason: {r}")
    print("=" * 78)
    print(f"Report: {OUT_DIR / 'report.json'}")
    print(f"Trades: {OUT_DIR / 'trades.jsonl'}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
