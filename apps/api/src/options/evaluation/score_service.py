"""Score service (Phase 11H).

Pure read. Walks 11G observations, builds ScoringInputs, runs the
deterministic score model, returns serialised result. Compute-on-read;
NEVER persists.

NEVER imports V2 / equity / governance / paper.engine mutation modules.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.data.liquidity_filter import filter_chain
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.evaluation.score_model import (
    EvaluationScore,
    SCORE_MODEL_VERSION,
    ScoringInputs,
    compute_score,
    serialise,
)
from apps.api.src.options.observatory.observations import (
    DEFAULT_LIST_LIMIT,
    DEFAULT_LOOKBACK_DAYS,
    _decode_observation_id,
    _observation_id,
)
from apps.api.src.options.observatory.rules import evaluate_rules
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)
from apps.api.src.options.service_readonly import get_latest_features


def _row_to_quote(r) -> OptionChainQuote:
    return OptionChainQuote(
        snapshot_at_utc=r.snapshot_at_utc,
        underlying=r.underlying,
        expiry=r.expiry,
        strike=r.strike,
        option_type=r.option_type,
        option_symbol=r.option_symbol,
        bid=r.bid, ask=r.ask, mid=r.mid, last=r.last,
        volume=r.volume, open_interest=r.open_interest,
        delta=r.delta, gamma=r.gamma,
        theta=r.theta, vega=r.vega, iv=r.iv,
        quote_age_seconds=r.quote_age_seconds,
        provider=r.provider, provider_version=r.provider_version,
    )


def _read_day(
    session: Session, *, symbol: str, day: datetime.date,
) -> list[OptionChainQuote]:
    rows = session.execute(text(
        """
        SELECT DISTINCT ON
           (underlying, expiry, strike, option_type)
           snapshot_at_utc, underlying, expiry, strike, option_type,
           option_symbol, bid, ask, mid, last,
           volume, open_interest,
           delta, gamma, theta, vega, iv,
           quote_age_seconds, provider, provider_version
        FROM options_chain_snapshot
        WHERE underlying = :symbol
          AND snapshot_at_utc::date = :day
        ORDER BY underlying, expiry, strike, option_type,
                 snapshot_at_utc DESC
        """
    ), {"symbol": symbol, "day": day}).all()
    return [_row_to_quote(r) for r in rows]


def _per_day_flags(
    session: Session, *, symbol: str, day: datetime.date,
) -> list[str]:
    """Surface engine flags scoped to (symbol, day) — assignment events,
    pin-risk + missing-settlement classifications on expirations, plus
    feature-row data-quality flags."""
    flags: list[str] = []

    n_assignments = session.execute(text(
        """
        SELECT COUNT(*)
        FROM options_assignment_event a
        JOIN options_paper_trade t ON t.id = a.trade_id
        WHERE t.underlying = :s
          AND a.event_at_utc::date = :d
        """
    ), {"s": symbol, "d": day}).scalar_one()
    if n_assignments and n_assignments > 0:
        flags.append(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT)

    pin_count = session.execute(text(
        """
        SELECT COUNT(*)
        FROM options_expiration_event e
        JOIN options_paper_trade t ON t.id = e.trade_id
        WHERE t.underlying = :s
          AND e.event_at_utc::date = :d
          AND e.classification = 'PIN_RISK'
        """
    ), {"s": symbol, "d": day}).scalar_one()
    if pin_count and pin_count > 0:
        flags.append(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)

    missing_count = session.execute(text(
        """
        SELECT COUNT(*)
        FROM options_expiration_event e
        JOIN options_paper_trade t ON t.id = e.trade_id
        WHERE t.underlying = :s
          AND e.event_at_utc::date = :d
          AND e.classification = 'MISSING_DATA'
        """
    ), {"s": symbol, "d": day}).scalar_one()
    if missing_count and missing_count > 0:
        flags.append(FLAG_MISSING_SETTLEMENT)

    return flags


def _score_one(
    session: Session, *, symbol: str, day: datetime.date, rule_id: str,
) -> EvaluationScore | None:
    quotes = _read_day(session, symbol=symbol, day=day)
    if not quotes:
        return None
    accepted = list(filter_chain(quotes).accepted)
    evals = evaluate_rules(accepted, as_of=day)
    selected = next((e for e in evals if e.rule_id == rule_id), None)
    if selected is None:
        return None
    feature = get_latest_features(session, symbol=symbol)
    flags = _per_day_flags(session, symbol=symbol, day=day)
    inputs = ScoringInputs(
        rule_id=rule_id,
        underlying=symbol,
        as_of_date=day,
        qualified=selected.qualified,
        candidate=selected.candidate,
        accepted_quotes=tuple(accepted),
        feature_row=feature,
        flags=tuple(flags),
    )
    return compute_score(inputs)


# ---------------------------------------------------------------------------
# Public service entry points
# ---------------------------------------------------------------------------

def list_scores(
    session: Session,
    *,
    underlying: str | None = None,
    strategy: str | None = None,
    qualified_only: bool = False,
    min_score: int | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = DEFAULT_LIST_LIMIT,
) -> dict[str, Any]:
    cutoff = datetime.date.today() - datetime.timedelta(days=int(lookback_days))
    where = ["snapshot_at_utc::date >= :cutoff"]
    params: dict[str, Any] = {"cutoff": cutoff}
    if underlying is not None:
        where.append("underlying = :underlying")
        params["underlying"] = underlying
    where_sql = " AND ".join(where)

    pairs = session.execute(text(
        f"""
        SELECT DISTINCT underlying, snapshot_at_utc::date AS d
        FROM options_chain_snapshot
        WHERE {where_sql}
        ORDER BY underlying, d DESC
        """
    ), params).all()

    out: list[dict[str, Any]] = []
    excluded = 0
    for p in pairs:
        if len(out) >= limit:
            break
        quotes = _read_day(session, symbol=p.underlying, day=p.d)
        if not quotes:
            continue
        accepted = list(filter_chain(quotes).accepted)
        evals = evaluate_rules(accepted, as_of=p.d)
        feature = get_latest_features(session, symbol=p.underlying)
        flags = _per_day_flags(session, symbol=p.underlying, day=p.d)
        for ev in evals:
            if strategy is not None and ev.rule_id != strategy:
                continue
            if qualified_only and not ev.qualified:
                excluded += 1
                continue
            inputs = ScoringInputs(
                rule_id=ev.rule_id,
                underlying=p.underlying,
                as_of_date=p.d,
                qualified=ev.qualified,
                candidate=ev.candidate,
                accepted_quotes=tuple(accepted),
                feature_row=feature,
                flags=tuple(flags),
            )
            sc = compute_score(inputs)
            if min_score is not None and sc.total_score < min_score:
                excluded += 1
                continue
            obs_id = _observation_id(p.underlying, p.d, ev.rule_id)
            row = serialise(sc)
            row["id"] = obs_id
            out.append(row)
            if len(out) >= limit:
                break

    return {
        "count": len(out),
        "excluded_count": excluded,
        "scores": out,
        "model_version": SCORE_MODEL_VERSION,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
        "evaluation_disclaimer":
            "Evaluation scores are fixed rule-based paper analytics. "
            "They are not trade recommendations.",
    }


def get_score_detail(
    session: Session, *, observation_id: str,
) -> dict[str, Any] | None:
    decoded = _decode_observation_id(observation_id)
    if decoded is None:
        return None
    sym, day, rule_id = decoded
    sc = _score_one(session, symbol=sym, day=day, rule_id=rule_id)
    if sc is None:
        return None
    out = serialise(sc)
    out["id"] = observation_id
    out["observation_only_notice"] = (
        "Observation only — not investment advice or execution guidance"
    )
    out["evaluation_disclaimer"] = (
        "Evaluation scores are fixed rule-based paper analytics. "
        "They are not trade recommendations."
    )
    return out


# Frozen bucket edges for distribution + threshold diagnostics
SCORE_BUCKETS: tuple[tuple[int, int], ...] = (
    (0, 19), (20, 39), (40, 59), (60, 79), (80, 100),
)
THRESHOLD = 60


def get_summary(
    session: Session,
    *,
    underlying: str | None = None,
    strategy: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Aggregate score counts, mean/median, distribution buckets."""
    listing = list_scores(
        session, underlying=underlying, strategy=strategy,
        lookback_days=lookback_days, limit=10_000,
    )
    scores = [s["total_score"] for s in listing["scores"]]
    n = len(scores)
    avg = sum(scores) / n if n else None
    sorted_s = sorted(scores)
    median = (
        sorted_s[n // 2] if n % 2 == 1
        else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2 if n
        else None
    )
    buckets = []
    for lo, hi in SCORE_BUCKETS:
        c = sum(1 for s in scores if lo <= s <= hi)
        buckets.append({"lo": lo, "hi": hi, "count": int(c)})

    n_above = sum(1 for s in scores if s >= THRESHOLD)
    n_below = n - n_above

    return {
        "n_observations_scored": n,
        "n_included_by_filter": n,
        "n_excluded_by_filter": int(listing["excluded_count"]),
        "average_score": (str(round(avg, 2)) if avg is not None else None),
        "median_score": (str(round(median, 2)) if median is not None else None),
        "score_distribution_buckets": buckets,
        "threshold": THRESHOLD,
        "n_at_or_above_threshold": int(n_above),
        "n_below_threshold": int(n_below),
        "model_version": SCORE_MODEL_VERSION,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
        "evaluation_disclaimer":
            "Evaluation scores are fixed rule-based paper analytics. "
            "They are not trade recommendations.",
    }


def get_distribution(
    session: Session,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Score buckets broken down by strategy + underlying."""
    listing = list_scores(
        session, lookback_days=lookback_days, limit=10_000,
    )
    by_strategy: dict[str, list[int]] = {}
    by_underlying: dict[str, list[int]] = {}
    for s in listing["scores"]:
        by_strategy.setdefault(s["rule_id"], []).append(s["total_score"])
        by_underlying.setdefault(s["underlying"], []).append(s["total_score"])

    def _bucketise(arr: list[int]) -> list[dict]:
        return [
            {"lo": lo, "hi": hi,
             "count": int(sum(1 for s in arr if lo <= s <= hi))}
            for lo, hi in SCORE_BUCKETS
        ]

    return {
        "by_strategy": [
            {"strategy": k, "n": len(v),
             "mean_score": (str(round(sum(v)/len(v), 2)) if v else None),
             "buckets": _bucketise(v)}
            for k, v in sorted(by_strategy.items())
        ],
        "by_underlying": [
            {"underlying": k, "n": len(v),
             "mean_score": (str(round(sum(v)/len(v), 2)) if v else None),
             "buckets": _bucketise(v)}
            for k, v in sorted(by_underlying.items())
        ],
        "buckets_definition": [
            {"lo": lo, "hi": hi} for lo, hi in SCORE_BUCKETS
        ],
        "model_version": SCORE_MODEL_VERSION,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
        "evaluation_disclaimer":
            "Evaluation scores are fixed rule-based paper analytics. "
            "They are not trade recommendations.",
    }


def get_diagnostics(
    session: Session,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """Common penalty drivers + missing-data drivers + threshold counts."""
    listing = list_scores(
        session, lookback_days=lookback_days, limit=10_000,
    )
    penalty_counter: dict[str, int] = {}
    missing_counter: dict[str, int] = {}
    n_above = 0
    n_below = 0
    for s in listing["scores"]:
        for p in s["penalties"]:
            penalty_counter[p["code"]] = penalty_counter.get(p["code"], 0) + 1
        for f in s["flags"]:
            missing_counter[f] = missing_counter.get(f, 0) + 1
        if s["total_score"] >= THRESHOLD:
            n_above += 1
        else:
            n_below += 1

    common_penalties = sorted(
        ({"code": k, "count": v} for k, v in penalty_counter.items()),
        key=lambda r: -r["count"],
    )
    common_missing = sorted(
        ({"code": k, "count": v} for k, v in missing_counter.items()),
        key=lambda r: -r["count"],
    )

    return {
        "n_total_scored": len(listing["scores"]),
        "threshold": THRESHOLD,
        "n_at_or_above_threshold": int(n_above),
        "n_below_threshold": int(n_below),
        "common_penalty_drivers": common_penalties,
        "common_missing_data_drivers": common_missing,
        "model_version": SCORE_MODEL_VERSION,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
        "evaluation_disclaimer":
            "Evaluation scores are fixed rule-based paper analytics. "
            "They are not trade recommendations.",
    }
