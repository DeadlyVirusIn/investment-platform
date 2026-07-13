"""Recommendation Publication Preflight — Wave 1A deterministic trust gate.

Decides whether a candidate recommendation may appear on beginner surfaces
(Discover / Today / idea detail). The verdict is a pure function of stored
system facts; no LLM, prompt, model narrative, or administrator can override
it silently — re-evaluation appends a new immutable row, it never edits one.

Design rules (enforced here, pinned by tests):
* ``load_inputs`` performs ALL database reads up front; ``evaluate`` is a
  pure function over that frozen input — no DB writes, no network, no LLM,
  no provider fetching inside checks.
* Ordered check registry; each check returns pass or fail with a fixed
  severity class: info | limitation | hold | block.
* Fail closed: a missing mandatory fact fails its check (never skips), and
  an unexpected evaluator exception is treated by callers as HOLD.
* Verdict mapping: any block-fail → BLOCKED · else any hold-fail → HOLD ·
  else any limitation-fail → READY_WITH_LIMITATIONS · else READY.
* Idempotency: identical (recommendation, rule set, input hash) persists at
  most one row (DB unique constraint; concurrent evaluators race safely via
  ON CONFLICT DO NOTHING + re-select).

Relationship to Research Safe Mode (Wave 1B): posture is consumed through
``domain.publication.posture.current_posture`` — SAFE fails a hold-severity
check (no new publications), RESTRICTED fails a limitation-severity check
(publishes capped at READY_WITH_LIMITATIONS). Existing published ideas,
portfolios, paper exits, and outcome processing are untouched by design:
this gate filters the publication read path only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.build_provenance import get_build_provenance
from apps.api.src.config import settings
from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Recommendation,
    RecommendationEvidence,
)
from apps.api.src.domain.publication.posture import Posture, current_posture

# ---------------------------------------------------------------------------
# Versioning + policy constants (bump RULE_SET_VERSION on ANY semantic change)
# ---------------------------------------------------------------------------

RULE_SET_VERSION = "pf-1"

#: Newest asset bar may be at most this many calendar days old.
MAX_BAR_AGE_DAYS = 5
#: Ingest job considered healthy if the last run finished within this window.
MAX_INGEST_AGE_HOURS = 30
#: generated_at may lead the wall clock by at most this skew.
MAX_FUTURE_SKEW_MINUTES = 15

PUBLISHABLE_ACTIONS = {"Buy", "Hold", "Trim", "Sell"}
APPROVED_CONFIDENCE_LABELS = {"High", "Medium", "Low"}
#: Evidence "family"/source values the rule engine emits — anything outside
#: this set is unreviewed/unknown provenance and fails closed.
TRUSTED_EVIDENCE_FAMILIES = {
    "trend_momentum", "volatility_risk", "exposure", "sentiment", "quality",
    "value", "engine", "policy",
}

#: Server-side prohibited-language list. Concept mirrors the web copy lint
#: (anti-theater + anti-guarantee); the list is owned here, not user-editable.
PROHIBITED_PHRASES = (
    "guaranteed", "guarantee", "can't lose", "cannot lose", "risk-free",
    "risk free", "sure thing", "no risk", "certain to", "will definitely",
    "expected to", "likely to", "powered by ai", "ai-generated",
    "the ai thinks", "we believe", "we think", "moon", "get rich",
)

_PROBABILITY_CLAIM = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s*%\s*(?:chance|probability|odds|likely|win rate)\b",
    re.IGNORECASE,
)

Severity = Literal["info", "limitation", "hold", "block"]
Verdict = Literal["READY", "READY_WITH_LIMITATIONS", "HOLD", "BLOCKED"]


# ---------------------------------------------------------------------------
# Frozen input
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreflightInput:
    """Every fact the evaluator may consult, loaded once, JSON-serializable."""

    recommendation_id: str
    asset_id: str
    symbol: str | None
    company_name: str | None
    action: str | None
    conviction: str | None
    confidence_label: str | None
    enough_data: bool
    stale_data: bool
    engine_version: str | None
    snapshot_hash: str | None
    generated_at: str | None                 # ISO
    thesis: str | None
    family_scores: dict[str, str | None]
    rationale_parse_error: bool
    evidence: tuple[dict[str, Any], ...]     # factor_key/family/direction/narrative
    evidence_parse_error: bool
    latest_bar_ts: str | None                # ISO, this asset, 1d
    latest_bar_close: str | None
    is_latest_for_asset: bool
    symbol_asset_count: int                  # assets sharing this symbol
    last_ingest_status: str | None           # success|failure|running|None
    last_ingest_finished_at: str | None
    ingest_contracts_enabled: bool
    posture: Posture
    evaluator_git_sha: str
    now: str                                 # ISO, frozen at load time
    extra: dict[str, Any] = field(default_factory=dict)

    def canonical_json(self) -> str:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}  # noqa: SLF001
        d["evidence"] = list(d["evidence"])
        # Idempotency contract: the hash covers INPUT FACTS, not the wall
        # clock. `now` is quantized to its calendar date (all freshness
        # policies are day-granular), so re-evaluating unchanged facts on the
        # same day is idempotent while a new day (which can move day-granular
        # freshness ages) legitimately appends a new verdict row.
        d["now"] = (d["now"] or "")[:10]
        return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)

    def input_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _iso(v: dt.datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


def _strict_parse_json(raw: str | None) -> tuple[dict[str, Any], bool]:
    """Parse JSON refusing NaN/Infinity. Returns (dict, parse_error)."""
    if not raw:
        return {}, False
    try:
        def _reject_const(v: str) -> None:
            raise ValueError(f"non-finite constant {v!r} in payload")
        parsed = json.loads(raw, parse_constant=_reject_const)
        if not isinstance(parsed, dict):
            return {}, True
        return parsed, False
    except (ValueError, TypeError):
        return {}, True


def load_inputs(db: Session, rec: Recommendation) -> PreflightInput:
    """Single load phase — the only place preflight touches the database."""
    now = dt.datetime.now(dt.timezone.utc)

    rationale, rat_err = _strict_parse_json(rec.rationale)

    asset = db.get(Asset, rec.asset_id)
    symbol = asset.symbol if asset else None
    name = asset.name if asset else None

    bar = db.execute(
        select(PriceBar.ts, PriceBar.close)
        .where(PriceBar.asset_id == rec.asset_id, PriceBar.timeframe == "1d")
        .order_by(PriceBar.ts.desc())
        .limit(1)
    ).first()

    newer = db.execute(
        select(Recommendation.id)
        .where(
            Recommendation.asset_id == rec.asset_id,
            Recommendation.generated_at > rec.generated_at,
        )
        .limit(1)
    ).scalar()

    symbol_asset_count = 1
    if symbol:
        symbol_asset_count = db.execute(
            text("SELECT count(*) FROM asset WHERE symbol = :s"), {"s": symbol}
        ).scalar() or 1

    ingest = db.execute(
        text(
            "SELECT jr.status, jr.finished_at FROM job_run jr "
            "JOIN job_schedule js ON js.id = jr.job_schedule_id "
            "WHERE js.name = 'ingest_prices_daily' "
            "ORDER BY jr.started_at DESC LIMIT 1"
        )
    ).first()

    ev_rows: list[dict[str, Any]] = []
    ev_err = False
    for ev in db.execute(
        select(RecommendationEvidence)
        .where(RecommendationEvidence.recommendation_id == rec.id)
    ).scalars():
        parsed, err = _strict_parse_json(ev.summary)
        ev_err = ev_err or err
        ev_rows.append({
            "factor_key": ev.evidence_type,
            "family": ev.source,
            "direction": parsed.get("direction"),
            "narrative": parsed.get("narrative") or "",
        })

    prov = get_build_provenance()

    return PreflightInput(
        recommendation_id=rec.id,
        asset_id=rec.asset_id,
        symbol=symbol,
        company_name=name,
        action=rec.action,
        conviction=str(rec.conviction) if rec.conviction is not None else None,
        confidence_label=rationale.get("confidence_label"),
        enough_data=bool(rationale.get("enough_data", False)),
        stale_data=bool(rationale.get("stale_data", False)),
        engine_version=rec.model_version,
        snapshot_hash=rec.snapshot_hash or rationale.get("snapshot_hash"),
        generated_at=_iso(rec.generated_at),
        thesis=rationale.get("thesis"),
        family_scores=dict(rationale.get("family_scores") or {}),
        rationale_parse_error=rat_err,
        evidence=tuple(ev_rows),
        evidence_parse_error=ev_err,
        latest_bar_ts=_iso(bar[0]) if bar else None,
        latest_bar_close=str(bar[1]) if bar and bar[1] is not None else None,
        is_latest_for_asset=newer is None,
        symbol_asset_count=int(symbol_asset_count),
        last_ingest_status=ingest[0] if ingest else None,
        last_ingest_finished_at=_iso(ingest[1]) if ingest else None,
        ingest_contracts_enabled=bool(settings.INGEST_CONTRACTS_ENABLED),
        posture=current_posture(db),
        evaluator_git_sha=str(prov.get("git_sha", "unknown")),
        now=now.isoformat(),
    )


# ---------------------------------------------------------------------------
# Checks — ordered registry of pure functions over PreflightInput
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    check_id: str
    severity: Severity
    passed: bool
    detail: str
    beginner_text: str | None = None   # shown publicly ONLY for limitations


def _age_days(now_iso: str, then_iso: str | None) -> float | None:
    if not then_iso:
        return None
    try:
        now = dt.datetime.fromisoformat(now_iso)
        then = dt.datetime.fromisoformat(then_iso)
    except ValueError:
        return None
    return (now - then).total_seconds() / 86_400.0


def _finite(s: str | None) -> bool:
    if s is None:
        return False
    try:
        v = float(s)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def _all_text(i: PreflightInput) -> str:
    parts = [i.thesis or ""]
    parts += [e.get("narrative") or "" for e in i.evidence]
    return " ".join(parts).lower()


# -- data & freshness -------------------------------------------------------

def _c_price_data_exists(i: PreflightInput) -> CheckResult:
    ok = i.latest_bar_ts is not None and _finite(i.latest_bar_close) \
        and float(i.latest_bar_close) > 0  # type: ignore[arg-type]
    return CheckResult(
        "price_data_exists", "block", ok,
        "daily price bar with positive finite close exists"
        if ok else "no usable daily price bar for this asset",
    )


def _c_price_freshness(i: PreflightInput) -> CheckResult:
    age = _age_days(i.now, i.latest_bar_ts)
    ok = age is not None and age <= MAX_BAR_AGE_DAYS
    return CheckResult(
        "price_freshness", "hold", ok,
        f"newest bar age {age:.1f}d <= {MAX_BAR_AGE_DAYS}d"
        if ok else f"newest bar age {age if age is not None else 'unknown'} exceeds policy ({MAX_BAR_AGE_DAYS}d)",
    )


def _c_provider_state(i: PreflightInput) -> CheckResult:
    if i.last_ingest_status is None:
        return CheckResult("provider_state", "hold", False,
                           "no ingest job history found (fail closed)")
    if i.last_ingest_status != "success":
        return CheckResult("provider_state", "hold", False,
                           f"last ingest run status={i.last_ingest_status}")
    age_h = _age_days(i.now, i.last_ingest_finished_at)
    age_h = age_h * 24 if age_h is not None else None
    ok = age_h is not None and age_h <= MAX_INGEST_AGE_HOURS
    return CheckResult(
        "provider_state", "hold", ok,
        f"last successful ingest {age_h:.1f}h ago" if ok
        else f"last successful ingest too old ({age_h} h)",
    )


def _c_ingest_contract(i: PreflightInput) -> CheckResult:
    if not i.ingest_contracts_enabled:
        return CheckResult(
            "ingest_contract", "limitation", False,
            "ingest contracts flag is off — dataset-level validation not enforced",
            beginner_text="Automated data-quality contracts are not yet "
                          "enforced on this environment.",
        )
    # Contracts run in-pipeline and abort datasets before rows land; if the
    # flag is on and fresh bars exist, no abort-level failure blocked them.
    return CheckResult("ingest_contract", "limitation", True,
                       "ingest contracts enforced upstream")


# -- recommendation integrity -----------------------------------------------

def _c_enough_data(i: PreflightInput) -> CheckResult:
    return CheckResult(
        "enough_data", "block", i.enough_data,
        "engine marked enough_data" if i.enough_data
        else "engine flagged insufficient data",
    )


def _c_stale_flag(i: PreflightInput) -> CheckResult:
    return CheckResult(
        "engine_stale_flag", "hold", not i.stale_data,
        "engine stale_data flag clear" if not i.stale_data
        else "engine flagged stale_data",
    )


def _c_action_publishable(i: PreflightInput) -> CheckResult:
    ok = i.action in PUBLISHABLE_ACTIONS
    return CheckResult(
        "action_publishable", "block", ok,
        f"action {i.action!r} publishable" if ok
        else f"action {i.action!r} not in publishable set",
    )


def _c_plan_inputs_valid(i: PreflightInput) -> CheckResult:
    # Entry/target/exit corridors are derived deterministically from the
    # latest close + typical-move stats; the server-side gate verifies the
    # derivation inputs (positive finite close + finite volatility family)
    # so the plan cannot render nonsense levels.
    close_ok = _finite(i.latest_bar_close) and float(i.latest_bar_close) > 0  # type: ignore[arg-type]
    vol = i.family_scores.get("volatility_risk")
    vol_ok = vol is None or _finite(vol)
    ok = close_ok and vol_ok
    return CheckResult(
        "plan_inputs_valid", "hold", ok,
        "plan derivation inputs valid" if ok
        else "plan inputs invalid (close or volatility not finite/positive)",
    )


def _c_identity_normalized(i: PreflightInput) -> CheckResult:
    ok = bool(i.symbol) and bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", i.symbol or ""))
    return CheckResult(
        "identity_normalized", "block", ok,
        f"symbol {i.symbol!r} normalized" if ok
        else f"symbol {i.symbol!r} missing or not normalized",
    )


def _c_no_duplicate_open_idea(i: PreflightInput) -> CheckResult:
    ok = i.is_latest_for_asset and i.symbol_asset_count == 1
    detail = []
    if not i.is_latest_for_asset:
        detail.append("a newer recommendation exists for this asset")
    if i.symbol_asset_count != 1:
        detail.append(f"{i.symbol_asset_count} assets share symbol {i.symbol!r}")
    return CheckResult(
        "no_duplicate_open_idea", "block", ok,
        "candidate is the unique live idea for its symbol" if ok
        else "; ".join(detail),
    )


def _c_timestamp_coherent(i: PreflightInput) -> CheckResult:
    if not i.generated_at:
        return CheckResult("timestamp_coherent", "block", False,
                           "generated_at missing")
    # age of generated_at relative to now: positive = in the past (fine),
    # negative = in the future (blocked beyond clock skew). Staleness of the
    # underlying data is deliberately NOT judged here — price_freshness
    # already holds old data; duplicating it at block severity would turn a
    # transient freshness problem into a false integrity failure.
    age = _age_days(i.now, i.generated_at)
    ok = age is not None and age >= -(MAX_FUTURE_SKEW_MINUTES / 1440.0)
    return CheckResult(
        "timestamp_coherent", "block", ok,
        "generated_at coherent with the wall clock" if ok
        else "generated_at is in the future beyond allowed clock skew",
    )


# -- evidence integrity -------------------------------------------------------

def _c_evidence_present(i: PreflightInput) -> CheckResult:
    ok = len(i.evidence) > 0 or bool(i.family_scores)
    return CheckResult(
        "evidence_present", "block", ok,
        f"{len(i.evidence)} evidence rows / {len(i.family_scores)} families"
        if ok else "no supporting evidence recorded",
    )


def _c_counter_evidence_present(i: PreflightInput) -> CheckResult:
    neg_ev = any((e.get("direction") or "").lower() in ("negative", "против", "down", "bear")
                 for e in i.evidence)
    neg_family = any(_finite(v) and float(v) < 0  # type: ignore[arg-type]
                     for v in i.family_scores.values())
    ok = neg_ev or neg_family
    return CheckResult(
        "counter_evidence_present", "limitation", ok,
        "cautionary signal present" if ok
        else "no cautionary/counter-evidence recorded",
        beginner_text="No cautionary signal was recorded for this idea — "
                      "treat the risk side as unexamined, not absent.",
    )


def _c_falsifier_present(i: PreflightInput) -> CheckResult:
    # A stock idea's falsifier is its exit-if-wrong condition, derivable
    # exactly when plan inputs and a volatility/risk reading exist.
    close_ok = _finite(i.latest_bar_close) and float(i.latest_bar_close) > 0  # type: ignore[arg-type]
    vol_present = _finite(i.family_scores.get("volatility_risk"))
    ok = close_ok and vol_present
    return CheckResult(
        "falsifier_present", "block", ok,
        "exit-if-wrong derivable (close + volatility present)" if ok
        else "falsifier not derivable — missing volatility/risk reading",
    )


def _c_evidence_review_state(i: PreflightInput) -> CheckResult:
    unknown = sorted({
        (e.get("family") or "?") for e in i.evidence
        if (e.get("family") or "") not in TRUSTED_EVIDENCE_FAMILIES
    })
    ok = not unknown
    return CheckResult(
        "evidence_review_state", "block", ok,
        "all evidence from trusted engine families" if ok
        else f"unreviewed evidence families present: {', '.join(unknown)}",
    )


def _c_evidence_provenance(i: PreflightInput) -> CheckResult:
    ok = bool(i.engine_version) and bool(i.snapshot_hash)
    return CheckResult(
        "evidence_provenance", "block", ok,
        "engine_version + snapshot_hash present" if ok
        else "missing engine_version or snapshot_hash",
    )


def _c_payload_wellformed(i: PreflightInput) -> CheckResult:
    ok = not i.rationale_parse_error and not i.evidence_parse_error
    return CheckResult(
        "payload_wellformed", "block", ok,
        "rationale + evidence JSON parse clean (NaN/Infinity rejected)"
        if ok else "malformed or non-finite JSON in stored payloads",
    )


# -- confidence & language ----------------------------------------------------

def _c_confidence_label_valid(i: PreflightInput) -> CheckResult:
    ok = i.confidence_label in APPROVED_CONFIDENCE_LABELS
    return CheckResult(
        "confidence_label_valid", "block", ok,
        f"label {i.confidence_label!r} approved" if ok
        else f"label {i.confidence_label!r} not in approved set",
    )


def _c_wording_consistent(i: PreflightInput) -> CheckResult:
    # Presentation collapse (High/Medium → "Meets the buy bar") is the shipped
    # default; this check records the mapping is applicable, and fails only
    # if a label outside the mapping table appears (already blocked above).
    ok = i.confidence_label in APPROVED_CONFIDENCE_LABELS
    return CheckResult(
        "wording_consistent", "limitation", ok,
        "buy-bar presentation mapping applies",
    )


def _c_no_probability_claim(i: PreflightInput) -> CheckResult:
    hit = _PROBABILITY_CLAIM.search(_all_text(i))
    return CheckResult(
        "no_probability_claim", "block", hit is None,
        "no unsupported probability claim" if hit is None
        else f"probability claim found: {hit.group(0)!r}",
    )


def _c_calibration_disclosed(i: PreflightInput) -> CheckResult:  # noqa: ARG001
    # Honest steady-state: until a production-grade calibration exists, every
    # published idea carries this limitation. Flips to pass when the
    # production reliability curve ships (documented promotion gate).
    return CheckResult(
        "calibration_disclosed", "limitation", False,
        "confidence calibration status is preliminary (research-only study)",
        beginner_text="Confidence wording is based on rules whose real-world "
                      "accuracy is still being measured.",
    )


def _c_prohibited_language(i: PreflightInput) -> CheckResult:
    blob = _all_text(i)
    hits = sorted({p for p in PROHIBITED_PHRASES if p in blob})
    ok = not hits
    return CheckResult(
        "prohibited_language", "block", ok,
        "no prohibited phrases" if ok
        else f"prohibited phrases present: {', '.join(hits)}",
    )


def _c_beginner_summary_present(i: PreflightInput) -> CheckResult:
    ok = bool((i.thesis or "").strip()) or bool(i.family_scores)
    return CheckResult(
        "beginner_summary_present", "hold", ok,
        "plain-English summary derivable" if ok
        else "no thesis and no signal families to derive a summary from",
    )


# -- provenance & posture -----------------------------------------------------

def _c_schema_version_present(i: PreflightInput) -> CheckResult:  # noqa: ARG001
    # Feature-schema stamping is not implemented anywhere yet (Trust Center:
    # not_yet_evaluated). Honest limitation until it ships.
    return CheckResult(
        "schema_version_present", "limitation", False,
        "feature/input schema version not stamped by the engine yet",
    )


def _c_git_sha_known(i: PreflightInput) -> CheckResult:
    ok = i.evaluator_git_sha not in ("", "unknown")
    return CheckResult(
        "git_sha_known", "limitation", ok,
        f"evaluator git sha {i.evaluator_git_sha[:12]}" if ok
        else "runtime git sha unknown (non-container dev process)",
    )


def _c_system_posture(i: PreflightInput) -> CheckResult:
    if i.posture == "SAFE":
        return CheckResult(
            "system_posture", "hold", False,
            "system posture SAFE — new publications paused",
            beginner_text="Publishing is paused while the data pipeline "
                          "recovers. Nothing you hold is affected.",
        )
    if i.posture == "RESTRICTED":
        return CheckResult(
            "system_posture", "limitation", False,
            "system posture RESTRICTED — publish with limitations only",
            beginner_text="Parts of the data pipeline are degraded; this "
                          "idea published under restrictions.",
        )
    return CheckResult("system_posture", "hold", True, "posture NORMAL")


#: THE ordered registry. Order is part of the rule set — changing it bumps
#: RULE_SET_VERSION.
CHECKS = (
    _c_price_data_exists,
    _c_price_freshness,
    _c_provider_state,
    _c_ingest_contract,
    _c_enough_data,
    _c_stale_flag,
    _c_action_publishable,
    _c_plan_inputs_valid,
    _c_identity_normalized,
    _c_no_duplicate_open_idea,
    _c_timestamp_coherent,
    _c_evidence_present,
    _c_counter_evidence_present,
    _c_falsifier_present,
    _c_evidence_review_state,
    _c_evidence_provenance,
    _c_payload_wellformed,
    _c_confidence_label_valid,
    _c_wording_consistent,
    _c_no_probability_claim,
    _c_calibration_disclosed,
    _c_prohibited_language,
    _c_beginner_summary_present,
    _c_schema_version_present,
    _c_git_sha_known,
    _c_system_posture,
)


# ---------------------------------------------------------------------------
# Evaluation (pure) + persistence (append-only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreflightResult:
    recommendation_id: str
    verdict: Verdict
    rule_set_version: str
    input_hash: str
    checks: tuple[CheckResult, ...]
    evaluated_at: str
    evaluator_git_sha: str
    source_freshness_at: str | None

    @property
    def limitations(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "limitation"]

    @property
    def blocking(self) -> list[CheckResult]:
        return [c for c in self.checks
                if not c.passed and c.severity in ("hold", "block")]


def evaluate(inp: PreflightInput) -> PreflightResult:
    """Pure deterministic evaluation. No I/O of any kind."""
    results = tuple(check(inp) for check in CHECKS)
    failed = [c for c in results if not c.passed]
    if any(c.severity == "block" for c in failed):
        verdict: Verdict = "BLOCKED"
    elif any(c.severity == "hold" for c in failed):
        verdict = "HOLD"
    elif any(c.severity == "limitation" for c in failed):
        verdict = "READY_WITH_LIMITATIONS"
    else:
        verdict = "READY"
    return PreflightResult(
        recommendation_id=inp.recommendation_id,
        verdict=verdict,
        rule_set_version=RULE_SET_VERSION,
        input_hash=inp.input_hash(),
        checks=results,
        evaluated_at=inp.now,
        evaluator_git_sha=inp.evaluator_git_sha,
        source_freshness_at=inp.latest_bar_ts,
    )


def _check_dict(c: CheckResult) -> dict[str, Any]:
    d = {"check_id": c.check_id, "severity": c.severity,
         "passed": c.passed, "detail": c.detail}
    if c.beginner_text:
        d["beginner_text"] = c.beginner_text
    return d


def run_and_persist(db: Session, rec: Recommendation) -> dict[str, Any]:
    """Load → evaluate → append verdict row (idempotent on identical input).

    Returns the persisted row as a dict. Never updates an existing row; a
    concurrent identical evaluation resolves to the single row created by
    whichever writer won (unique key + ON CONFLICT DO NOTHING).
    """
    inp = load_inputs(db, rec)
    res = evaluate(inp)

    row_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO recommendation_preflight "
            "(id, recommendation_id, verdict, rule_set_version, input_hash, "
            " checks_json, limitations_json, blocking_reasons_json, "
            " evaluated_at, evaluator_git_sha, source_freshness_at, created_at) "
            "VALUES (:id, :rid, :verdict, :rsv, :ih, :checks, :lims, :blocks, "
            "        :eat, :sha, :sfa, now()) "
            "ON CONFLICT (recommendation_id, rule_set_version, input_hash) "
            "DO NOTHING"
        ),
        {
            "id": row_id,
            "rid": res.recommendation_id,
            "verdict": res.verdict,
            "rsv": res.rule_set_version,
            "ih": res.input_hash,
            "checks": json.dumps([_check_dict(c) for c in res.checks]),
            "lims": json.dumps([_check_dict(c) for c in res.limitations]),
            "blocks": json.dumps([_check_dict(c) for c in res.blocking]),
            "eat": res.evaluated_at,
            "sha": res.evaluator_git_sha,
            "sfa": res.source_freshness_at,
        },
    )
    db.commit()
    row = db.execute(
        text(
            "SELECT id, recommendation_id, verdict, rule_set_version, "
            "input_hash, checks_json, limitations_json, blocking_reasons_json, "
            "evaluated_at, evaluator_git_sha, source_freshness_at, created_at "
            "FROM recommendation_preflight "
            "WHERE recommendation_id = :rid AND rule_set_version = :rsv "
            "AND input_hash = :ih"
        ),
        {"rid": res.recommendation_id, "rsv": res.rule_set_version,
         "ih": res.input_hash},
    ).mappings().first()
    return dict(row) if row else {}


def latest_verdict(db: Session, recommendation_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            "SELECT id, recommendation_id, verdict, rule_set_version, "
            "input_hash, checks_json, limitations_json, blocking_reasons_json, "
            "evaluated_at, evaluator_git_sha, source_freshness_at, created_at "
            "FROM recommendation_preflight WHERE recommendation_id = :rid "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"rid": recommendation_id},
    ).mappings().first()
    return dict(row) if row else None


def ensure_current_verdict(db: Session, rec: Recommendation) -> dict[str, Any]:
    """Publication-transaction guarantee: the verdict used to publish matches
    the EXACT current input hash. Re-loads inputs; if the stored latest row's
    hash differs (facts moved), a fresh evaluation is appended and used.
    Fail closed: any exception yields a synthetic HOLD (never published)."""
    try:
        inp = load_inputs(db, rec)
        current_hash = inp.input_hash()
        existing = db.execute(
            text(
                "SELECT id, recommendation_id, verdict, rule_set_version, "
                "input_hash, checks_json, limitations_json, "
                "blocking_reasons_json, evaluated_at, evaluator_git_sha, "
                "source_freshness_at, created_at "
                "FROM recommendation_preflight "
                "WHERE recommendation_id = :rid AND rule_set_version = :rsv "
                "AND input_hash = :ih"
            ),
            {"rid": rec.id, "rsv": RULE_SET_VERSION, "ih": current_hash},
        ).mappings().first()
        if existing:
            return dict(existing)
        res = evaluate(inp)
        # persist via the same idempotent path
        return run_and_persist(db, rec) or {
            "verdict": res.verdict, "input_hash": res.input_hash,
        }
    except Exception:  # noqa: BLE001 — deliberate fail-closed boundary
        db.rollback()
        return {
            "recommendation_id": rec.id,
            "verdict": "HOLD",
            "rule_set_version": RULE_SET_VERSION,
            "input_hash": None,
            "checks_json": json.dumps([{
                "check_id": "evaluator_error", "severity": "hold",
                "passed": False,
                "detail": "preflight evaluation failed — failing closed",
            }]),
            "limitations_json": "[]",
            "blocking_reasons_json": "[]",
            "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "evaluator_git_sha": "unknown",
            "source_freshness_at": None,
            "synthetic": True,
        }
