"""Phase 11P.5 - DB layer for paper observation labels.

Reads pending observations from the strict + exploratory + options
paper data, fetches forward prices from existing tables, computes
deterministic labels via `forward_returns.label_for_observation`,
appends rows to `paper_observation_label`. Re-runs are idempotent
(UNIQUE constraints + provisional UPDATE path).

NEVER writes to strict-engine tables. NEVER writes to paper_position
or paper_trade. NEVER imports broker / live / execution modules.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.labeling.forward_returns import (
    DEFAULT_THRESHOLD_PCT,
    LABEL_VERSION,
    label_for_observation,
)


HORIZONS = (1, 3, 5, 10, 20)
PRIMARY_HORIZON = 20


# ---------------------------------------------------------------------------
# Config / models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabellerConfig:
    domain: str                               # 'equity' | 'options' | 'both'
    as_of_date: dt.date
    horizon_days: int
    threshold_pct: Decimal
    dry_run: bool
    commit: bool
    reprocess_provisional: bool
    label_version: str

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError("dry_run and commit are mutually exclusive")
        if self.domain not in ("equity", "options", "both"):
            raise ValueError(
                f"domain must be equity|options|both (got {self.domain!r})"
            )
        if self.horizon_days != 20:
            raise ValueError("horizon_days is frozen at 20 in v1")
        if self.threshold_pct <= 0:
            raise ValueError("threshold_pct must be > 0")


@dataclass(frozen=True)
class LabellerSummary:
    config: LabellerConfig
    n_equity_observations: int
    n_options_observations: int
    n_inserted: int
    n_updated_provisional: int
    n_skipped_existing: int


# ---------------------------------------------------------------------------
# Equity domain — reads from decision_log + price_bar
# ---------------------------------------------------------------------------

def _equity_pending_rows(
    session: Session, *, max_entry_date: dt.date,
) -> list[dict]:
    """Return decision_log rows that:
      - are tagged source IN ('strict_paper','exploratory_paper')
      - have entry_date <= max_entry_date − horizon (so 20-day forward
        is computable)
      - are not yet labeled in paper_observation_label
    """
    cutoff = max_entry_date - dt.timedelta(days=PRIMARY_HORIZON)
    rows = session.execute(text(
        """
        SELECT
            d.id::text          AS id,
            d.as_of_date        AS entry_date,
            d.instrument        AS symbol,
            d.engine            AS engine,
            d.source            AS source,
            d.failed_gates      AS failed_gates,
            d.context_values    AS context_values,
            d.action            AS action
        FROM decision_log d
        LEFT JOIN paper_observation_label l
          ON l.domain = 'equity'
         AND l.paper_decision_log_id = d.id
         AND l.label_version = :lv
        WHERE d.source IN ('strict_paper', 'exploratory_paper')
          AND d.as_of_date <= :cutoff
          AND l.id IS NULL
        ORDER BY d.as_of_date
        """
    ), {"cutoff": cutoff, "lv": LABEL_VERSION}).all()
    return [dict(r._mapping) for r in rows]


def _equity_forward_prices(
    session: Session,
    *,
    symbol: str,
    entry_date: dt.date,
) -> tuple[Decimal | None, dict[int, Decimal | None], list[Decimal]]:
    """Returns (entry_price, prices_by_horizon, prices_full_window)."""
    rows = session.execute(text(
        """
        SELECT pb.ts::date AS d, pb.adjusted_close AS px
        FROM price_bar pb
        JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = :sym
          AND pb.timeframe = '1d'
          AND pb.ts::date BETWEEN :start AND :end
        ORDER BY pb.ts::date
        """
    ), {
        "sym": symbol, "start": entry_date,
        "end": entry_date + dt.timedelta(days=PRIMARY_HORIZON + 10),
    }).all()
    if not rows:
        return None, {h: None for h in HORIZONS}, []
    by_date = {r.d: Decimal(str(r.px)) for r in rows}
    bdays = sorted(by_date.keys())
    if entry_date not in by_date:
        # Walk forward to next available bar (e.g. weekend entries)
        future = [d for d in bdays if d >= entry_date]
        if not future:
            return None, {h: None for h in HORIZONS}, []
        entry_date = future[0]
    entry_price = by_date.get(entry_date)
    bdays_after = [d for d in bdays if d > entry_date]
    by_horizon: dict[int, Decimal | None] = {}
    for h in HORIZONS:
        if h - 1 < len(bdays_after):
            by_horizon[h] = by_date.get(bdays_after[h - 1])
        else:
            by_horizon[h] = None
    full_window = [
        by_date[d] for d in bdays_after[:PRIMARY_HORIZON]
    ]
    return entry_price, by_horizon, full_window


# ---------------------------------------------------------------------------
# Options domain — reads from options_paper_trade
# ---------------------------------------------------------------------------

def _options_pending_rows(
    session: Session, *, max_entry_date: dt.date,
) -> list[dict]:
    cutoff = max_entry_date - dt.timedelta(days=PRIMARY_HORIZON)
    rows = session.execute(text(
        """
        SELECT
            t.id                AS trade_id,
            t.opened_at::date   AS entry_date,
            t.underlying        AS symbol,
            t.strategy_name     AS rule_id,
            t.entry_credit_dollars AS entry_credit_dollars,
            t.realized_pnl_dollars AS realized_pnl_dollars,
            t.status            AS status,
            t.paper_only        AS paper_only
        FROM options_paper_trade t
        LEFT JOIN paper_observation_label l
          ON l.domain = 'options'
         AND l.options_paper_trade_id = t.id
         AND l.label_version = :lv
        WHERE t.paper_only = TRUE
          AND t.opened_at::date <= :cutoff
          AND l.id IS NULL
        ORDER BY t.opened_at::date
        """
    ), {"cutoff": cutoff, "lv": LABEL_VERSION}).all()
    return [dict(r._mapping) for r in rows]


def _options_forward_prices(
    session: Session,
    *,
    symbol: str,
    entry_date: dt.date,
) -> tuple[Decimal | None, dict[int, Decimal | None], list[Decimal]]:
    """For options the forward prices are the underlying — same as
    equity. Lets us reuse the same labeling math without confusing the
    options paper P&L (which is encoded in `realized_pnl_dollars`)."""
    return _equity_forward_prices(
        session, symbol=symbol, entry_date=entry_date,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_INSERT_LABEL_SQL = text(
    """
    INSERT INTO paper_observation_label
      (domain, source,
       paper_decision_log_id, paper_trade_id,
       options_paper_trade_id, options_observation_id,
       entry_date, symbol, rule_id, failed_gates, gate_snapshot,
       entry_price,
       return_1d, return_3d, return_5d, return_10d, return_20d,
       max_adverse_excursion, max_favorable_excursion,
       outcome_class, outcome_threshold_pct, label_confidence,
       label_version, is_provisional)
    VALUES
      (:domain, :source,
       :paper_decision_log_id, :paper_trade_id,
       :options_paper_trade_id, :options_observation_id,
       :entry_date, :symbol, :rule_id, :failed_gates,
       CAST(:gate_snapshot AS jsonb),
       :entry_price,
       :return_1d, :return_3d, :return_5d, :return_10d, :return_20d,
       :max_adverse_excursion, :max_favorable_excursion,
       :outcome_class, :outcome_threshold_pct, :label_confidence,
       :label_version, :is_provisional)
    ON CONFLICT DO NOTHING
    """
)

_UPDATE_PROVISIONAL_SQL = text(
    """
    UPDATE paper_observation_label
    SET return_1d              = :return_1d,
        return_3d              = :return_3d,
        return_5d              = :return_5d,
        return_10d             = :return_10d,
        return_20d             = :return_20d,
        max_adverse_excursion  = :max_adverse_excursion,
        max_favorable_excursion= :max_favorable_excursion,
        outcome_class          = :outcome_class,
        outcome_threshold_pct  = :outcome_threshold_pct,
        label_confidence       = :label_confidence,
        is_provisional         = FALSE,
        computed_at            = now()
    WHERE id = :id
      AND is_provisional = TRUE
    """
)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _build_label_row(
    *,
    domain: str,
    source: str,
    obs: dict,
    entry_price: Decimal | None,
    label: dict,
    is_provisional: bool,
    paper_decision_log_id: str | None = None,
    paper_trade_id: int | None = None,
    options_paper_trade_id: int | None = None,
    options_observation_id: str | None = None,
    rule_id: str | None = None,
    failed_gates: Sequence[str] | None = None,
    gate_snapshot: dict | None = None,
) -> dict:
    return {
        "domain": domain,
        "source": source,
        "paper_decision_log_id": paper_decision_log_id,
        "paper_trade_id": paper_trade_id,
        "options_paper_trade_id": options_paper_trade_id,
        "options_observation_id": options_observation_id,
        "entry_date": obs["entry_date"],
        "symbol": obs["symbol"],
        "rule_id": rule_id,
        "failed_gates": list(failed_gates or []),
        "gate_snapshot": json.dumps(gate_snapshot or {}, default=str),
        "entry_price": entry_price,
        "return_1d":  label["return_1d"],
        "return_3d":  label["return_3d"],
        "return_5d":  label["return_5d"],
        "return_10d": label["return_10d"],
        "return_20d": label["return_20d"],
        "max_adverse_excursion":  label["max_adverse_excursion"],
        "max_favorable_excursion": label["max_favorable_excursion"],
        "outcome_class": label["outcome_class"],
        "outcome_threshold_pct": label["outcome_threshold_pct"],
        "label_confidence": label["label_confidence"],
        "label_version": label["label_version"],
        "is_provisional": is_provisional,
    }


def run_equity(
    session: Session,
    *,
    cfg: LabellerConfig,
) -> tuple[int, int]:
    pending = _equity_pending_rows(session, max_entry_date=cfg.as_of_date)
    n_inserted = 0
    n_skipped = 0
    for obs in pending:
        entry_price, by_horizon, window = _equity_forward_prices(
            session, symbol=obs["symbol"], entry_date=obs["entry_date"],
        )
        label = label_for_observation(
            entry_price=entry_price,
            prices_by_horizon=by_horizon,
            prices_full_window=window,
            threshold_pct=cfg.threshold_pct,
            primary_horizon=PRIMARY_HORIZON,
        )
        is_provisional = (
            label["return_20d"] is None
            or entry_price is None
        )
        ctx = obs.get("context_values") or {}
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except Exception:  # noqa: BLE001
                ctx = {}
        params = _build_label_row(
            domain="equity",
            source=obs["source"],
            obs=obs,
            entry_price=entry_price,
            label=label,
            is_provisional=is_provisional,
            paper_decision_log_id=obs["id"],
            rule_id=obs.get("engine"),
            failed_gates=obs.get("failed_gates") or [],
            gate_snapshot=ctx if isinstance(ctx, dict) else {},
        )
        if cfg.commit:
            r = session.execute(_INSERT_LABEL_SQL, params)
            if r.rowcount and r.rowcount > 0:
                n_inserted += 1
            else:
                n_skipped += 1
    return n_inserted, n_skipped


def run_options(
    session: Session,
    *,
    cfg: LabellerConfig,
) -> tuple[int, int]:
    pending = _options_pending_rows(
        session, max_entry_date=cfg.as_of_date,
    )
    n_inserted = 0
    n_skipped = 0
    for obs in pending:
        entry_price, by_horizon, window = _options_forward_prices(
            session, symbol=obs["symbol"], entry_date=obs["entry_date"],
        )
        label = label_for_observation(
            entry_price=entry_price,
            prices_by_horizon=by_horizon,
            prices_full_window=window,
            threshold_pct=cfg.threshold_pct,
            primary_horizon=PRIMARY_HORIZON,
        )
        is_provisional = (
            label["return_20d"] is None
            or entry_price is None
        )
        params = _build_label_row(
            domain="options",
            source="options_paper",
            obs=obs,
            entry_price=entry_price,
            label=label,
            is_provisional=is_provisional,
            options_paper_trade_id=obs["trade_id"],
            rule_id=obs.get("rule_id"),
            failed_gates=[],
            gate_snapshot={
                "status": obs.get("status"),
                "entry_credit_dollars":
                    str(obs.get("entry_credit_dollars"))
                    if obs.get("entry_credit_dollars") is not None
                    else None,
            },
        )
        if cfg.commit:
            r = session.execute(_INSERT_LABEL_SQL, params)
            if r.rowcount and r.rowcount > 0:
                n_inserted += 1
            else:
                n_skipped += 1
    return n_inserted, n_skipped


def reprocess_provisional(
    session: Session,
    *,
    cfg: LabellerConfig,
) -> int:
    """Re-evaluate provisional rows whose horizon has now elapsed.
    Only mutates rows where is_provisional=TRUE — never overwrites a
    finalized label."""
    cutoff = cfg.as_of_date - dt.timedelta(days=PRIMARY_HORIZON)
    rows = session.execute(text(
        """
        SELECT id, domain, symbol, entry_date,
               entry_price, outcome_threshold_pct
        FROM paper_observation_label
        WHERE is_provisional = TRUE
          AND label_version = :lv
          AND entry_date <= :cutoff
        """
    ), {"lv": cfg.label_version, "cutoff": cutoff}).all()
    n_updated = 0
    for r in rows:
        threshold = (
            Decimal(str(r.outcome_threshold_pct))
            if r.outcome_threshold_pct is not None
            else cfg.threshold_pct
        )
        if r.domain == "equity":
            entry_price, by_horizon, window = _equity_forward_prices(
                session, symbol=r.symbol, entry_date=r.entry_date,
            )
        else:
            entry_price, by_horizon, window = _options_forward_prices(
                session, symbol=r.symbol, entry_date=r.entry_date,
            )
        if entry_price is None or by_horizon.get(PRIMARY_HORIZON) is None:
            continue
        label = label_for_observation(
            entry_price=entry_price,
            prices_by_horizon=by_horizon,
            prices_full_window=window,
            threshold_pct=threshold,
            primary_horizon=PRIMARY_HORIZON,
        )
        if cfg.commit:
            res = session.execute(_UPDATE_PROVISIONAL_SQL, {
                "id": r.id,
                "return_1d":  label["return_1d"],
                "return_3d":  label["return_3d"],
                "return_5d":  label["return_5d"],
                "return_10d": label["return_10d"],
                "return_20d": label["return_20d"],
                "max_adverse_excursion":
                    label["max_adverse_excursion"],
                "max_favorable_excursion":
                    label["max_favorable_excursion"],
                "outcome_class": label["outcome_class"],
                "outcome_threshold_pct":
                    label["outcome_threshold_pct"],
                "label_confidence": label["label_confidence"],
            })
            if res.rowcount and res.rowcount > 0:
                n_updated += 1
    return n_updated


def run(
    cfg: LabellerConfig,
    *,
    session_factory=None,
) -> LabellerSummary:
    sf = session_factory or SessionLocal
    n_equity = 0
    n_options = 0
    n_inserted = 0
    n_skipped = 0
    n_updated = 0
    with sf() as session:
        if cfg.domain in ("equity", "both"):
            ni, ns = run_equity(session, cfg=cfg)
            n_equity = ni + ns
            n_inserted += ni
            n_skipped += ns
        if cfg.domain in ("options", "both"):
            ni, ns = run_options(session, cfg=cfg)
            n_options = ni + ns
            n_inserted += ni
            n_skipped += ns
        if cfg.reprocess_provisional:
            n_updated = reprocess_provisional(session, cfg=cfg)
        if cfg.commit:
            session.commit()
    summary = LabellerSummary(
        config=cfg,
        n_equity_observations=n_equity,
        n_options_observations=n_options,
        n_inserted=n_inserted,
        n_updated_provisional=n_updated,
        n_skipped_existing=n_skipped,
    )
    logger.info(
        "phase 11P labeller complete: dry_run={} domain={} "
        "inserted={} updated={} skipped={}",
        cfg.dry_run, cfg.domain, summary.n_inserted,
        summary.n_updated_provisional, summary.n_skipped_existing,
    )
    return summary
