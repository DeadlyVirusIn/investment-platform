"""Research-only regime classifier — MA200 PERSIST-3 variant.

Same volatility / drawdown triggers as research_backfill_v1, but the
MA200 stress trigger requires THREE consecutive closes below MA200.

Tagged `status='diagnostic'`, `logic_version='research_backfill_persist3_v1'`.
NEVER overlaps with v1 production rows. NEVER affects current B2.

PIT-safe: uses only closes ≤ as_of_date.

Rules (only MA200 differs from v1):

  rvol_20d  ≥ 0.30   → stress
  rvol_5d   ≥ 0.45   → stress
  dd_60d    ≤ -0.10  → stress
  close_i < MA200_i  for i in {t-2, t-1, t}  → stress  (PERSIST-3)

  directional_regime: identical to v1 (MA50 > MA200 AND close > MA50
    AND rvol_20d < 0.25 AND NOT stress_regime)
"""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


LOGIC_VERSION = "research_backfill_persist3_v1"
STATUS = "diagnostic"

PERIODS_PER_YEAR = 252
RVOL_20_STRESS = 0.30
RVOL_5_STRESS  = 0.45
DD_60_STRESS   = -0.10
RVOL_20_CALM   = 0.25
MA_FAST        = 50
MA_SLOW        = 200
DD_LOOKBACK    = 60
PERSIST_N      = 3   # NEW — closes below MA200 required


SOURCE_FEATURES = [
    "close_pit", "rvol_20d_pit", "rvol_5d_pit",
    "drawdown_60d_pit", "ma_50_pit", "ma_200_pit",
    "ma_200_persist_3_pit",
]


def _rvol(rets: Sequence[float], window: int) -> float:
    arr = [float(r) for r in rets if r is not None and math.isfinite(float(r))]
    if len(arr) < window:
        return float("nan")
    sub = arr[-window:]
    try:
        sd = statistics.stdev(sub)
    except statistics.StatisticsError:
        return float("nan")
    if not math.isfinite(sd):
        return float("nan")
    return sd * math.sqrt(PERIODS_PER_YEAR)


def _drawdown_now(closes: Sequence[float], lookback: int) -> float:
    if len(closes) < 2:
        return 0.0
    window = list(closes[-lookback:]) if len(closes) >= lookback \
        else list(closes)
    peak = max(window)
    if peak == 0 or not math.isfinite(peak):
        return 0.0
    last = float(window[-1])
    return last / peak - 1.0


def _ma(closes: Sequence[float], window: int, end_idx: int = None) -> float:
    """MA over the last `window` closes ending at index end_idx (default last).

    `closes` is the full PIT array. If end_idx is None, uses the entire
    array's last `window` elements.
    """
    if end_idx is None:
        if len(closes) < window:
            return float("nan")
        return sum(closes[-window:]) / window
    # MA at position end_idx using the `window` closes ENDING at end_idx-1
    # (matches v1 convention: MA at time t uses bars strictly before t).
    if end_idx < window:
        return float("nan")
    return sum(closes[end_idx - window:end_idx]) / window


def _persist_below_ma200(closes: Sequence[float], n: int = PERSIST_N) -> bool:
    """True if for each of the last `n` bars, close[i] < MA200[i] where
    MA200[i] is the average of the 200 closes BEFORE i."""
    if len(closes) < MA_SLOW + n:
        return False
    last = len(closes) - 1
    for k in range(n):
        i = last - k
        ma200_i = _ma(closes, MA_SLOW, end_idx=i)
        if not math.isfinite(ma200_i):
            return False
        if closes[i] >= ma200_i:
            return False
    return True


@dataclass(frozen=True)
class RegimeLabels:
    as_of_date: date
    stress_regime: bool
    directional_regime: bool
    rvol_20d: float
    rvol_5d: float
    dd_60d: float
    ma50: float
    ma200: float
    close: float
    persist_below_ma200_n: int
    insufficient_history: bool


def classify_pit(
    as_of: date,
    closes_thru_today: Sequence[float],
) -> RegimeLabels:
    """Compute persist-3 variant regime labels.

    Caller guarantees the last element of closes_thru_today is the
    close at as_of. No future bars allowed.
    """
    closes = list(closes_thru_today)
    n = len(closes)
    if n < 2:
        return RegimeLabels(
            as_of_date=as_of, stress_regime=False, directional_regime=False,
            rvol_20d=float("nan"), rvol_5d=float("nan"),
            dd_60d=0.0, ma50=float("nan"), ma200=float("nan"),
            close=float(closes[-1]) if closes else float("nan"),
            persist_below_ma200_n=0,
            insufficient_history=True,
        )
    rets = []
    for i in range(1, n):
        a, b = float(closes[i - 1]), float(closes[i])
        if a == 0 or not (math.isfinite(a) and math.isfinite(b)):
            continue
        rets.append(b / a - 1.0)
    rvol_20 = _rvol(rets, 20)
    rvol_5  = _rvol(rets, 5)
    dd      = _drawdown_now(closes, DD_LOOKBACK)
    ma50    = _ma(closes, MA_FAST)
    ma200   = _ma(closes, MA_SLOW)
    last    = float(closes[-1])

    # Count trailing closes below their respective MA200 (up to PERSIST_N)
    persist_count = 0
    for k in range(PERSIST_N):
        i = n - 1 - k
        if i < MA_SLOW:
            break
        ma_i = _ma(closes, MA_SLOW, end_idx=i)
        if not math.isfinite(ma_i):
            break
        if closes[i] < ma_i:
            persist_count += 1
        else:
            break

    insufficient = (n < MA_SLOW) or not math.isfinite(rvol_20) \
        or not math.isfinite(ma200)
    if insufficient:
        return RegimeLabels(
            as_of_date=as_of, stress_regime=False,
            directional_regime=False,
            rvol_20d=rvol_20, rvol_5d=rvol_5, dd_60d=dd,
            ma50=ma50, ma200=ma200, close=last,
            persist_below_ma200_n=persist_count,
            insufficient_history=True,
        )

    # Stress: same vol/dd triggers + persist-3 MA200 condition (NOT
    # single close).
    stress = (
        (math.isfinite(rvol_20) and rvol_20 >= RVOL_20_STRESS)
        or (math.isfinite(rvol_5) and rvol_5 >= RVOL_5_STRESS)
        or (math.isfinite(dd) and dd <= DD_60_STRESS)
        or _persist_below_ma200(closes, n=PERSIST_N)
    )
    directional = (
        (math.isfinite(ma50) and math.isfinite(ma200) and ma50 > ma200)
        and last > ma50
        and (math.isfinite(rvol_20) and rvol_20 < RVOL_20_CALM)
        and (not stress)
    )
    return RegimeLabels(
        as_of_date=as_of, stress_regime=stress,
        directional_regime=directional,
        rvol_20d=rvol_20, rvol_5d=rvol_5, dd_60d=dd,
        ma50=ma50, ma200=ma200, close=last,
        persist_below_ma200_n=persist_count,
        insufficient_history=False,
    )


def logic_hash() -> str:
    body = (
        f"v={LOGIC_VERSION};"
        f"rvol20>={RVOL_20_STRESS};rvol5>={RVOL_5_STRESS};"
        f"dd60<={DD_60_STRESS};rvol20_calm<{RVOL_20_CALM};"
        f"ma_fast={MA_FAST};ma_slow={MA_SLOW};dd_lb={DD_LOOKBACK};"
        f"persist={PERSIST_N}"
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
