"""Phase 11O - Manual options paper evaluation runner.

Pure orchestrator. Walks today's chain snapshots -> evaluates the
frozen 11G rule registry -> builds PlannedTrade records -> optionally
calls paper.engine.open_trade when run in commit mode.

Defaults to DRY-RUN. Mutation requires explicit commit + an external
confirm gate enforced by the CLI layer.

NEVER imports broker / live / execution modules. NEVER touches the
worker job registry. NEVER imports V2 / equity / governance modules.
NEVER calls an LLM. NEVER produces ranking or "best" output.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings as default_settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data.chain_ingest import ingest_universe
from apps.api.src.options.data.liquidity_filter import filter_chain
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.observatory.observations import (
    _observation_id,
    _read_day,
)
from apps.api.src.options.observatory.rules import (
    RuleEvaluation,
    evaluate_rules,
)
from apps.api.src.options.paper.engine import TradeRequest, open_trade
from apps.api.src.options.paper.eval_runner_models import (
    PlannedTrade,
    RunnerConfig,
    RunnerSummary,
)
from apps.api.src.options.paper.strategies import (
    LegSpec,
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
    compute_risk,
    net_credit_dollars,
    validate_defined_risk,
)


STRATEGY_VERSION = "v1.0"
JSONL_LOG_DIR = Path("logs")
JSONL_LOG_PREFIX = "options_paper_eval_"


# Frozen REGISTRY snapshot. Drift detector. Adding any options-related
# job to apps.worker.src.jobs.registry.REGISTRY would auto-fail this.
FROZEN_REGISTRY_KEYS: frozenset[str] = frozenset({
    "ingest_prices_daily",
    "backfill_prices",
    "tiingo_backfill_eod",
    "compute_regime_snapshot",
    "compute_factor_snapshots",
    "generate_stock_candidates",
    "run_weekly_rebalance",
    "fetch_news",
    "run_recommendations_for_all_accounts",
    "score_recommendation_outcomes",
    "run_paper_trading",
    "run_daily_pipeline",
    "v2_promotion_snapshot",
})


# Forbidden import-name patterns. Runner refuses to operate when any
# loaded sys.modules key matches one of these. Patterns are anchored
# to the *top-level* package name to avoid false positives on third-
# party UI libraries (e.g. `rich.live_render`) that happen to contain
# the substring "live_" deeper in the dotted path.
FORBIDDEN_MODULE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"^live_"),
    re.compile(r"^broker_"),
    re.compile(r"^execution_"),
    re.compile(r"^order_router($|\.)"),
)


# ---------------------------------------------------------------------------
# Errors (mapped to CLI exit codes)
# ---------------------------------------------------------------------------

class EvalRunnerSafetyError(RuntimeError):
    """Safety invariant failed. CLI exit 2."""


class EvalRunnerIngestError(RuntimeError):
    """Chain ingest failed. CLI exit 3."""


class EvalRunnerNoQualifiedError(RuntimeError):
    """No qualified observations. CLI exit 4."""


class EvalRunnerCommitError(RuntimeError):
    """open_trade rejected during commit. CLI exit 5."""


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def assert_safety_invariants(settings_obj=None) -> None:
    """Reject the run if any kill-switch or import invariant is wrong."""
    s = settings_obj if settings_obj is not None else default_settings
    if not getattr(s, "OPTIONS_ENABLED", False):
        raise EvalRunnerSafetyError(
            "OPTIONS_ENABLED must be True before running the evaluator"
        )
    if not getattr(s, "OPTIONS_PAPER_ONLY", False):
        raise EvalRunnerSafetyError(
            "OPTIONS_PAPER_ONLY must be True (permanent v1 invariant)"
        )
    if getattr(s, "OPTIONS_ML_CAN_AFFECT_TRADES", False):
        raise EvalRunnerSafetyError(
            "OPTIONS_ML_CAN_AFFECT_TRADES must be False"
        )
    bad = [
        name for name in list(sys.modules.keys())
        if any(p.search(name) for p in FORBIDDEN_MODULE_PATTERNS)
    ]
    if bad:
        raise EvalRunnerSafetyError(
            f"forbidden module(s) loaded: {bad}"
        )


def assert_no_scheduler_drift() -> None:
    """Re-import REGISTRY and assert it matches the frozen snapshot.

    Refuses to operate if anyone added an options job — runner is
    manual only. Refuses if any key was removed too (drift in either
    direction is a signal that this snapshot is stale and should be
    reviewed).
    """
    from apps.worker.src.jobs.registry import REGISTRY
    actual = frozenset(REGISTRY.keys())
    if actual != FROZEN_REGISTRY_KEYS:
        added = sorted(actual - FROZEN_REGISTRY_KEYS)
        removed = sorted(FROZEN_REGISTRY_KEYS - actual)
        raise EvalRunnerSafetyError(
            "REGISTRY drift detected. "
            f"added={added} removed={removed}"
        )
    options_jobs = sorted(k for k in actual if "options" in k.lower())
    if options_jobs:
        raise EvalRunnerSafetyError(
            f"REGISTRY contains options job(s) {options_jobs}; "
            "this runner is manual-only"
        )


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_ingest_chain(
    *,
    snapshot_at_utc: datetime.datetime,
    universe: Sequence[str],
) -> int:
    """Append-only chain snapshot ingest (idempotent via ON CONFLICT).
    Returns total rows inserted across the universe."""
    try:
        summaries = ingest_universe(
            universe=tuple(universe),
            snapshot_at_utc=snapshot_at_utc,
        )
    except Exception as exc:  # noqa: BLE001
        raise EvalRunnerIngestError(f"chain ingest failed: {exc}") from exc
    return sum(s.n_inserted for s in summaries)


def _quotes_by_symbol(
    quotes: Iterable[OptionChainQuote],
) -> dict[str, OptionChainQuote]:
    return {q.option_symbol: q for q in quotes}


def step_collect_qualified(
    session: Session,
    *,
    date: datetime.date,
    underlyings: Sequence[str],
    strategy_filter: Sequence[str] | None = None,
) -> tuple[int, list[tuple[str, RuleEvaluation, list[OptionChainQuote]]]]:
    """For each (underlying, day) pair walk the chain, run the frozen
    rule evaluator, return (n_total_evaluations, qualified_triples).

    `qualified_triples` is a list of (underlying, RuleEvaluation,
    accepted_quotes) tuples for evaluations where `qualified is True`.
    """
    total = 0
    qualified: list[tuple[str, RuleEvaluation, list[OptionChainQuote]]] = []
    for sym in underlyings:
        quotes = _read_day(session, symbol=sym, day=date)
        if not quotes:
            continue
        accepted = list(filter_chain(quotes).accepted)
        if not accepted:
            continue
        evals = evaluate_rules(accepted, as_of=date)
        for ev in evals:
            if (strategy_filter is not None
                    and ev.rule_id not in tuple(strategy_filter)):
                continue
            total += 1
            if not ev.qualified:
                continue
            qualified.append((sym, ev, accepted))
    return total, qualified


def _legs_from_credit_spread(
    *,
    candidate: dict,
    side: str,
    qty: int = 1,
) -> tuple[LegSpec, ...]:
    expiry = datetime.date.fromisoformat(candidate["expiry"])
    return (
        LegSpec(
            side="SELL", option_type=side,
            strike=Decimal(candidate["short_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=candidate["short_symbol"],
        ),
        LegSpec(
            side="BUY", option_type=side,
            strike=Decimal(candidate["long_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=candidate["long_symbol"],
        ),
    )


def _legs_from_iron_condor(
    *,
    candidate: dict,
    qty: int = 1,
) -> tuple[LegSpec, ...]:
    put = candidate["put_wing"]
    call = candidate["call_wing"]
    expiry = datetime.date.fromisoformat(put["expiry"])
    return (
        LegSpec(
            side="BUY", option_type="PUT",
            strike=Decimal(put["long_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=put["long_symbol"],
        ),
        LegSpec(
            side="SELL", option_type="PUT",
            strike=Decimal(put["short_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=put["short_symbol"],
        ),
        LegSpec(
            side="SELL", option_type="CALL",
            strike=Decimal(call["short_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=call["short_symbol"],
        ),
        LegSpec(
            side="BUY", option_type="CALL",
            strike=Decimal(call["long_strike"]),
            expiry=expiry, qty=qty,
            option_symbol=call["long_symbol"],
        ),
    )


def step_plan_trade(
    *,
    underlying: str,
    rule_eval: RuleEvaluation,
    accepted_quotes: Sequence[OptionChainQuote],
    as_of_date: datetime.date,
) -> PlannedTrade:
    """Build a PlannedTrade from a qualified RuleEvaluation. On any
    structural failure (missing candidate, missing quote, defined-risk
    rejection, missing mid) returns a non-committable PlannedTrade with
    populated `rejection_reasons`."""
    obs_id = _observation_id(underlying, as_of_date, rule_eval.rule_id)
    candidate = rule_eval.candidate

    if candidate is None:
        return PlannedTrade(
            observation_id=obs_id, underlying=underlying,
            rule_id=rule_eval.rule_id, legs=(),
            risk=None, entry_credit_dollars=None,
            quote_age_max_seconds=None,
            rejection_reasons=("CANDIDATE_MISSING",),
            qualified=rule_eval.qualified,
        )

    if rule_eval.rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD:
        legs = _legs_from_credit_spread(candidate=candidate, side="PUT")
    elif rule_eval.rule_id == STRATEGY_SHORT_CALL_CREDIT_SPREAD:
        legs = _legs_from_credit_spread(candidate=candidate, side="CALL")
    elif rule_eval.rule_id == STRATEGY_IRON_CONDOR:
        legs = _legs_from_iron_condor(candidate=candidate)
    else:
        return PlannedTrade(
            observation_id=obs_id, underlying=underlying,
            rule_id=rule_eval.rule_id, legs=(),
            risk=None, entry_credit_dollars=None,
            quote_age_max_seconds=None,
            rejection_reasons=(f"UNKNOWN_RULE:{rule_eval.rule_id}",),
            qualified=rule_eval.qualified,
        )

    qmap = _quotes_by_symbol(accepted_quotes)
    missing = [
        leg.option_symbol for leg in legs
        if leg.option_symbol not in qmap
    ]
    if missing:
        return PlannedTrade(
            observation_id=obs_id, underlying=underlying,
            rule_id=rule_eval.rule_id, legs=tuple(legs),
            risk=None, entry_credit_dollars=None,
            quote_age_max_seconds=None,
            rejection_reasons=tuple(
                f"QUOTE_MISSING:{sym}" for sym in missing
            ),
            qualified=rule_eval.qualified,
        )

    try:
        validate_defined_risk(rule_eval.rule_id, legs)
    except ValueError as exc:
        return PlannedTrade(
            observation_id=obs_id, underlying=underlying,
            rule_id=rule_eval.rule_id, legs=tuple(legs),
            risk=None, entry_credit_dollars=None,
            quote_age_max_seconds=None,
            rejection_reasons=(f"NOT_DEFINED_RISK:{exc}",),
            qualified=rule_eval.qualified,
        )

    mids: list[Decimal] = []
    for leg in legs:
        q = qmap[leg.option_symbol]
        if q.mid is None:
            return PlannedTrade(
                observation_id=obs_id, underlying=underlying,
                rule_id=rule_eval.rule_id, legs=tuple(legs),
                risk=None, entry_credit_dollars=None,
                quote_age_max_seconds=None,
                rejection_reasons=(f"MID_MISSING:{leg.option_symbol}",),
                qualified=rule_eval.qualified,
            )
        mids.append(q.mid)

    risk = compute_risk(rule_eval.rule_id, legs, mids)
    credit = net_credit_dollars(legs, mids)
    qage = max(qmap[leg.option_symbol].quote_age_seconds for leg in legs)

    return PlannedTrade(
        observation_id=obs_id, underlying=underlying,
        rule_id=rule_eval.rule_id, legs=tuple(legs),
        risk=risk, entry_credit_dollars=credit,
        quote_age_max_seconds=qage,
        rejection_reasons=(), qualified=True,
    )


def step_dedupe_open(
    session: Session,
    planned: Sequence[PlannedTrade],
    *,
    date: datetime.date,
) -> tuple[list[PlannedTrade], int]:
    """Drop planned trades that match an already-open paper trade for
    the same (underlying, rule_id, opened_at::date)."""
    if not planned:
        return [], 0
    existing = session.execute(text(
        """
        SELECT underlying, strategy_name
        FROM options_paper_trade
        WHERE opened_at::date = :d
          AND status IN ('OPEN', 'EXPIRING')
          AND paper_only = TRUE
        """
    ), {"d": date}).all()
    existing_set = {(r.underlying, r.strategy_name) for r in existing}
    kept: list[PlannedTrade] = []
    dropped = 0
    for p in planned:
        key = (p.underlying, p.rule_id)
        if key in existing_set:
            dropped += 1
            continue
        kept.append(p)
    return kept, dropped


def step_apply_max_open(
    planned: Sequence[PlannedTrade],
    *,
    cap: int,
) -> list[PlannedTrade]:
    """Stable lexicographic truncation. NEVER ranked, NEVER labeled
    "best" / "top"."""
    sorted_p = sorted(planned, key=lambda p: (p.underlying, p.rule_id))
    return list(sorted_p[: max(0, cap)])


def step_commit_trades(
    planned: Sequence[PlannedTrade],
    *,
    accepted_quotes_by_obs: dict[str, list[OptionChainQuote]],
    session_factory=SessionLocal,
) -> list[int]:
    """Open a paper trade per planned entry. Halts on first rejection.

    NEVER calls a broker. Always uses paper.engine.open_trade which
    enforces the OPTIONS_PAPER_ONLY kill switch internally.
    """
    trade_ids: list[int] = []
    for p in planned:
        qmap = _quotes_by_symbol(
            accepted_quotes_by_obs.get(p.observation_id, [])
        )
        req = TradeRequest(
            underlying=p.underlying,
            strategy_name=p.rule_id,
            strategy_version=STRATEGY_VERSION,
            legs=p.legs,
            quotes_by_symbol=qmap,
            rationale_note=f"phase 11O manual eval - {p.observation_id}",
        )
        res = open_trade(req, session_factory=session_factory)
        if not res.accepted or res.trade_id is None:
            raise EvalRunnerCommitError(
                f"open_trade rejected for {p.observation_id}: "
                f"{res.rejected_reasons}"
            )
        trade_ids.append(int(res.trade_id))
    return trade_ids


# ---------------------------------------------------------------------------
# Audit log (commit-only)
# ---------------------------------------------------------------------------

def _audit_log_path(
    date: datetime.date,
    *,
    log_dir: Path = JSONL_LOG_DIR,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{JSONL_LOG_PREFIX}{date.isoformat()}.jsonl"


def _serialise_planned(p: PlannedTrade) -> dict:
    return {
        "observation_id": p.observation_id,
        "underlying": p.underlying,
        "rule_id": p.rule_id,
        "qualified": p.qualified,
        "rejection_reasons": list(p.rejection_reasons),
        "legs": [
            {
                "side": leg.side,
                "option_type": leg.option_type,
                "strike": str(leg.strike),
                "expiry": leg.expiry.isoformat(),
                "qty": leg.qty,
                "option_symbol": leg.option_symbol,
            }
            for leg in p.legs
        ],
        "max_loss_dollars": (
            str(p.risk.max_loss_dollars) if p.risk else None
        ),
        "max_profit_dollars": (
            str(p.risk.max_profit_dollars) if p.risk else None
        ),
        "entry_credit_dollars": (
            str(p.entry_credit_dollars)
            if p.entry_credit_dollars is not None else None
        ),
        "quote_age_max_seconds": p.quote_age_max_seconds,
    }


def write_audit_log(
    summary: RunnerSummary,
    *,
    log_dir: Path = JSONL_LOG_DIR,
) -> Path:
    """Append one summary line + one filled-paper-trade line per
    committed trade. ONLY callable for commit runs."""
    if not summary.config.commit:
        raise RuntimeError("audit log is for commit runs only")
    path = _audit_log_path(summary.config.date, log_dir=log_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "summary",
            "date": summary.config.date.isoformat(),
            "n_planned": summary.n_planned,
            "n_committed": summary.n_committed,
            "n_dedup": summary.n_existing_open_trade_dedup,
            "max_open": summary.config.max_open,
        }) + "\n")
        for p, tid in zip(
            summary.planned_trades, summary.committed_trade_ids,
        ):
            row = {"kind": "filled_paper_trade", "trade_id": tid}
            row.update(_serialise_planned(p))
            f.write(json.dumps(row, default=str) + "\n")
    return path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(
    config: RunnerConfig,
    *,
    settings_obj=None,
    session_factory=SessionLocal,
    now_utc: datetime.datetime | None = None,
    audit_log_dir: Path | None = None,
) -> RunnerSummary:
    """Entry point. Pure over (config, db, settings). Mutates DB only
    when config.commit is True; mutates filesystem audit log only on
    commit.
    """
    assert_safety_invariants(settings_obj)
    assert_no_scheduler_drift()

    snap_at = now_utc or datetime.datetime.now(datetime.timezone.utc)

    n_inserted = 0
    if not config.skip_ingest:
        n_inserted = step_ingest_chain(
            snapshot_at_utc=snap_at,
            universe=config.underlyings,
        )

    with session_factory() as session:
        n_total, qualified_triples = step_collect_qualified(
            session,
            date=config.date,
            underlyings=config.underlyings,
            strategy_filter=config.strategy_filter,
        )
        n_qualified = len(qualified_triples)
        if n_qualified == 0:
            return RunnerSummary(
                config=config,
                n_chain_inserted=n_inserted,
                n_observations_total=n_total,
                n_qualified=0,
                n_planned=0,
                n_planned_rejected=0,
                n_existing_open_trade_dedup=0,
                n_committed=0,
                planned_trades=(),
                committed_trade_ids=(),
            )

        accepted_by_obs: dict[str, list[OptionChainQuote]] = {}
        planned_all: list[PlannedTrade] = []
        for sym, ev, accepted in qualified_triples:
            p = step_plan_trade(
                underlying=sym, rule_eval=ev,
                accepted_quotes=accepted, as_of_date=config.date,
            )
            planned_all.append(p)
            accepted_by_obs[p.observation_id] = list(accepted)

        committable = [p for p in planned_all if p.committable]
        rejected = [p for p in planned_all if not p.committable]

        deduped, n_dedup = step_dedupe_open(
            session, committable, date=config.date,
        )
        capped = step_apply_max_open(deduped, cap=config.max_open)

        committed_ids: list[int] = []
        if config.commit:
            committed_ids = step_commit_trades(
                capped,
                accepted_quotes_by_obs=accepted_by_obs,
                session_factory=session_factory,
            )

    summary = RunnerSummary(
        config=config,
        n_chain_inserted=n_inserted,
        n_observations_total=n_total,
        n_qualified=n_qualified,
        n_planned=len(capped),
        n_planned_rejected=len(rejected),
        n_existing_open_trade_dedup=n_dedup,
        n_committed=len(committed_ids),
        planned_trades=tuple(capped),
        committed_trade_ids=tuple(committed_ids),
    )

    if config.commit:
        write_audit_log(
            summary,
            log_dir=(audit_log_dir or JSONL_LOG_DIR),
        )

    logger.info(
        "phase 11O eval complete: dry_run={} qualified={} planned={} "
        "rejected={} dedup={} committed={}",
        config.dry_run, summary.n_qualified, summary.n_planned,
        summary.n_planned_rejected, summary.n_existing_open_trade_dedup,
        summary.n_committed,
    )
    return summary
