"""M5A — pure aggregation tests for the demand-validation report (no DB)."""

from __future__ import annotations

from apps.api.src.api.feedback_report import aggregate_feedback


def _row(signal_type, surface="pick_detail", user_id=None, device=None, value=None):
    return {
        "user_id": user_id,
        "session_or_device_id": device,
        "surface": surface,
        "signal_type": signal_type,
        "value": value,
        "created_at": None,
    }


def test_empty_table_returns_zero_report():
    r = aggregate_feedback([])
    assert r["total_signals"] == 0
    assert r["authenticated_users"] == 0
    assert r["anonymous_contexts"] == 0
    assert r["useful_ratio"] is None
    assert r["would_use_again_ratio"] is None
    assert r["beta_interest"] == 0
    assert r["text_samples"] == []


def test_authenticated_and_anonymous_counted_separately():
    rows = [
        _row("trust_useful", user_id="u1"),
        _row("trust_useful", user_id="u1"),     # same user → 1 distinct
        _row("trust_useful", user_id="u2"),
        _row("trust_useful", device="dev-a"),   # anon
        _row("trust_useful", device="dev-a"),   # same device → 1 distinct
        _row("trust_useful", device="dev-b"),
    ]
    r = aggregate_feedback(rows)
    assert r["authenticated_users"] == 2
    assert r["anonymous_contexts"] == 2
    assert r["total_signals"] == 6


def test_useful_ratio_correct():
    rows = [_row("trust_useful")] * 3 + [_row("trust_not_useful")]
    r = aggregate_feedback(rows)
    assert r["useful"] == 3 and r["not_useful"] == 1
    assert r["useful_ratio"] == 0.75


def test_would_use_again_ratio_correct():
    rows = [_row("would_use_again")] * 2 + [_row("would_not_use_again")] * 2
    r = aggregate_feedback(rows)
    assert r["would_use_again_ratio"] == 0.5


def test_beta_interest_counted():
    rows = [_row("beta_interest", surface="account"), _row("beta_interest", surface="account")]
    assert aggregate_feedback(rows)["beta_interest"] == 2


def test_surface_breakdown():
    rows = [_row("trust_useful", surface="pick_detail"), _row("trust_useful", surface="options_detail"),
            _row("beta_interest", surface="account")]
    r = aggregate_feedback(rows)
    assert r["by_surface"] == {"account": 1, "options_detail": 1, "pick_detail": 1}


def test_text_samples_capped_and_anonymized():
    rows = [_row("feedback_text", user_id=f"secret-user-{i}", value="x" * 500) for i in range(20)]
    r = aggregate_feedback(rows, sample_cap=3, text_cap=50)
    assert r["feedback_text_count"] == 20
    assert len(r["text_samples"]) == 3            # count capped
    assert all(len(s) <= 50 for s in r["text_samples"])  # length capped
    # no identity is present anywhere in the report
    blob = repr(r)
    assert "secret-user" not in blob and "user_id" not in r
