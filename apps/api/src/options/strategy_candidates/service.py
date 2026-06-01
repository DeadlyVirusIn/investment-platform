"""Phase B6.2 — strategy_candidate persistence + batch generation.

Glue between `generator.generate()` and the DB. Idempotent upsert
on (shadow_observation_id, rule_id) via the migration's unique
constraint.

Read-only on shadow_decision_log, options_chain_snapshot,
options_feature_daily. Write-only on options_strategy_candidate.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.options.strategy_candidates.event_proximity import (
    earliest_event_in_window,
)
from apps.api.src.options.strategy_candidates.generator import (
    ChainQuote, ShadowObservation, StrategyCandidate, UnderlyingFeature,
    build_iron_condor, generate,
)


def _action_to_bias(action: str | None) -> str:
    """Map a recommendation.action → directional bias. buy*→bullish,
    sell*→bearish, everything else (hold/none)→neutral."""
    a = (action or "").lower()
    if "buy" in a:
        return "bullish"
    if "sell" in a:
        return "bearish"
    return "neutral"


def _bias_by_underlying(
    session: Session, symbols: Iterable[str],
) -> dict[str, str]:
    """Latest recommendation action → bias per underlying symbol (Opt-B,
    decision 3 — bias comes from the recommendation signal, never inferred
    from contract type). Underlyings with NO recommendation are absent
    from the result; callers treat absence as 'neutral, no signal'."""
    syms = sorted({s for s in symbols if s})
    if not syms:
        return {}
    rows = session.execute(text(
        """
        SELECT a.symbol AS symbol, r.action AS action
        FROM asset a
        JOIN LATERAL (
            SELECT action FROM recommendation r2
            WHERE r2.asset_id = a.id
            ORDER BY r2.generated_at DESC LIMIT 1
        ) r ON TRUE
        WHERE a.symbol = ANY(:syms)
        """
    ), {"syms": syms}).mappings().all()
    return {row["symbol"]: _action_to_bias(row["action"]) for row in rows}


_INSERT_SQL = text(
    """
    INSERT INTO options_strategy_candidate
      (shadow_observation_id, run_date, underlying, rule_id,
       bias, directional_view, risk_profile,
       confidence, iv_suitability, expiry_suitability,
       liquidity_suitability, composite_score,
       why_emitted, triggering_rule,
       rejected_alternatives,
       strategy_fit_reason, iv_fit_reason,
       dte_fit_reason, liquidity_fit_reason,
       diagnostics,
       earliest_event_date, earliest_event_type,
       earliest_event_importance, event_days_away)
    VALUES
      (:shadow_obs, :run_date, :underlying, :rule_id,
       :bias, :directional_view, :risk_profile,
       :confidence, :iv_suit, :expiry_suit,
       :liq_suit, :composite,
       :why_emitted, :triggering_rule,
       CAST(:rejected AS jsonb),
       :strategy_fit, :iv_fit,
       :dte_fit, :liq_fit,
       CAST(:diagnostics AS jsonb),
       :event_date, :event_type,
       :event_importance, :event_days_away)
    ON CONFLICT ON CONSTRAINT ux_strategy_candidate_observation_rule
      DO NOTHING
    RETURNING id
    """
)


def _row_to_observation(row: dict) -> ShadowObservation:
    return ShadowObservation(
        observation_id=int(row["id"]),
        run_date=row["run_date"],
        underlying=str(row["underlying_symbol"]),
        option_symbol=str(row["option_symbol"]),
        expiration=row["expiration"],
        strike=float(row["strike"]),
        option_type=str(row["option_type"]),
        side=str(row["side"]),
        would_trade=bool(row["would_trade"]),
        liquidity_pass=bool(row["liquidity_pass"]),
        spread_pass=bool(row["spread_pass"]),
        open_interest_pass=bool(row["open_interest_pass"]),
        volume_pass=bool(row["volume_pass"]),
        greeks_pass=bool(row["greeks_pass"]),
        iv_rank_pass=bool(row["iv_rank_pass"]),
        risk_pass=bool(row["risk_pass"]),
        score=float(row["score"]) if row["score"] is not None else None,
        diagnostics=row["diagnostics"] or {},
    )


def _persist_one(
    session: Session, obs: ShadowObservation,
    candidate: StrategyCandidate,
) -> bool:
    """Insert one candidate. Returns True on new row, False on conflict."""
    res = session.execute(_INSERT_SQL, {
        "shadow_obs":      obs.observation_id,
        "run_date":        obs.run_date,
        "underlying":      obs.underlying,
        "rule_id":         candidate.rule_id,
        "bias":            candidate.bias,
        "directional_view": candidate.directional_view,
        "risk_profile":    candidate.risk_profile,
        "confidence":      round(candidate.confidence, 4),
        "iv_suit":         round(candidate.iv_suitability, 4),
        "expiry_suit":     round(candidate.expiry_suitability, 4),
        "liq_suit":        round(candidate.liquidity_suitability, 4),
        "composite":       round(candidate.composite_score, 4),
        "why_emitted":     candidate.why_emitted,
        "triggering_rule": candidate.triggering_rule,
        "rejected":        json.dumps(candidate.rejected_alternatives),
        "strategy_fit":    candidate.strategy_fit_reason,
        "iv_fit":          candidate.iv_fit_reason,
        "dte_fit":         candidate.dte_fit_reason,
        "liq_fit":         candidate.liquidity_fit_reason,
        "diagnostics":     json.dumps(candidate.diagnostics, default=str),
        "event_date":      candidate.earliest_event_date,
        "event_type":      candidate.earliest_event_type,
        "event_importance": candidate.earliest_event_importance,
        "event_days_away": candidate.event_days_away,
    })
    return res.first() is not None


def generate_for_observations(
    session: Session,
    observation_ids: Iterable[int] | None = None,
    *,
    run_date: dt.date | None = None,
    skip_existing: bool = True,
) -> dict[str, int]:
    """Generate candidates for one or more shadow observations.

    `observation_ids` filters to specific rows; when None, every
    accepted observation with `would_trade=True` on `run_date` is
    processed (or across all dates if `run_date` also None).

    Returns counts: {processed, candidates_generated, inserted, skipped}.
    """
    where_clauses: list[str] = ["s.would_trade = TRUE"]
    params: dict = {}
    if observation_ids is not None:
        where_clauses.append("s.id = ANY(:obs_ids)")
        params["obs_ids"] = list(observation_ids)
    if run_date is not None:
        where_clauses.append("s.run_date = :run_date")
        params["run_date"] = run_date
    where_sql = " AND ".join(where_clauses)

    # Pull shadow rows + their latest chain snapshot + the underlying's
    # latest feature row.
    rows = session.execute(text(f"""
        SELECT
          s.id, s.run_date, s.underlying_symbol, s.option_symbol,
          s.expiration, s.strike, s.option_type, s.side,
          s.would_trade,
          s.liquidity_pass, s.spread_pass, s.open_interest_pass,
          s.volume_pass, s.greeks_pass, s.iv_rank_pass, s.risk_pass,
          s.score, s.diagnostics,
          c.bid, c.ask, c.mid, c.delta, c.gamma, c.theta, c.vega,
          c.iv AS chain_iv, c.open_interest, c.volume,
          f.iv_rank_252d, f.atm_iv, f.realized_vol_30d
        FROM options_shadow_decision_log s
        LEFT JOIN LATERAL (
          SELECT bid, ask, mid, delta, gamma, theta, vega, iv,
                 open_interest, volume
          FROM options_chain_snapshot
          WHERE option_symbol = s.option_symbol
          ORDER BY snapshot_at_utc DESC LIMIT 1
        ) c ON TRUE
        LEFT JOIN options_feature_daily f
          ON f.underlying = s.underlying_symbol
         AND f.as_of_date = s.run_date
        WHERE {where_sql}
        ORDER BY s.id
    """), params).mappings().all()

    # Idempotency optimization — skip observations already enriched.
    seen_obs_ids: set[int] = set()
    if skip_existing and rows:
        existing = session.execute(text(
            """
            SELECT DISTINCT shadow_observation_id
            FROM options_strategy_candidate
            WHERE shadow_observation_id = ANY(:ids)
            """
        ), {"ids": [int(r["id"]) for r in rows]}).scalars().all()
        seen_obs_ids = set(int(x) for x in existing)

    # Opt-B — output taxonomy + per-underlying recommendation bias.
    structures = (
        getattr(settings, "OPTIONS_GENERATOR_STRUCTURES", "directional")
        or "directional"
    ).lower()
    bias_by_underlying = (
        _bias_by_underlying(session, [r["underlying_symbol"] for r in rows])
        if structures in ("credit", "both") else {}
    )
    # Representative would-trade observation per NEUTRAL underlying, used to
    # anchor the underlying-level IRON_CONDOR composition pass (decision 2).
    # Keyed by underlying; we keep the obs whose |delta| is closest to the
    # ~0.30 IC short-strike target.
    ic_reps: dict[str, dict] = {}

    processed = 0
    candidates_generated = 0
    inserted = 0
    skipped = 0
    for row in rows:
        obs_id = int(row["id"])
        if obs_id in seen_obs_ids:
            skipped += 1
            continue
        obs = _row_to_observation(dict(row))
        quote = ChainQuote(
            bid=float(row["bid"]) if row["bid"] is not None else None,
            ask=float(row["ask"]) if row["ask"] is not None else None,
            mid=float(row["mid"]) if row["mid"] is not None else None,
            delta=float(row["delta"]) if row["delta"] is not None else None,
            gamma=float(row["gamma"]) if row["gamma"] is not None else None,
            theta=float(row["theta"]) if row["theta"] is not None else None,
            vega=float(row["vega"]) if row["vega"] is not None else None,
            iv=float(row["chain_iv"]) if row["chain_iv"] is not None else None,
            open_interest=(int(row["open_interest"])
                           if row["open_interest"] is not None else None),
            volume=(int(row["volume"])
                    if row["volume"] is not None else None),
        )
        feat = UnderlyingFeature(
            iv_rank_252d=(float(row["iv_rank_252d"])
                          if row["iv_rank_252d"] is not None else None),
            atm_iv=(float(row["atm_iv"])
                    if row["atm_iv"] is not None else None),
            realized_vol_30d=(float(row["realized_vol_30d"])
                              if row["realized_vol_30d"] is not None
                              else None),
        )
        catalyst = earliest_event_in_window(
            session,
            underlying=obs.underlying,
            run_date=obs.run_date,
            expiry=obs.expiration,
        )
        u_bias = bias_by_underlying.get(obs.underlying, "neutral")
        cands = generate(
            obs=obs, quote=quote, feat=feat, catalyst=catalyst,
            structures=structures, bias=u_bias,
        )
        candidates_generated += len(cands)
        for c in cands:
            try:
                if _persist_one(session, obs, c):
                    inserted += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[strategy_candidate] persist failed obs={} rule={}: {}",
                    obs_id, c.rule_id, exc,
                )

        # Credit mode: capture the best IC anchor for neutral underlyings
        # (no directional credit spread is emitted for them per-contract).
        if structures in ("credit", "both") and u_bias == "neutral":
            d = abs(quote.delta) if quote.delta is not None else 999.0
            dist = abs(d - 0.30)
            cur = ic_reps.get(obs.underlying)
            if cur is None or dist < cur["dist"]:
                ic_reps[obs.underlying] = {
                    "obs": obs, "quote": quote, "feat": feat,
                    "catalyst": catalyst, "dist": dist,
                    "has_rec": obs.underlying in bias_by_underlying,
                }
        processed += 1

    # Opt-B underlying-level IRON_CONDOR pass (decision 2). One IC per
    # neutral underlying, skipped if an IC already exists for that
    # underlying+run_date (idempotent re-runs).
    if structures in ("credit", "both") and ic_reps:
        existing_ic = set(session.execute(text(
            """
            SELECT DISTINCT underlying
            FROM options_strategy_candidate
            WHERE rule_id = 'IRON_CONDOR'
              AND run_date = ANY(:dates)
            """
        ), {"dates": sorted({r["obs"].run_date for r in ic_reps.values()})}
        ).scalars().all())
        for u, rep in ic_reps.items():
            if u in existing_ic:
                continue
            ic = build_iron_condor(
                obs=rep["obs"], quote=rep["quote"], feat=rep["feat"],
                catalyst=rep["catalyst"], has_directional_signal=rep["has_rec"],
            )
            candidates_generated += 1
            try:
                if _persist_one(session, rep["obs"], ic):
                    inserted += 1
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[strategy_candidate] IC persist failed underlying={}: {}",
                    u, exc,
                )

    session.commit()
    return {
        "processed": processed,
        "candidates_generated": candidates_generated,
        "inserted": inserted,
        "skipped_already_enriched": skipped,
    }
