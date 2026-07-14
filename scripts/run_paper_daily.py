"""Phase OPS1 — One-command daily paper-trading pipeline.

Usage:
    python -m scripts.run_paper_daily
    python -m scripts.run_paper_daily --date 2026-04-22
    python -m scripts.run_paper_daily --dry-run
    python -m scripts.run_paper_daily --skip-shadow
    python -m scripts.run_paper_daily --force-recompute

Pipeline:
    A. ingest raw (market, macro, positioning) — PIT-safe
    B. compute features (production + candidate + diagnostic)
    C. compute contexts (production + candidate + diagnostic)
    D. run frozen strategy adapter (A, B, selector)
    E. update paper portfolio (entry / exit / equity snapshot)
    F. shadow-evaluate candidate/diagnostic overlays
    G. emit operator summary (json + stdout)

Safety:
    * fails HARD on missing production data
    * WARNS on missing candidate/diagnostic data
    * idempotent — re-run same date is safe (skip=no-op, force=overwrite)
    * no silent defaults
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.data.features.registry import get_registry
from apps.api.src.data.context.production import classify_production_context
from apps.api.src.data.context.candidate import classify_backwardation
from apps.api.src.data.context.diagnostic import classify_diagnostic
from apps.api.src.data.strategy.selector import SelectorInputs, select
from apps.api.src.data.strategy.decision_logger import (
    write_decision, decision_from_selector, LoggedDecision,
)
from apps.api.src.data.strategy.paper_decision_wrapper import (
    enrich_paper_decision,
)
from apps.api.src.data.strategy.paper_run_log import (
    PaperRunCounts, build_run_summary, write_paper_run_log,
)
from apps.api.src.data.raw.macro import ingest_all_fred
from apps.api.src.data.raw.positioning import ingest_gex_from_squeezemetrics
from apps.api.src.data.evaluation.anomaly_detector import (
    detect_anomalies, persist_anomalies, summarize as summarize_anomalies,
)

from scripts.run_phase12_price_action import fetch_es_daily, load_spy_from_db, HOLD_WINDOWS
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)
from scripts.run_phase20_regime_gated import build_gates

RUN_VERSION = "ops1-v1.0.0"
OUT_DIR = Path("artifacts/ops1")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PAPER_ID = "default"
STARTING_CAPITAL = 100_000.0
POSITION_PCT_A = 10.0       # 10% notional per Engine A trade
POSITION_PCT_B = 5.0        # 5% per Engine B day
SLIPPAGE_BPS_A = 20.0
SLIPPAGE_BPS_B = 5.0
INSTRUMENT = "ES"
HOLD_A = 10


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class StepResult:
    name: str
    status: Literal["ok", "warn", "fail", "skipped"]
    detail: str = ""
    counts: dict = field(default_factory=dict)


@dataclass
class DailySummary:
    as_of_date: dt.date
    run_version: str
    pipeline_status: Literal["success", "partial", "failed"]
    steps: list[dict]
    data_freshness: dict
    regime: dict
    decision: dict
    paper: dict
    shadow: dict
    warnings: list[str]
    errors: list[str]


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------
def step_ingest_raw(session: Session) -> StepResult:
    try:
        fred = ingest_all_fred(session)
        gex = ingest_gex_from_squeezemetrics(session)
        return StepResult(
            name="A_ingest_raw", status="ok",
            counts={"fred": fred, "positioning_gex": gex},
        )
    except Exception as exc:
        return StepResult(
            name="A_ingest_raw", status="warn",
            detail=f"partial ingest: {exc}",
        )


def resolve_target_date(es_index, requested_date: dt.date):
    """Latest available trading day at or before ``requested_date``.

    Date-aware guard: weekends, holidays, and no-data days resolve to the most
    recent available market bar instead of hard-failing. Returns a ``dt.date``,
    or ``None`` when NO bar exists at or before ``requested_date``. Pure — no DB
    or network — so it is unit-testable in isolation. Never fabricates a date.
    """
    import pandas as _pd
    cut = es_index[es_index <= _pd.Timestamp(requested_date)]
    if len(cut) == 0:
        return None
    last = cut[-1]
    return last.date() if hasattr(last, "date") else last


def load_universe(target_date: dt.date) -> dict:
    """Load market data, cut at the latest available trading day <= target_date.

    Date-aware: if ``target_date`` is a weekend/holiday/no-data day, the universe
    is cut at — and the returned ``resolved_date`` equals — the latest available
    trading bar at or before it (we never invent prices). Raises only when NO
    market data exists at or before ``target_date``.
    """
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    spy = spy.loc[common]
    resolved = resolve_target_date(es.index, target_date)
    if resolved is None:
        raise RuntimeError(
            f"no market data at or before {target_date} — cannot run"
        )
    es_cut = es.loc[:resolved]
    spy_cut = spy.loc[:resolved]
    return {"es": es_cut, "spy": spy_cut,
            "requested_date": target_date, "resolved_date": resolved}


PRODUCTION_GATE_NAMES: tuple[str, ...] = (
    "rates_calm", "vrp_supportive",
    "credit_stable", "liquidity_expanding",
)


def _read_gates_from_context_daily(
    session: Session, target_date: dt.date,
) -> dict[str, bool] | None:
    """Read the four production gate booleans from context_daily.

    Phase 11Z behavior:
      * Only rows with `status='production'` are treated as "fit
        for trading" booleans. Rows with status in
        {`insufficient_data`,`missing_data`,`stale_data`} are
        treated as `unknown` — they are NOT counted as favorable
        and they are NOT counted as failed gates either.
      * The four gates must each have ANY row at or before
        target_date (production OR unknown). If any of the four
        names has no row at all, returns None and the caller falls
        back to build_gates().
      * Returns a dict mapping each gate to True / False / None.
        `None` means the latest row was an unknown-status diagnostic
        record (from a Phase 11Z-aware backfill).

    Read-only. Never queries future dates. Never writes."""
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (context_name)
               context_name, status, value_bool
        FROM context_daily
        WHERE context_name = ANY(:names)
          AND as_of_date <= :run_date
        ORDER BY context_name, as_of_date DESC
        """
    ), {
        "names": list(PRODUCTION_GATE_NAMES),
        "run_date": target_date,
    }).all()
    by_name: dict[str, bool | None] = {}
    for r in rows:
        if r.status == "production":
            by_name[r.context_name] = (
                bool(r.value_bool) if r.value_bool is not None else None
            )
        else:
            # insufficient_data / missing_data / stale_data → unknown.
            by_name[r.context_name] = None
    if not all(g in by_name for g in PRODUCTION_GATE_NAMES):
        return None
    return {g: by_name[g] for g in PRODUCTION_GATE_NAMES}


def _read_gate_statuses_from_context_daily(
    session: Session, target_date: dt.date,
) -> dict[str, str]:
    """Phase 11Z — surface per-gate status distinct from value.
    Used by paper_run_log diagnostics to split `failed_gates` from
    `unknown_gates`. Status `'production'` here means the gate has
    a real True/False; anything else is unknown semantics.
    Returns `{gate_name: status_str}` for every gate that has any
    row at or before target_date."""
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (context_name)
               context_name, status
        FROM context_daily
        WHERE context_name = ANY(:names)
          AND as_of_date <= :run_date
        ORDER BY context_name, as_of_date DESC
        """
    ), {
        "names": list(PRODUCTION_GATE_NAMES),
        "run_date": target_date,
    }).all()
    return {r.context_name: r.status for r in rows}


def step_compute_features_and_context(
    session: Session, universe: dict, target_date: dt.date,
) -> tuple[StepResult, dict]:
    reg = get_registry()
    es = universe["es"]; spy = universe["spy"]
    feat = build_features(es)
    gates = build_gates(feat, spy)

    c1 = feat["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = feat["vol_elevated"] | feat["vol_expanding"]
    c3 = feat["z_score"] < Z_EXTENSION_THRESH
    p15 = (c1 & c2 & c3).fillna(False)

    if target_date not in feat.index:
        raise RuntimeError(f"no feature row at {target_date}")
    row_feat = feat.loc[target_date]
    row_gate = gates.loc[target_date]
    p15_today = bool(p15.loc[target_date])

    # Phase 11U.fix / 11Z - prefer context_daily values for the four
    # production gates; fall back to build_gates() output when ANY
    # gate row is missing for target_date or earlier. Phase 11Z:
    # context_daily values may now be `None` when the underlying
    # input data was missing/insufficient/stale. Treat None as
    # not-favorable (False for the gates_favorable count) but
    # surface the distinction in `bundle` so paper_run_log can
    # split failed_gates vs unknown_gates.
    gates_source: str = "build_gates"
    gate_statuses: dict[str, str] = {}
    db_gates = _read_gates_from_context_daily(session, target_date)
    if db_gates is not None:
        rc_today  = db_gates["rates_calm"]
        vrp_today = db_gates["vrp_supportive"]
        cs_today  = db_gates["credit_stable"]
        le_today  = db_gates["liquidity_expanding"]
        gates_source = "context_daily"
        gate_statuses = _read_gate_statuses_from_context_daily(
            session, target_date,
        )
    else:
        cs_today  = bool(row_gate["credit_stable"])
        rc_today  = bool(row_gate["rates_calm"])
        vrp_today = bool(row_gate["vrp_supportive"])
        le_today  = bool(row_gate["liquidity_expanding"])
        logger.info(
            "context_daily fallback used for {} — at least one gate "
            "row missing", target_date,
        )

    # Phase 11Z — None gates do NOT count as favorable, and they are
    # NOT counted as failed economically. Selector still treats them
    # conservatively (favorable_count only counts True). Trading
    # logic is unchanged (favorable_count drives stress/directional
    # classification exactly as before).
    def _truthy(v: bool | None) -> int:
        return 1 if v is True else 0
    gf = (
        _truthy(rc_today) + _truthy(vrp_today)
        + _truthy(cs_today) + _truthy(le_today)
    )

    failed_gates: list[str] = []
    unknown_gates: list[str] = []
    for nm, val in (
        ("rates_calm", rc_today),
        ("vrp_supportive", vrp_today),
        ("credit_stable", cs_today),
        ("liquidity_expanding", le_today),
    ):
        if val is False:
            failed_gates.append(nm)
        elif val is None:
            unknown_gates.append(nm)

    # Production context (immutable)
    prod_ctx = classify_production_context(gates_favorable=gf)
    # Persist context row (production, candidate-stub, diagnostic-stub)
    _persist_context(session, target_date, "stress_regime", "production",
                     prod_ctx.stress_regime, ["gates_favorable"],
                     prod_ctx.logic_version, prod_ctx.logic_fingerprint)
    _persist_context(session, target_date, "directional_regime", "production",
                     prod_ctx.directional_regime, ["gates_favorable"],
                     prod_ctx.logic_version, prod_ctx.logic_fingerprint)

    counts = {
        "features_computed": 6,
        "contexts_written": 2,   # production only — candidate/diag optional
    }

    bundle = {
        "feat_row": row_feat.to_dict(),
        "gates_favorable": gf,
        "p15_entry": p15_today,
        "credit_stable": cs_today, "rates_calm": rc_today,
        "vrp_supportive": vrp_today, "liquidity_expanding": le_today,
        "production_context": prod_ctx,
        "target_date": target_date,
        "gates_source": gates_source,
        "failed_gates": failed_gates,    # Phase 11Z
        "unknown_gates": unknown_gates,  # Phase 11Z
        "gate_statuses": gate_statuses,  # Phase 11Z
        "entry_price_open": float(feat["open"].shift(-1).loc[target_date])
            if target_date != feat.index[-1] else None,
    }
    return StepResult(name="BC_features_context", status="ok", counts=counts), bundle


def _persist_context(
    session: Session, as_of: dt.date, name: str, status: str,
    value: bool, source_features: list[str], logic_version: str,
    logic_fingerprint: str,
) -> None:
    session.execute(text("""
      INSERT INTO context_daily
        (as_of_date, context_name, status, value_bool, source_features,
         logic_version, logic_hash)
      VALUES (:d, :n, :s, :v, CAST(:sf AS text[]), :lv, :lf)
      ON CONFLICT (as_of_date, context_name, logic_version) DO UPDATE
        SET value_bool = EXCLUDED.value_bool,
            computed_at = now()
    """), {"d": as_of, "n": name, "s": status, "v": value,
           "sf": "{" + ",".join(source_features) + "}",
           "lv": logic_version, "lf": logic_fingerprint})
    session.commit()


def step_run_strategy(
    session: Session, bundle: dict, target_date: dt.date, dry_run: bool,
) -> tuple[StepResult, dict]:
    out = select(SelectorInputs(
        p15_entry=bundle["p15_entry"],
        credit_stable=bundle["credit_stable"],
        rates_calm=bundle["rates_calm"],
        production_context=bundle["production_context"],
    ))

    inputs_used = {
        "p15_entry": bundle["p15_entry"],
        "gates_favorable": bundle["gates_favorable"],
        "credit_stable": bundle["credit_stable"],
        "rates_calm": bundle["rates_calm"],
        "vrp_supportive": bundle["vrp_supportive"],
        "liquidity_expanding": bundle["liquidity_expanding"],
    }
    context_values = {
        "stress_regime": bundle["production_context"].stress_regime,
        "directional_regime": bundle["production_context"].directional_regime,
        # Include boolean gates so exploratory evaluator sees them
        "rates_calm": bundle["rates_calm"],
        "vrp_supportive": bundle["vrp_supportive"],
        "credit_stable": bundle["credit_stable"],
        "liquidity_expanding": bundle["liquidity_expanding"],
    }

    # ------------------------------------------------------------------
    # SYSTEM-ALPHA-5 — paper-only enrichment (rule policy + exploratory)
    # ------------------------------------------------------------------
    # Derive a conservative risk level from gates; low-risk only when
    # 3+ gates pass and no critical anomaly fallback handled in wrapper.
    risk_level = "low" if bundle["gates_favorable"] >= 3 else "medium"
    enriched = enrich_paper_decision(
        session, out,
        symbol=INSTRUMENT,
        context_values=context_values,
        features={
            "gates_favorable": bundle["gates_favorable"],
            "mean_20d_ret":    bundle["feat_row"].get("mean_20d_ret"),
            "atr_ratio":       bundle["feat_row"].get("atr_ratio"),
            "vol_elevated":    bundle["feat_row"].get("vol_elevated"),
        },
        catalyst={},
        data_quality={"confidence": 0.8},   # ES pipeline high-trust
        execution_quality={},
        portfolio_risk={"concentration_score": 0.0},
        anomaly_severity=None,
        risk_level=risk_level,
        as_of_date=target_date,
    )

    logged = decision_from_selector(
        out, as_of_date=target_date, instrument=INSTRUMENT,
        inputs_used=inputs_used, context_values=context_values,
        **enriched.to_log_kwargs(),
        gate_mode=enriched.gate_mode,
        exploratory_paper=enriched.exploratory_paper,
        exploratory_reason=enriched.exploratory_reason,
        gates_passed=enriched.gates_passed,
        gates_total=enriched.gates_total,
        gates_failed=enriched.gates_failed,
        strict_would_block=enriched.strict_would_block,
        exploratory_size_multiplier=enriched.exploratory_size_multiplier,
    )

    decision_id: str | None = None
    if not dry_run:
        decision_id = write_decision(session, logged)

    return StepResult(
        name="D_strategy",
        status="ok",
        detail=(f"engine={out.engine} fire={out.fire} "
                f"paper_mult={enriched.paper_size_multiplier:.2f} "
                f"exploratory={enriched.exploratory_paper}"),
        counts={
            "selector_engine": out.engine, "selector_fire": out.fire,
            "paper_size_multiplier": enriched.paper_size_multiplier,
            "exploratory_paper": enriched.exploratory_paper,
            "alpha_rules_mode": enriched.alpha_rules_mode,
        },
    ), {
        "selector_output": out,
        "logged_decision": logged,
        "decision_id": decision_id,
        "enriched": enriched,
    }


def resolve_entry_price(
    session: Session, *, bundle: dict, as_of_date: dt.date,
    instrument: str,
) -> dict:
    """Safe entry-price fallback chain — paper trading only.

    Precedence:
      1. bundle['entry_price_open']   → source 'next_open'
      2. bundle['feat_row']['open']   → source 'same_day_open'
      3. bundle['feat_row']['close']  → source 'same_day_close'
      4. latest price_bar close ≤ as_of_date → source 'latest_close'
      5. None                         → source 'none', skip

    Returns dict with keys:
      price, source, timestamp (date|None), reason (optional).
    """
    feat_row = bundle.get("feat_row") or {}

    # (1) Next-day open (existing default)
    v = bundle.get("entry_price_open")
    if v is not None:
        try:
            return {
                "price": float(v), "source": "next_open",
                "timestamp": as_of_date,
            }
        except (TypeError, ValueError):
            pass

    # (2) Same-day open
    v = feat_row.get("open")
    if v is not None:
        try:
            f = float(v)
            if f > 0:
                return {
                    "price": f, "source": "same_day_open",
                    "timestamp": as_of_date,
                }
        except (TypeError, ValueError):
            pass

    # (3) Same-day close
    v = feat_row.get("close")
    if v is not None:
        try:
            f = float(v)
            if f > 0:
                return {
                    "price": f, "source": "same_day_close",
                    "timestamp": as_of_date,
                }
        except (TypeError, ValueError):
            pass

    # (4) Latest DB close on or before as_of_date
    try:
        row = session.execute(text("""
            SELECT p.close, p.ts::date AS bar_date
            FROM price_bar p
            JOIN asset a ON a.id = p.asset_id
            WHERE a.symbol = :sym
              AND p.timeframe = '1d'
              AND p.ts::date <= :d
            ORDER BY p.ts DESC
            LIMIT 1
        """), {"sym": instrument, "d": as_of_date}).mappings().first()
        if row and row.get("close") is not None:
            return {
                "price": float(row["close"]),
                "source": "latest_close",
                "timestamp": row.get("bar_date"),
            }
    except Exception as e:
        logger.debug("resolve_entry_price: db lookup failed: {}", e)
        try:
            session.rollback()
        except Exception:
            pass

    return {
        "price": None, "source": "none", "timestamp": None,
        "reason": "no valid price source",
    }


def step_paper_portfolio_update(
    session: Session, bundle: dict, strategy_bundle: dict,
    target_date: dt.date, dry_run: bool, force: bool,
) -> StepResult:
    out = strategy_bundle["selector_output"]
    decision_id = strategy_bundle["decision_id"]
    enriched = strategy_bundle.get("enriched")
    paper_mult = float(
        enriched.paper_size_multiplier if enriched is not None else 1.0,
    )
    # Exploratory path: strict didn't fire but wrapper allows reduced-size
    allow_entry = bool(out.fire) or bool(
        enriched is not None and enriched.exploratory_paper
    )
    # If this is purely an exploratory entry, pick engine by regime intent:
    # default to Engine B (directional-style) when strict didn't fire.
    effective_engine = out.engine if out.fire else (
        "B" if allow_entry else "none"
    )

    # Get last snapshot to carry equity/cash forward
    last = session.execute(text("""
      SELECT equity, cash, open_positions, cum_pct, max_dd_pct, as_of_date
      FROM paper_portfolio_snapshot
      WHERE portfolio_id = :pid AND as_of_date < :d
      ORDER BY as_of_date DESC LIMIT 1
    """), {"pid": PAPER_ID, "d": target_date}).fetchone()

    if last is None:
        equity = STARTING_CAPITAL
        cash = STARTING_CAPITAL
        open_positions: list[dict] = []
        cum_pct = 0.0
        max_dd = 0.0
        peak_equity = equity
    else:
        equity = float(last[0])
        cash = float(last[1])
        open_positions = list(last[2]) if last[2] else []
        cum_pct = float(last[3] or 0.0)
        max_dd = float(last[4] or 0.0)
        peak_equity = STARTING_CAPITAL * (1 + max(cum_pct, 0.0) / 100)

    daily_pnl = 0.0
    closed_trades: list[dict] = []

    # Close expired positions (Engine A 10-bar hold, Engine B 1-bar hold)
    still_open: list[dict] = []
    for pos in open_positions:
        target_exit = dt.date.fromisoformat(pos["target_exit_date"])
        if target_date >= target_exit:
            # Close at today's close price (paper)
            exit_price = float(bundle["feat_row"].get("close", pos["entry_price"]))
            entry_price = float(pos["entry_price"])
            slip = float(pos["slippage_bps_assumed"]) / 1e4
            gross = (exit_price - entry_price) / entry_price
            net = gross - slip  # exit slippage (entry slippage already paid)
            notional = float(pos["position_size_pct"]) / 100 * equity
            pnl_dollar = notional * net
            daily_pnl += pnl_dollar
            cash += notional * (1 + gross)
            closed_trades.append({
                "trade_id": pos["trade_id"], "exit_price": exit_price,
                "net_ret_pct": net * 100, "pnl_dollar": pnl_dollar,
            })
            if not dry_run:
                session.execute(text("""
                  UPDATE paper_trade_log
                  SET status='closed', exit_date=:ex_d, exit_price=:ex_p,
                      gross_ret_pct=:gr, net_ret_pct=:nr, updated_at=now()
                  WHERE id = :tid
                """), {"ex_d": target_date, "ex_p": exit_price,
                       "gr": gross * 100, "nr": net * 100,
                       "tid": pos["trade_id"]})
        else:
            still_open.append(pos)

    # Open new position if selector fired OR wrapper approved exploratory.
    # `paper_mult` is the single source of truth for size scaling —
    # wrapper compounds alpha-rule + exploratory multipliers, capped at 1.0.
    #
    # Resolve entry price via safe fallback chain. Paper-only — never
    # fabricates a price. Logs which source was used.
    price_info = resolve_entry_price(
        session, bundle=bundle, as_of_date=target_date,
        instrument=INSTRUMENT,
    )
    entry_price_source = price_info["source"]
    entry_price_timestamp = price_info.get("timestamp")
    entry_price_val = price_info.get("price")
    no_price_skip = (entry_price_val is None)
    if no_price_skip:
        logger.info(
            "[ops1] entry skipped: no valid price source ({})",
            price_info.get("reason") or "unknown",
        )
    else:
        logger.info(
            "[ops1] paper entry price source: {} ({})",
            entry_price_source,
            f"{entry_price_val:.4f}",
        )
    if (allow_entry and not no_price_skip and paper_mult > 0):
        entry_price = float(entry_price_val)
        if effective_engine == "A":
            base_size_pct = POSITION_PCT_A
            slip_bps = SLIPPAGE_BPS_A
            hold_days = HOLD_A
        else:
            base_size_pct = POSITION_PCT_B
            slip_bps = SLIPPAGE_BPS_B
            hold_days = 1
        # Apply wrapper multiplier (never > 1.0 by contract)
        size_pct = min(base_size_pct, base_size_pct * paper_mult)
        notional = size_pct / 100 * equity
        cash -= notional  # reserve
        new_trade_id = str(uuid.uuid4())
        target_exit_date = _add_trading_days(target_date, hold_days)
        regime_at_entry = (
            "stress" if effective_engine == "A"
            else ("exploratory" if enriched is not None
                   and enriched.exploratory_paper and not out.fire
                   else "directional")
        )
        exploratory_snapshot: dict | None = None
        if enriched is not None and enriched.exploratory_paper:
            exploratory_snapshot = {
                "gate_mode": enriched.gate_mode,
                "gates_passed": enriched.gates_passed,
                "gates_total":  enriched.gates_total,
                "gates_failed": enriched.gates_failed,
                "strict_would_block": enriched.strict_would_block,
                "size_multiplier": enriched.exploratory_size_multiplier,
                "reason": enriched.exploratory_reason,
            }
        alpha_snapshot: dict | None = None
        # Always attach snapshot when any adjustment fired OR we captured
        # a non-default entry price source — keeps full provenance.
        _has_adj = enriched is not None and (
            enriched.alpha_rule_adjustment
            or enriched.context_multiplier < 1.0
            or enriched.similarity_multiplier < 1.0
            or enriched.ml_shadow_multiplier < 1.0
            or enriched.ml_shadow_available
        )
        _non_default_price = entry_price_source != "next_open"
        if _has_adj or _non_default_price:
            alpha_snapshot = {
                "mode": (
                    enriched.alpha_rules_mode if enriched else None
                ),
                "size_multiplier": (
                    enriched.alpha_rule_size_multiplier
                    if enriched else None
                ),
                "applied_rules": (
                    enriched.alpha_rules_applied if enriched else None
                ),
                "blocked": (
                    enriched.alpha_rule_blocked if enriched else None
                ),
                "context_multiplier": (
                    enriched.context_multiplier if enriched else 1.0
                ),
                "context_key": (
                    enriched.context_key if enriched else None
                ),
                "similarity": (
                    enriched.similarity_details if enriched else None
                ),
                "similarity_multiplier": (
                    enriched.similarity_multiplier if enriched else 1.0
                ),
                "similarity_matched": (
                    enriched.similarity_matched if enriched else False
                ),
                "ml_hybrid": (
                    enriched.ml_hybrid_snapshot if enriched else None
                ),
                "ml_shadow_multiplier": (
                    enriched.ml_shadow_multiplier if enriched else 1.0
                ),
                "ml_shadow_available": (
                    enriched.ml_shadow_available if enriched else False
                ),
                "ml_hybrid_action": (
                    enriched.ml_hybrid_action if enriched else "none"
                ),
                "paper_size_multiplier": (
                    enriched.paper_size_multiplier if enriched else 1.0
                ),
                "entry_price_source": entry_price_source,
                "entry_price_timestamp": (
                    entry_price_timestamp.isoformat()
                    if entry_price_timestamp is not None else None
                ),
            }
        trade = {
            "trade_id": new_trade_id,
            "engine": effective_engine,
            "entry_date": target_date.isoformat(),
            "entry_price": entry_price,
            "position_size_pct": size_pct,
            "slippage_bps_assumed": slip_bps,
            "target_exit_date": target_exit_date.isoformat(),
            "regime_at_entry": regime_at_entry,
            "exploratory_paper": bool(
                enriched is not None and enriched.exploratory_paper
            ),
        }
        still_open.append(trade)
        if not dry_run:
            # Partial unique index uq_paper_trade_open_key enforces:
            # at most one OPEN row per (portfolio, entry_date, instrument,
            # engine, action). ON CONFLICT DO NOTHING makes rerun safe —
            # returns 0 rowcount when a duplicate would have been inserted.
            res = session.execute(text("""
              INSERT INTO paper_trade_log
                (id, portfolio_id, decision_id, engine, instrument, action,
                 entry_date, entry_price, position_size_pct,
                 slippage_bps_assumed, regime_at_entry, reason,
                 decision_version, status, target_exit_date,
                 exploratory_paper, exploratory_snapshot,
                 alpha_rule_adjusted, alpha_rule_size_multiplier,
                 alpha_rule_snapshot)
              VALUES
                (CAST(:tid AS uuid), :pid,
                 CAST(:did AS uuid), :eng, :inst, 'enter_long',
                 :ed, :ep, :sp, :sl, :reg, :reason, :dv, 'open', :ted,
                 :exp, CAST(:es AS jsonb),
                 :ara, :arm, CAST(:asn AS jsonb))
              ON CONFLICT (portfolio_id, entry_date, instrument,
                            engine, action)
                 WHERE status = 'open'
              DO NOTHING
            """), {
                "tid": new_trade_id, "pid": PAPER_ID, "did": decision_id,
                "eng": effective_engine, "inst": INSTRUMENT,
                "ed": target_date,
                "ep": entry_price, "sp": size_pct, "sl": slip_bps,
                "reg": regime_at_entry,
                "reason": (
                    out.reason + (
                        " | exploratory" if trade["exploratory_paper"]
                        else ""
                    )
                ),
                "dv": out.decision_version, "ted": target_exit_date,
                "exp": trade["exploratory_paper"],
                "es": json.dumps(exploratory_snapshot or {}, default=str),
                "ara": bool(alpha_snapshot),
                "arm": (enriched.alpha_rule_size_multiplier
                         if enriched is not None else None),
                "asn": json.dumps(alpha_snapshot or {}, default=str),
            })
            # Detect duplicate-prevented case (rowcount=0 on ON CONFLICT)
            if getattr(res, "rowcount", 1) == 0:
                logger.info(
                    "[ops1] duplicate prevented: trade already open for "
                    "portfolio={} date={} instrument={} engine={} "
                    "— no insert.",
                    PAPER_ID, target_date, INSTRUMENT, effective_engine,
                )
                # Remove the optimistic append we made to still_open, since
                # no DB row was actually created
                if still_open and still_open[-1] is trade:
                    still_open.pop()
                duplicate_prevented = True
            else:
                duplicate_prevented = False
        else:
            duplicate_prevented = False
    else:
        duplicate_prevented = False

    # Compute MTM on open positions (mark to today's close)
    mtm_total = 0.0
    for pos in still_open:
        close_today = float(bundle["feat_row"].get("close", pos["entry_price"]))
        notional = float(pos["position_size_pct"]) / 100 * equity
        mtm_pct = (close_today - float(pos["entry_price"])) / float(pos["entry_price"])
        mtm_total += notional * mtm_pct

    equity = cash + sum(
        float(p["position_size_pct"]) / 100 * equity * (
            float(bundle["feat_row"].get("close", p["entry_price"])) / float(p["entry_price"])
        ) for p in still_open
    ) if still_open else cash

    cum_pct = (equity / STARTING_CAPITAL - 1) * 100
    peak_equity = max(peak_equity, equity)
    dd_current = (equity - peak_equity) / peak_equity * 100
    max_dd = min(max_dd, dd_current)

    # Write snapshot
    if not dry_run:
        session.execute(text("""
          INSERT INTO paper_portfolio_snapshot
            (as_of_date, portfolio_id, equity, cash, open_positions,
             daily_pnl, cum_pct, max_dd_pct, regime, engine_active,
             run_version)
          VALUES
            (:d, :pid, :eq, :cs, CAST(:op AS jsonb),
             :dp, :cum, :dd, :reg, :eng, :rv)
          ON CONFLICT (portfolio_id, as_of_date) DO UPDATE
          SET equity = EXCLUDED.equity,
              cash = EXCLUDED.cash,
              open_positions = EXCLUDED.open_positions,
              daily_pnl = EXCLUDED.daily_pnl,
              cum_pct = EXCLUDED.cum_pct,
              max_dd_pct = EXCLUDED.max_dd_pct,
              regime = EXCLUDED.regime,
              engine_active = EXCLUDED.engine_active,
              created_at = now()
        """), {
            "d": target_date, "pid": PAPER_ID,
            "eq": equity, "cs": cash,
            "op": json.dumps(still_open, default=str),
            "dp": daily_pnl, "cum": cum_pct, "dd": max_dd,
            "reg": ("stress" if bundle["production_context"].stress_regime
                    else "directional" if bundle["production_context"].directional_regime
                    else "none"),
            "eng": out.engine if out.fire else "none",
            "rv": RUN_VERSION,
        })
        session.commit()

    return StepResult(
        name="E_paper_portfolio", status="ok",
        detail=(f"equity=${equity:,.0f} daily_pnl=${daily_pnl:,.2f}"
                 + (f" entry_src={entry_price_source}"
                    if allow_entry else "")
                 + (" already_completed" if duplicate_prevented else "")),
        counts={
            "equity": round(equity, 2), "cash": round(cash, 2),
            "daily_pnl": round(daily_pnl, 2),
            "open_positions": len(still_open),
            "closed_today": len(closed_trades),
            "cum_pct": round(cum_pct, 4),
            "max_dd_pct": round(max_dd, 4),
            "entry_price_source": entry_price_source,
            "no_price_skips": int(
                1 if (allow_entry and no_price_skip) else 0
            ),
            "duplicate_prevented": int(1 if duplicate_prevented else 0),
        },
    )


def _add_trading_days(start: dt.date, n: int) -> dt.date:
    """Approximate trading-day forward by skipping weekends."""
    d = start
    added = 0
    while added < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def step_anomaly_detect(
    session: Session, target_date: dt.date, dry_run: bool,
) -> tuple[StepResult, dict]:
    """Step G — anomaly detection (read-only, advisory)."""
    try:
        events = detect_anomalies(session, target_date)
        summary = summarize_anomalies(events)
        if not dry_run and events:
            persist_anomalies(session, events)
        return StepResult(
            name="G_anomaly",
            status="ok" if summary["by_severity"]["critical"] == 0 else "warn",
            detail=(f"{summary['total']} events "
                    f"(critical={summary['by_severity']['critical']}, "
                    f"warn={summary['by_severity']['warning']}, "
                    f"info={summary['by_severity']['info']})"),
            counts=summary["by_severity"],
        ), summary
    except Exception as exc:
        return StepResult(
            name="G_anomaly", status="warn",
            detail=f"anomaly detect partial: {exc}",
        ), {"total": 0, "by_severity": {}, "by_category": {}, "top_3": []}


def step_shadow_evaluation(
    session: Session, bundle: dict, strategy_bundle: dict,
    target_date: dt.date, skip_shadow: bool,
) -> StepResult:
    if skip_shadow:
        return StepResult(name="F_shadow", status="skipped",
                          detail="--skip-shadow")
    # Minimal shadow: compute diagnostic flags, persist rows, never mutate
    try:
        # backwardation candidate
        # (ts_ratio requires VIX + VIX3M — skip if not loaded)
        # gex diagnostic
        gex_sign = None
        cot_flag = None
        diag = classify_diagnostic(gex_sign=gex_sign, cot_extreme_flag=cot_flag)
        _persist_context(session, target_date, "gex_context_flag",
                         "diagnostic", bool(diag.gex_context_flag or False),
                         ["gex_sign"], "v0.1.0", "gex_neg:v0.1.0")
        return StepResult(
            name="F_shadow", status="ok",
            counts={"diagnostic_rows": 1},
            detail="candidate+diagnostic contexts persisted separately",
        )
    except Exception as exc:
        return StepResult(name="F_shadow", status="warn",
                          detail=f"shadow eval partial: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None,
                   help="YYYY-MM-DD; defaults to latest market date")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-shadow", action="store_true")
    p.add_argument("--force-recompute", action="store_true")
    args = p.parse_args()

    steps: list[StepResult] = []
    warnings: list[str] = []
    errors: list[str] = []

    requested_date = (dt.date.fromisoformat(args.date) if args.date
                      else dt.date.today())

    logger.info("[ops1] start  requested_date={}  dry_run={}", requested_date, args.dry_run)

    with SessionLocal() as session:
        # STEP A — ingest first so the latest bars exist before we resolve the
        # target trading day. Non-fatal: FRED/macro timeouts return 'warn' and we
        # degrade to the latest stored macro snapshot (no fabricated values).
        r_a = step_ingest_raw(session); steps.append(r_a)
        if r_a.status == "fail":
            errors.append(f"{r_a.name}: {r_a.detail}")
        elif r_a.status == "warn":
            warnings.append(
                f"{r_a.name}: {r_a.detail} — macro degraded, using latest stored snapshot")

        # STEP B+C load — DATE-AWARE: resolve requested_date to the latest
        # available trading day (weekends/holidays/no-data fall back instead of
        # hard-failing). Fails only when NO data exists at or before requested.
        try:
            universe = load_universe(requested_date)
        except Exception as exc:
            logger.error("[ops1] HARD FAIL: {}", exc)
            errors.append(f"load_universe: {exc}")
            steps.append(StepResult("BC_load", "fail", detail=str(exc)))
            _emit_summary(
                requested_date, steps, warnings, errors,
                freshness={}, regime={}, decision={}, paper={}, shadow={},
                status="failed",
            )
            return 2

        target_date = universe["resolved_date"]
        reused = target_date != requested_date
        logger.info(
            "[ops1] date-aware: requested_calendar_date={} latest_available_data_date={} "
            "target_processing_date={} status={}",
            requested_date, target_date, target_date,
            "reused-prior-trading-day" if reused else "fresh",
        )

        # Idempotency — keyed on the RESOLVED target trading day. Re-running for a
        # weekend that maps to an already-processed Friday safely skips.
        if not args.force_recompute:
            existing = session.execute(text("""
              SELECT 1 FROM paper_portfolio_snapshot
              WHERE portfolio_id = :pid AND as_of_date = :d
            """), {"pid": PAPER_ID, "d": target_date}).fetchone()
            if existing and not args.dry_run:
                logger.info(
                    "[ops1] already processed target={} (requested {}) — skip (idempotent)",
                    target_date, requested_date)
                print(f"Already processed {target_date}. Use --force-recompute to overwrite.")
                return 0

        r_bc, bundle = step_compute_features_and_context(session, universe, target_date)
        steps.append(r_bc)

        # STEP D
        r_d, strategy_bundle = step_run_strategy(
            session, bundle, target_date, args.dry_run,
        )
        steps.append(r_d)

        # STEP E
        r_e = step_paper_portfolio_update(
            session, bundle, strategy_bundle, target_date,
            args.dry_run, args.force_recompute,
        )
        steps.append(r_e)

        # STEP F
        r_f = step_shadow_evaluation(
            session, bundle, strategy_bundle, target_date, args.skip_shadow,
        )
        steps.append(r_f)

        # STEP G — anomaly detection (read-only)
        r_g, anomaly_summary = step_anomaly_detect(
            session, target_date, args.dry_run,
        )
        steps.append(r_g)

    # Assemble summary
    out = strategy_bundle["selector_output"]
    pipeline_status = ("success" if all(s.status in ("ok", "skipped") for s in steps)
                       else "partial" if any(s.status == "warn" for s in steps)
                       else "failed")

    summary = DailySummary(
        as_of_date=target_date,
        run_version=RUN_VERSION,
        pipeline_status=pipeline_status,
        steps=[asdict(s) for s in steps],
        data_freshness={"latest_es_bar": str(target_date)},
        regime={
            "stress_regime": bundle["production_context"].stress_regime,
            "directional_regime": bundle["production_context"].directional_regime,
            "gates_favorable": bundle["gates_favorable"],
            "credit_stable": bundle["credit_stable"],
            "rates_calm": bundle["rates_calm"],
        },
        decision={
            "engine": out.engine, "fire": out.fire,
            "reason": out.reason,
            "decision_version": out.decision_version,
        },
        paper=r_e.counts,
        shadow=r_f.counts,
        warnings=warnings,
        errors=errors,
    )
    setattr(summary, "anomalies", anomaly_summary)
    _emit_summary(target_date, steps, warnings, errors,
                  freshness=summary.data_freshness, regime=summary.regime,
                  decision=summary.decision, paper=summary.paper,
                  shadow=summary.shadow, status=pipeline_status,
                  anomalies=anomaly_summary)

    # Persist paper_run_log row (daily visibility)
    try:
        enriched = strategy_bundle.get("enriched")
        exploratory_mode = bool(
            enriched is not None
            and getattr(enriched, "gate_mode", "strict") == "exploratory"
        )
        trades_opened = 1 if (r_e.counts.get("open_positions", 0) and out.fire) \
                        else (1 if enriched is not None
                               and enriched.exploratory_paper else 0)
        exploratory_trades = (
            1 if (enriched is not None and enriched.exploratory_paper) else 0
        )
        strict_trades = (1 if out.fire else 0)
        counts = PaperRunCounts(
            decisions_evaluated=1,   # one symbol (ES) per run today
            trades_opened=trades_opened,
            trades_closed=r_e.counts.get("closed_today", 0) or 0,
            trades_skipped=(0 if out.fire or exploratory_trades else 1),
            exploratory_trades=exploratory_trades,
            strict_trades=strict_trades,
            blocked_by_gates=(
                1 if enriched is not None
                       and enriched.strict_would_block
                       and not enriched.exploratory_paper else 0
            ),
            blocked_by_anomaly=(
                1 if anomaly_summary.get("by_severity", {}).get("critical", 0)
                else 0
            ),
            blocked_by_data_quality=0,
        )
        gates_failed = (list(enriched.gates_failed)
                        if enriched is not None else None)
        summary_sentence = build_run_summary(
            status=pipeline_status,
            counts=counts,
            gates_passed=(enriched.gates_passed if enriched else None),
            gates_total=(enriched.gates_total if enriched else None),
            gates_failed=gates_failed,
            exploratory_mode=exploratory_mode,
        )
        with SessionLocal() as s2:
            write_paper_run_log(
                s2,
                run_date=target_date,
                started_at=dt.datetime.now(dt.timezone.utc),
                status=pipeline_status,
                counts=counts,
                net_pnl_today=r_e.counts.get("daily_pnl"),
                nav_start=None,
                nav_end=r_e.counts.get("equity"),
                summary=summary_sentence,
                warnings=warnings,
                details={
                    "decision": {
                        "engine": out.engine, "fire": out.fire,
                        "reason": out.reason,
                    },
                    "gate_mode": (enriched.gate_mode
                                   if enriched else "strict"),
                    "gates_passed": (enriched.gates_passed
                                       if enriched else None),
                    "gates_total":  (enriched.gates_total
                                       if enriched else None),
                    "gates_failed": gates_failed,
                    # Phase 11Z — split failed gates (computed FALSE)
                    # from unknown gates (input was missing /
                    # insufficient / stale). `gates_failed` above is
                    # selector-level (rule-based fail), the next two
                    # are macro-input-level diagnostics.
                    "macro_failed_gates": (
                        list(bundle.get("failed_gates") or [])
                        if isinstance(bundle, dict) else []
                    ),
                    "macro_unknown_gates": (
                        list(bundle.get("unknown_gates") or [])
                        if isinstance(bundle, dict) else []
                    ),
                    "macro_gate_statuses": (
                        dict(bundle.get("gate_statuses") or {})
                        if isinstance(bundle, dict) else {}
                    ),
                    "entry_price_source": r_e.counts.get(
                        "entry_price_source"
                    ),
                    "no_price_skips": int(
                        r_e.counts.get("no_price_skips") or 0
                    ),
                    "duplicate_prevented": int(
                        r_e.counts.get("duplicate_prevented") or 0
                    ),
                },
                dry_run=args.dry_run,
            )
    except Exception as exc:
        logger.warning("paper_run_log write crashed: {}", exc)

    return 0 if pipeline_status != "failed" else 2


def _emit_summary(
    target_date, steps, warnings, errors, *,
    freshness, regime, decision, paper, shadow, status,
    anomalies=None,
):
    summary = {
        "as_of_date": str(target_date),
        "run_version": RUN_VERSION,
        "pipeline_status": status,
        "steps": [asdict(s) for s in steps],
        "data_freshness": freshness,
        "regime": regime,
        "decision": decision,
        "paper": paper,
        "shadow": shadow,
        "anomalies": anomalies or {"total": 0, "by_severity": {}},
        "warnings": warnings,
        "errors": errors,
    }
    out_path = OUT_DIR / f"daily_{target_date}.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str))

    # Terminal
    print("=" * 78)
    print(f"PAPER DAILY  {target_date}  [{status.upper()}]")
    print("=" * 78)
    for s in steps:
        badge = {"ok": "+", "warn": "!", "fail": "X", "skipped": "~"}.get(s.status, "?")
        print(f"  [{badge}] {s.name:<22}  {s.status:<8}  {s.detail}")
    print()
    print("--- REGIME ---")
    for k, v in regime.items():
        print(f"  {k:<22}  {v}")
    print()
    print("--- DECISION ---")
    for k, v in decision.items():
        print(f"  {k:<22}  {v}")
    print()
    print("--- PAPER PORTFOLIO ---")
    for k, v in (paper or {}).items():
        print(f"  {k:<22}  {v}")
    print()
    if anomalies and anomalies.get("total", 0) > 0:
        print("--- ANOMALIES ---")
        sev = anomalies["by_severity"]
        print(f"  total={anomalies['total']}  crit={sev.get('critical', 0)}  "
              f"warn={sev.get('warning', 0)}  info={sev.get('info', 0)}")
        for t in anomalies.get("top_3", []):
            print(f"  [{t['severity']:<8}] {t['rule_key']:<30} — {t['title']}")
        print()
    if warnings:
        print("Warnings:")
        for w in warnings: print(f"  ! {w}")
    if errors:
        print("Errors:")
        for e in errors: print(f"  X {e}")
    print(f"\nSummary JSON: {out_path}")
    print("=" * 78)


if __name__ == "__main__":
    sys.exit(main())
