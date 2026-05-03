"""Research-only regime label backfill for context_daily.

Deterministic, price-only rules. No look-ahead. Tagged
`status='diagnostic'` and `logic_version='research_backfill_v1'` so it
NEVER pollutes the production regime registry (which is owned by the
v1.0.0 macro-gate logic in apps.api.src.data.context.production).

Rules (PIT — uses only closes ≤ as_of_date):

  rvol_20d  = annualized stdev of daily returns over 20 trailing bars
  rvol_5d   = annualized stdev of daily returns over 5 trailing bars
  dd_60d    = current drawdown vs trailing-60d peak close
  ma50      = 50-bar simple moving average of close
  ma200     = 200-bar simple moving average of close

  stress_regime = (rvol_20d >= 0.30)
                   OR (rvol_5d  >= 0.45)
                   OR (dd_60d   <= -0.10)
                   OR (close < ma200)

  directional_regime = (ma50 > ma200)
                          AND (close > ma50)
                          AND (rvol_20d < 0.25)
                          AND (NOT stress_regime)

Any date with insufficient history (< 200 bars prior) yields BOTH labels
False — matches a "no opinion / be conservative" stance.

Source features = ["close@<asof>", "rolling_rvol", "rolling_drawdown",
"ma50", "ma200"].
"""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date


LOGIC_VERSION = "research_backfill_v1"
STATUS = "diagnostic"          # NOT production — research lane only

PERIODS_PER_YEAR = 252
RVOL_20_STRESS = 0.30
RVOL_5_STRESS  = 0.45
DD_60_STRESS   = -0.10
RVOL_20_CALM   = 0.25
MA_FAST        = 50
MA_SLOW        = 200
DD_LOOKBACK    = 60


SOURCE_FEATURES = [
    "close_pit", "rvol_20d_pit", "rvol_5d_pit",
    "drawdown_60d_pit", "ma_50_pit", "ma_200_pit",
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


def _ma(closes: Sequence[float], window: int) -> float:
    if len(closes) < window:
        return float("nan")
    return sum(closes[-window:]) / window


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
    insufficient_history: bool

    def to_features(self) -> dict:
        return {
            "rvol_20d": _safe(self.rvol_20d),
            "rvol_5d": _safe(self.rvol_5d),
            "dd_60d": _safe(self.dd_60d),
            "ma50": _safe(self.ma50),
            "ma200": _safe(self.ma200),
            "close": _safe(self.close),
            "insufficient_history": self.insufficient_history,
        }


def _safe(x: float) -> float | None:
    return None if not math.isfinite(float(x)) else round(float(x), 6)


def classify_pit(
    as_of: date,
    closes_thru_today: Sequence[float],
) -> RegimeLabels:
    """Compute regime labels using ONLY the close series ending at `as_of`.

    Caller must guarantee the last element of `closes_thru_today` is the
    close at `as_of`. No future bars allowed.
    """
    closes = list(closes_thru_today)
    n = len(closes)
    if n < 2:
        return RegimeLabels(
            as_of_date=as_of, stress_regime=False, directional_regime=False,
            rvol_20d=float("nan"), rvol_5d=float("nan"),
            dd_60d=0.0, ma50=float("nan"), ma200=float("nan"),
            close=float(closes[-1]) if closes else float("nan"),
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
    insufficient = (n < MA_SLOW) or not math.isfinite(rvol_20) \
        or not math.isfinite(ma200)

    if insufficient:
        return RegimeLabels(
            as_of_date=as_of, stress_regime=False,
            directional_regime=False,
            rvol_20d=rvol_20, rvol_5d=rvol_5, dd_60d=dd,
            ma50=ma50, ma200=ma200, close=last,
            insufficient_history=True,
        )

    stress = (
        (math.isfinite(rvol_20) and rvol_20 >= RVOL_20_STRESS)
        or (math.isfinite(rvol_5) and rvol_5 >= RVOL_5_STRESS)
        or (math.isfinite(dd) and dd <= DD_60_STRESS)
        or (last < ma200)
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
        insufficient_history=False,
    )


def logic_hash() -> str:
    body = (
        f"v={LOGIC_VERSION};"
        f"rvol20>={RVOL_20_STRESS};rvol5>={RVOL_5_STRESS};"
        f"dd60<={DD_60_STRESS};rvol20_calm<{RVOL_20_CALM};"
        f"ma_fast={MA_FAST};ma_slow={MA_SLOW};dd_lb={DD_LOOKBACK}"
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
