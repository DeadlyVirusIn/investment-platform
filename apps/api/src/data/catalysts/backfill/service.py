"""Backfill orchestrator — per-symbol per-window fan-out with dedupe.

Never raises: all provider failures captured as warnings per symbol. Writes
are idempotent (UPSERT on dedupe_key) so re-runs are safe.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProvider, BackfillProviderError,
    EarningsRecord, NewsRecord,
)
from apps.api.src.data.catalysts.backfill.alpha_vantage import (
    AlphaVantageBackfillProvider,
)
from apps.api.src.data.catalysts.backfill.dedupe import (
    earnings_dedupe_key, news_dedupe_key,
)
from apps.api.src.data.catalysts.backfill.finnhub import (
    FinnhubBackfillProvider,
)
from apps.api.src.data.catalysts.backfill.fmp import FMPBackfillProvider
from apps.api.src.data.catalysts.backfill.rate_limit import RateLimiter
from apps.api.src.data.catalysts.backfill.yahoo import (
    YahooBackfillProvider,
)


_PROVIDERS: dict[str, Any] = {
    "finnhub": FinnhubBackfillProvider,
    "yahoo":   YahooBackfillProvider,
    "alpha_vantage": AlphaVantageBackfillProvider,
    "fmp":     FMPBackfillProvider,
}


@dataclass(frozen=True)
class BackfillRunConfig:
    symbols: tuple[str, ...]
    start_date: dt.date
    end_date: dt.date
    providers: tuple[str, ...]
    window_days: int = 30
    rate_limit_per_min: int = 60
    dry_run: bool = True


@dataclass
class BackfillRunResult:
    run_id: str
    news_inserted: int = 0
    news_skipped: int = 0
    earnings_inserted: int = 0
    earnings_skipped: int = 0
    provider_errors: list[str] = field(default_factory=list)
    symbol_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    persisted: bool = False


# ---------------------------------------------------------------------------
class BackfillService:
    def __init__(
        self, session: Session,
        *,
        rate_limiter: RateLimiter | None = None,
    ):
        self._session = session
        self._rl = rate_limiter

    # ------------------------------------------------------------------
    def run(self, cfg: BackfillRunConfig) -> BackfillRunResult:
        if cfg.start_date > cfg.end_date:
            raise ValueError(
                f"start_date {cfg.start_date} > end_date {cfg.end_date}"
            )
        if cfg.end_date > dt.date.today():
            raise ValueError("end_date must be ≤ today")
        if not cfg.symbols:
            return BackfillRunResult(run_id="empty-universe",
                                       warnings=["no symbols supplied"])

        run_id = self._create_run_row(cfg)
        providers = self._build_providers(cfg.providers)
        rl = self._rl or RateLimiter(max_per_minute=cfg.rate_limit_per_min)
        result = BackfillRunResult(run_id=run_id, persisted=not cfg.dry_run)

        for sym in cfg.symbols:
            result.symbol_counts.setdefault(sym, {
                "news_inserted": 0, "news_skipped": 0,
                "earnings_inserted": 0, "earnings_skipped": 0,
            })
            self._process_symbol(
                sym=sym, cfg=cfg, providers=providers,
                rl=rl, result=result, run_id=run_id,
            )

        # finalize
        if not cfg.dry_run:
            self._update_run(run_id, status="completed",
                              summary=self._summary_dict(result),
                              warnings=result.warnings)
            self._session.commit()
        else:
            logger.info("backfill dry-run: not persisting results")
        return result

    # ------------------------------------------------------------------
    def _process_symbol(
        self, *, sym: str, cfg: BackfillRunConfig,
        providers: list[tuple[str, BackfillProvider]],
        rl: RateLimiter,
        result: BackfillRunResult,
        run_id: str,
    ) -> None:
        # Chunk into windows
        windows = _chunk_windows(
            cfg.start_date, cfg.end_date, days=cfg.window_days,
        )
        for (w_start, w_end) in windows:
            for prov_name, prov in providers:
                if not rl.wait():
                    result.warnings.append(
                        f"rate limit wait exceeded for {prov_name}:{sym}"
                    )
                    continue
                try:
                    pfr = prov.fetch(sym, start=w_start, end=w_end)
                except BackfillProviderError as e:
                    result.provider_errors.append(
                        f"{prov_name}:{sym}:{w_start}..{w_end}: {e}"
                    )
                    continue
                except Exception as e:     # last-resort: never crash the run
                    result.provider_errors.append(
                        f"{prov_name}:{sym}:{w_start}..{w_end}: "
                        f"crash {type(e).__name__}: {e}"
                    )
                    continue
                result.warnings.extend(pfr.warnings)
                self._persist_news(
                    pfr.news, cfg=cfg, sym=sym, result=result, run_id=run_id,
                )
                self._persist_earnings(
                    pfr.earnings, cfg=cfg, sym=sym, result=result,
                    run_id=run_id,
                )

    # ------------------------------------------------------------------
    def _persist_news(
        self, items: list[NewsRecord], *,
        cfg: BackfillRunConfig, sym: str,
        result: BackfillRunResult, run_id: str,
    ) -> None:
        if not items:
            return
        sc = result.symbol_counts[sym]
        for rec in items:
            try:
                rec.validate()
            except BackfillProviderError as e:
                result.provider_errors.append(
                    f"{rec.provider}:{sym}: news validate {e}"
                )
                continue
            key = news_dedupe_key(
                symbol=rec.symbol, provider=rec.provider,
                url=rec.url, title=rec.title,
                published_at=rec.published_at,
            )
            if cfg.dry_run:
                sc["news_inserted"] += 1
                result.news_inserted += 1
                continue
            # UPSERT — on existing dedupe_key, bump updated_at; skip.
            inserted = self._session.execute(text("""
                INSERT INTO news_item
                  (id, source, url, url_hash, title, summary,
                   published_at, category, sentiment, sentiment_score,
                   impact_level, impact_score, raw_payload,
                   provider, ingested_at, dedupe_key, updated_at)
                VALUES
                  (:id, :src, :url, :uh, :title, :sum,
                   :pub, :cat, :sent_label, :sent_score,
                   'low', 0, CAST(:payload AS jsonb),
                   :prov, :now, :ddk, :now)
                ON CONFLICT (dedupe_key) DO NOTHING
                RETURNING id
            """), {
                "id":    str(uuid.uuid4()),
                "src":   rec.source[:32],
                "url":   rec.url,
                "uh":    hashlib.sha1(
                    rec.url.encode("utf-8"), usedforsecurity=False,
                ).hexdigest(),
                "title": rec.title,
                "sum":   rec.summary,
                "pub":   rec.published_at,
                "cat":   (rec.category or "unknown")[:24],
                "sent_label": _sentiment_label(rec.sentiment),
                "sent_score": rec.sentiment or 0,
                "payload": json.dumps(rec.raw_payload or {}, default=str),
                "prov":  rec.provider[:32],
                "now":   dt.datetime.now(dt.timezone.utc),
                "ddk":   key,
            }).fetchone()
            if inserted is None:
                sc["news_skipped"] += 1
                result.news_skipped += 1
            else:
                new_id = str(inserted[0])
                # Symbol map
                self._session.execute(text("""
                    INSERT INTO news_symbol_map (news_id, symbol)
                    VALUES (:id, :sym)
                    ON CONFLICT DO NOTHING
                """), {"id": new_id, "sym": rec.symbol.upper()})
                sc["news_inserted"] += 1
                result.news_inserted += 1
        if not cfg.dry_run:
            self._session.commit()

    # ------------------------------------------------------------------
    def _persist_earnings(
        self, items: list[EarningsRecord], *,
        cfg: BackfillRunConfig, sym: str,
        result: BackfillRunResult, run_id: str,
    ) -> None:
        if not items:
            return
        sc = result.symbol_counts[sym]
        for rec in items:
            try:
                rec.validate()
            except BackfillProviderError as e:
                result.provider_errors.append(
                    f"{rec.provider}:{sym}: earnings validate {e}"
                )
                continue
            key = earnings_dedupe_key(
                symbol=rec.symbol, provider=rec.provider,
                event_date=rec.event_date,
                fiscal_period=rec.fiscal_period,
            )
            if cfg.dry_run:
                sc["earnings_inserted"] += 1
                result.earnings_inserted += 1
                continue
            inserted = self._session.execute(text("""
                INSERT INTO earnings_event
                  (id, asset_id, symbol, event_date, event_time,
                   announcement_timestamp, announcement_timestamp_raw,
                   fiscal_period, source, ingested_ts, updated_ts,
                   known_at, provider, dedupe_key, fiscal_year,
                   event_time_hint, eps_estimate, eps_actual,
                   revenue_estimate, revenue_actual, raw_payload)
                VALUES
                  (:id, :aid, :sym, :ev, :etime,
                   :ats, :atsr,
                   :fp, :src, :now, :now,
                   :known, :prov, :ddk, :fy,
                   :ehint, :epse, :epsa,
                   :revs, :reva, CAST(:payload AS jsonb))
                ON CONFLICT ON CONSTRAINT ux_earnings_event_asset_date
                  DO NOTHING
                RETURNING id
            """), {
                "id":   str(uuid.uuid4()),
                "aid":  rec.symbol.upper(),     # use symbol as asset_id in legacy
                "sym":  rec.symbol.upper(),
                "ev":   rec.event_date,
                "etime": (rec.event_time_hint or "unknown")[:16],
                "ats":  rec.known_at,
                "atsr": rec.known_at.isoformat() if rec.known_at else None,
                "fp":   rec.fiscal_period,
                "src":  (rec.source or rec.provider)[:64],
                "now":  dt.datetime.now(dt.timezone.utc),
                "known": rec.known_at,
                "prov":  rec.provider[:32],
                "ddk":   key,
                "fy":    rec.fiscal_year,
                "ehint": rec.event_time_hint,
                "epse":  rec.eps_estimate,
                "epsa":  rec.eps_actual,
                "revs":  rec.revenue_estimate,
                "reva":  rec.revenue_actual,
                "payload": json.dumps(rec.raw_payload or {}, default=str),
            }).fetchone()
            if inserted is None:
                sc["earnings_skipped"] += 1
                result.earnings_skipped += 1
            else:
                sc["earnings_inserted"] += 1
                result.earnings_inserted += 1
            if rec.known_at is None:
                result.warnings.append(
                    f"{rec.provider}:{sym}:{rec.event_date} "
                    f"missing known_at — confidence lowered"
                )
        if not cfg.dry_run:
            self._session.commit()

    # ------------------------------------------------------------------
    def _build_providers(
        self, names: tuple[str, ...],
    ) -> list[tuple[str, BackfillProvider]]:
        out: list[tuple[str, BackfillProvider]] = []
        for n in names:
            builder = _PROVIDERS.get(n)
            if builder is None:
                logger.warning("backfill: unknown provider '{}' skipped", n)
                continue
            try:
                out.append((n, builder()))
            except Exception as e:
                logger.warning(
                    "backfill: provider '{}' init failed: {}", n, e,
                )
        return out

    # ------------------------------------------------------------------
    def _create_run_row(self, cfg: BackfillRunConfig) -> str:
        if cfg.dry_run:
            return f"dryrun-{uuid.uuid4()}"
        row = self._session.execute(text("""
            INSERT INTO catalyst_backfill_run
              (symbols, start_date, end_date, providers,
               dry_run, config, status)
            VALUES
              (CAST(:s AS jsonb), :sd, :ed, CAST(:p AS jsonb),
               :dr, CAST(:c AS jsonb), 'running')
            RETURNING id
        """), {
            "s":  json.dumps(list(cfg.symbols)),
            "sd": cfg.start_date,
            "ed": cfg.end_date,
            "p":  json.dumps(list(cfg.providers)),
            "dr": cfg.dry_run,
            "c":  json.dumps({
                "window_days": cfg.window_days,
                "rate_limit_per_min": cfg.rate_limit_per_min,
            }),
        }).fetchone()
        self._session.commit()
        return str(row[0])

    def _update_run(
        self, run_id: str, *, status: str,
        summary: dict[str, Any], warnings: list[str],
    ) -> None:
        self._session.execute(text("""
            UPDATE catalyst_backfill_run
               SET status      = :st,
                   finished_at = :now,
                   summary     = CAST(:s AS jsonb),
                   warnings    = CAST(:w AS jsonb)
             WHERE id = :id
        """), {
            "st": status,
            "now": dt.datetime.now(dt.timezone.utc),
            "s":  json.dumps(summary, default=str),
            "w":  json.dumps(warnings, default=str),
            "id": run_id,
        })

    @staticmethod
    def _summary_dict(r: BackfillRunResult) -> dict[str, Any]:
        return {
            "news_inserted": r.news_inserted,
            "news_skipped":  r.news_skipped,
            "earnings_inserted": r.earnings_inserted,
            "earnings_skipped":  r.earnings_skipped,
            "provider_errors": len(r.provider_errors),
            "symbol_counts": r.symbol_counts,
            "n_symbols": len(r.symbol_counts),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _chunk_windows(
    start: dt.date, end: dt.date, *, days: int,
) -> list[tuple[dt.date, dt.date]]:
    days = max(1, days)
    out: list[tuple[dt.date, dt.date]] = []
    cursor = start
    while cursor <= end:
        w_end = min(cursor + dt.timedelta(days=days - 1), end)
        out.append((cursor, w_end))
        cursor = w_end + dt.timedelta(days=1)
    return out


def _sentiment_label(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"
