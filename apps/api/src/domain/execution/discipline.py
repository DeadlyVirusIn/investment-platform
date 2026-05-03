"""Phase 6 — Execution Discipline layer.

Single thin layer between sized candidates and PnL accounting. Does NOT
modify signal generation, routing, sizing, or regime classification.

Three robust controls (minimum viable knob surface):

  1. HYSTERESIS      — skip rebalance if |size change| < min_position_change
  2. THRESHOLDS      — regime-aware minimum conviction to open a new position
  3. HOLDING RULES   — min_hold_days, cooldown_days, override_conviction_gap

Override bypasses min_hold and cooldown when a NEW candidate's conviction
is >= regime_floor + override_conviction_gap (strong adverse reversal or
strong replacement signal).

Pure domain logic. No DB. No I/O. No mutation of candidate objects. The
`PortfolioBook` is the single mutable state container and is owned by the
caller (one per strategy across the replay).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Regime-aware open floors. Conviction = composite × confidence, so ∈ [0, 1].
# Low-vol / sideways require stronger evidence to justify a new trade's cost;
# trend_up keeps threshold modest (router + regime already filter).
DEFAULT_MIN_OPEN_CONVICTION: dict[str, float] = {
    "low_vol":  0.35,
    "sideways": 0.45,
    "trend_up": 0.20,
    "high_vol": 0.50,
}
DEFAULT_MIN_OPEN_CONVICTION_FALLBACK: float = 0.40


@dataclass(frozen=True)
class ExecutionDisciplineConfig:
    """All execution-discipline knobs. Frozen so tests can swap freely."""

    # Hysteresis
    min_position_change: float = 0.02

    # Thresholds — regime → min conviction to OPEN a new position
    min_open_conviction: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MIN_OPEN_CONVICTION),
    )
    min_open_conviction_fallback: float = DEFAULT_MIN_OPEN_CONVICTION_FALLBACK

    # Holding rules
    min_hold_days: int = 3
    cooldown_days: int = 1
    override_conviction_gap: float = 0.25   # beyond floor; bypasses min_hold + cooldown

    # Global feature flag (disabled -> identity pass-through)
    enabled: bool = True


# ---------------------------------------------------------------------------
# State types
# ---------------------------------------------------------------------------


@dataclass
class HeldPosition:
    symbol: str
    size: float
    entry_date: dt.date
    entry_conviction: float
    per_bar_return: float      # frozen at entry — forward/n_bars attribution
    n_bars_forward: int         # horizon of the forward return (typically 20)


@dataclass(frozen=True)
class Candidate:
    """Today's proposal for one symbol: (size already computed by sizer,
    conviction = composite × confidence, per-bar return for PnL, horizon)."""
    symbol: str
    proposed_size: float
    conviction: float
    per_bar_return: float
    n_bars_forward: int


@dataclass
class PortfolioBook:
    """Mutable carrier. Owned by the evaluator, one per strategy.

    `positions` = currently-held entries (symbol → HeldPosition).
    `cooldown` = symbol → last-exit date (for cooldown_days re-entry block).
    """
    positions: dict[str, HeldPosition] = field(default_factory=dict)
    cooldown: dict[str, dt.date] = field(default_factory=dict)

    def held_days(self, symbol: str, today: dt.date) -> int:
        pos = self.positions.get(symbol)
        if pos is None:
            return 0
        return (today - pos.entry_date).days

    def in_cooldown(self, symbol: str, today: dt.date, cooldown_days: int) -> bool:
        exit_date = self.cooldown.get(symbol)
        if exit_date is None:
            return False
        return (today - exit_date).days < cooldown_days


# ---------------------------------------------------------------------------
# Core rule application
# ---------------------------------------------------------------------------


def _override_threshold(floor: float, config: ExecutionDisciplineConfig) -> float:
    return floor + config.override_conviction_gap


def apply_discipline(
    book: PortfolioBook,
    candidates: list[Candidate],
    today: dt.date,
    regime: str,
    config: ExecutionDisciplineConfig,
) -> dict[str, float]:
    """Apply execution discipline to today's candidate set.

    Returns {symbol: actual_size_today}. Mutates `book` in place
    (positions + cooldown).

    When `config.enabled` is False, the book is refreshed to reflect today's
    candidates as-is (no hysteresis, no min-hold, no cooldown, no threshold)
    — equivalent to the pre-Phase-6 behavior, but with book state populated
    so per-bar PnL attribution still flows through the disciplined PnL path.
    """
    # --- disabled: identity pass-through (book kept for PnL plumbing) ------
    if not config.enabled:
        out: dict[str, float] = {}
        book.positions = {}
        for c in candidates:
            if c.proposed_size > 0:
                out[c.symbol] = c.proposed_size
                book.positions[c.symbol] = HeldPosition(
                    symbol=c.symbol, size=c.proposed_size,
                    entry_date=today, entry_conviction=c.conviction,
                    per_bar_return=c.per_bar_return,
                    n_bars_forward=c.n_bars_forward,
                )
        return out

    # --- enabled: apply three controls --------------------------------------
    today_by_sym = {c.symbol: c for c in candidates}
    next_positions: dict[str, HeldPosition] = {}
    actual: dict[str, float] = {}

    floor = config.min_open_conviction.get(
        regime, config.min_open_conviction_fallback,
    )
    override_level = _override_threshold(floor, config)

    # 1) Incumbents — decide keep / rebalance / close
    for sym, pos in list(book.positions.items()):
        cand = today_by_sym.get(sym)
        held_n = book.held_days(sym, today)

        if cand is None:
            # No signal today — min-hold can keep position; otherwise close
            if held_n < config.min_hold_days:
                # Keep without refreshing entry; attribution stays frozen
                actual[sym] = pos.size
                next_positions[sym] = pos
                continue
            # Past min-hold and no renewing signal -> close
            book.cooldown[sym] = today
            continue

        # Candidate refreshes today; apply hysteresis
        delta = abs(cand.proposed_size - pos.size)
        if delta < config.min_position_change:
            actual[sym] = pos.size
            next_positions[sym] = pos   # unchanged, entry intact
        else:
            # Rebalance — keep entry metadata (still same holding episode)
            actual[sym] = cand.proposed_size
            next_positions[sym] = HeldPosition(
                symbol=sym,
                size=cand.proposed_size,
                entry_date=pos.entry_date,
                entry_conviction=pos.entry_conviction,
                per_bar_return=pos.per_bar_return,
                n_bars_forward=pos.n_bars_forward,
            )

    # 2) New candidates (not currently held)
    for c in candidates:
        if c.symbol in next_positions:
            continue   # already handled via incumbent branch
        if c.symbol in book.positions:
            # Symbol WAS held but was closed above due to missing candidate.
            # This cannot happen because cand is None was the branch for
            # closing — if we're here, the sym was processed. Skip defensively.
            continue
        if c.proposed_size <= 0:
            continue

        # Threshold gate
        weak_signal = c.conviction < floor
        # Cooldown gate
        in_cooldown = book.in_cooldown(c.symbol, today, config.cooldown_days)

        if weak_signal or in_cooldown:
            # Both require override strength
            if c.conviction < override_level:
                continue
            # Strong enough — proceed (override applied)

        # Open new position
        actual[c.symbol] = c.proposed_size
        next_positions[c.symbol] = HeldPosition(
            symbol=c.symbol,
            size=c.proposed_size,
            entry_date=today,
            entry_conviction=c.conviction,
            per_bar_return=c.per_bar_return,
            n_bars_forward=c.n_bars_forward,
        )

    book.positions = next_positions
    return actual


# ---------------------------------------------------------------------------
# PnL attribution from a disciplined book
# ---------------------------------------------------------------------------


def daily_return_from_book(
    book: PortfolioBook, today: dt.date, actual_sizes: dict[str, float],
) -> float:
    """Size-weighted per-bar return across held positions today.

    Positions beyond their original forward horizon contribute zero
    (no phantom returns past the 20-bar lookahead window).
    """
    total_size = sum(actual_sizes.values())
    if total_size <= 0:
        return 0.0
    weighted = 0.0
    for sym, size in actual_sizes.items():
        pos = book.positions.get(sym)
        if pos is None:
            continue
        bars_since = (today - pos.entry_date).days
        if bars_since > pos.n_bars_forward:
            continue   # outside forward horizon -> no attribution
        if size <= 0:
            continue
        weighted += size * pos.per_bar_return
    return weighted / total_size
