"""Publication Preflight evaluator — pure-function invariants (Wave 1A).

Pins:
  * deterministic: identical input → identical hash, verdict, check order;
  * verdict matrix: block > hold > limitation > READY;
  * fail closed: missing mandatory facts fail their checks;
  * posture coupling: SAFE → HOLD, RESTRICTED caps at
    READY_WITH_LIMITATIONS;
  * language gates: prohibited phrases and unsupported probability claims
    block;
  * NaN/Infinity payloads block via payload_wellformed;
  * the public projection never leaks internal ids, hashes, checks, or shas;
  * evaluator purity: `evaluate` performs no I/O (no db/session attribute
    is even reachable from the frozen input).
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from apps.api.src.api.publication_preflight import public_projection
from apps.api.src.domain.publication import preflight as pf


def good_input(**overrides) -> pf.PreflightInput:
    """A candidate that passes every deterministic check except the two
    honest always-limitations (calibration_disclosed, schema_version).

    pf-2: buckets are derived from the time fields unless explicitly
    overridden, mirroring load_inputs."""
    base = dict(
        recommendation_id="rec-1",
        asset_id="asset-1",
        symbol="GE",
        company_name="GE Aerospace",
        action="Buy",
        conviction="66.67",
        confidence_label="High",
        enough_data=True,
        stale_data=False,
        engine_version="0.1.0",
        snapshot_hash="a29f8f728b908128",
        generated_at="2026-07-12T01:00:00+00:00",
        thesis="Trend supportive; risk from volatility.",
        family_scores={"trend_momentum": "0.7", "volatility_risk": "-0.2"},
        rationale_parse_error=False,
        evidence=(
            {"factor_key": "sma", "family": "trend_momentum",
             "direction": "positive", "narrative": "above long-term average"},
            {"factor_key": "beta", "family": "volatility_risk",
             "direction": "negative", "narrative": "bigger swings than market"},
        ),
        evidence_parse_error=False,
        latest_bar_ts="2026-07-11T20:00:00+00:00",
        latest_bar_close="359.27",
        is_latest_for_asset=True,
        newer_rec_id=None,
        symbol_asset_count=1,
        last_ingest_run_id="run-1",
        last_ingest_status="success",
        last_ingest_finished_at="2026-07-12T00:30:00+00:00",
        ingest_contracts_enabled=True,
        posture="NORMAL",
        posture_event_id=None,
        evaluator_git_sha="abc123def456",
        now="2026-07-12T02:00:00+00:00",
    )
    base.update(overrides)
    if "buckets" not in base:
        base["buckets"] = pf.compute_buckets(
            base["now"], base["latest_bar_ts"], base["last_ingest_status"],
            base["last_ingest_finished_at"], base["generated_at"],
        )
    # keep the duplicate-idea facts coherent unless a test overrides both
    if not base["is_latest_for_asset"] and base["newer_rec_id"] is None:
        base["newer_rec_id"] = "rec-newer"
    return pf.PreflightInput(**base)


def verdict_of(**overrides) -> str:
    return pf.evaluate(good_input(**overrides)).verdict


# ---------------------------------------------------------------------------
# determinism + baseline
# ---------------------------------------------------------------------------

def test_baseline_is_ready_with_limitations_by_honest_design():
    # calibration_disclosed + schema_version are permanent limitations until
    # their promotion gates clear — a fully healthy idea is therefore
    # READY_WITH_LIMITATIONS, never a false plain READY.
    res = pf.evaluate(good_input())
    assert res.verdict == "READY_WITH_LIMITATIONS"
    failed = {c.check_id for c in res.checks if not c.passed}
    assert failed == {"calibration_disclosed", "schema_version_present"}


def test_identical_input_identical_hash_and_checks():
    a = pf.evaluate(good_input())
    b = pf.evaluate(good_input())
    assert a.input_hash == b.input_hash
    assert a.verdict == b.verdict
    assert [c.check_id for c in a.checks] == [c.check_id for c in b.checks]


def test_changed_input_changes_hash():
    a = good_input()
    b = good_input(latest_bar_close="360.00")
    assert a.input_hash() != b.input_hash()


def test_check_order_is_stable_registry_order():
    res = pf.evaluate(good_input())
    assert [c.check_id for c in res.checks] == [
        "price_data_exists", "price_freshness", "provider_state",
        "ingest_contract", "enough_data", "engine_stale_flag",
        "action_publishable", "plan_inputs_valid", "identity_normalized",
        "no_duplicate_open_idea", "timestamp_coherent", "evidence_present",
        "counter_evidence_present", "falsifier_present",
        "evidence_review_state", "evidence_provenance", "payload_wellformed",
        "confidence_label_valid", "wording_consistent",
        "no_probability_claim", "calibration_disclosed",
        "prohibited_language", "beginner_summary_present",
        "schema_version_present", "git_sha_known", "system_posture",
    ]


# ---------------------------------------------------------------------------
# verdict matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mutation, expected", [
    # BLOCKED — data/identity/evidence/provenance/language failures
    (dict(latest_bar_ts=None, latest_bar_close=None), "BLOCKED"),
    (dict(enough_data=False), "BLOCKED"),
    (dict(action="Yolo"), "BLOCKED"),
    (dict(symbol="ge!"), "BLOCKED"),
    (dict(is_latest_for_asset=False), "BLOCKED"),
    (dict(symbol_asset_count=2), "BLOCKED"),
    (dict(generated_at=None), "BLOCKED"),
    (dict(evidence=(), family_scores={}), "BLOCKED"),
    (dict(family_scores={"trend_momentum": "0.7"}), "BLOCKED"),  # falsifier: no volatility_risk
    (dict(evidence=({"factor_key": "x", "family": "mystery_llm",
                     "direction": "positive", "narrative": ""},)), "BLOCKED"),
    (dict(engine_version=None), "BLOCKED"),
    (dict(snapshot_hash=None), "BLOCKED"),
    (dict(rationale_parse_error=True), "BLOCKED"),
    (dict(confidence_label="Extreme"), "BLOCKED"),
    (dict(thesis="This has a 90% chance of profit."), "BLOCKED"),
    (dict(thesis="Returns are guaranteed here."), "BLOCKED"),
    # HOLD — transient/data-freshness failures
    (dict(latest_bar_ts="2026-07-01T20:00:00+00:00"), "HOLD"),
    (dict(last_ingest_status="failure"), "HOLD"),
    (dict(last_ingest_status=None), "HOLD"),
    (dict(stale_data=True), "HOLD"),
    (dict(posture="SAFE"), "HOLD"),
    # limitations only → READY_WITH_LIMITATIONS
    (dict(), "READY_WITH_LIMITATIONS"),
    (dict(posture="RESTRICTED"), "READY_WITH_LIMITATIONS"),
    (dict(ingest_contracts_enabled=False), "READY_WITH_LIMITATIONS"),
    (dict(evidence=(good_input().evidence[0],),
          family_scores={"trend_momentum": "0.7",
                         "volatility_risk": "-0.2"}), "READY_WITH_LIMITATIONS"),
])
def test_verdict_matrix(mutation, expected):
    assert verdict_of(**mutation) == expected


def test_block_wins_over_hold_and_limitation():
    assert verdict_of(enough_data=False, stale_data=True,
                      posture="RESTRICTED") == "BLOCKED"


def test_hold_wins_over_limitation():
    assert verdict_of(stale_data=True, posture="RESTRICTED") == "HOLD"


def test_nan_in_family_scores_blocks_plan_or_falsifier():
    # NaN volatility → falsifier not derivable → BLOCKED (fail closed).
    assert verdict_of(
        family_scores={"trend_momentum": "0.7", "volatility_risk": "NaN"}
    ) == "BLOCKED"


def test_future_generated_at_blocks():
    assert verdict_of(generated_at="2026-07-12T04:00:00+00:00") == "BLOCKED"


def test_missing_git_sha_is_limitation_not_block():
    assert verdict_of(evaluator_git_sha="unknown") == "READY_WITH_LIMITATIONS"


# ---------------------------------------------------------------------------
# strict JSON parsing (NaN / Infinity / malformed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    '{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', '{broken',
    '[1,2,3]',
])
def test_strict_parse_rejects_nonfinite_and_malformed(raw):
    parsed, err = pf._strict_parse_json(raw)
    assert err is True
    assert parsed == {}


def test_strict_parse_accepts_clean_json():
    parsed, err = pf._strict_parse_json('{"a": 1.5}')
    assert err is False and parsed == {"a": 1.5}


# ---------------------------------------------------------------------------
# public projection redaction
# ---------------------------------------------------------------------------

def test_public_projection_redacts_internals():
    res = pf.evaluate(good_input(posture="RESTRICTED"))
    row = {
        "id": "row-id", "recommendation_id": "rec-1",
        "verdict": res.verdict, "rule_set_version": res.rule_set_version,
        "input_hash": res.input_hash,
        "checks_json": json.dumps([pf._check_dict(c) for c in res.checks]),
        "limitations_json": json.dumps(
            [pf._check_dict(c) for c in res.limitations]),
        "blocking_reasons_json": "[]",
        "evaluated_at": res.evaluated_at,
        "evaluator_git_sha": res.evaluator_git_sha,
        "source_freshness_at": res.source_freshness_at,
    }
    proj = public_projection(row)
    assert set(proj.keys()) == {
        "verdict", "limitations", "evaluated_at", "freshness_summary",
    }
    blob = json.dumps(proj)
    assert res.input_hash not in blob
    assert "row-id" not in blob
    assert "abc123def456" not in blob            # git sha
    assert "check_id" not in blob                # raw checks
    # beginner_text lines only, and RESTRICTED posture surfaced honestly
    assert any("degraded" in t for t in proj["limitations"])


def test_projection_survives_malformed_limitations_json():
    proj = public_projection({"verdict": "READY", "limitations_json": "{bad"})
    assert proj["limitations"] == []


# ---------------------------------------------------------------------------
# purity guard
# ---------------------------------------------------------------------------

def test_input_is_frozen_and_json_serializable():
    inp = good_input()
    with pytest.raises(dataclasses.FrozenInstanceError):
        inp.symbol = "X"  # type: ignore[misc]
    json.loads(inp.canonical_json())  # must round-trip


def test_evaluate_source_has_no_db_or_network_calls():
    import inspect
    src = inspect.getsource(pf.evaluate)
    for token in ("db.", "session.", "requests", "httpx", "execute("):
        assert token not in src
