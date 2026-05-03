"""Catalyst coverage report — per-symbol + global."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class SymbolCoverage:
    symbol: str
    months_covered: int
    news_count_total: int
    news_count_by_month: dict[str, int] = field(default_factory=dict)
    earnings_events: int = 0
    earnings_known_at_count: int = 0
    missing_months: list[str] = field(default_factory=list)
    oldest_published_at: str | None = None
    latest_published_at: str | None = None
    provider_mix: dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0
    quality_tier: str = "weak"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "months_covered": self.months_covered,
            "news_count_total": self.news_count_total,
            "news_count_by_month": self.news_count_by_month,
            "earnings_events": self.earnings_events,
            "earnings_known_at_count": self.earnings_known_at_count,
            "earnings_known_at_rate": (
                self.earnings_known_at_count / self.earnings_events
                if self.earnings_events else 0.0
            ),
            "missing_months": self.missing_months,
            "oldest_published_at": self.oldest_published_at,
            "latest_published_at": self.latest_published_at,
            "provider_mix": self.provider_mix,
            "confidence": round(self.confidence, 4),
            "quality_tier": self.quality_tier,
        }


@dataclass
class CoverageReport:
    window_start: dt.date
    window_end:   dt.date
    total_symbols: int
    total_news: int
    total_earnings: int
    pct_symbol_month_coverage: float
    pct_known_at_coverage: float
    symbols: list[SymbolCoverage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    global_quality_tier: str = "weak"

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end":   self.window_end.isoformat(),
            "total_symbols": self.total_symbols,
            "total_news": self.total_news,
            "total_earnings": self.total_earnings,
            "pct_symbol_month_coverage": round(
                self.pct_symbol_month_coverage, 4
            ),
            "pct_known_at_coverage": round(self.pct_known_at_coverage, 4),
            "global_quality_tier": self.global_quality_tier,
            "symbols": [s.to_dict() for s in self.symbols],
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
def coverage_for_symbol(
    session: Session, symbol: str, *,
    window_start: dt.date, window_end: dt.date,
) -> SymbolCoverage:
    months = _months_between(window_start, window_end)
    rows = session.execute(text("""
        SELECT n.published_at, n.provider
        FROM news_item n
        JOIN news_symbol_map m ON m.news_id = n.id
        WHERE m.symbol = :sym
          AND n.published_at >= :ws
          AND n.published_at <= :we
    """), {
        "sym": symbol.upper(),
        "ws": dt.datetime.combine(window_start, dt.time(0, 0),
                                    tzinfo=dt.timezone.utc),
        "we": dt.datetime.combine(window_end, dt.time(23, 59, 59),
                                    tzinfo=dt.timezone.utc),
    }).mappings().all()

    count_by_month: dict[str, int] = {m: 0 for m in months}
    provider_mix: dict[str, int] = {}
    oldest: dt.datetime | None = None
    latest: dt.datetime | None = None
    for r in rows:
        pub: dt.datetime = r["published_at"]
        key = pub.strftime("%Y-%m")
        if key in count_by_month:
            count_by_month[key] += 1
        prov = r.get("provider") or "unknown"
        provider_mix[prov] = provider_mix.get(prov, 0) + 1
        if oldest is None or pub < oldest:
            oldest = pub
        if latest is None or pub > latest:
            latest = pub
    months_covered = sum(1 for v in count_by_month.values() if v > 0)
    missing_months = [m for m, v in count_by_month.items() if v == 0]

    earn = session.execute(text("""
        SELECT known_at
        FROM earnings_event
        WHERE symbol = :sym
          AND event_date BETWEEN :ws AND :we
    """), {
        "sym": symbol.upper(),
        "ws":  window_start,
        "we":  window_end,
    }).mappings().all()
    earnings_events = len(earn)
    known_at_count = sum(1 for r in earn if r.get("known_at") is not None)

    # Confidence scoring: coverage 60% + known_at 20% + earnings presence 20%
    if not months:
        cov_ratio = 0.0
    else:
        cov_ratio = months_covered / len(months)
    known_ratio = (
        known_at_count / earnings_events if earnings_events else 0.0
    )
    earn_presence = 1.0 if earnings_events > 0 else 0.0
    confidence = cov_ratio * 0.6 + known_ratio * 0.2 + earn_presence * 0.2
    tier = _tier_for_confidence(confidence)

    return SymbolCoverage(
        symbol=symbol.upper(),
        months_covered=months_covered,
        news_count_total=sum(count_by_month.values()),
        news_count_by_month=count_by_month,
        earnings_events=earnings_events,
        earnings_known_at_count=known_at_count,
        missing_months=missing_months,
        oldest_published_at=oldest.isoformat() if oldest else None,
        latest_published_at=latest.isoformat() if latest else None,
        provider_mix=provider_mix,
        confidence=confidence,
        quality_tier=tier,
    )


def build_coverage_report(
    session: Session, symbols: list[str],
    *,
    window_start: dt.date, window_end: dt.date,
) -> CoverageReport:
    per_sym = [
        coverage_for_symbol(
            session, s,
            window_start=window_start, window_end=window_end,
        )
        for s in symbols
    ]
    total_news = sum(s.news_count_total for s in per_sym)
    total_earn = sum(s.earnings_events for s in per_sym)
    months = _months_between(window_start, window_end)
    total_cells = max(1, len(symbols) * len(months))
    filled_cells = sum(s.months_covered for s in per_sym)
    symbol_month_cov = filled_cells / total_cells

    known_total = sum(s.earnings_known_at_count for s in per_sym)
    known_rate = known_total / total_earn if total_earn else 0.0

    warnings: list[str] = []
    if symbol_month_cov < 0.5:
        warnings.append(
            f"symbol-month coverage {symbol_month_cov:.0%} < 50% — "
            f"not usable for replay ML training yet"
        )
    if total_earn and known_rate < 0.5:
        warnings.append(
            f"known_at populated on only {known_rate:.0%} of earnings — "
            "replay cannot trust the event-date horizon"
        )
    for s in per_sym:
        if s.earnings_events == 0:
            warnings.append(
                f"{s.symbol}: no earnings events in window"
            )

    global_tier = _tier_for_coverage(symbol_month_cov, known_rate)
    return CoverageReport(
        window_start=window_start,
        window_end=window_end,
        total_symbols=len(symbols),
        total_news=total_news,
        total_earnings=total_earn,
        pct_symbol_month_coverage=symbol_month_cov,
        pct_known_at_coverage=known_rate,
        symbols=per_sym,
        warnings=warnings,
        global_quality_tier=global_tier,
    )


# ---------------------------------------------------------------------------
def _months_between(start: dt.date, end: dt.date) -> list[str]:
    out: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _tier_for_confidence(c: float) -> str:
    if c >= 0.8: return "excellent"
    if c >= 0.5: return "usable"
    return "weak"


def _tier_for_coverage(cov: float, known_rate: float) -> str:
    if cov >= 0.8 and known_rate >= 0.5:
        return "excellent"
    if cov >= 0.5:
        return "usable"
    return "weak"
