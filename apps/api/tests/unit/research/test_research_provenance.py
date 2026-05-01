"""Phase 11W (Phase C) — provenance helper tests."""

from __future__ import annotations

import pytest

from apps.api.src.research.provenance import (
    ALLOWED_PROVIDERS,
    HASH_ALGO,
    PROVENANCE_SCHEMA_VERSION,
    ProvenanceError,
    compute_body_hash,
    compute_input_snapshot_hash,
    compute_prompt_hash,
    normalize_provider_metadata,
)


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------


def test_hash_algo_is_sha256():
    assert HASH_ALGO == "sha256"


def test_provenance_schema_version_is_v1():
    assert PROVENANCE_SCHEMA_VERSION == "v1.0.0"


def test_allowed_providers_is_frozen_tuple():
    assert isinstance(ALLOWED_PROVIDERS, tuple)
    for p in ("anthropic", "openai", "google", "xai", "deepseek", "local"):
        assert p in ALLOWED_PROVIDERS


# ---------------------------------------------------------------------------
# compute_prompt_hash
# ---------------------------------------------------------------------------


def test_prompt_hash_is_deterministic():
    p = "Render this prompt with these inputs: A, B, C."
    assert compute_prompt_hash(p) == compute_prompt_hash(p)


def test_prompt_hash_is_64_hex_chars():
    h = compute_prompt_hash("anything")
    assert len(h) == 64
    int(h, 16)  # parses as hex


def test_prompt_hash_differs_for_different_prompts():
    a = compute_prompt_hash("prompt A")
    b = compute_prompt_hash("prompt B")
    assert a != b


def test_prompt_hash_rejects_empty():
    with pytest.raises(ProvenanceError):
        compute_prompt_hash("")


# ---------------------------------------------------------------------------
# compute_body_hash
# ---------------------------------------------------------------------------


def test_body_hash_is_deterministic_and_64_hex():
    h = compute_body_hash("body text")
    assert len(h) == 64
    assert h == compute_body_hash("body text")


def test_body_hash_handles_unicode():
    h = compute_body_hash("narrative — observation")
    assert len(h) == 64


# ---------------------------------------------------------------------------
# compute_input_snapshot_hash
# ---------------------------------------------------------------------------


def test_input_snapshot_hash_deterministic_for_same_dict():
    snap = {"symbol": "AAPL", "as_of": "2026-04-30", "source_tables": []}
    h1 = compute_input_snapshot_hash(snap)
    h2 = compute_input_snapshot_hash(snap)
    assert h1 == h2


def test_input_snapshot_hash_excludes_generated_at():
    snap_a = {
        "symbol": "AAPL",
        "as_of": "2026-04-30",
        "generated_at": "2026-04-30T10:00:00Z",
    }
    snap_b = {
        "symbol": "AAPL",
        "as_of": "2026-04-30",
        "generated_at": "2026-04-30T23:59:59Z",
    }
    assert compute_input_snapshot_hash(snap_a) == (
        compute_input_snapshot_hash(snap_b)
    )


def test_input_snapshot_hash_invariant_to_key_order():
    snap_a = {"a": 1, "b": 2, "c": 3}
    snap_b = {"c": 3, "b": 2, "a": 1}
    assert compute_input_snapshot_hash(snap_a) == (
        compute_input_snapshot_hash(snap_b)
    )


def test_input_snapshot_hash_changes_on_value_change():
    snap_a = {"symbol": "AAPL", "as_of": "2026-04-30"}
    snap_b = {"symbol": "AAPL", "as_of": "2026-05-01"}
    assert compute_input_snapshot_hash(snap_a) != (
        compute_input_snapshot_hash(snap_b)
    )


def test_input_snapshot_hash_rejects_non_dict():
    with pytest.raises(ProvenanceError):
        compute_input_snapshot_hash(None)  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError):
        compute_input_snapshot_hash("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# normalize_provider_metadata
# ---------------------------------------------------------------------------


def _valid_meta(**override):
    base = {
        "provider": "anthropic",
        "model_id": "claude-opus-4-7",
        "model_version": "2026-04-15",
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.001,
    }
    base.update(override)
    return base


def test_normalize_returns_required_block():
    out = normalize_provider_metadata(_valid_meta())
    assert out["provider"] == "anthropic"
    assert out["model_id"] == "claude-opus-4-7"
    assert out["tokens_in"] == 100
    assert out["cost_usd"] == 0.001
    assert out["provenance_schema_version"] == "v1.0.0"
    assert out["hash_algo"] == "sha256"


def test_normalize_lowercases_provider():
    out = normalize_provider_metadata(_valid_meta(provider="Anthropic"))
    assert out["provider"] == "anthropic"


def test_normalize_preserves_optional_fields():
    out = normalize_provider_metadata(
        _valid_meta(temperature=0.7, seed=42, latency_ms=1234,
                    prompt_template_id="t1", prompt_template_version=1),
    )
    assert out["temperature"] == 0.7
    assert out["seed"] == 42
    assert out["latency_ms"] == 1234
    assert out["prompt_template_id"] == "t1"
    assert out["prompt_template_version"] == 1


def test_normalize_rejects_unknown_provider():
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(_valid_meta(provider="random_provider"))


def test_normalize_rejects_negative_tokens():
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(_valid_meta(tokens_in=-1))


def test_normalize_rejects_negative_cost():
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(_valid_meta(cost_usd=-0.01))


@pytest.mark.parametrize("missing", [
    "provider", "model_id", "model_version",
    "tokens_in", "tokens_out", "cost_usd",
])
def test_normalize_rejects_missing_required(missing):
    meta = _valid_meta()
    del meta[missing]
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(meta)


def test_normalize_rejects_non_dict():
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(None)  # type: ignore[arg-type]
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata("string")  # type: ignore[arg-type]


def test_normalize_rejects_empty_model_strings():
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(_valid_meta(model_id=""))
    with pytest.raises(ProvenanceError):
        normalize_provider_metadata(_valid_meta(model_version=""))
