"""Phase Opt-B3a — filter calibration audit (read-only, no DB writes).

Pulls Tradier sandbox chains for the 5-ETF universe, computes distributions
across spread/age/OI dimensions, simulates alternative threshold profiles.
NEVER writes to DB. NEVER persists. NEVER triggers any worker job.
"""
from __future__ import annotations

import datetime as dt
import statistics
import time
from collections import Counter, defaultdict
from decimal import Decimal

from apps.api.src.options.data.liquidity_filter import (
    MAX_BID_ASK_SPREAD_DOLLARS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_OPEN_INTEREST,
    evaluate_quote,
)
from apps.api.src.options.data_provider.tradier_adapter import (
    TradierOptionsAdapter,
)


UNIVERSE = ["SPY", "QQQ", "IWM", "GLD", "TLT"]


def main() -> None:
    print(f"--- Pulling {UNIVERSE} from Tradier sandbox (read-only) ---")
    print(f"current locked v1 thresholds:")
    print(f"  MIN_OPEN_INTEREST          = {MIN_OPEN_INTEREST}")
    print(f"  MAX_BID_ASK_SPREAD_DOLLARS = ${MAX_BID_ASK_SPREAD_DOLLARS}")
    print(f"  MAX_QUOTE_AGE_SECONDS      = {MAX_QUOTE_AGE_SECONDS}")

    t0 = time.perf_counter()
    all_quotes = []
    adapter = TradierOptionsAdapter()
    ts = dt.datetime.now(dt.timezone.utc)
    for sym in UNIVERSE:
        r = adapter.get_chain_snapshot(symbol=sym, timestamp=ts)
        print(f"  {sym}: {len(r.quotes)} quotes (partial={r.partial})")
        for q in r.quotes:
            all_quotes.append((sym, q))
    adapter.close()
    elapsed = time.perf_counter() - t0
    print(f"pull elapsed: {elapsed:.1f} s, total quotes: {len(all_quotes)}")

    # ============================================================
    # Helpers
    # ============================================================
    def pct_spread(b, a):
        if b is None or a is None or b <= 0 or a <= b:
            return None
        mid = (float(b) + float(a)) / 2
        return (float(a - b)) / mid * 100.0 if mid > 0 else None

    def hist(values, bins, label):
        print(f"\n--- {label} (n={len(values)}) ---")
        if not values:
            print("  (empty)")
            return
        s = sorted(values)
        n = len(s)
        print(
            f"  min={s[0]:.4f}  p25={s[n//4]:.4f}  median={statistics.median(s):.4f}  "
            f"p75={s[3*n//4]:.4f}  p90={s[int(0.9*n)]:.4f}  "
            f"p95={s[int(0.95*n)]:.4f}  max={s[-1]:.4f}"
        )
        for lo, hi in bins:
            cnt = sum(1 for v in values if lo <= v < hi)
            bar = "#" * min(60, int(cnt / max(1, n) * 200))
            print(f"  [{lo:>9.3f}, {hi:>9.3f}): {cnt:>6}  {bar}")

    # ============================================================
    # 1. Aggregate distributions
    # ============================================================
    spreads_d = []
    spreads_p = []
    ages = []
    ois = []
    for _sym, q in all_quotes:
        if q.bid is not None and q.ask is not None and q.ask > q.bid > 0:
            spreads_d.append(float(q.ask - q.bid))
            p = pct_spread(q.bid, q.ask)
            if p is not None:
                spreads_p.append(p)
        ages.append(q.quote_age_seconds)
        ois.append(q.open_interest or 0)

    hist(
        spreads_d,
        [(0, 0.01), (0.01, 0.02), (0.02, 0.05), (0.05, 0.10),
         (0.10, 0.20), (0.20, 0.50), (0.50, 1.00), (1.00, 5.00),
         (5.00, 1e9)],
        "spread $ histogram",
    )
    hist(
        spreads_p,
        [(0, 1), (1, 2), (2, 5), (5, 10), (10, 25), (25, 50),
         (50, 100), (100, 1e9)],
        "spread % of mid histogram",
    )
    hist(
        ages,
        [(0, 300), (300, 600), (600, 900), (900, 1200), (1200, 1800),
         (1800, 3600), (3600, 1e9)],
        "quote_age_seconds histogram",
    )
    hist(
        ois,
        [(0, 10), (10, 50), (50, 100), (100, 500), (500, 1000),
         (1000, 5000), (5000, 10000), (10000, 1e9)],
        "open_interest histogram",
    )

    # ============================================================
    # 2. Per-symbol breakdown
    # ============================================================
    print("\n--- per-symbol breakdown ---")
    print(
        f'  {"sym":<5} {"raw":>5} {"valid_ba":>9} '
        f'{"med_sp$":>9} {"med_sp%":>9} {"med_age":>9} {"med_OI":>8}'
    )
    by_sym = defaultdict(list)
    for sym, q in all_quotes:
        by_sym[sym].append(q)
    for sym, qs in by_sym.items():
        valid = [q for q in qs if q.bid and q.ask and q.ask > q.bid > 0]
        sp_d = [float(q.ask - q.bid) for q in valid]
        sp_p = [pct_spread(q.bid, q.ask) for q in valid
                if pct_spread(q.bid, q.ask) is not None]
        ag = [q.quote_age_seconds for q in qs]
        oi = [q.open_interest or 0 for q in qs]

        def med(x): return statistics.median(x) if x else float("nan")
        print(
            f"  {sym:<5} {len(qs):>5} {len(valid):>9} "
            f"{med(sp_d):>9.4f} {med(sp_p):>9.2f} "
            f"{med(ag):>9.0f} {med(oi):>8.0f}"
        )

    # ============================================================
    # 3. ATM proxy vs OTM
    # ============================================================
    print("\n--- ATM proxy vs OTM analysis ---")
    print(
        f'  {"sym":<5} {"bucket":<14} {"n":>5} {"valid":>5} '
        f'{"med_sp$":>9} {"med_sp%":>9} {"med_OI":>8}'
    )
    for sym in UNIVERSE:
        qs = by_sym.get(sym, [])
        if not qs:
            continue
        strikes = sorted(set(float(q.strike) for q in qs))
        median_strike = strikes[len(strikes)//2]
        near = [q for q in qs
                if abs(float(q.strike)-median_strike) < median_strike*0.05]
        far = [q for q in qs
               if abs(float(q.strike)-median_strike) >= median_strike*0.10]
        for label, group in (("near_ATM(<5%)", near),
                             ("far_OTM(>10%)", far)):
            valid = [q for q in group if q.bid and q.ask and q.ask > q.bid > 0]
            sp_d = [float(q.ask-q.bid) for q in valid]
            sp_p = [pct_spread(q.bid, q.ask) for q in valid
                    if pct_spread(q.bid, q.ask) is not None]
            oi = [q.open_interest or 0 for q in group]

            def med(x): return statistics.median(x) if x else float("nan")
            print(
                f"  {sym:<5} {label:<14} {len(group):>5} {len(valid):>5} "
                f"{med(sp_d):>9.4f} {med(sp_p):>9.2f} {med(oi):>8.0f}"
            )

    # ============================================================
    # 4. Threshold simulation
    # ============================================================
    print("\n--- threshold simulation ---")
    profiles = [
        ("CURRENT (locked v1)",       500, Decimal("0.10"),   60),
        ("A_research_loose",          100, Decimal("0.50"), 1800),
        ("B_research_moderate",       250, Decimal("0.25"), 1800),
        ("C_sandbox_calibrated",      100, Decimal("1.00"), 3600),
        ("D_strict_OI_loose_spread",  500, Decimal("1.00"), 3600),
        ("E_provider_native_only",    100, Decimal("99.99"), 86400),
    ]
    print(
        f'  {"profile":<28} {"min_oi":>6} {"max_$":>7} '
        f'{"max_age":>8} {"pass":>7} {"%pass":>7}'
    )
    n_total = len(all_quotes)
    results = {}
    for name, min_oi, max_sp, max_age in profiles:
        n_pass = 0
        reasons = Counter()
        for _sym, q in all_quotes:
            r = evaluate_quote(
                q, min_open_interest=min_oi,
                max_spread_dollars=max_sp,
                max_quote_age_seconds=max_age,
            )
            if r is None:
                n_pass += 1
            else:
                reasons[r] += 1
        pct_pass = n_pass / n_total * 100 if n_total else 0
        results[name] = (n_pass, reasons)
        print(
            f"  {name:<28} {min_oi:>6} {str(max_sp):>7} {max_age:>8} "
            f"{n_pass:>7} {pct_pass:>6.1f}%"
        )

    print("\n--- top rejection reasons per profile ---")
    for name, (n_pass, reasons) in results.items():
        top = ", ".join(f"{k}={v}" for k, v in reasons.most_common(4))
        print(f"  {name:<28}  pass={n_pass:>6}  top: {top}")

    # ============================================================
    # 5. Gate isolation (which single gate dominates current rejections)
    # ============================================================
    print("\n--- gate isolation (apply ONE gate at a time) ---")
    gates = [
        ("bid_or_ask present",     lambda q: q.bid is not None and q.ask is not None),
        ("bid > 0",                lambda q: q.bid is not None and q.bid > 0),
        ("ask > bid",              lambda q: q.bid is not None and q.ask is not None and q.ask > q.bid),
        ("spread <= $0.10",        lambda q: q.bid is not None and q.ask is not None and (q.ask-q.bid) <= Decimal("0.10")),
        ("spread <= $0.25",        lambda q: q.bid is not None and q.ask is not None and (q.ask-q.bid) <= Decimal("0.25")),
        ("spread <= $1.00",        lambda q: q.bid is not None and q.ask is not None and (q.ask-q.bid) <= Decimal("1.00")),
        ("OI >= 500",              lambda q: (q.open_interest or 0) >= 500),
        ("OI >= 250",              lambda q: (q.open_interest or 0) >= 250),
        ("OI >= 100",              lambda q: (q.open_interest or 0) >= 100),
        ("age <= 60s",             lambda q: q.quote_age_seconds <= 60),
        ("age <= 1800s",           lambda q: q.quote_age_seconds <= 1800),
        ("age <= 3600s",           lambda q: q.quote_age_seconds <= 3600),
    ]
    for label, fn in gates:
        try:
            n = sum(1 for _, q in all_quotes if fn(q))
        except Exception:
            n = -1
        print(f"  {label:<22}: {n:>6} / {n_total} pass ({n/n_total*100:.1f}%)")


if __name__ == "__main__":
    main()
