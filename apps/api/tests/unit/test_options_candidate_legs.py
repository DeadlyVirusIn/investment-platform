"""Phase C Stage 2A — candidate leg materialization unit coverage.

Pure: the chain ladder is pre-seeded into the cache so no DB/session is
touched (session passed as None). Asserts the exact selected legs for the
three engine-executable structures + the incomplete/omit paths.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from apps.api.src.options.strategy_candidates.legs import (  # noqa: E402
    materialize_legs,
    _Row,
)

PAF = dt.datetime(2026, 6, 1, 14, 0, 0)
EXP = dt.date(2026, 6, 18)
# QW1-FIX.B — candidate decision date; now part of the ladder cache key.
RUN_DATE = dt.date(2026, 6, 17)


def _row(strike: float, mid: float, delta: float, sym: str = "X") -> _Row:
    return _Row(
        strike=strike, option_symbol=sym,
        bid=mid - 0.02, ask=mid + 0.02, mid=mid, delta=delta,
        priced_as_of=PAF,
    )


def _obs(**kw):
    base = dict(underlying="QQQ", expiration=EXP, strike=720.0,
                option_type="put", run_date=RUN_DATE)
    base.update(kw)
    return SimpleNamespace(**base)


def _cand(rule_id: str):
    return SimpleNamespace(rule_id=rule_id, legs=[])


def test_put_credit_spread_two_legs():
    puts = [_row(719, 6.565, -0.235), _row(720, 6.815, -0.280), _row(721, 7.065, -0.289)]
    cache = {("QQQ", str(EXP), "PUT", str(RUN_DATE)): puts}
    legs = materialize_legs(None, _obs(strike=720.0, option_type="put"),
                            _cand("SHORT_PUT_CREDIT_SPREAD"), cache)
    assert [l.role for l in legs] == ["short_put", "long_put"]
    assert [l.side for l in legs] == ["SELL", "BUY"]
    assert legs[0].strike == 720 and legs[1].strike == 719   # long = next BELOW
    assert all(l.entry_mid is not None and l.priced_as_of == PAF for l in legs)


def test_call_credit_spread_two_legs():
    calls = [_row(765, 5.165, 0.382), _row(766, 4.72, 0.363), _row(767, 4.315, 0.340)]
    cache = {("SPY", str(EXP), "CALL", str(RUN_DATE)): calls}
    legs = materialize_legs(None, _obs(underlying="SPY", strike=765.0, option_type="call"),
                            _cand("SHORT_CALL_CREDIT_SPREAD"), cache)
    assert [l.role for l in legs] == ["short_call", "long_call"]
    assert legs[0].strike == 765 and legs[1].strike == 766   # long = next ABOVE


def test_iron_condor_four_legs_anchored_call_side():
    puts = [_row(746, 4.46, -0.273), _row(747, 4.69, -0.286), _row(748, 4.94, -0.3025),
            _row(749, 5.20, -0.314), _row(750, 5.48, -0.330)]
    calls = [_row(764, 5.625, 0.398), _row(765, 5.165, 0.382),
             _row(766, 4.72, 0.363), _row(767, 4.315, 0.340)]
    cache = {("SPY", str(EXP), "PUT", str(RUN_DATE)): puts, ("SPY", str(EXP), "CALL", str(RUN_DATE)): calls}
    # anchor = accepted short CALL 765; put short chosen by ~0.30 delta → 748
    legs = materialize_legs(None, _obs(underlying="SPY", strike=765.0, option_type="call"),
                            _cand("IRON_CONDOR"), cache)
    assert [l.role for l in legs] == ["short_put", "long_put", "short_call", "long_call"]
    by = {l.role: l for l in legs}
    assert by["short_call"].strike == 765   # anchored short call (engine pick)
    assert by["long_call"].strike == 766    # 1-strike wing above
    assert by["short_put"].strike == 748    # closest to 0.30 delta
    assert by["long_put"].strike == 747     # 1-strike wing below
    # no duplicate roles
    assert len({l.role for l in legs}) == 4


def test_incomplete_when_wing_missing():
    # short put at the lowest listed strike → no protective wing below → omit
    puts = [_row(720, 6.815, -0.28), _row(721, 7.065, -0.289)]
    cache = {("QQQ", str(EXP), "PUT", str(RUN_DATE)): puts}
    legs = materialize_legs(None, _obs(strike=720.0, option_type="put"),
                            _cand("SHORT_PUT_CREDIT_SPREAD"), cache)
    assert legs == []


def test_short_strike_absent_from_ladder():
    puts = [_row(700, 3.0, -0.16)]
    cache = {("QQQ", str(EXP), "PUT", str(RUN_DATE)): puts}
    legs = materialize_legs(None, _obs(strike=720.0, option_type="put"),
                            _cand("SHORT_PUT_CREDIT_SPREAD"), cache)
    assert legs == []


def test_research_structure_gets_no_legs():
    legs = materialize_legs(None, _obs(), _cand("LONG_CALL"), {})
    assert legs == []
