"""Phase 11W (Phase D.1) — manual research run orchestrator.

INTERNAL function — NOT exposed via any HTTP route in Phase B,
Phase C, or Phase D.1. Operator-only entry point: imported from a
Python REPL or admin script.

Behaviour (single ticker, single agent, single artifact):
  1. Build deterministic input snapshot via Phase C helper.
  2. Compute input_snapshot_hash (excludes generated_at).
  3. Render prompt via prompts.render_single_asset_context_note.
  4. Compute prompt_hash server-side.
  5. Call provider (default mock; offline + deterministic).
  6. Validate provider body via safety.assert_no_action_language.
  7. INSERT one research_ro.research_run row.
  8. INSERT one research_ro.research_agent_output row.
  9. Commit both inserts in one transaction.

Fail-closed paths:
  * Forbidden tokens in body → INSERT research_run with
    status='token_violation', NO research_agent_output row.
  * ProviderError → INSERT research_run with
    status='provider_error', NO research_agent_output row.
  * Idempotency unique-key conflict → caller decides; manual_run
    raises so the caller knows the run is already persisted.

NEVER writes to any execution table. Whitelisted SELECTs only,
through the Phase C input-snapshot helper.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.research.input_snapshot import build_input_snapshot
from apps.api.src.research.prompts import (
    PROMPT_TEMPLATE_ID,
    PROMPT_TEMPLATE_VERSION,
    render_single_asset_context_note,
)
from apps.api.src.research.provenance import (
    compute_body_hash,
    compute_input_snapshot_hash,
    compute_prompt_hash,
)
from apps.api.src.research.provider_base import (
    ProviderError,
    ProviderResult,
    ResearchProvider,
)
from apps.api.src.research.providers.gemini_provider import (
    GeminiResearchProvider,
    estimate_cost_usd as gemini_estimate_cost_usd,
)
from apps.api.src.research.providers.mock_provider import (
    MockResearchProvider,
)
from apps.api.src.research.safety import (
    ResearchSafetyError,
    assert_no_action_language,
)


# Frozen agent role for Phase D.1. Future phases may add more.
PHASE_D1_AGENT_ROLE: Final[str] = "fundamentals"
PHASE_D1_SCHEMA_VERSION: Final[str] = "research-run-v1.0.0"
PHASE_D1_PROMPT_BUNDLE_VERSION: Final[str] = "single-asset-v1.0.0"


RunStatus = Literal[
    "succeeded", "token_violation", "provider_error", "cost_exceeded",
]


@dataclass(frozen=True)
class ResearchRunResult:
    """Caller-facing result. Pure-fn dataclass; no DB handle."""

    run_id: str
    status: RunStatus
    input_snapshot_hash: str
    prompt_hash: str
    body_hash: str | None
    agent_output_id: str | None


def _resolve_provider(provider_name: str) -> ResearchProvider:
    """Phase D.2: 'mock' is always available. 'gemini' requires
    BOTH `RESEARCH_REAL_PROVIDER_ENABLED=True` AND a non-empty
    `RESEARCH_GEMINI_API_KEY`. All other names raise so a typo
    cannot route to a real LLM."""
    if provider_name == "mock":
        return MockResearchProvider()
    if provider_name == "gemini":
        if not settings.RESEARCH_REAL_PROVIDER_ENABLED:
            raise ValueError(
                "RESEARCH_REAL_PROVIDER_ENABLED=False; gemini "
                "provider blocked at resolver. Default OFF in prod."
            )
        if not settings.RESEARCH_GEMINI_API_KEY:
            raise ValueError(
                "RESEARCH_GEMINI_API_KEY missing; gemini provider "
                "blocked at resolver. Fail-closed."
            )
        return GeminiResearchProvider(
            api_key=settings.RESEARCH_GEMINI_API_KEY,
            timeout_seconds=settings.RESEARCH_PROVIDER_TIMEOUT_SECONDS,
            max_output_tokens=settings.RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS,
        )
    raise ValueError(
        f"unknown provider_name={provider_name!r}. Supported: "
        f"'mock' (always); 'gemini' (when enabled + key present)."
    )


def _insert_run_row(
    session: Session,
    *,
    run_id: str,
    symbol: str,
    as_of: dt.date,
    candidate_idea_id: str | None,
    prompt_bundle_hash: str,
    input_snapshot_hash: str,
    provider: str,
    model_id: str,
    model_version: str,
    prompt_hash: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    status: RunStatus,
    operator_id: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO research_ro.research_run
              (id, symbol, as_of, candidate_idea_id, schema_version,
               prompt_bundle_hash, input_snapshot_hash,
               provider, model_id, model_version,
               prompt_template_id, prompt_template_version,
               prompt_hash, temperature, seed,
               tokens_in, tokens_out, cost_usd, status,
               error_code, error_message,
               triggered_by, operator_id, finished_at)
            VALUES
              (:id, :symbol, :as_of, :cid, :schema_version,
               :prompt_bundle_hash, :input_snapshot_hash,
               :provider, :model_id, :model_version,
               :prompt_template_id, :prompt_template_version,
               :prompt_hash, 0.0, 0,
               :tokens_in, :tokens_out, :cost_usd, :status,
               :error_code, :error_message,
               'manual', :operator_id, now())
            """
        ),
        {
            "id": run_id,
            "symbol": symbol,
            "as_of": as_of,
            "cid": candidate_idea_id,
            "schema_version": PHASE_D1_SCHEMA_VERSION,
            "prompt_bundle_hash": prompt_bundle_hash,
            "input_snapshot_hash": input_snapshot_hash,
            "provider": provider,
            "model_id": model_id,
            "model_version": model_version,
            "prompt_template_id": PROMPT_TEMPLATE_ID,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "prompt_hash": prompt_hash,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "operator_id": operator_id,
        },
    )


def _insert_agent_output_row(
    session: Session,
    *,
    output_id: str,
    run_id: str,
    body: str,
    body_hash: str,
    provider_result: ProviderResult,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO research_ro.research_agent_output
              (id, run_id, agent_role, sequence_no,
               body, body_hash,
               evidence_refs,
               provider, model_id, model_version, prompt_hash,
               tokens_in, tokens_out, cost_usd, status, latency_ms)
            VALUES
              (:id, :run_id, :agent_role, 1,
               :body, :body_hash,
               '[]'::jsonb,
               :provider, :model_id, :model_version, :prompt_hash,
               :tokens_in, :tokens_out, :cost_usd,
               'succeeded', :latency_ms)
            """
        ),
        {
            "id": output_id,
            "run_id": run_id,
            "agent_role": PHASE_D1_AGENT_ROLE,
            "body": body,
            "body_hash": body_hash,
            "provider": provider_result.provider,
            "model_id": provider_result.model_id,
            "model_version": provider_result.model_version,
            "prompt_hash": provider_result.raw_response_hash,
            "tokens_in": provider_result.tokens_in,
            "tokens_out": provider_result.tokens_out,
            "cost_usd": provider_result.cost_usd,
            "latency_ms": provider_result.latency_ms,
        },
    )


def run_single_asset_context_note(
    session: Session,
    *,
    symbol: str,
    as_of: dt.date,
    candidate_idea_id: str | None = None,
    provider_name: str = "mock",
    operator_id: str = "manual",
) -> ResearchRunResult:
    """Manual entry point. Returns a ResearchRunResult; never raises
    on safety / provider failure (those return a status). Raises
    only on truly unexpected conditions (e.g., DB connectivity).
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("symbol must be a non-empty str")
    if not isinstance(as_of, dt.date):
        raise ValueError("as_of must be a datetime.date")
    if not operator_id:
        raise ValueError("operator_id must be non-empty")

    snapshot = build_input_snapshot(
        session,
        symbol=symbol,
        as_of=as_of,
        candidate_idea_id=candidate_idea_id,
    )
    input_snapshot_hash = compute_input_snapshot_hash(snapshot)

    rendered_prompt = render_single_asset_context_note(
        symbol=symbol,
        as_of=as_of,
        asset_meta=snapshot.get("asset"),
        context_gates=snapshot.get("context_daily"),
        candidate=snapshot.get("candidate_idea"),
    )
    prompt_hash = compute_prompt_hash(rendered_prompt)
    prompt_bundle_hash = compute_prompt_hash(
        f"{PROMPT_TEMPLATE_ID}:{PROMPT_TEMPLATE_VERSION}"
    )

    provider = _resolve_provider(provider_name)

    # Phase D.2 — cost-cap pre-check. Only applies to providers that
    # carry a non-trivial cost. The mock provider's flat $0.0 cost
    # short-circuits this check trivially. For gemini (and any
    # future real provider) we estimate worst-case cost from prompt
    # length + max output tokens BEFORE invoking the provider; over
    # cap → status='cost_exceeded', no provider call, no output row.
    run_id = str(uuid.uuid4())
    if isinstance(provider, GeminiResearchProvider):
        worst_case_cost = gemini_estimate_cost_usd(
            rendered_prompt=rendered_prompt,
            max_output_tokens=(
                settings.RESEARCH_PROVIDER_MAX_OUTPUT_TOKENS
            ),
        )
        max_cost = settings.RESEARCH_PROVIDER_MAX_COST_USD
        if worst_case_cost > max_cost:
            _insert_run_row(
                session,
                run_id=run_id,
                symbol=symbol,
                as_of=as_of,
                candidate_idea_id=candidate_idea_id,
                prompt_bundle_hash=prompt_bundle_hash,
                input_snapshot_hash=input_snapshot_hash,
                provider=provider_name,
                model_id=GeminiResearchProvider.MODEL_ID,
                model_version=GeminiResearchProvider.MODEL_VERSION,
                prompt_hash=prompt_hash,
                tokens_in=0,
                tokens_out=0,
                cost_usd=worst_case_cost,
                status="cost_exceeded",
                operator_id=operator_id,
                error_code="cost_exceeded",
                error_message=(
                    f"estimated ${worst_case_cost:.6f} > cap "
                    f"${max_cost:.6f}"
                ),
            )
            session.commit()
            return ResearchRunResult(
                run_id=run_id,
                status="cost_exceeded",
                input_snapshot_hash=input_snapshot_hash,
                prompt_hash=prompt_hash,
                body_hash=None,
                agent_output_id=None,
            )

    # Call provider; on failure, persist provider_error.
    try:
        result = provider.generate(
            rendered_prompt,
            metadata={
                "symbol": symbol, "as_of": as_of.isoformat(),
            },
        )
    except ProviderError as exc:
        _insert_run_row(
            session,
            run_id=run_id,
            symbol=symbol,
            as_of=as_of,
            candidate_idea_id=candidate_idea_id,
            prompt_bundle_hash=prompt_bundle_hash,
            input_snapshot_hash=input_snapshot_hash,
            provider=provider_name,
            model_id="unknown",
            model_version="unknown",
            prompt_hash=prompt_hash,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            status="provider_error",
            operator_id=operator_id,
            error_code="provider_error",
            error_message=str(exc)[:500],
        )
        session.commit()
        return ResearchRunResult(
            run_id=run_id,
            status="provider_error",
            input_snapshot_hash=input_snapshot_hash,
            prompt_hash=prompt_hash,
            body_hash=None,
            agent_output_id=None,
        )

    # Validate body — fail-closed on forbidden tokens.
    try:
        assert_no_action_language(result.body)
    except ResearchSafetyError as exc:
        _insert_run_row(
            session,
            run_id=run_id,
            symbol=symbol,
            as_of=as_of,
            candidate_idea_id=candidate_idea_id,
            prompt_bundle_hash=prompt_bundle_hash,
            input_snapshot_hash=input_snapshot_hash,
            provider=result.provider,
            model_id=result.model_id,
            model_version=result.model_version,
            prompt_hash=prompt_hash,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            status="token_violation",
            operator_id=operator_id,
            error_code="token_violation",
            error_message=str(exc)[:500],
        )
        session.commit()
        return ResearchRunResult(
            run_id=run_id,
            status="token_violation",
            input_snapshot_hash=input_snapshot_hash,
            prompt_hash=prompt_hash,
            body_hash=None,
            agent_output_id=None,
        )

    # Happy path: insert run + agent_output in a single transaction.
    body_hash = compute_body_hash(result.body)
    output_id = str(uuid.uuid4())
    try:
        _insert_run_row(
            session,
            run_id=run_id,
            symbol=symbol,
            as_of=as_of,
            candidate_idea_id=candidate_idea_id,
            prompt_bundle_hash=prompt_bundle_hash,
            input_snapshot_hash=input_snapshot_hash,
            provider=result.provider,
            model_id=result.model_id,
            model_version=result.model_version,
            prompt_hash=prompt_hash,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=result.cost_usd,
            status="succeeded",
            operator_id=operator_id,
        )
        _insert_agent_output_row(
            session,
            output_id=output_id,
            run_id=run_id,
            body=result.body,
            body_hash=body_hash,
            provider_result=result,
        )
        session.commit()
    except IntegrityError:
        # Idempotency hit — caller can recover.
        session.rollback()
        raise

    return ResearchRunResult(
        run_id=run_id,
        status="succeeded",
        input_snapshot_hash=input_snapshot_hash,
        prompt_hash=prompt_hash,
        body_hash=body_hash,
        agent_output_id=output_id,
    )
