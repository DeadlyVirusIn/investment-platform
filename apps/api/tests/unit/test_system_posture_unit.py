"""Research Safe Mode — pure transition/hysteresis invariants (Wave 1B)."""

from __future__ import annotations

import pytest

from apps.api.src.domain.publication import posture as ps


def sig(level: str, sid: str = "s") -> ps.Signal:
    return ps.Signal(sid, level, f"{sid}:{level}", {})


def prev(posture: str, *, clean: bool = False, acked: bool = False,
         reasons: list | None = None) -> dict:
    import json
    return {
        "id": "prev-1", "posture": posture,
        "signals_clean": clean,
        "acknowledged_at": "2026-07-13T00:00:00+00:00" if acked else None,
        "reasons_json": json.dumps(reasons or []),
        "input_hash": "h",
    }


# ---------------------------------------------------------------------------
# proposal
# ---------------------------------------------------------------------------

def test_any_critical_proposes_safe():
    assert ps.propose([sig("ok"), sig("critical")]) == ("SAFE", False)


def test_any_warning_proposes_restricted():
    assert ps.propose([sig("ok"), sig("warning")]) == ("RESTRICTED", False)


def test_all_ok_is_clean_normal():
    assert ps.propose([sig("ok"), sig("ok")]) == ("NORMAL", True)


# ---------------------------------------------------------------------------
# transitions — downgrades immediate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_p", ["NORMAL", "RESTRICTED", "SAFE"])
def test_downgrade_to_safe_is_immediate(from_p):
    p, _ = ps.transition(prev(from_p), "SAFE", clean=False)
    assert p == "SAFE"


def test_normal_to_restricted_immediate():
    p, _ = ps.transition(prev("NORMAL"), "RESTRICTED", clean=False)
    assert p == "RESTRICTED"


# ---------------------------------------------------------------------------
# recovery hysteresis
# ---------------------------------------------------------------------------

def test_clean_from_normal_stays_normal():
    p, _ = ps.transition(prev("NORMAL"), "NORMAL", clean=True)
    assert p == "NORMAL"


def test_first_event_clean_is_normal():
    p, _ = ps.transition(None, "NORMAL", clean=True)
    assert p == "NORMAL"


def test_restricted_dirty_then_clean_needs_one_cooldown_cycle():
    # prev RESTRICTED created with dirty signals → first clean eval stays
    # RESTRICTED (cooldown); a prev RESTRICTED that was already clean → NORMAL.
    p1, r1 = ps.transition(prev("RESTRICTED", clean=False), "NORMAL", True)
    assert p1 == "RESTRICTED"
    assert any(x["kind"] == "recovery_cooldown" for x in r1)
    p2, _ = ps.transition(prev("RESTRICTED", clean=True), "NORMAL", True)
    assert p2 == "NORMAL"


def test_safe_clean_without_ack_stays_safe():
    p, r = ps.transition(prev("SAFE", clean=True, acked=False), "NORMAL", True)
    assert p == "SAFE"
    assert any(x["kind"] == "awaiting_acknowledgment" for x in r)


def test_safe_clean_with_ack_recovers_via_restricted():
    p, r = ps.transition(prev("SAFE", clean=True, acked=True), "NORMAL", True)
    assert p == "RESTRICTED"
    assert any(x["kind"] == "recovering" for x in r)


def test_illegal_direct_safe_to_normal_is_impossible():
    # No combination of prev-SAFE inputs yields NORMAL in one step.
    for clean in (True, False):
        for acked in (True, False):
            p, _ = ps.transition(prev("SAFE", clean=clean, acked=acked),
                                 "NORMAL", True)
            assert p != "NORMAL"


def test_ack_marker_in_reasons_also_unlocks():
    p, _ = ps.transition(
        prev("SAFE", clean=True, reasons=[{"kind": "acknowledged"}]),
        "NORMAL", True)
    assert p == "RESTRICTED"


# ---------------------------------------------------------------------------
# no flapping: identical dirty cycles keep the same posture proposal
# ---------------------------------------------------------------------------

def test_repeated_identical_cycles_are_stable():
    signals = [sig("warning", "drift")]
    seq = []
    prev_event = prev("RESTRICTED", clean=False)
    for _ in range(5):
        proposed, clean = ps.propose(signals)
        p, _ = ps.transition(prev_event, proposed, clean)
        seq.append(p)
        prev_event = prev("RESTRICTED", clean=False)
    assert set(seq) == {"RESTRICTED"}
