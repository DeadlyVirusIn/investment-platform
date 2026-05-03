"""Replayer — generate synthetic decisions over historical dates.

For each (as_of_date, symbol) pair:
  1. build PIT price window
  2. compute PIT features (vol / range / z / momentum)
  3. build PIT catalyst summary (db only)
  4. derive a minimal regime context from PIT bars
  5. run a deterministic selector mirroring Engine A + Engine B rules
  6. emit ml_replay_decision row (never touches decision_log)

Engines are REPLAY-MODE: they do not read live portfolio state. Everything
consumed is a function of PIT data only.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.catalysts.types import CatalystSummary, TradePolicy
from apps.api.src.ml.replay.pit_catalyst import PITCatalystService
from apps.api.src.ml.replay.point_in_time import (
    PointInTimeDataAccessor,
)

REPLAY_VERSION = "replayer-v1.0.0"


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplayRunConfig:
    replay_name: str
    start_date: dt.date
    end_date: dt.date
    universe: tuple[str, ...]
    max_symbols: int | None = None
    dry_run: bool = False
    bar_symbol_map: dict[str, str] = field(default_factory=dict)
    # Business-day sampling: replay every Nth trading day in the window
    every_n_days: int = 1


@dataclass
class ReplayRunResult:
    run_id: str
    n_decisions: int
    n_symbols: int
    n_dates: int
    warnings: list[str] = field(default_factory=list)
    persisted: bool = False


# ---------------------------------------------------------------------------
# replayer
# ---------------------------------------------------------------------------

class Replayer:
    def __init__(self, session: Session):
        self._session = session
        self._pit = PointInTimeDataAccessor(session)
        self._cat = PITCatalystService(session)

    def run(self, cfg: ReplayRunConfig) -> ReplayRunResult:
        if cfg.start_date > cfg.end_date:
            raise ValueError(
                f"start_date {cfg.start_date} > end_date {cfg.end_date}"
            )
        today = dt.date.today()
        if cfg.end_date > today:
            raise ValueError(
                f"end_date {cfg.end_date} must be ≤ today {today}"
            )
        universe = list(cfg.universe)
        if cfg.max_symbols:
            universe = universe[: cfg.max_symbols]

        run_id = self._create_run_row(cfg, universe)
        warnings: list[str] = []
        n_decisions = 0
        n_dates = 0

        trading_days = _business_days(cfg.start_date, cfg.end_date)
        if cfg.every_n_days > 1:
            trading_days = trading_days[::cfg.every_n_days]

        for as_of in trading_days:
            n_dates += 1
            for sym in universe:
                record = self._replay_one(sym, as_of, cfg)
                if record is None:
                    continue
                if not cfg.dry_run:
                    self._persist_decision(run_id, record)
                n_decisions += 1
            # Periodic commit to keep txn small
            if not cfg.dry_run and n_dates % 10 == 0:
                self._session.commit()

        if not cfg.dry_run:
            self._update_run_status(
                run_id,
                status="completed",
                summary={
                    "n_decisions": n_decisions,
                    "n_symbols": len(universe),
                    "n_dates": n_dates,
                    "warnings": warnings,
                    "replay_version": REPLAY_VERSION,
                },
            )
            self._session.commit()
        else:
            logger.info("replay dry-run: not persisting; run_id synthetic")

        return ReplayRunResult(
            run_id=run_id, n_decisions=n_decisions,
            n_symbols=len(universe), n_dates=n_dates,
            warnings=warnings, persisted=not cfg.dry_run,
        )

    # ------------------------------------------------------------------
    # per-row replay
    # ------------------------------------------------------------------

    def _replay_one(
        self, symbol: str, as_of: dt.date, cfg: ReplayRunConfig,
    ) -> dict[str, Any] | None:
        bars = self._pit.get_bars(symbol, as_of=as_of, lookback_days=200)
        if bars.empty or len(bars) < 40:
            return None
        # Features
        feats, feat_ts_max = _compute_pit_features(bars)
        if feat_ts_max is None or feat_ts_max > as_of:
            # Defensive — PIT accessor already filters, but verify
            return None
        # Catalyst (db-only, PIT)
        catalyst = self._cat.summary_for(symbol, as_of=as_of)
        # Regime — simple PIT proxy
        regime = _regime_from_features(feats)
        # Anomaly — none in replay (we don't replay anomalies)
        anomaly = {"present": False, "note": "not replayed"}
        # Selector — mirrors Engines A/B rules with replay-safe inputs
        decision, confidence, engine, skip_reason = _replay_selector(
            feats=feats, regime=regime, catalyst=catalyst,
        )
        data_quality = _replay_data_quality(feats, catalyst)
        advisory = {
            "suggested_action": "needs_more_data",
            "reason": "replay=true; not advisory-eligible until real-log backed",
        }
        provenance = {
            "replay_version": REPLAY_VERSION,
            "replayer": "Replayer",
            "replay_name": cfg.replay_name,
            "sources": {
                "bars": "market_series_observation",
                "catalyst": "news_item+earnings_event (db-only)",
                "catalyst_partial": catalyst.partial,
            },
            "feature_timestamps": {
                "price_bar_last": feat_ts_max.isoformat(),
            },
        }
        return {
            "id": str(uuid.uuid4()),
            "as_of_date": as_of,
            "decision_ts": dt.datetime.combine(
                as_of, dt.time(16, 0), tzinfo=dt.timezone.utc,
            ),
            "symbol": symbol,
            "engine": engine,
            "decision": decision,
            "confidence": confidence,
            "features": feats,
            "data_quality": data_quality,
            "catalyst": catalyst.to_dict(),
            "regime": regime,
            "anomaly": anomaly,
            "advisory": advisory,
            "missing_features": [],
            "skip_reason": skip_reason,
            "provenance": provenance,
        }

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _create_run_row(
        self, cfg: ReplayRunConfig, universe: list[str],
    ) -> str:
        if cfg.dry_run:
            return f"dryrun-{uuid.uuid4()}"
        row = self._session.execute(text("""
            INSERT INTO ml_replay_run
              (replay_name, replay_version, start_date, end_date,
               universe, engine_versions, config, provider_priority, status)
            VALUES
              (:name, :ver, :start, :end,
               CAST(:uni AS jsonb), CAST(:ev AS jsonb),
               CAST(:cfg AS jsonb), CAST(:pp AS jsonb),
               'running')
            RETURNING id
        """), {
            "name": cfg.replay_name,
            "ver":  REPLAY_VERSION,
            "start": cfg.start_date,
            "end":   cfg.end_date,
            "uni":   json.dumps(list(universe)),
            "ev":    json.dumps({"A": "engineA-v1.0.0",
                                  "B": "engineB-v1.0.0"}),
            "cfg":   json.dumps({
                "every_n_days": cfg.every_n_days,
                "max_symbols":  cfg.max_symbols,
                "dry_run":      cfg.dry_run,
            }),
            "pp":    json.dumps(["db-only"]),
        }).fetchone()
        self._session.commit()
        return str(row[0])

    def _update_run_status(
        self, run_id: str, *, status: str, summary: dict[str, Any],
    ) -> None:
        self._session.execute(text("""
            UPDATE ml_replay_run
               SET status = :st,
                   summary = CAST(:sm AS jsonb)
             WHERE id = :id
        """), {"st": status, "sm": json.dumps(summary), "id": run_id})

    def _persist_decision(self, run_id: str, rec: dict[str, Any]) -> None:
        self._session.execute(text("""
            INSERT INTO ml_replay_decision
              (id, replay_run_id, as_of_date, decision_ts, symbol,
               engine, decision, confidence,
               features, data_quality, catalyst, regime, anomaly,
               advisory, missing_features, skip_reason, provenance)
            VALUES
              (:id, :run, :asof, :ts, :sym,
               :eng, :dec, :conf,
               CAST(:feat AS jsonb), CAST(:dq AS jsonb),
               CAST(:cat AS jsonb), CAST(:reg AS jsonb),
               CAST(:an AS jsonb),
               CAST(:adv AS jsonb), CAST(:miss AS jsonb), :skip,
               CAST(:prov AS jsonb))
        """), {
            "id":   rec["id"],
            "run":  run_id,
            "asof": rec["as_of_date"],
            "ts":   rec["decision_ts"],
            "sym":  rec["symbol"],
            "eng":  rec["engine"],
            "dec":  rec["decision"],
            "conf": rec["confidence"],
            "feat": json.dumps(rec["features"], default=str),
            "dq":   json.dumps(rec["data_quality"], default=str),
            "cat":  json.dumps(rec["catalyst"], default=str),
            "reg":  json.dumps(rec["regime"], default=str),
            "an":   json.dumps(rec["anomaly"], default=str),
            "adv":  json.dumps(rec["advisory"], default=str),
            "miss": json.dumps(rec["missing_features"], default=str),
            "skip": rec["skip_reason"],
            "prov": json.dumps(rec["provenance"], default=str),
        })


# ---------------------------------------------------------------------------
# feature computation (PIT only)
# ---------------------------------------------------------------------------

def _compute_pit_features(bars: pd.DataFrame) -> tuple[dict[str, Any], dt.date | None]:
    """All features computed strictly from rows in `bars`. Returns the max
    bar date used so caller can verify it's ≤ as_of."""
    if bars.empty:
        return {}, None
    df = bars.copy().sort_values("date")
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    if len(close) < 30:
        return {}, df["date"].max()
    rets = close.pct_change().dropna()
    mean20 = rets.tail(20).mean()
    std20 = rets.tail(20).std(ddof=0)
    z_score = (
        float((rets.iloc[-1] - mean20) / std20) if std20 > 1e-9 else 0.0
    )
    # ATR proxies
    tr = (high - low).dropna()
    atr10 = float(tr.tail(10).mean()) if len(tr) >= 10 else 0.0
    atr50 = float(tr.tail(50).mean()) if len(tr) >= 50 else 0.0
    atr_ratio = atr10 / atr50 if atr50 > 1e-9 else 1.0

    vol20 = float(rets.tail(20).std(ddof=0))
    vol60 = float(rets.tail(60).std(ddof=0)) if len(rets) >= 60 else vol20
    vol_expanding = 1 if vol20 > vol60 * 1.1 else 0
    vol_elevated = 1 if vol20 > (vol60 * 1.25) else 0

    # 20-period high/low range-loose proxy
    hh = close.tail(20).max()
    ll = close.tail(20).min()
    loose = 1 if (hh - ll) / max(1e-9, ll) > 0.06 else 0

    feats = {
        "z_score": _num(z_score),
        "atr_ratio": _num(atr_ratio),
        "atr10": _num(atr10),
        "atr50": _num(atr50),
        "vol_20d": _num(vol20),
        "vol_60d": _num(vol60),
        "vol_elevated": int(vol_elevated),
        "vol_expanding": int(vol_expanding),
        "range_loose": int(loose),
        "last_close": _num(float(close.iloc[-1])),
        "mean_20d_ret": _num(float(mean20)),
    }
    return feats, df["date"].max()


def _regime_from_features(f: dict[str, Any]) -> dict[str, Any]:
    vol_elev = bool(f.get("vol_elevated"))
    vol_exp = bool(f.get("vol_expanding"))
    loose = bool(f.get("range_loose"))
    mean_ret = float(f.get("mean_20d_ret") or 0.0)
    stress = vol_elev and loose
    directional = (not stress) and mean_ret > 0.0005 and (not vol_exp)
    return {
        "stress_regime": bool(stress),
        "directional_regime": bool(directional),
        "neutral_regime": not (stress or directional),
        "gates_favorable": int(directional) + int(not stress)
                           + int(mean_ret > 0) + int(not vol_exp),
    }


def _replay_selector(
    *, feats: dict[str, Any], regime: dict[str, Any],
    catalyst: CatalystSummary,
) -> tuple[str, float, str, str | None]:
    """Deterministic Engine A / Engine B mirror. No live state."""
    if catalyst.trade_policy == TradePolicy.BLOCK_NEW_ENTRY:
        return ("skip", 0.0, "none",
                "catalyst blocks new entry")
    # Engine A — stress mean-reversion
    if regime["stress_regime"] and feats.get("z_score", 0.0) < -1 \
       and feats.get("range_loose") and feats.get("vol_elevated"):
        return ("enter_long", 0.6, "A", None)
    # Engine B — directional (credit/rates alignment proxy simplified)
    if regime["directional_regime"] and feats.get("mean_20d_ret", 0.0) > 0:
        return ("enter_long", 0.55, "B", None)
    return ("no_fire", 0.0, "none",
            "no engine conditions met")


def _replay_data_quality(
    feats: dict[str, Any], catalyst: CatalystSummary,
) -> dict[str, Any]:
    missing: list[str] = []
    if not feats:
        missing.append("features")
    if catalyst.partial:
        missing.append("catalyst")
    # Base confidence from feature completeness + catalyst partial flag
    conf = 1.0
    if catalyst.partial:
        conf *= 0.8
    if not feats:
        conf = 0.0
    return {
        "confidence": round(conf, 4),
        "missing_fields": missing,
        "stale_fields": [],
        "provider_usage": {"db": 1},
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _business_days(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        if not np.isfinite(x):
            return None
        return x
    except (TypeError, ValueError):
        return None
