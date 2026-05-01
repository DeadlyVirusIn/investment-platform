"""Phase 11W (Phase C) — Pydantic schemas for the Research
Intelligence + Audit Layer.

INTERNAL models only. NEVER exposed via any FastAPI router in
Phase B or Phase C — they exist purely to give a future Phase E /
Phase F orchestrator a typed contract for what it would persist
into the `research_ro` schema.

Every model carries a `ProvenanceBlock` and is read-validated
against the same forbidden-token regex used by the DB CHECK and the
client render guard. Defense in depth.

NEVER imports execution / scoring / ML modules. NEVER imports the
public FastAPI router. Verified by `test_research_phase_c_boundaries`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.api.src.research.safety import validate_research_text


# ---------------------------------------------------------------------------
# Frozen status + role enums (mirror DB enums in
# infra/alembic/versions/052_research_ro_init.py).
# ---------------------------------------------------------------------------

ResearchRunStatus = Literal[
    "pending", "running", "succeeded", "failed", "partial",
    "token_violation", "cost_exceeded", "provider_error",
    "timeout", "schema_violation",
]

ResearchAgentRole = Literal[
    "fundamentals", "sentiment", "news", "technical",
    "bull_researcher", "bear_researcher", "risk_analyst",
    "reflector",
]

TriggeredBy = Literal["manual", "operator"]


# ---------------------------------------------------------------------------
# Provenance + evidence
# ---------------------------------------------------------------------------


class ProvenanceBlock(BaseModel):
    """Mandatory metadata block carried by every research artifact.

    `prompt_hash` is computed server-side over the rendered prompt;
    LLM payloads must NEVER overwrite it (enforced at the persister
    layer, not here)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(..., min_length=1)
    model_id: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    prompt_template_id: str = Field(..., min_length=1)
    prompt_template_version: int = Field(..., ge=1)
    prompt_hash: str = Field(..., min_length=1)
    temperature: float = Field(..., ge=0.0, le=2.0)
    seed: int = Field(...)
    tokens_in: int = Field(..., ge=0)
    tokens_out: int = Field(..., ge=0)
    cost_usd: float = Field(..., ge=0.0)
    status: ResearchRunStatus
    latency_ms: int | None = Field(default=None, ge=0)


class EvidenceRef(BaseModel):
    """Provenance for a single claim inside a research artifact body.

    Every material claim must reference a public-table row + an
    as-of timestamp. References are stored in the `evidence_refs`
    jsonb column on `research_agent_output` and friends."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_table: str = Field(..., min_length=1)
    source_pk: str = Field(..., min_length=1)
    as_of_ts: dt.datetime


class InputSnapshot(BaseModel):
    """Schema mirror of the dict returned by
    `apps.api.src.research.input_snapshot.build_input_snapshot`.

    Carried into a research run so the orchestrator (future phase)
    can record exactly which inputs the LLM saw. Hashing rule:
    `compute_input_snapshot_hash` excludes `generated_at`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    as_of: dt.date
    candidate_idea: dict[str, Any] | None = None
    asset: dict[str, Any] | None = None
    context_daily: dict[str, Any] | None = None
    source_tables: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: dt.datetime


# ---------------------------------------------------------------------------
# Body-text validators
# ---------------------------------------------------------------------------


def _no_action_language(value: str) -> str:
    ok, matched = validate_research_text(value)
    if not ok:
        raise ValueError(
            f"forbidden action token in body: {matched!r}"
        )
    return value


# ---------------------------------------------------------------------------
# Research-row internal models
# ---------------------------------------------------------------------------


class ResearchRunCreateInternal(BaseModel):
    """Internal-only payload that a future orchestrator would use to
    INSERT a row into `research_ro.research_run`. NOT exposed via any
    HTTP route in Phase B or Phase C."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(..., min_length=1)
    as_of: dt.date
    candidate_idea_id: str | None = None
    decision_id: str | None = None
    schema_version: str = Field(..., min_length=1)
    prompt_bundle_hash: str = Field(..., min_length=1)
    input_snapshot_hash: str = Field(..., min_length=1)
    triggered_by: TriggeredBy
    operator_id: str = Field(..., min_length=1)
    provenance: ProvenanceBlock


class ResearchAgentOutputInternal(BaseModel):
    """Per-agent output row. Body text is validated against the
    forbidden-token regex at construction time — fail-closed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(..., min_length=1)
    agent_role: ResearchAgentRole
    sequence_no: int = Field(..., ge=1)
    body: str = Field(..., min_length=1)
    body_hash: str = Field(..., min_length=1)
    structured_output: dict[str, Any] | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    provenance: ProvenanceBlock

    @field_validator("body")
    @classmethod
    def _body_safe(cls, v: str) -> str:
        return _no_action_language(v)


class ResearchDebateSummaryInternal(BaseModel):
    """Bull / Bear / tension-note debate artifact. All three text
    fields are validated against the forbidden-token regex."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(..., min_length=1)
    bullish_summary: str = Field(..., min_length=1)
    bearish_summary: str = Field(..., min_length=1)
    tension_note: str = Field(..., min_length=1)
    bullish_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    bearish_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    body_hash: str = Field(..., min_length=1)
    provenance: ProvenanceBlock

    @field_validator("bullish_summary", "bearish_summary", "tension_note")
    @classmethod
    def _segments_safe(cls, v: str) -> str:
        return _no_action_language(v)


class ResearchReflectionInternal(BaseModel):
    """Append-only reflection on a past decision's realized return.
    Cannot influence future scoring; it is labeled history only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(..., min_length=1)
    decision_id: str = Field(..., min_length=1)
    outcome_window: str = Field(..., min_length=1)
    realized_return: float | None = None
    benchmark_return: float | None = None
    alpha_vs_benchmark: float | None = None
    body: str = Field(..., min_length=1)
    body_hash: str = Field(..., min_length=1)
    provenance: ProvenanceBlock

    @field_validator("body")
    @classmethod
    def _body_safe(cls, v: str) -> str:
        return _no_action_language(v)
