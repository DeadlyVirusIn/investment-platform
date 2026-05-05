"""Cross-signal routing — decide stock vs options expression.

Pure functions only. NO env reads, NO DB writes, NO execution side
effects. The operator script consumes these decisions; this module
never touches a runner.

Layered safety:
  * `decide_route` returns one of {prefer_stock, prefer_options,
    watchlist_only, insufficient_data}. The function alone never
    sets `execution_allowed=True` — it only sets the route_hint.
  * `apply_caps` enforces per-day and per-symbol caps; surplus
    routes are downgraded to `watchlist_only` (route remains, but
    execution_allowed=False).
  * `mark_executable` is the only function that ever flips
    `execution_allowed` to True, and only when the gate predicate
    (env-flag check supplied by the caller) returns True.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingThresholds:
    edge_prefer_pct: float = 0.005
    confidence_required: tuple[str, ...] = ("medium", "high")


@dataclass(frozen=True)
class RoutingCaps:
    max_routed_per_day: int = 5
    max_options_per_day: int = 2
    max_stock_per_day: int = 3
    max_per_underlying: int = 1
    max_total_options_exposure_pct: float = 0.05
    max_per_underlying_exposure_pct: float = 0.02


VALID_ROUTE_HINTS = (
    "prefer_stock", "prefer_options",
    "watchlist_only", "insufficient_data",
)


# ---------------------------------------------------------------------------
# Pure routing
# ---------------------------------------------------------------------------

def decide_route(
    *, confidence: str | None,
    relative_edge_pct: float | None,
    stock_status: str | None,
    best_options_strategy: str | None,
    options_liquidity_ok: bool = True,
    options_chain_available: bool = True,
    thresholds: RoutingThresholds = RoutingThresholds(),
) -> tuple[str, str]:
    """Decide route hint + reason from cross-signal evidence.

    Returns (route_hint, reason)."""
    if confidence is None or confidence == "low":
        return (
            "insufficient_data",
            "Cross-signal evidence below medium-confidence floor.",
        )
    if confidence not in thresholds.confidence_required:
        return (
            "insufficient_data",
            f"Confidence={confidence!r} not in "
            f"{thresholds.confidence_required}.",
        )
    if relative_edge_pct is None:
        return (
            "insufficient_data",
            "No relative edge computed (forward returns missing).",
        )
    if stock_status not in ("trade_ready", "watchlist_candidate"):
        return (
            "watchlist_only",
            f"Stock status={stock_status!r} — not actionable.",
        )

    edge = float(relative_edge_pct)
    if edge >= thresholds.edge_prefer_pct:
        if not best_options_strategy:
            return (
                "watchlist_only",
                "Edge favors options but no matching strategy "
                "in this bucket.",
            )
        if not options_chain_available:
            return (
                "watchlist_only",
                "Edge favors options but chain snapshot is "
                "missing — never bypass next-bar guard.",
            )
        if not options_liquidity_ok:
            return (
                "watchlist_only",
                "Edge favors options but liquidity gate would "
                "block this strategy.",
            )
        return (
            "prefer_options",
            f"Options outperformed stock by "
            f"{edge:+.4f} over 5D with {confidence} confidence.",
        )
    if edge <= -thresholds.edge_prefer_pct:
        if stock_status != "trade_ready":
            return (
                "watchlist_only",
                f"Edge favors stock but stock is "
                f"{stock_status!r} — watchlist only.",
            )
        return (
            "prefer_stock",
            f"Stock outperformed options by {-edge:+.4f} "
            f"over 5D with {confidence} confidence.",
        )
    return (
        "watchlist_only",
        f"Edge {edge:+.4f} below action threshold "
        f"({thresholds.edge_prefer_pct:+.4f}).",
    )


# ---------------------------------------------------------------------------
# Caps
# ---------------------------------------------------------------------------

@dataclass
class RouteCandidate:
    underlying: str
    stock_score: float | None
    stock_status: str
    best_options_strategy: str | None
    cross_signal_confidence: str | None
    relative_edge_pct: float | None
    stock_avg_return_pct: float | None
    options_avg_return_pct: float | None
    sample_count: int
    iv_bucket: str
    trend_bucket: str
    route_hint: str = "insufficient_data"
    reason: str = ""
    execution_allowed: bool = False
    blocked_reason: str | None = None


def apply_caps(
    candidates: list[RouteCandidate],
    caps: RoutingCaps = RoutingCaps(),
) -> list[RouteCandidate]:
    """Enforce per-day and per-symbol caps; downgrade surplus to
    watchlist_only with `blocked_reason`. Stable order; first-come
    first-served by input order. Pure — does not flip
    execution_allowed (that's `mark_executable`'s job)."""
    seen_symbols: set[str] = set()
    stock_count = 0
    options_count = 0
    total_count = 0
    out: list[RouteCandidate] = []
    for c in candidates:
        new_hint = c.route_hint
        block_reason = None
        if c.route_hint in ("prefer_stock", "prefer_options"):
            if total_count >= caps.max_routed_per_day:
                new_hint = "watchlist_only"
                block_reason = (
                    f"max_routed_per_day={caps.max_routed_per_day}"
                )
            elif c.underlying in seen_symbols:
                new_hint = "watchlist_only"
                block_reason = (
                    f"per_underlying_cap={caps.max_per_underlying} "
                    f"reached for {c.underlying}"
                )
            elif (
                c.route_hint == "prefer_stock"
                and stock_count >= caps.max_stock_per_day
            ):
                new_hint = "watchlist_only"
                block_reason = (
                    f"max_stock_per_day={caps.max_stock_per_day}"
                )
            elif (
                c.route_hint == "prefer_options"
                and options_count >= caps.max_options_per_day
            ):
                new_hint = "watchlist_only"
                block_reason = (
                    f"max_options_per_day={caps.max_options_per_day}"
                )
            else:
                if c.route_hint == "prefer_stock":
                    stock_count += 1
                else:
                    options_count += 1
                total_count += 1
                seen_symbols.add(c.underlying)
        new_c = RouteCandidate(
            underlying=c.underlying,
            stock_score=c.stock_score, stock_status=c.stock_status,
            best_options_strategy=c.best_options_strategy,
            cross_signal_confidence=c.cross_signal_confidence,
            relative_edge_pct=c.relative_edge_pct,
            stock_avg_return_pct=c.stock_avg_return_pct,
            options_avg_return_pct=c.options_avg_return_pct,
            sample_count=c.sample_count,
            iv_bucket=c.iv_bucket, trend_bucket=c.trend_bucket,
            route_hint=new_hint, reason=c.reason,
            execution_allowed=False,
            blocked_reason=block_reason,
        )
        out.append(new_c)
    return out


def mark_executable(
    candidates: list[RouteCandidate],
    *, gate_open: bool,
) -> list[RouteCandidate]:
    """Flip `execution_allowed` to True only when (a) the gate
    predicate is True AND (b) route_hint is prefer_stock/options.
    Otherwise stays False. Returns a new list."""
    out: list[RouteCandidate] = []
    for c in candidates:
        allow = bool(
            gate_open
            and c.route_hint in ("prefer_stock", "prefer_options")
        )
        out.append(RouteCandidate(
            underlying=c.underlying,
            stock_score=c.stock_score, stock_status=c.stock_status,
            best_options_strategy=c.best_options_strategy,
            cross_signal_confidence=c.cross_signal_confidence,
            relative_edge_pct=c.relative_edge_pct,
            stock_avg_return_pct=c.stock_avg_return_pct,
            options_avg_return_pct=c.options_avg_return_pct,
            sample_count=c.sample_count,
            iv_bucket=c.iv_bucket, trend_bucket=c.trend_bucket,
            route_hint=c.route_hint, reason=c.reason,
            execution_allowed=allow,
            blocked_reason=c.blocked_reason,
        ))
    return out


def candidate_to_dict(c: RouteCandidate) -> dict[str, Any]:
    return {
        "underlying": c.underlying,
        "stock_score": c.stock_score,
        "stock_status": c.stock_status,
        "best_options_strategy": c.best_options_strategy,
        "cross_signal_confidence": c.cross_signal_confidence,
        "relative_edge_pct": c.relative_edge_pct,
        "stock_avg_return_pct": c.stock_avg_return_pct,
        "options_avg_return_pct": c.options_avg_return_pct,
        "sample_count": c.sample_count,
        "iv_bucket": c.iv_bucket,
        "trend_bucket": c.trend_bucket,
        "route_hint": c.route_hint,
        "reason": c.reason,
        "execution_allowed": c.execution_allowed,
        "blocked_reason": c.blocked_reason,
    }


# ---------------------------------------------------------------------------
# Build pipeline (depends on cross-signal today-assistant output)
# ---------------------------------------------------------------------------

def build_route_candidates(
    today_items: Iterable[dict[str, Any]],
    *,
    options_chain_available_for: Callable[[str], bool] | None = None,
    options_liquidity_ok_for: Callable[[str], bool] | None = None,
    thresholds: RoutingThresholds = RoutingThresholds(),
    caps: RoutingCaps = RoutingCaps(),
    gate_open: bool = False,
) -> list[RouteCandidate]:
    """Compose: today-items -> decide_route -> apply_caps ->
    mark_executable. Caller injects the chain/liquidity oracles so
    this layer never touches the DB itself."""
    cands: list[RouteCandidate] = []
    for it in today_items:
        u = it["underlying"]
        evidence = it.get("historical_edge", {}) or {}
        confidence = evidence.get("confidence")
        edge = evidence.get("relative_edge_pct")
        sample_count = evidence.get("sample_count", 0)
        chain_ok = (
            options_chain_available_for(u)
            if options_chain_available_for else True
        )
        liq_ok = (
            options_liquidity_ok_for(u)
            if options_liquidity_ok_for else True
        )
        hint, reason = decide_route(
            confidence=confidence,
            relative_edge_pct=edge,
            stock_status=it.get("stock_status"),
            best_options_strategy=it.get("best_options_strategy"),
            options_liquidity_ok=liq_ok,
            options_chain_available=chain_ok,
            thresholds=thresholds,
        )
        cands.append(RouteCandidate(
            underlying=u,
            stock_score=it.get("stock_score"),
            stock_status=it.get("stock_status", "watchlist_candidate"),
            best_options_strategy=it.get("best_options_strategy"),
            cross_signal_confidence=confidence,
            relative_edge_pct=edge,
            stock_avg_return_pct=evidence.get("stock_avg_return_pct"),
            options_avg_return_pct=evidence.get(
                "options_avg_return_pct",
            ),
            sample_count=sample_count,
            iv_bucket=it.get("iv_bucket", "unknown_iv"),
            trend_bucket=it.get("trend_bucket", "sideways"),
            route_hint=hint,
            reason=reason,
        ))
    capped = apply_caps(cands, caps=caps)
    finalized = mark_executable(capped, gate_open=gate_open)
    return finalized
