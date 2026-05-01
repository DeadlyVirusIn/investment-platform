"""Phase 11W (Phase C) — provenance + content-addressing helpers.

Pure-fn hash + metadata utilities. Every research artifact row must
carry the provenance produced here. No DB writes, no LLM calls, no
network IO.

Determinism contract:
  * `compute_prompt_hash(s)` — sha256 of the rendered prompt, server
    side. The LLM payload's prompt-hash field is NEVER trusted.
  * `compute_input_snapshot_hash(snapshot)` — sha256 of the canonical
    JSON serialization (sorted keys, no whitespace, no `generated_at`
    timestamp). Same DB state → same hash.
  * `compute_body_hash(body)` — sha256 of the LLM output body, raw.

NEVER imports any execution / scoring / ML module. Verified by
`test_research_phase_c_boundaries.py`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final


# Frozen — keeping these as constants makes them grep-able for future
# audit (e.g., proving the hash algorithm was sha256 at every layer).
HASH_ALGO: Final[str] = "sha256"
PROVENANCE_SCHEMA_VERSION: Final[str] = "v1.0.0"

ALLOWED_PROVIDERS: Final[tuple[str, ...]] = (
    "anthropic", "openai", "google", "xai", "deepseek", "local",
)


class ProvenanceError(ValueError):
    """Raised when provenance metadata is malformed or incomplete."""


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def compute_prompt_hash(rendered_prompt: str) -> str:
    """Hash the fully-rendered LLM prompt (template + bound inputs).
    Computed server-side; LLM responses must NEVER overwrite this
    field. Empty / None raises — every artifact has a prompt."""
    if not rendered_prompt:
        raise ProvenanceError("rendered_prompt must be non-empty")
    return _sha256_hex(rendered_prompt.encode("utf-8"))


def compute_body_hash(body: str) -> str:
    """Hash the LLM output body, raw bytes. Empty bodies are rejected
    at the DB layer (NOT NULL); here we still allow hashing of an
    empty string for testing convenience but the production path will
    refuse the row before this is called."""
    return _sha256_hex(body.encode("utf-8"))


def compute_input_snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Hash a JSON-serializable input snapshot. Excludes any
    `generated_at` key from the hash so timestamps don't perturb
    determinism. Sorted keys + compact separators ensure two
    structurally-equal dicts hash identically regardless of insertion
    order."""
    if snapshot is None:
        raise ProvenanceError("snapshot must be a dict")
    if not isinstance(snapshot, dict):
        raise ProvenanceError(
            f"snapshot must be a dict, got {type(snapshot).__name__}"
        )
    # Drop generated_at recursively (only at top-level: input snapshot
    # is not nested by spec, but defend in depth).
    cleaned = {k: v for k, v in snapshot.items() if k != "generated_at"}
    payload = json.dumps(
        cleaned,
        sort_keys=True,
        separators=(",", ":"),
        default=str,  # date / datetime → ISO string
    )
    return _sha256_hex(payload.encode("utf-8"))


def normalize_provider_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize + validate a provider metadata block. Returns a new
    dict with required fields lower-cased + present.

    Required keys (raises ProvenanceError if missing or invalid):
      - provider          (one of ALLOWED_PROVIDERS)
      - model_id          (non-empty str)
      - model_version     (non-empty str)
      - tokens_in         (int >= 0)
      - tokens_out        (int >= 0)
      - cost_usd          (float-like >= 0)

    Optional keys preserved:
      - prompt_template_id
      - prompt_template_version
      - temperature
      - seed
      - latency_ms
    """
    if metadata is None or not isinstance(metadata, dict):
        raise ProvenanceError("metadata must be a non-null dict")
    required = (
        "provider", "model_id", "model_version",
        "tokens_in", "tokens_out", "cost_usd",
    )
    for key in required:
        if key not in metadata:
            raise ProvenanceError(f"missing required field: {key}")
    provider = str(metadata["provider"]).strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ProvenanceError(
            f"unknown provider {provider!r}; "
            f"allowed: {ALLOWED_PROVIDERS}"
        )
    model_id = str(metadata["model_id"]).strip()
    model_version = str(metadata["model_version"]).strip()
    if not model_id or not model_version:
        raise ProvenanceError("model_id and model_version must be non-empty")
    try:
        tokens_in = int(metadata["tokens_in"])
        tokens_out = int(metadata["tokens_out"])
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"tokens must be ints: {exc}") from exc
    if tokens_in < 0 or tokens_out < 0:
        raise ProvenanceError("tokens_in / tokens_out must be >= 0")
    try:
        cost_usd = float(metadata["cost_usd"])
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"cost_usd must be numeric: {exc}") from exc
    if cost_usd < 0:
        raise ProvenanceError("cost_usd must be >= 0")
    out: dict[str, Any] = {
        "provider": provider,
        "model_id": model_id,
        "model_version": model_version,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "hash_algo": HASH_ALGO,
    }
    for opt in (
        "prompt_template_id", "prompt_template_version",
        "temperature", "seed", "latency_ms",
    ):
        if opt in metadata:
            out[opt] = metadata[opt]
    return out
