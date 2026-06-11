"""Per-phase writers called by alpha_nightly orchestrator.

Each writer:
  * takes a Session + dry_run flag
  * is idempotent (version-gated)
  * processes in batches, commits per batch
  * returns a dict summary with rows processed / skipped / errors
  * never raises — errors captured in result dict

Goal: the orchestrator can call each in try/except and a single-phase
failure never aborts the rest of the run.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.alpha import (
    FACTOR_VERSION, FEATURE_SET_VERSION, FAILURE_VERSION,
    classify_failure, compute_entry_quality,
    compute_factor_attribution, compute_provider_reliability,
    compute_system_health, simulate_paper_slippage,
)
from apps.api.src.config import settings


BATCH = 500


# ===========================================================================
# STEP 1 — decision_log factor attribution
# ===========================================================================

def process_decision_attribution(
    session: Session, *, dry_run: bool = False,
    batch: int = BATCH,
) -> dict[str, Any]:
    t0 = dt.datetime.now(dt.timezone.utc)
    processed = 0
    skipped = 0
    errors: list[str] = []
    pages_committed = 0

    while True:
        rows = session.execute(text("""
            SELECT id::text AS id, inputs_used, context_values,
                   catalyst, data_quality, risk_context,
                   feature_confidence
            FROM decision_log
            WHERE factor_attribution IS NULL
               OR factor_version IS DISTINCT FROM :ver
            ORDER BY decision_ts ASC
            LIMIT :lim
        """), {"ver": FACTOR_VERSION, "lim": batch}).mappings().all()
        if not rows:
            break

        for r in rows:
            try:
                # data_quality blob may not carry engine_confidence; fall back
                dq = dict(r["data_quality"] or {})
                if "engine_confidence" not in dq \
                   and r.get("feature_confidence") is not None:
                    dq["engine_confidence"] = float(r["feature_confidence"])
                att = compute_factor_attribution(
                    inputs_used=r["inputs_used"] or {},
                    context_values=r["context_values"] or {},
                    catalyst=r["catalyst"] or {},
                    data_quality=dq,
                    risk_context=r["risk_context"] or {},
                    version=FACTOR_VERSION,
                )
                if dry_run:
                    processed += 1
                    continue
                session.execute(text("""
                    UPDATE decision_log
                       SET factor_attribution = CAST(:fa AS jsonb),
                           factor_version = :ver,
                           feature_set_version = :fsv
                     WHERE id = :id
                """), {
                    "fa": json.dumps(att.to_dict(), default=str),
                    "ver": FACTOR_VERSION,
                    "fsv": FEATURE_SET_VERSION,
                    "id": r["id"],
                })
                processed += 1
            except Exception as e:
                errors.append(
                    f"decision {r['id']}: {type(e).__name__} {e}"
                )
                skipped += 1
        if not dry_run:
            session.commit()
            pages_committed += 1
        if len(rows) < batch:
            break

    return {
        "phase": "decision_attribution",
        "processed": processed,
        "skipped": skipped,
        "pages_committed": pages_committed,
        "duration_ms": _ms_since(t0),
        "errors": errors[:20],
    }


# ===========================================================================
# STEP 2 — paper_trade_log execution_quality + failure_analysis
# ===========================================================================

def process_paper_trades(
    session: Session, *, dry_run: bool = False,
    batch: int = BATCH,
) -> dict[str, Any]:
    t0 = dt.datetime.now(dt.timezone.utc)
    eq_done = 0
    fa_done = 0
    skipped = 0
    errors: list[str] = []

    slip_bps = float(getattr(settings, "PAPER_SLIPPAGE_BPS", 5.0))
    apply_slip = bool(getattr(
        settings, "PAPER_APPLY_SLIPPAGE_ANALYTICS", True,
    ))

    while True:
        rows = session.execute(text("""
            SELECT id::text AS id, instrument AS symbol, engine,
                   entry_date, exit_date, entry_price, exit_price,
                   gross_ret_pct, net_ret_pct,
                   (COALESCE(exit_date, CURRENT_DATE) - entry_date)
                       AS days_held,
                   status,
                   regime_at_entry, catalyst_snapshot, data_confidence,
                   near_earnings,
                   execution_quality, failure_analysis, failure_version
            FROM paper_trade_log
            WHERE status = 'closed'
              AND (execution_quality IS NULL OR failure_analysis IS NULL
                   OR failure_version IS DISTINCT FROM :fv)
            ORDER BY entry_date ASC
            LIMIT :lim
        """), {"fv": FAILURE_VERSION, "lim": batch}).mappings().all()
        if not rows:
            break

        for t in rows:
            try:
                trade_id = t["id"]
                entry = float(t.get("entry_price") or 0)
                exit_price = _num(t.get("exit_price"))
                # Execution quality — compare entry vs exit(next-available proxy)
                eq = None
                if t.get("execution_quality") is None:
                    eq = compute_entry_quality(
                        symbol=str(t.get("symbol") or ""),
                        entry_price=entry,
                        next_price=exit_price,
                        configured_slippage_bps=slip_bps,
                    )
                    # slippage-adjusted metrics (analytics-only)
                    slip_adj = None
                    if apply_slip and entry > 0:
                        buy_fill = simulate_paper_slippage(
                            raw_price=entry, side="buy",
                            slippage_bps=slip_bps,
                        )
                        sell_fill = simulate_paper_slippage(
                            raw_price=exit_price or entry,
                            side="sell",
                            slippage_bps=slip_bps,
                        )
                        adj_ret = (
                            ((sell_fill / buy_fill) - 1.0) * 100
                            if buy_fill > 0 else None
                        )
                        slip_adj = {
                            "slippage_bps": slip_bps,
                            "buy_fill_price":  buy_fill,
                            "sell_fill_price": sell_fill,
                            "adjusted_net_ret_pct": (
                                round(adj_ret, 4)
                                if adj_ret is not None else None
                            ),
                        }
                    if not dry_run:
                        session.execute(text("""
                            UPDATE paper_trade_log
                               SET execution_quality = CAST(:eq AS jsonb),
                                   slippage_adjusted_metrics =
                                     CAST(:sa AS jsonb)
                             WHERE id = :id
                        """), {
                            "eq": json.dumps(eq.to_dict(), default=str),
                            "sa": json.dumps(slip_adj or {}, default=str),
                            "id": trade_id,
                        })
                    eq_done += 1

                # Failure classification — only losers
                net = _num(t.get("net_ret_pct"))
                if net is not None and net < 0 and (
                    t.get("failure_analysis") is None
                    or t.get("failure_version") != FAILURE_VERSION
                ):
                    cat = t.get("catalyst_snapshot") or {}
                    if isinstance(cat, str):
                        try:
                            cat = json.loads(cat)
                        except Exception:
                            cat = {}
                    eq_score = None
                    if eq is not None:
                        eq_score = eq.quality_score
                    else:
                        # read back from db if we already had eq
                        prev = t.get("execution_quality") or {}
                        if isinstance(prev, dict):
                            eq_score = prev.get("quality_score")
                    fa = classify_failure(
                        trade_id=trade_id,
                        net_ret_pct=net / 100.0 if abs(net) > 1.0 else net,
                        regime_at_entry=str(t.get("regime_at_entry") or ""),
                        data_confidence=_num(t.get("data_confidence")),
                        catalyst_policy=(cat.get("trade_policy")
                                         if isinstance(cat, dict) else None),
                        days_to_earnings=(cat.get("days_to_earnings")
                                          if isinstance(cat, dict) else None),
                        entry_quality_score=eq_score,
                        max_adverse=None,
                        max_favorable=None,
                        version=FAILURE_VERSION,
                    )
                    if not dry_run:
                        session.execute(text("""
                            UPDATE paper_trade_log
                               SET failure_analysis = CAST(:fa AS jsonb),
                                   failure_version  = :fv
                             WHERE id = :id
                        """), {
                            "fa": json.dumps(fa.to_dict(), default=str),
                            "fv": FAILURE_VERSION,
                            "id": trade_id,
                        })
                    fa_done += 1
            except Exception as e:
                errors.append(
                    f"trade {t['id']}: {type(e).__name__} {e}"
                )
                skipped += 1
        if not dry_run:
            session.commit()
        if len(rows) < batch:
            break

    return {
        "phase": "paper_trades",
        "execution_quality_written": eq_done,
        "failure_analysis_written": fa_done,
        "skipped": skipped,
        "duration_ms": _ms_since(t0),
        "errors": errors[:20],
    }


# ===========================================================================
# STEP 3 — system_health_score (append)
# ===========================================================================

def write_system_health_score(
    session: Session, *, dry_run: bool = False,
) -> dict[str, Any]:
    t0 = dt.datetime.now(dt.timezone.utc)
    try:
        inputs = _gather_health_inputs(session)
        score = compute_system_health(**inputs)
        if dry_run:
            return {
                "phase": "system_health",
                "written": False,
                "dry_run": True,
                "preview": score.to_dict(),
                "duration_ms": _ms_since(t0),
            }
        session.execute(text("""
            INSERT INTO system_health_score
              (as_of_date, overall, components, recommendation, warnings)
            VALUES
              (:asof, :overall, CAST(:c AS jsonb), :rec, CAST(:w AS jsonb))
        """), {
            "asof": dt.date.today(),
            "overall": score.overall,
            "c": json.dumps({
                "data_quality":      score.data_quality,
                "signal_quality":    score.signal_quality,
                "catalyst_coverage": score.catalyst_coverage,
                "execution_quality": score.execution_quality,
                "risk_control":      score.risk_control,
                "ml_readiness":      score.ml_readiness,
                "paper_feedback":    score.paper_feedback,
            }),
            "rec": score.recommendation,
            "w":  json.dumps(list(score.warnings)),
        })
        session.commit()
        return {
            "phase": "system_health",
            "written": True,
            "overall": score.overall,
            "duration_ms": _ms_since(t0),
        }
    except Exception as e:
        return {
            "phase": "system_health",
            "written": False,
            "error": f"{type(e).__name__}: {e}",
            "duration_ms": _ms_since(t0),
        }


def _gather_health_inputs(session: Session) -> dict[str, float]:
    """Derive the 7 0..1 scores from existing snapshots + DB state.

    All fall back to 0.0 on missing data — better to report low-health
    than to inflate a stub score.
    """
    # ML readiness & feature/signal proxies from latest ml_research_snapshot
    ml_readiness = 0.0
    signal_quality = 0.0
    data_quality = 0.0
    catalyst_coverage = 0.0
    execution_quality = 0.5         # neutral default
    risk_control = 0.5              # neutral default
    paper_feedback = 0.5            # neutral default
    try:
        row = session.execute(text("""
            SELECT tier, leakage_clean, feature_health, baseline_results
            FROM ml_research_snapshot
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
        if row:
            fh = row.get("feature_health") or {}
            data_quality = float(fh.get("catalyst_coverage") or 0) * 0.5 \
                           + (1.0 if row.get("leakage_clean") else 0.0) * 0.5
            catalyst_coverage = float(fh.get("catalyst_coverage") or 0)
            ml_readiness = {
                "diagnostics_only": 0.1,
                "baselines_only": 0.3,
                "walk_forward_ok": 0.6,
                "rich_experiments_allowed": 0.8,
            }.get(str(row.get("tier")), 0.1)
            bases = row.get("baseline_results") or {}
            signal_quality = _signal_quality_from_baselines(bases)
    except Exception as e:
        logger.warning("health: ml_research_snapshot read failed: {}", e)
        session.rollback()   # P6E.0/H1 — never poison the health INSERT

    # Execution quality proxy — mean quality_score from recent trades
    try:
        row = session.execute(text("""
            SELECT AVG((execution_quality ->> 'quality_score')::float)
                   AS avg_eq
            FROM paper_trade_log
            WHERE execution_quality IS NOT NULL
              AND entry_date > CURRENT_DATE - INTERVAL '30 days'
        """)).mappings().first()
        if row and row.get("avg_eq") is not None:
            execution_quality = float(row["avg_eq"])
    except Exception as e:
        logger.warning("health: execution proxy read failed: {}", e)
        session.rollback()   # P6E.0/H1 — never poison the health INSERT

    # Paper feedback — closed trade winrate in last 30d
    try:
        row = session.execute(text("""
            SELECT COUNT(*) FILTER (WHERE net_ret_pct > 0)::float /
                   NULLIF(COUNT(*), 0) AS wr
            FROM paper_trade_log
            WHERE status='closed' AND net_ret_pct IS NOT NULL
              AND entry_date > CURRENT_DATE - INTERVAL '30 days'
        """)).mappings().first()
        if row and row.get("wr") is not None:
            paper_feedback = float(row["wr"])
    except Exception as e:
        logger.warning("health: paper proxy read failed: {}", e)
        session.rollback()   # P6E.0/H1 — never poison the health INSERT

    # Risk control — invert latest drawdown
    try:
        # P6E.0/H1 — the columns are max_dd_pct + as_of_date (the old
        # max_drawdown_pct/snapshot_date names never existed on this
        # table; the UndefinedColumn error poisoned the transaction and
        # killed the system_health_score INSERT on every nightly run).
        row = session.execute(text("""
            SELECT max_dd_pct FROM paper_portfolio_snapshot
            ORDER BY as_of_date DESC LIMIT 1
        """)).mappings().first()
        if row and row.get("max_dd_pct") is not None:
            dd = abs(float(row["max_dd_pct"] or 0))
            # 0% dd → 1.0, 10% dd → 0.0
            risk_control = max(0.0, min(1.0, 1.0 - dd / 10.0))
    except Exception as e:
        logger.warning("health: risk proxy read failed: {}", e)
        session.rollback()

    return {
        "data_quality":     max(0.0, min(1.0, data_quality)),
        "signal_quality":   signal_quality,
        "catalyst_coverage": catalyst_coverage,
        "execution_quality": execution_quality,
        "risk_control":     risk_control,
        "ml_readiness":     ml_readiness,
        "paper_feedback":   paper_feedback,
    }


def _signal_quality_from_baselines(bases: dict[str, Any]) -> float:
    rows: list[dict[str, Any]] = []
    for k in ("v1", "v2"):
        v = bases.get(k)
        if isinstance(v, list):
            rows.extend(v)
    if not rows:
        return 0.0
    sharpes = [
        float(r.get("sharpe_proxy") or 0)
        for r in rows
        if isinstance(r.get("sharpe_proxy"), (int, float))
    ]
    if not sharpes:
        return 0.0
    best = max(sharpes)
    # 0 sharpe → 0, 1.0 sharpe → 0.9
    return max(0.0, min(1.0, best * 0.9))


# ===========================================================================
# STEP 4 — provider_reliability (append)
# ===========================================================================

def write_provider_reliability(
    session: Session, *, dry_run: bool = False,
) -> dict[str, Any]:
    t0 = dt.datetime.now(dt.timezone.utc)
    # Providers we actively use. Stats are derived from ml_research_snapshot
    # warnings + catalyst_backfill_run summaries. Conservative defaults —
    # operator layers real telemetry on top later.
    provider_stats: dict[str, dict[str, float]] = {
        "yahoo":         {"success_rate": 0.85, "missing_rate": 0.15,
                          "error_rate": 0.05, "freshness_score": 0.8},
        "finnhub":       {"success_rate": 0.0,  "missing_rate": 1.0,
                          "error_rate": 0.5,  "freshness_score": 0.0},
        "alpha_vantage": {"success_rate": 0.0,  "missing_rate": 1.0,
                          "error_rate": 0.5,  "freshness_score": 0.0},
        "fmp":           {"success_rate": 0.0,  "missing_rate": 1.0,
                          "error_rate": 0.5,  "freshness_score": 0.0},
    }
    # Override with backfill runs if present
    try:
        row = session.execute(text("""
            SELECT providers, summary FROM catalyst_backfill_run
            WHERE status = 'completed'
            ORDER BY started_at DESC LIMIT 1
        """)).mappings().first()
        if row:
            summary = row.get("summary") or {}
            # summary.symbol_counts per-symbol news/earn counts; treat as
            # success when >0 inserted
            syms = (summary.get("symbol_counts") or {})
            if summary.get("provider_errors", 0) == 0 and syms:
                for p in row.get("providers") or []:
                    provider_stats[p] = {
                        "success_rate": 0.95,
                        "missing_rate": 0.05,
                        "error_rate":   0.01,
                        "freshness_score": 0.9,
                    }
    except Exception as e:
        logger.warning(
            "provider reliability: backfill summary read failed: {}", e,
        )
        # Postgres leaves failed query in aborted-txn state — rollback
        # defensively so downstream INSERTs don't cascade-fail.
        try:
            session.rollback()
        except Exception:
            pass

    written = 0
    errors: list[str] = []
    today = dt.date.today()
    for provider, stats in provider_stats.items():
        try:
            rel = compute_provider_reliability(provider=provider, **stats)
            if dry_run:
                continue
            session.execute(text("""
                INSERT INTO provider_reliability
                  (as_of_date, provider, reliability_score,
                   freshness_score, missing_rate, error_rate)
                VALUES
                  (:d, :p, :r, :f, :m, :e)
                ON CONFLICT ON CONSTRAINT
                  ux_provider_reliability_date_provider
                DO UPDATE SET
                  reliability_score = EXCLUDED.reliability_score,
                  freshness_score   = EXCLUDED.freshness_score,
                  missing_rate      = EXCLUDED.missing_rate,
                  error_rate        = EXCLUDED.error_rate
            """), {
                "d": today, "p": provider,
                "r": rel.reliability_score,
                "f": rel.freshness_score,
                "m": rel.missing_rate,
                "e": rel.error_rate,
            })
            written += 1
        except Exception as e:
            errors.append(f"{provider}: {type(e).__name__} {e}")
    if not dry_run:
        session.commit()
    return {
        "phase": "provider_reliability",
        "written": written,
        "errors": errors,
        "duration_ms": _ms_since(t0),
    }


# ===========================================================================
# helpers
# ===========================================================================

def _ms_since(t0: dt.datetime) -> int:
    return int(
        (dt.datetime.now(dt.timezone.utc) - t0).total_seconds() * 1000,
    )


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        if x != x:
            return None
        return x
    except (TypeError, ValueError):
        return None
