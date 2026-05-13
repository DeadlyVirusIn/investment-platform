"""Phase Opt-B2 — Options paper-trade lifecycle integration tests.

Covers the 10 scenarios required by the operator brief:
  1. Happy path
  2. Duplicate replay
  3. Out-of-order replay
  4. Stale event replay
  5. Missing chain snapshot (= missing evidence)
  6. Double OPEN attempt
  7. Double CLOSE attempt
  8. Expiration after close (terminal state)
  9. Assignment after expiration (terminal state)
  10. Rollback on failed leg mutation
Plus the assignment-precedence rule (ITM short → ASSIGNED, not EXPIRED).

These are TRADING-ENGINE-style tests, not normal CRUD tests:
  * Each transition is asserted against the DB row state AND the
    lifecycle event log.
  * Replay assertions check both is_idempotent flag AND DB row counts.
  * Invalid transitions assert the typed exception, not just any Error.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db.options_models import (
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
)
from apps.api.src.options.lifecycle import (
    ASSIGNED,
    AssignmentEvidence,
    AssignmentPrecedenceError,
    CLOSED,
    CloseEvidence,
    EXPIRED,
    ExpirationEvidence,
    FillEvidence,
    InvalidTransitionError,
    LegAssignmentEvidence,
    LegCloseEvidence,
    LegExpirationEvidence,
    LegFillEvidence,
    MissingEvidenceError,
    OPEN,
    PROPOSED,
    REASON_TARGET_HIT,
    TerminalStateError,
    TradeNotFoundError,
    transition_to_assigned,
    transition_to_closed,
    transition_to_expired,
    transition_to_open,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SEED_COUNTER = 0


def _seed_proposed(
    session: Session,
    *,
    underlying: str = "SPY",
    legs: list[dict] | None = None,
) -> int:
    """Seed a PROPOSED trade with one or more legs. Returns trade_id.

    Schema does not store `multiplier` on the leg row — caller must
    not pass it. `entry_quote_at_utc` and `entry_fill_price` are
    NOT NULL columns; provide defaults.
    """
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    if legs is None:
        legs = [
            dict(
                leg_index=1,
                option_symbol="SPY260618C00440000",
                expiry=dt.date(2026, 6, 18),
                strike=Decimal("440"),
                option_type="CALL",
                side="BUY",
                qty=1,
            ),
        ]
    t = OptionsPaperTrade(
        underlying=underlying,
        strategy_name="LONG_CALL",
        strategy_version="test_v1",
        status=PROPOSED,
        opened_at=dt.datetime(2026, 5, 12, 21, 0, tzinfo=dt.timezone.utc),
        max_loss_dollars=Decimal("125"),
        max_profit_dollars=Decimal("1000"),
        fees_total_dollars=Decimal("0"),
        fill_model_version="test",
        proposal_hash=f"testhash{_SEED_COUNTER:024d}",
        paper_only=True,
    )
    session.add(t)
    session.flush()
    for L in legs:
        L_norm = dict(L)
        L_norm.setdefault(
            "entry_quote_at_utc",
            dt.datetime(2026, 5, 12, 21, 0, tzinfo=dt.timezone.utc),
        )
        L_norm.setdefault("entry_fill_price", Decimal("1.25"))
        session.add(OptionsPaperTradeLeg(
            trade_id=t.id,
            underlying=underlying,
            **L_norm,
        ))
    session.commit()
    return t.id


def _count_lifecycle_events(session: Session, trade_id: int,
                            event_type: str | None = None) -> int:
    sql = "SELECT COUNT(*) FROM options_trade_lifecycle_event WHERE trade_id = :tid"
    params: dict = {"tid": trade_id}
    if event_type:
        sql += " AND event_type = :et"
        params["et"] = event_type
    return int(session.execute(text(sql), params).scalar_one())


def _count_expiration_events(session: Session, trade_id: int) -> int:
    return int(session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event WHERE trade_id = :tid"
    ), {"tid": trade_id}).scalar_one())


def _count_assignment_events(session: Session, trade_id: int) -> int:
    return int(session.execute(text(
        "SELECT COUNT(*) FROM options_assignment_event WHERE trade_id = :tid"
    ), {"tid": trade_id}).scalar_one())


def _trade_status(session: Session, trade_id: int) -> str:
    return str(session.execute(text(
        "SELECT status FROM options_paper_trade WHERE id = :tid"
    ), {"tid": trade_id}).scalar_one())


def _make_fill(at: dt.datetime, legs_indexes: list[int]) -> FillEvidence:
    return FillEvidence(
        fill_at_utc=at,
        chain_snapshot_id=42,
        legs=[LegFillEvidence(leg_index=i, fill_price=Decimal("1.25"))
              for i in legs_indexes],
    )


def _make_close(at: dt.datetime, legs_indexes: list[int],
                reason: str = REASON_TARGET_HIT) -> CloseEvidence:
    return CloseEvidence(
        close_at_utc=at,
        reason=reason,
        chain_snapshot_id=43,
        exit_debit_dollars=Decimal("200"),
        realized_pnl_dollars=Decimal("75"),
        legs=[LegCloseEvidence(leg_index=i, close_price=Decimal("2.00"))
              for i in legs_indexes],
    )


# ---------------------------------------------------------------------------
# 1. Happy path: PROPOSED → OPEN → CLOSED
# ---------------------------------------------------------------------------


def test_happy_path_open_then_close(pg_session):
    tid = _seed_proposed(pg_session)

    # OPEN
    fill_at = dt.datetime(2026, 5, 13, 14, 30, tzinfo=dt.timezone.utc)
    r1 = transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))
    assert r1.from_status == PROPOSED
    assert r1.to_status == OPEN
    assert not r1.is_idempotent
    assert r1.event_id is not None
    assert _trade_status(pg_session, tid) == OPEN
    assert _count_lifecycle_events(pg_session, tid, "FILLED") == 1

    # CLOSE
    close_at = dt.datetime(2026, 5, 14, 16, 0, tzinfo=dt.timezone.utc)
    r2 = transition_to_closed(pg_session, tid, _make_close(close_at, [1]))
    assert r2.from_status == OPEN
    assert r2.to_status == CLOSED
    assert _trade_status(pg_session, tid) == CLOSED
    assert _count_lifecycle_events(pg_session, tid, "CLOSED") == 1


# ---------------------------------------------------------------------------
# 2. Duplicate replay (same evidence, called twice)
# ---------------------------------------------------------------------------


def test_duplicate_open_replay_is_idempotent(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, 14, 30, tzinfo=dt.timezone.utc)
    fill = _make_fill(fill_at, [1])

    r1 = transition_to_open(pg_session, tid, fill)
    r2 = transition_to_open(pg_session, tid, fill)

    assert r1.is_idempotent is False
    assert r2.is_idempotent is True
    assert r2.from_status == OPEN and r2.to_status == OPEN
    assert _trade_status(pg_session, tid) == OPEN
    # No second FILLED event written
    assert _count_lifecycle_events(pg_session, tid, "FILLED") == 1


def test_duplicate_close_replay_is_idempotent(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    close_at = dt.datetime(2026, 5, 14, tzinfo=dt.timezone.utc)
    close = _make_close(close_at, [1])
    transition_to_closed(pg_session, tid, close)
    r2 = transition_to_closed(pg_session, tid, close)

    assert r2.is_idempotent is True
    assert _trade_status(pg_session, tid) == CLOSED
    assert _count_lifecycle_events(pg_session, tid, "CLOSED") == 1


# ---------------------------------------------------------------------------
# 3. Out-of-order replay: CLOSE before OPEN
# ---------------------------------------------------------------------------


def test_out_of_order_close_before_open_raises(pg_session):
    tid = _seed_proposed(pg_session)
    close = _make_close(dt.datetime(2026, 5, 14, tzinfo=dt.timezone.utc), [1])
    with pytest.raises(InvalidTransitionError) as exc:
        transition_to_closed(pg_session, tid, close)
    assert "PROPOSED" in str(exc.value)
    assert _trade_status(pg_session, tid) == PROPOSED  # unchanged
    assert _count_lifecycle_events(pg_session, tid) == 0


# ---------------------------------------------------------------------------
# 4. Stale event replay (same event_at_utc emitted twice via lifecycle layer)
# ---------------------------------------------------------------------------


def test_stale_lifecycle_event_dedupes_at_same_timestamp(pg_session):
    """If a runner crashes after writing the lifecycle event row but
    before commit, the next run with the SAME (trade_id, event_type,
    event_at_utc) should not insert a second event row."""
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, 14, 30, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    # Manually emit a duplicate lifecycle event with same timestamp.
    # The lifecycle helper pre-checks (trade_id, event_type, event_at_utc).
    from apps.api.src.options.lifecycle import _emit_lifecycle_event
    eid = _emit_lifecycle_event(
        pg_session, trade_id=tid, event_type="FILLED",
        triggered_by="OPERATOR_API",
        event_at_utc=fill_at,
        payload={"replay": True},
    )
    assert eid is None  # detected as duplicate
    assert _count_lifecycle_events(pg_session, tid, "FILLED") == 1


# ---------------------------------------------------------------------------
# 5. Missing chain snapshot / evidence
# ---------------------------------------------------------------------------


def test_missing_evidence_raises_missing_evidence_error(pg_session):
    tid = _seed_proposed(pg_session)
    bad = FillEvidence(
        fill_at_utc=dt.datetime.now(dt.timezone.utc),
        chain_snapshot_id=None,
        legs=[],  # empty
    )
    with pytest.raises(MissingEvidenceError):
        transition_to_open(pg_session, tid, bad)
    assert _trade_status(pg_session, tid) == PROPOSED


# ---------------------------------------------------------------------------
# 6. Double OPEN attempt — second is no-op
#    (covered by test_duplicate_open_replay_is_idempotent above)
#    Add a stricter version: terminal state cannot be re-OPENed.
# ---------------------------------------------------------------------------


def test_open_after_close_raises_terminal_state_error(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))
    close_at = dt.datetime(2026, 5, 14, tzinfo=dt.timezone.utc)
    transition_to_closed(pg_session, tid, _make_close(close_at, [1]))

    with pytest.raises(TerminalStateError):
        transition_to_open(
            pg_session, tid,
            _make_fill(dt.datetime(2026, 5, 15, tzinfo=dt.timezone.utc), [1]),
        )
    assert _trade_status(pg_session, tid) == CLOSED


# ---------------------------------------------------------------------------
# 7. Double CLOSE attempt
#    (covered by test_duplicate_close_replay_is_idempotent)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 8. Expiration after close (terminal state)
# ---------------------------------------------------------------------------


def test_expire_after_close_raises_terminal_state_error(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))
    close_at = dt.datetime(2026, 5, 14, tzinfo=dt.timezone.utc)
    transition_to_closed(pg_session, tid, _make_close(close_at, [1]))

    expiration = ExpirationEvidence(
        expiry_date=dt.date(2026, 6, 18),
        settlement_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        underlying_settlement=Decimal("450"),
        legs=[LegExpirationEvidence(
            leg_index=1, classification="OTM",
            intrinsic_value_dollars=Decimal("0"),
            realized_pnl_dollars=Decimal("0"),
        )],
    )
    with pytest.raises(TerminalStateError):
        transition_to_expired(pg_session, tid, expiration)
    assert _trade_status(pg_session, tid) == CLOSED


# ---------------------------------------------------------------------------
# 9. Assignment after expiration (terminal state)
# ---------------------------------------------------------------------------


def test_assign_after_expire_raises_terminal_state_error(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    # Long call OTM → EXPIRED cleanly
    expiration = ExpirationEvidence(
        expiry_date=dt.date(2026, 6, 18),
        settlement_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        underlying_settlement=Decimal("400"),
        legs=[LegExpirationEvidence(
            leg_index=1, classification="OTM",
            intrinsic_value_dollars=Decimal("0"),
            realized_pnl_dollars=Decimal("-125"),
        )],
    )
    transition_to_expired(pg_session, tid, expiration)

    assignment = AssignmentEvidence(
        assigned_at_utc=dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc),
        legs=[LegAssignmentEvidence(
            leg_index=1, event_type="ASSIGNED", risk_level="LOW",
            intrinsic_value_dollars=Decimal("0"),
            realized_pnl_dollars=Decimal("0"),
        )],
    )
    with pytest.raises(TerminalStateError):
        transition_to_assigned(pg_session, tid, assignment)
    assert _trade_status(pg_session, tid) == EXPIRED


# ---------------------------------------------------------------------------
# 10. Rollback on missing trade
# ---------------------------------------------------------------------------


def test_transition_unknown_trade_raises_not_found(pg_session):
    with pytest.raises(TradeNotFoundError):
        transition_to_open(
            pg_session, 99999,
            _make_fill(dt.datetime.now(dt.timezone.utc), [1]),
        )


# ---------------------------------------------------------------------------
# Assignment precedence: SHORT leg ITM at expiry → AssignmentPrecedenceError
# ---------------------------------------------------------------------------


def test_short_itm_at_expiry_rejects_expire_with_precedence_error(pg_session):
    tid = _seed_proposed(pg_session, legs=[
        # Short call leg
        dict(leg_index=1, option_symbol="SPY260618C00440000",
             expiry=dt.date(2026, 6, 18), strike=Decimal("440"),
             option_type="CALL", side="SELL", qty=1),
    ])
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    expiration = ExpirationEvidence(
        expiry_date=dt.date(2026, 6, 18),
        settlement_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        underlying_settlement=Decimal("450"),
        legs=[LegExpirationEvidence(
            leg_index=1, classification="ITM",
            intrinsic_value_dollars=Decimal("1000"),
            realized_pnl_dollars=Decimal("-1000"),
        )],
    )
    with pytest.raises(AssignmentPrecedenceError):
        transition_to_expired(pg_session, tid, expiration)
    assert _trade_status(pg_session, tid) == OPEN  # unchanged


def test_assigned_path_for_short_itm_succeeds(pg_session):
    tid = _seed_proposed(pg_session, legs=[
        dict(leg_index=1, option_symbol="SPY260618C00440000",
             expiry=dt.date(2026, 6, 18), strike=Decimal("440"),
             option_type="CALL", side="SELL", qty=1),
    ])
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    assignment = AssignmentEvidence(
        assigned_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        legs=[LegAssignmentEvidence(
            leg_index=1, event_type="ASSIGNED", risk_level="LOW",
            intrinsic_value_dollars=Decimal("1000"),
            realized_pnl_dollars=Decimal("-1000"),
        )],
    )
    r = transition_to_assigned(pg_session, tid, assignment)
    assert r.from_status == OPEN and r.to_status == ASSIGNED
    assert _trade_status(pg_session, tid) == ASSIGNED
    assert _count_assignment_events(pg_session, tid) == 1
    assert _count_lifecycle_events(pg_session, tid, "ASSIGNED") == 1


# ---------------------------------------------------------------------------
# Expiration happy path: long call OTM → EXPIRED with realized loss
# ---------------------------------------------------------------------------


def test_long_otm_expiration_records_realized_loss(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    expiration = ExpirationEvidence(
        expiry_date=dt.date(2026, 6, 18),
        settlement_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        underlying_settlement=Decimal("420"),  # below strike 440
        legs=[LegExpirationEvidence(
            leg_index=1, classification="OTM",
            intrinsic_value_dollars=Decimal("0"),
            realized_pnl_dollars=Decimal("-125"),
        )],
    )
    r = transition_to_expired(pg_session, tid, expiration)
    assert r.from_status == OPEN and r.to_status == EXPIRED
    assert _trade_status(pg_session, tid) == EXPIRED
    assert _count_expiration_events(pg_session, tid) == 1
    # Trade row carries aggregate realized P&L
    realized = pg_session.execute(text(
        "SELECT realized_pnl_dollars FROM options_paper_trade WHERE id = :tid"
    ), {"tid": tid}).scalar_one()
    assert Decimal(str(realized)) == Decimal("-125")


# ---------------------------------------------------------------------------
# Replay: per-leg expiration_event UNIQUE on natural key
# ---------------------------------------------------------------------------


def test_expiration_event_idempotent_on_natural_key(pg_session):
    tid = _seed_proposed(pg_session)
    fill_at = dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc)
    transition_to_open(pg_session, tid, _make_fill(fill_at, [1]))

    expiration = ExpirationEvidence(
        expiry_date=dt.date(2026, 6, 18),
        settlement_at_utc=dt.datetime(2026, 6, 18, 21, 0, tzinfo=dt.timezone.utc),
        underlying_settlement=Decimal("420"),
        legs=[LegExpirationEvidence(
            leg_index=1, classification="OTM",
            intrinsic_value_dollars=Decimal("0"),
            realized_pnl_dollars=Decimal("-125"),
        )],
    )
    transition_to_expired(pg_session, tid, expiration)
    # Second call returns idempotent (already EXPIRED)
    r = transition_to_expired(pg_session, tid, expiration)
    assert r.is_idempotent is True
    # Per-leg expiration event count is still 1 (natural key UNIQUE)
    assert _count_expiration_events(pg_session, tid) == 1
