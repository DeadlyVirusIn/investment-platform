"""Unit tests for price normalization + validation + reconciliation."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.prices.canonical import (
    CanonicalBar,
    RawProviderBar,
    source_priority,
)
from apps.api.src.domain.prices.normalize import (
    normalize_batch,
    parse_date,
    to_canonical,
)
from apps.api.src.domain.prices.reconcile import (
    ExistingBar,
    dedupe_payload,
    should_upsert,
)
from apps.api.src.domain.prices.validate import validate_bar, validate_batch


FETCHED_AT = dt.datetime(2026, 4, 19, tzinfo=dt.timezone.utc)


def _bar(
    date: str = "2026-01-01",
    o: str = "100", h: str = "102", low: str = "99", c: str = "101",
    adj: str | None = "101", vol: int | None = 1000,
    source: str = "tiingo",
) -> CanonicalBar:
    return CanonicalBar(
        symbol="X",
        trade_date=dt.date.fromisoformat(date),
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
        adjusted_close=Decimal(adj) if adj else None,
        volume=vol, source=source, fetched_at=FETCHED_AT,
    )


# --------------------------------------------------------------------------
# parse_date
# --------------------------------------------------------------------------


def test_parse_date_ymd() -> None:
    assert parse_date("2026-01-01") == dt.date(2026, 1, 1)


def test_parse_date_full_iso() -> None:
    assert parse_date("2026-01-01T00:00:00.000Z") == dt.date(2026, 1, 1)


def test_parse_date_bad() -> None:
    assert parse_date("garbage") is None
    assert parse_date("") is None


# --------------------------------------------------------------------------
# to_canonical
# --------------------------------------------------------------------------


def test_to_canonical_complete() -> None:
    raw = RawProviderBar(
        symbol="aapl", date_iso="2026-01-01",
        open=Decimal("100"), high=Decimal("102"),
        low=Decimal("99"), close=Decimal("101"),
        adjusted_close=Decimal("101"), volume=1000,
    )
    c = to_canonical(raw, source="tiingo", fetched_at=FETCHED_AT)
    assert c is not None
    assert c.symbol == "AAPL"
    assert c.trade_date == dt.date(2026, 1, 1)
    assert c.source == "tiingo"


def test_to_canonical_drops_missing_ohlc() -> None:
    raw = RawProviderBar(
        symbol="X", date_iso="2026-01-01",
        open=None, high=Decimal("1"), low=Decimal("1"), close=Decimal("1"),
        adjusted_close=None, volume=None,
    )
    assert to_canonical(raw, source="yahoo") is None


def test_normalize_batch_counts_dropped() -> None:
    raws = [
        RawProviderBar("X", "2026-01-01", Decimal("1"), Decimal("2"), Decimal("1"), Decimal("2"), None, None),
        RawProviderBar("X", "bad", None, None, None, None, None, None),
    ]
    out, dropped = normalize_batch(raws, source="tiingo")
    assert len(out) == 1
    assert dropped == 1


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def test_validate_ok() -> None:
    r = validate_bar(_bar())
    assert r.ok
    assert r.warnings == []


def test_validate_rejects_high_lt_low() -> None:
    r = validate_bar(_bar(h="50", low="100"))
    assert not r.ok
    assert "high < low" in (r.reject_reason or "")


def test_validate_rejects_open_zero() -> None:
    r = validate_bar(_bar(o="0"))
    assert not r.ok


def test_validate_rejects_close_negative() -> None:
    r = validate_bar(_bar(c="-1"))
    assert not r.ok


def test_validate_rejects_high_below_open_or_close() -> None:
    r = validate_bar(_bar(o="105", h="102", low="99", c="101"))
    assert not r.ok
    assert "high" in (r.reject_reason or "").lower()


def test_validate_rejects_low_above_open_or_close() -> None:
    r = validate_bar(_bar(o="100", h="110", low="105", c="108"))
    assert not r.ok


def test_validate_warns_missing_volume() -> None:
    r = validate_bar(_bar(vol=None))
    assert r.ok
    assert any("volume" in w for w in r.warnings)


def test_validate_warns_missing_adj_close() -> None:
    r = validate_bar(_bar(adj=None))
    assert r.ok
    assert any("adjusted_close" in w for w in r.warnings)


def test_validate_warns_large_move() -> None:
    r = validate_bar(
        _bar(o="100", h="200", low="99", c="200"),
        prior_close=Decimal("100"),
    )
    assert r.ok
    assert any("large_move" in w for w in r.warnings)


def test_validate_batch_partitions() -> None:
    ok = _bar(date="2026-01-01")
    bad = _bar(date="2026-01-02", h="1", low="100")
    accepted, rejected = validate_batch([bad, ok])
    assert [b.trade_date for b in accepted] == [dt.date(2026, 1, 1)]
    assert [r[0].trade_date for r in rejected] == [dt.date(2026, 1, 2)]


# --------------------------------------------------------------------------
# dedupe_payload
# --------------------------------------------------------------------------


def test_dedupe_keeps_more_complete_row() -> None:
    a = _bar(date="2026-01-01", adj=None, vol=None, source="tiingo")
    b = _bar(date="2026-01-01", adj="101", vol=1000, source="yahoo")
    out = dedupe_payload([a, b])
    assert len(out) == 1
    # Yahoo is more complete here despite lower priority
    assert out[0].source == "yahoo"


def test_dedupe_tiebreaks_to_higher_priority() -> None:
    a = _bar(date="2026-01-01", source="yahoo")
    b = _bar(date="2026-01-01", source="tiingo")
    out = dedupe_payload([a, b])
    assert out[0].source == "tiingo"


def test_dedupe_preserves_unique_dates() -> None:
    bars = [_bar(date="2026-01-01"), _bar(date="2026-01-02"), _bar(date="2026-01-03")]
    out = dedupe_payload(bars)
    assert len(out) == 3
    assert [b.trade_date for b in out] == sorted(b.trade_date for b in out)


# --------------------------------------------------------------------------
# should_upsert (source priority)
# --------------------------------------------------------------------------


def _existing(source: str, adj: bool = True, vol: bool = True) -> ExistingBar:
    return ExistingBar(
        source=source,
        open=Decimal("100"),
        close=Decimal("101"),
        adjusted_close=Decimal("101") if adj else None,
        volume=1000 if vol else None,
    )


def test_upsert_no_existing_always_writes() -> None:
    assert should_upsert(_bar(source="yahoo"), None) is True


def test_upsert_same_source_overwrites() -> None:
    incoming = _bar(source="tiingo")
    existing = _existing("tiingo")
    assert should_upsert(incoming, existing) is True


def test_upsert_higher_priority_overwrites() -> None:
    incoming = _bar(source="tiingo")
    existing = _existing("yahoo")
    assert should_upsert(incoming, existing) is True


def test_upsert_lower_priority_skipped_when_existing_complete() -> None:
    incoming = _bar(source="yahoo")
    existing = _existing("tiingo", adj=True, vol=True)
    assert should_upsert(incoming, existing) is False


def test_upsert_lower_priority_allowed_when_existing_incomplete() -> None:
    incoming = _bar(source="yahoo")
    existing = _existing("tiingo", adj=False, vol=False)
    assert should_upsert(incoming, existing) is True


def test_source_priority_rank() -> None:
    assert source_priority("tiingo") > source_priority("yahoo")
    assert source_priority("yahoo") > source_priority("unknown")
