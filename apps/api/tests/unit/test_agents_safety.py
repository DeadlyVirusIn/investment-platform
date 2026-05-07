"""Unit tests for agents.safety — pure functions, no DB / no I/O."""

from __future__ import annotations

import pytest

from apps.api.src.domain.agents import safety


# -----------------------------------------------------------------
# scrub_sensitive_ids
# -----------------------------------------------------------------

def test_scrub_redacts_top_level_sensitive_fields():
    payload = {
        "portfolio_id": "fdc48224-fb64-4883-973c-206a924bd7a5",
        "trade_id": "31bd1721-3da0-4b52-82d5-4559add82d03",
        "symbol": "NVDA",
    }
    out = safety.scrub_sensitive_ids(payload)
    assert out["portfolio_id"] == "[redacted]"
    assert out["trade_id"] == "[redacted]"
    assert out["symbol"] == "NVDA"  # preserved


def test_scrub_redacts_nested_sensitive_fields():
    payload = {
        "rows": [
            {"trade_id": "abc", "qty": 1},
            {"position_id": "def", "qty": 2},
        ],
    }
    out = safety.scrub_sensitive_ids(payload)
    assert out["rows"][0]["trade_id"] == "[redacted]"
    assert out["rows"][1]["position_id"] == "[redacted]"
    assert out["rows"][0]["qty"] == 1
    assert out["rows"][1]["qty"] == 2


def test_scrub_redacts_uuid_inside_string_value():
    payload = {
        "reason": (
            "trade fdc48224-fb64-4883-973c-206a924bd7a5 "
            "fired at 15:00 UTC"
        ),
    }
    out = safety.scrub_sensitive_ids(payload)
    assert "[redacted-uuid]" in out["reason"]
    # Original UUID must be gone.
    assert "fdc48224" not in out["reason"]


def test_scrub_does_not_mutate_input():
    payload = {"trade_id": "x", "rows": [{"trade_id": "y"}]}
    original_top = payload["trade_id"]
    original_nested = payload["rows"][0]["trade_id"]
    _ = safety.scrub_sensitive_ids(payload)
    assert payload["trade_id"] == original_top
    assert payload["rows"][0]["trade_id"] == original_nested


def test_scrub_passes_numbers_bools_none_through():
    payload = {"score": 72, "qualified": True, "extra": None}
    out = safety.scrub_sensitive_ids(payload)
    assert out == {"score": 72, "qualified": True, "extra": None}


# -----------------------------------------------------------------
# extract_numeric_facts
# -----------------------------------------------------------------

def test_extract_numerics_walks_nested_structures():
    payload = {
        "score": 72,
        "components": {"entry": 20, "return": 15.5},
        "rows": [{"x": 1}, {"x": 2}, {"x": 3.5}],
    }
    nums = safety.extract_numeric_facts(payload)
    assert sorted(nums) == [1, 2, 3.5, 15.5, 20, 72]


def test_extract_numerics_excludes_booleans():
    """bool ⊂ int in Python, but booleans are NOT numeric facts."""
    payload = {"qualified": True, "n": 5, "ok": False}
    nums = safety.extract_numeric_facts(payload)
    assert nums == [5]


def test_extract_numerics_handles_empty_payload():
    assert safety.extract_numeric_facts({}) == []
    assert safety.extract_numeric_facts({"k": "v"}) == []


# -----------------------------------------------------------------
# validate_no_forbidden_terms
# -----------------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "Please place trade on NVDA tomorrow.",
    "Execute order at market open.",
    "Operator should change threshold to -3%.",
    "Recommend rebalance portfolio toward QQQ.",
    "Allow override guard for one cycle.",
    "Bypass next-bar fill rule.",
])
def test_validate_rejects_forbidden_phrases(phrase):
    with pytest.raises(ValueError):
        safety.validate_no_forbidden_terms(phrase)


def test_validate_accepts_clean_text():
    safety.validate_no_forbidden_terms(
        "The score is 72. The trade was a stop-loss exit."
    )


def test_validate_is_case_insensitive():
    with pytest.raises(ValueError):
        safety.validate_no_forbidden_terms("PLACE TRADE NOW")


# -----------------------------------------------------------------
# assert_banner_present
# -----------------------------------------------------------------

def test_banner_present_passes():
    safety.assert_banner_present(
        "Header line\nAI research insight — not execution logic.\n"
    )


def test_banner_missing_raises():
    with pytest.raises(AssertionError):
        safety.assert_banner_present("Some text without the banner.")


# -----------------------------------------------------------------
# assert_no_hallucinated_numbers
# -----------------------------------------------------------------

def test_hallucination_passes_for_payload_numbers():
    safety.assert_no_hallucinated_numbers(
        "Score is 72. Component entry was 20.",
        {"score": 72, "components": {"entry": 20}},
    )


def test_hallucination_passes_for_allowed_constants():
    safety.assert_no_hallucinated_numbers(
        "Grades: A 85+, B 70+, C 55+, D 40+ out of 100.",
        {},
        allowed_constants=(85, 70, 55, 40, 100),
    )


def test_hallucination_rejects_invented_number():
    with pytest.raises(ValueError):
        safety.assert_no_hallucinated_numbers(
            "Score is 999.",
            {"score": 72},
        )


def test_hallucination_passes_when_text_has_no_numbers():
    safety.assert_no_hallucinated_numbers(
        "All text and no digits here.",
        {"k": "v"},
    )


def test_hallucination_handles_float_formatting_variants():
    """`-5.063591` in payload → both `5.063591` and `-5.063591`
    should be acceptable formats; common rounded variants too."""
    safety.assert_no_hallucinated_numbers(
        "Realized -5.063591 dollars.",
        {"realized": -5.063591},
    )
    safety.assert_no_hallucinated_numbers(
        "Realized -5.06 dollars.",
        {"realized": -5.063591},
    )


def test_hallucination_rejects_modified_payload_number():
    """Off-by-one number that doesn't trace to payload must
    fail — this is the core fabrication guard."""
    with pytest.raises(ValueError):
        safety.assert_no_hallucinated_numbers(
            "Score is 73 (one off).",
            {"score": 72},
        )
