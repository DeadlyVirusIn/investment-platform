"""Phase 11R - integration tests against Postgres."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.data.research.fast_fill_runner import (
    DEFAULT_RULE_ID,
    FILL_MODEL,
    LABEL_VERSION,
    RunnerConfig,
    SOURCE,
    run as run_fast_fill,
)
from apps.api.src.db.models import PaperResearchFill  # noqa: F401
from apps.api.src.labeling.forward_returns import (
    LABEL_VERSION as OBS_LABEL_VERSION,
)
from apps.api.src.labeling.labeller_service import (
    LabellerConfig,
    run as run_labeller,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_factory(pg_engine):
    return sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
def _ensure_label_table(pg_engine):
    """11R reuses paper_observation_label from 11P. Ensure the table
    + the expanded source CHECK are present on the test DB."""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS decision_log (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            decision_ts timestamptz NOT NULL DEFAULT now(),
            as_of_date date NOT NULL,
            engine text NOT NULL,
            action text NOT NULL,
            instrument text NOT NULL,
            inputs_used jsonb NOT NULL DEFAULT '{}'::jsonb,
            context_values jsonb NOT NULL DEFAULT '{}'::jsonb,
            decision_version text NOT NULL,
            reason text,
            blocked_by text,
            diagnostic_snapshot jsonb,
            data_quality jsonb,
            catalyst jsonb,
            feature_confidence numeric(6,4),
            skip_reason text,
            missing_features jsonb,
            ml_advisory jsonb,
            baseline_advisory jsonb,
            pattern_flags jsonb,
            factor_attribution jsonb,
            factor_version text,
            feature_set_version text,
            risk_context jsonb,
            alpha_rule_adjustment jsonb,
            alpha_rules_applied jsonb,
            alpha_rules_mode text,
            alpha_rule_size_multiplier numeric(6,4),
            alpha_rule_blocked boolean NOT NULL DEFAULT FALSE,
            alpha_rule_block_reason text,
            gate_mode text,
            exploratory_paper boolean NOT NULL DEFAULT FALSE,
            exploratory_reason text,
            gates_passed integer,
            gates_total integer,
            gates_failed jsonb,
            strict_would_block boolean NOT NULL DEFAULT FALSE,
            exploratory_size_multiplier numeric(6,4),
            source text NOT NULL DEFAULT 'strict_paper',
            strict_gates_passed boolean,
            failed_gates text[] NOT NULL DEFAULT '{}'::text[],
            ml_label_eligible boolean NOT NULL DEFAULT FALSE,
            CONSTRAINT ck_decision_log_source
              CHECK (source IN ('strict_paper','exploratory_paper','backfill'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS paper_observation_label (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            domain text NOT NULL,
            source text NOT NULL,
            paper_decision_log_id uuid,
            paper_trade_id bigint,
            options_paper_trade_id bigint,
            options_observation_id text,
            entry_date date NOT NULL,
            symbol text NOT NULL,
            rule_id text,
            failed_gates text[] NOT NULL DEFAULT '{}'::text[],
            gate_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            entry_price numeric(18,6),
            return_1d numeric(10,6),
            return_3d numeric(10,6),
            return_5d numeric(10,6),
            return_10d numeric(10,6),
            return_20d numeric(10,6),
            max_adverse_excursion numeric(10,6),
            max_favorable_excursion numeric(10,6),
            outcome_class text,
            outcome_threshold_pct numeric(6,4),
            label_confidence numeric(6,4),
            label_version text NOT NULL DEFAULT 'label-v1.0.0',
            computed_at timestamptz NOT NULL DEFAULT now(),
            is_provisional boolean NOT NULL DEFAULT TRUE,
            UNIQUE (domain, paper_decision_log_id, label_version),
            UNIQUE (domain, paper_trade_id, label_version),
            UNIQUE (domain, options_paper_trade_id, label_version),
            UNIQUE (domain, options_observation_id, label_version)
        )
        """,
    ]
    with pg_engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE TABLE paper_observation_label, "
            "paper_research_fill, decision_log "
            "RESTART IDENTITY CASCADE"
        ))


def _today() -> dt.date:
    return dt.date(2026, 4, 28)


def _seed_asset(pg_session: Session, *, symbol: str = "SPY") -> str:
    asset_id = f"asset-{symbol.lower()}"
    pg_session.execute(text(
        """
        INSERT INTO asset
          (id, symbol, name, asset_class, exchange, currency,
           is_active, created_at, updated_at)
        VALUES
          (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
           TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": asset_id, "sym": symbol})
    pg_session.commit()
    return asset_id


def _seed_bars(
    pg_session: Session,
    *,
    asset_id: str,
    days: int = 30,
    base_date: dt.datetime | None = None,
    base_price: Decimal = Decimal("440.00"),
) -> None:
    base = base_date or dt.datetime(
        2026, 4, 13, 21, 0, tzinfo=dt.timezone.utc,
    )
    for i in range(days):
        ts = base + dt.timedelta(days=i)
        price = base_price + Decimal("0.50") * i
        pg_session.execute(text(
            """
            INSERT INTO price_bar
              (id, asset_id, timeframe, ts, open, high, low, close,
               adjusted_close, volume, provider, created_at)
            VALUES
              (gen_random_uuid()::text, :aid, '1d', :ts,
               :p, :p, :p, :p, :p, 1000000, 'tiingo', now())
            ON CONFLICT DO NOTHING
            """
        ), {"aid": asset_id, "ts": ts, "p": price})
    pg_session.commit()


def _cfg(**kw):
    base = dict(
        date=_today(), backfill_from=None,
        underlyings=("SPY",),
        max_per_day=20,
        label_version=LABEL_VERSION,
        dry_run=True, commit=False,
        explain=False, skip_context=True,
    )
    base.update(kw)
    return RunnerConfig(**base)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dry_run_writes_zero_rows_pg(
    pg_session, session_factory,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    summary = run_fast_fill(
        _cfg(),
        session_factory=session_factory,
    )
    assert summary.n_committed == 0
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_research_fill"
    )).scalar_one()
    assert n == 0


def test_commit_writes_research_fill_rows_pg(
    pg_session, session_factory, tmp_path,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    summary = run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory,
        audit_log_dir=tmp_path,
    )
    assert summary.n_filled == 1
    assert summary.n_committed == 1
    rows = pg_session.execute(text(
        """
        SELECT source, fill_model, label_version,
               strict_fill_model_used, ml_label_eligible,
               fill_price_source, side
        FROM paper_research_fill
        """
    )).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.source == SOURCE
    assert r.fill_model == FILL_MODEL
    assert r.label_version == LABEL_VERSION
    assert r.strict_fill_model_used is False
    assert r.ml_label_eligible is True
    assert r.fill_price_source in ("close", "open", "vwap")
    assert r.side == "BUY"


def test_commit_idempotent_across_two_invocations_pg(
    pg_session, session_factory, tmp_path,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    cfg = _cfg(commit=True, dry_run=False)
    s1 = run_fast_fill(
        cfg, session_factory=session_factory, audit_log_dir=tmp_path,
    )
    s2 = run_fast_fill(
        cfg, session_factory=session_factory, audit_log_dir=tmp_path,
    )
    assert s1.n_committed == 1
    assert s2.n_committed == 0
    assert s2.n_skipped_existing == 1
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_research_fill"
    )).scalar_one()
    assert n == 1


def test_commit_skips_when_no_same_day_bar_pg(
    pg_session, session_factory, tmp_path,
):
    # Asset exists but no bar for today
    _seed_asset(pg_session)
    summary = run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory,
        audit_log_dir=tmp_path,
    )
    assert summary.n_skipped_no_bar >= 1
    assert summary.n_filled == 0
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_research_fill"
    )).scalar_one()
    assert n == 0


def test_commit_never_writes_to_paper_trade_pg(
    pg_session, session_factory, tmp_path,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    n_trade = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_trade"
    )).scalar_one()
    n_pos = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_position"
    )).scalar_one()
    assert n_trade == 0
    assert n_pos == 0


def test_commit_never_writes_to_decision_log_pg(
    pg_engine, pg_session, session_factory, tmp_path,
):
    # Ensure decision_log table exists in test DB.
    with pg_engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                decision_ts timestamptz NOT NULL DEFAULT now(),
                as_of_date date NOT NULL,
                engine text NOT NULL,
                action text NOT NULL,
                instrument text NOT NULL,
                inputs_used jsonb NOT NULL DEFAULT '{}'::jsonb,
                context_values jsonb NOT NULL DEFAULT '{}'::jsonb,
                decision_version text NOT NULL,
                source text NOT NULL DEFAULT 'strict_paper'
            )
            """
        ))
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM decision_log"
    )).scalar_one()
    assert n == 0


def test_max_per_day_cap_respected_pg(
    pg_session, session_factory, tmp_path,
):
    # Three assets with bars; cap to 2.
    for sym in ("SPY", "QQQ", "IWM"):
        aid = _seed_asset(pg_session, symbol=sym)
        _seed_bars(pg_session, asset_id=aid, base_price=Decimal("100"))
    summary = run_fast_fill(
        _cfg(commit=True, dry_run=False,
             underlyings=("SPY", "QQQ", "IWM"), max_per_day=2),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    assert summary.n_filled == 2
    assert summary.n_committed == 2


def test_audit_jsonl_only_on_commit(
    pg_session, session_factory, tmp_path,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    # Dry-run: no audit
    run_fast_fill(
        _cfg(),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    assert list(tmp_path.glob("research_fast_fill_*.jsonl")) == []
    # Commit: audit present
    run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    files = list(tmp_path.glob("research_fast_fill_*.jsonl"))
    assert len(files) == 1


def test_label_generation_after_commit_creates_label_rows_pg(
    pg_session, session_factory, tmp_path,
):
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id, days=40)
    # Use a date with sufficient forward window for labelling.
    entry_day = dt.date(2026, 4, 14)
    cfg_run = RunnerConfig(
        date=entry_day, backfill_from=None,
        underlyings=("SPY",), max_per_day=20,
        label_version=LABEL_VERSION,
        dry_run=False, commit=True,
        explain=False, skip_context=True,
    )
    run_fast_fill(
        cfg_run,
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    # Run labeller as_of 30 days later so 20-day horizon is satisfied
    lcfg = LabellerConfig(
        domain="equity",
        as_of_date=entry_day + dt.timedelta(days=30),
        horizon_days=20,
        threshold_pct=Decimal("0.005"),
        dry_run=False, commit=True,
        reprocess_provisional=False,
        label_version=OBS_LABEL_VERSION,
    )
    run_labeller(lcfg, session_factory=session_factory)
    rows = pg_session.execute(text(
        """
        SELECT source, label_version, options_observation_id
        FROM paper_observation_label
        WHERE source = 'research_fast_fill'
        """
    )).all()
    assert len(rows) >= 1
    for r in rows:
        assert r.source == SOURCE
        assert r.label_version == OBS_LABEL_VERSION


def test_strict_t1_fill_path_unchanged_after_research_commit_pg(
    pg_session, session_factory, tmp_path,
):
    """Smoke: write a research-fill row, then verify strict tables
    (paper_trade / paper_position) remain empty."""
    asset_id = _seed_asset(pg_session)
    _seed_bars(pg_session, asset_id=asset_id)
    run_fast_fill(
        _cfg(commit=True, dry_run=False),
        session_factory=session_factory, audit_log_dir=tmp_path,
    )
    n_trade = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_trade"
    )).scalar_one()
    n_pos = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_position"
    )).scalar_one()
    n_research = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_research_fill"
    )).scalar_one()
    assert n_trade == 0
    assert n_pos == 0
    assert n_research == 1


def test_paper_research_fill_check_constraints_block_bad_rows(
    pg_session,
):
    # source must be 'research_fast_fill' — try to insert otherwise.
    with pytest.raises(Exception):
        pg_session.execute(text(
            """
            INSERT INTO paper_research_fill
              (source, fill_model, label_version,
               ml_label_eligible, strict_fill_model_used,
               decision_ts, as_of_date, underlying, rule_id, side,
               fill_price, fill_price_source, fill_ts, qty)
            VALUES
              ('not_allowed_source', 'same_day_research_v1',
               'research-fast-fill-v1.0.0', TRUE, FALSE,
               '2026-04-28T15:00:00Z', '2026-04-28', 'SPY',
               'research_fast_fill_open_buy_v1', 'BUY',
               100.0, 'close', '2026-04-28T21:00:00Z', 1.0)
            """
        ))
        pg_session.commit()
    pg_session.rollback()

    # strict_fill_model_used MUST be FALSE
    with pytest.raises(Exception):
        pg_session.execute(text(
            """
            INSERT INTO paper_research_fill
              (source, fill_model, label_version,
               ml_label_eligible, strict_fill_model_used,
               decision_ts, as_of_date, underlying, rule_id, side,
               fill_price, fill_price_source, fill_ts, qty)
            VALUES
              ('research_fast_fill', 'same_day_research_v1',
               'research-fast-fill-v1.0.0', TRUE, TRUE,
               '2026-04-28T15:00:00Z', '2026-04-28', 'SPY',
               'research_fast_fill_open_buy_v1', 'BUY',
               100.0, 'close', '2026-04-28T21:00:00Z', 1.0)
            """
        ))
        pg_session.commit()
    pg_session.rollback()
