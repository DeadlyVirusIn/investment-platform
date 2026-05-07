"""Pre-ML trade-quality scoring — pure functions, no DB.

A deterministic 0-100 score with grade + reason bullets + a data
completeness flag. NEVER fabricates inputs; missing data
DECREASES completeness and the relevant component drops to 0
points. The output is explicitly labelled "diagnostic" by the
endpoint and frontend so the operator never mistakes it for a
production signal.

Component allocation (max 100):
  Entry quality        20   where the fill landed in the day's range
  Return quality       30   realized for closed, unrealized for open
  Hold discipline      15   held within max_hold rule
  Exit / Open status   25   closed: TP/SL/max_hold/other;
                            open : positive/negative/pending/no-data
  Data completeness    10   bonus when full data; 0 when incomplete

Grade ladder:
  A   85..100
  B   70..84
  C   55..69
  D   40..54
  F   < 40

Thesis enum (frozen, frontend-stable):
  open_positive, open_negative, stopped_out, take_profit, max_hold,
  closed_other, pending_next_bar, insufficient_data
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


Thesis = Literal[
    "open_positive", "open_negative",
    "stopped_out", "take_profit", "max_hold", "closed_other",
    "pending_next_bar", "insufficient_data",
]

Grade = Literal["A", "B", "C", "D", "F"]
Completeness = Literal["full", "partial", "low"]


# Component caps — frontend pulls these to render the
# breakdown bar. Edit these and the grade ladder together.
ENTRY_MAX = 20
RETURN_MAX = 30
HOLD_MAX = 15
EXIT_MAX = 25
COMPLETENESS_MAX = 10
TOTAL_MAX = ENTRY_MAX + RETURN_MAX + HOLD_MAX + EXIT_MAX + COMPLETENESS_MAX
assert TOTAL_MAX == 100

DEFAULT_MAX_HOLD_DAYS = 10  # mirrors PAPER_MAX_HOLD_DAYS env default


@dataclass
class ScoreInputs:
    """Everything the scoring functions need. Caller assembles this
    from DB rows and passes it in.

    Decimal fields are converted to float internally — this is a
    diagnostic, not an accounting calculation.
    """

    side: str                         # "buy" | "sell"
    is_closed: bool                   # paper_position.is_open is FALSE
    entry_price: float                # paper_trade.fill_price
    qty: float                        # paper_trade.quantity (signed for SELL? no — abs)
    held_days: int | None             # trading days from entry to as_of/exit
    max_hold_days: int = DEFAULT_MAX_HOLD_DAYS

    # Bar context for entry quality (paper_trade.fill_ts day's bar):
    bar_open: float | None = None
    bar_high: float | None = None
    bar_low: float | None = None
    bar_close: float | None = None

    # Mark / realized:
    current_price: float | None = None  # latest price_bar close (open trades)
    realized_pnl: float | None = None   # paper_trade.realized_pnl (sell rows)

    # Closure context:
    exit_reason: str | None = None      # paper_trade.reason on the sell

    # Pending-fill marker (no fill bar yet on the BUY side):
    pending_next_bar: bool = False

    # MFE / MAE — optional. None when not derivable.
    mfe_pct: float | None = None
    mae_pct: float | None = None


@dataclass
class ScoreResult:
    score: int
    grade: Grade
    thesis: Thesis
    completeness: Completeness
    components: dict[str, int] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Component scorers — each returns (points, reason_or_none)
# ---------------------------------------------------------------------------

def _score_entry(inp: ScoreInputs) -> tuple[int, str]:
    """How the fill landed in the day's range. Lower-half good
    for BUYs, upper-half good for SELLs. Neutral when bar
    missing or zero range.

    Reason text is explicitly side-aware so the operator never has
    to mentally invert the framing for a SELL row:
        BUY  · lower quartile = favorable
        SELL · upper quartile = favorable
    """
    lo, hi = inp.bar_low, inp.bar_high
    if lo is None or hi is None or hi <= lo:
        return ENTRY_MAX // 2, (
            "Entry: bar range unavailable — neutral score "
            f"({ENTRY_MAX // 2} of {ENTRY_MAX})."
        )
    pos = (inp.entry_price - lo) / (hi - lo)
    pos = max(0.0, min(1.0, pos))
    side_upper = inp.side.upper()
    if inp.side == "buy":
        # lower position = better (bought near low)
        if pos <= 0.25:
            pts = ENTRY_MAX
            quality = "favorable"
            zone = "lower quartile"
        elif pos <= 0.5:
            pts = int(ENTRY_MAX * 0.65)
            quality = "decent"
            zone = "lower half"
        elif pos <= 0.75:
            pts = int(ENTRY_MAX * 0.35)
            quality = "weak"
            zone = "upper half"
        else:
            pts = 0
            quality = "unfavorable"
            zone = "top quartile (chased)"
    else:
        # sell: higher = better
        if pos >= 0.75:
            pts = ENTRY_MAX
            quality = "favorable"
            zone = "upper quartile"
        elif pos >= 0.5:
            pts = int(ENTRY_MAX * 0.65)
            quality = "decent"
            zone = "upper half"
        elif pos >= 0.25:
            pts = int(ENTRY_MAX * 0.35)
            quality = "weak"
            zone = "lower half"
        else:
            pts = 0
            quality = "unfavorable"
            zone = "bottom quartile (sold low)"
    return pts, (
        f"Entry: {quality} fill for {side_upper} ({zone}, "
        f"{pos * 100:.0f}% of day range) — {pts} of {ENTRY_MAX}."
    )


def _score_return(inp: ScoreInputs) -> tuple[int, str]:
    """Realized for closed; unrealized vs entry for open."""
    if inp.is_closed and inp.realized_pnl is not None:
        # Map dollar PnL onto pct via cost basis = entry_price * qty.
        cost = inp.entry_price * abs(inp.qty)
        if cost <= 0:
            return RETURN_MAX // 2, (
                "Return: cost basis unavailable — neutral "
                f"({RETURN_MAX // 2})."
            )
        pct = inp.realized_pnl / cost
        return _return_pts(pct, label="Realized")
    if not inp.is_closed and inp.current_price is not None:
        if inp.entry_price <= 0:
            return 0, "Return: entry_price <= 0 — 0 pts."
        pct = (inp.current_price - inp.entry_price) / inp.entry_price
        return _return_pts(pct, label="Unrealized")
    return 0, "Return: insufficient data — 0 pts."


def _return_pts(pct: float, *, label: str) -> tuple[int, str]:
    """Linear: -10% → 0 pts, 0% → 15 pts, +10% → 30 pts. Clamped."""
    pts = int(round((pct / 0.10) * (RETURN_MAX / 2) + (RETURN_MAX / 2)))
    pts = max(0, min(RETURN_MAX, pts))
    return pts, (
        f"{label} return: {pct * 100:+.2f}% → {pts} of {RETURN_MAX}."
    )


def _score_hold(inp: ScoreInputs) -> tuple[int, str]:
    """Held within max_hold rule — applies to both open and
    closed. Open positions overstaying max_hold lose points."""
    if inp.held_days is None:
        return HOLD_MAX // 2, (
            "Hold: held-days unavailable — neutral "
            f"({HOLD_MAX // 2})."
        )
    over = inp.held_days - inp.max_hold_days
    if over <= 0:
        return HOLD_MAX, (
            f"Hold: {inp.held_days}d of "
            f"{inp.max_hold_days}d budget — {HOLD_MAX} of {HOLD_MAX}."
        )
    if over <= 5:
        pts = int(HOLD_MAX * 0.6)
        return pts, (
            f"Hold: {inp.held_days}d (~{over}d over budget) — "
            f"{pts} of {HOLD_MAX}."
        )
    pts = int(HOLD_MAX * 0.25)
    return pts, (
        f"Hold: {inp.held_days}d ({over}d over budget) — overheld; "
        f"{pts} of {HOLD_MAX}."
    )


def _score_exit_or_status(inp: ScoreInputs) -> tuple[int, str, Thesis]:
    """Closed → exit-reason quality. Open → position status."""
    if inp.pending_next_bar:
        return EXIT_MAX // 4, (
            f"Status: awaiting next-bar fill — {EXIT_MAX // 4} of {EXIT_MAX}."
        ), "pending_next_bar"
    if inp.is_closed:
        reason = (inp.exit_reason or "").lower()
        if "take_profit" in reason:
            return EXIT_MAX, (
                f"Exit: take-profit — {EXIT_MAX} of {EXIT_MAX}."
            ), "take_profit"
        if "stop_loss" in reason:
            # A clean stop is acceptable risk management — not
            # a perfect outcome but not a worst-case either.
            pts = int(EXIT_MAX * 0.7)
            return pts, (
                f"Exit: stop-loss — {pts} of {EXIT_MAX}."
            ), "stopped_out"
        if "max_hold" in reason:
            pts = int(EXIT_MAX * 0.5)
            return pts, (
                f"Exit: max-hold expiration — {pts} of {EXIT_MAX}."
            ), "max_hold"
        pts = int(EXIT_MAX * 0.4)
        return pts, (
            f"Exit: other ({inp.exit_reason or 'unrecorded'}) — "
            f"{pts} of {EXIT_MAX}."
        ), "closed_other"
    # Open
    if inp.current_price is None:
        return EXIT_MAX // 5, (
            f"Status: no current price — {EXIT_MAX // 5} of {EXIT_MAX}."
        ), "insufficient_data"
    if inp.current_price > inp.entry_price:
        return int(EXIT_MAX * 0.85), (
            f"Status: open with positive mark — "
            f"{int(EXIT_MAX * 0.85)} of {EXIT_MAX}."
        ), "open_positive"
    return int(EXIT_MAX * 0.45), (
        f"Status: open with negative mark — "
        f"{int(EXIT_MAX * 0.45)} of {EXIT_MAX}."
    ), "open_negative"


def _score_completeness(inp: ScoreInputs) -> tuple[int, str, Completeness]:
    """Bonus for complete data; flag the rest. Each missing
    field deducts 2 points."""
    missing: list[str] = []
    if inp.bar_high is None or inp.bar_low is None:
        missing.append("entry-bar OHLC")
    if inp.is_closed and inp.realized_pnl is None:
        missing.append("realized_pnl")
    if not inp.is_closed and inp.current_price is None:
        missing.append("current price")
    if inp.held_days is None:
        missing.append("held_days")
    pts = max(0, COMPLETENESS_MAX - 2 * len(missing))
    if pts >= COMPLETENESS_MAX:
        flag: Completeness = "full"
    elif pts >= COMPLETENESS_MAX // 2:
        flag = "partial"
    else:
        flag = "low"
    if missing:
        note = "Completeness: missing " + ", ".join(missing) + (
            f" — {pts} of {COMPLETENESS_MAX}."
        )
    else:
        note = (
            f"Completeness: full — {pts} of {COMPLETENESS_MAX}."
        )
    return pts, note, flag


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------

def _grade(score: int) -> Grade:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


def score_trade(inp: ScoreInputs) -> ScoreResult:
    entry_pts, entry_reason = _score_entry(inp)
    return_pts, return_reason = _score_return(inp)
    hold_pts, hold_reason = _score_hold(inp)
    exit_pts, exit_reason, thesis = _score_exit_or_status(inp)
    comp_pts, comp_reason, completeness = _score_completeness(inp)
    total = entry_pts + return_pts + hold_pts + exit_pts + comp_pts
    total = max(0, min(TOTAL_MAX, total))
    return ScoreResult(
        score=total,
        grade=_grade(total),
        thesis=thesis,
        completeness=completeness,
        components={
            "entry": entry_pts,
            "return": return_pts,
            "hold": hold_pts,
            "exit_or_status": exit_pts,
            "completeness": comp_pts,
        },
        reasons=[entry_reason, return_reason, hold_reason,
                 exit_reason, comp_reason],
    )


def to_float(v: Decimal | float | int | None) -> float | None:
    """Convenience: Decimal/None → float|None."""
    if v is None:
        return None
    return float(v)
