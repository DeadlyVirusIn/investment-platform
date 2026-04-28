"""Phase 11P - end-to-end integration against Postgres."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.config import settings
from apps.api.src.data.macro.fred_adapter import (
    FredAdapter,
    FredConfig,
)
from apps.api.src.data.strategy.exploratory_runner import (
    ExploratoryConfig,
    EXPLORATORY_RULE_VERSION,
    SOURCE_TAG as EXPLORATORY_SOURCE,
    run as run_exploratory,
)
from apps.api.src.db.options_models import (  # noqa: F401 — register models
    OptionsAssignmentEvent,
    OptionsExpirationEvent,
    OptionsPaperTrade,
    OptionsPaperTradeLeg,
    OptionsTradeLifecycleEvent,
)
from apps.api.src.db.models import PaperObservationLabel  # noqa: F401
from apps.api.src.labeling.forward_returns import LABEL_VERSION
from apps.api.src.labeling.labeller_service import (
    LabellerConfig,
    run as run_labeller,
)
from scripts.backfill_macro_features import (
    BackfillConfig,
    run as run_backfill,
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
def _ensure_11p_supporting_tables(pg_engine):
    """The 11P test path needs context_daily / decision_log /
    features_daily — none of which have ORM classes (managed via
    raw SQL + alembic in production). Create + truncate them here
    so testcontainers PG can run end-to-end."""
    ddl = [
        """
        CREATE TABLE IF NOT EXISTS context_daily (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date date NOT NULL,
            context_name text NOT NULL,
            status text NOT NULL,
            value_bool boolean NOT NULL,
            source_features text[] NOT NULL,
            logic_version text NOT NULL,
            logic_hash text NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (as_of_date, context_name, logic_version)
        )
        """,
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
            -- Phase 11P.1 columns
            source text NOT NULL DEFAULT 'strict_paper',
            strict_gates_passed boolean,
            failed_gates text[] NOT NULL DEFAULT '{}'::text[],
            ml_label_eligible boolean NOT NULL DEFAULT FALSE,
            CONSTRAINT ck_decision_log_source
              CHECK (source IN ('strict_paper','exploratory_paper','backfill'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS features_daily (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            as_of_date date NOT NULL,
            feature_name text NOT NULL,
            value numeric(24,8),
            value_bool boolean,
            input_hash text NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now(),
            feature_version text NOT NULL,
            UNIQUE (as_of_date, feature_name, feature_version)
        )
        """,
    ]
    with pg_engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE TABLE context_daily, decision_log, "
            "features_daily RESTART IDENTITY CASCADE"
        ))


@pytest.fixture
def exploratory_enabled(monkeypatch):
    monkeypatch.setattr(
        settings, "EQUITY_EXPLORATORY_ENABLED", True,
    )


def _seed_context_daily(
    pg_session: Session,
    *,
    days: int = 5,
    pattern: dict[str, list[bool | None]] | None = None,
) -> list[dt.date]:
    """Seed `context_daily` with the four production gate booleans
    over `days` business days. `pattern` overrides per-gate values
    for granular control."""
    base = dt.date(2026, 4, 13)            # Monday
    dates: list[dt.date] = []
    d = base
    while len(dates) < days:
        if d.weekday() < 5:
            dates.append(d)
        d += dt.timedelta(days=1)
    pattern = pattern or {}
    for i, d in enumerate(dates):
        for name in (
            "rates_calm", "vrp_supportive",
            "credit_stable", "liquidity_expanding",
        ):
            vals = pattern.get(name, [True] * days)
            v = vals[i] if i < len(vals) else True
            pg_session.execute(text(
                """
                INSERT INTO context_daily
                  (as_of_date, context_name, status, value_bool,
                   source_features, logic_version, logic_hash)
                VALUES
                  (:d, :name, 'ok', :v,
                   ARRAY['test'], 'v1.0.0', 'test_hash')
                """
            ), {
                "d": d, "name": name,
                "v": False if v is None else bool(v),
            })
    pg_session.commit()
    return dates


def _seed_price_bars(pg_session: Session, *, symbol: str = "SPY") -> None:
    """Seed asset + 30 daily price_bar rows for forward-return labeling."""
    pg_session.execute(text(
        """
        INSERT INTO asset (id, symbol, name, asset_class, exchange,
                           currency, is_active, created_at, updated_at)
        VALUES (:id, :sym, :sym, 'equity', 'NASDAQ', 'USD',
                TRUE, now(), now())
        ON CONFLICT ON CONSTRAINT uq_asset_symbol_exchange DO NOTHING
        """
    ), {"id": "asset-spy", "sym": symbol})
    asset_id = pg_session.execute(text(
        "SELECT id FROM asset WHERE symbol = :sym"
    ), {"sym": symbol}).scalar_one()
    base_date = dt.datetime(
        2026, 4, 13, 21, 0, tzinfo=dt.timezone.utc,
    )
    px = Decimal("440.00")
    for i in range(40):
        ts = base_date + dt.timedelta(days=i)
        # Simple positive drift so 20-day forward return is non-zero.
        price = px + Decimal("0.50") * i
        pg_session.execute(text(
            """
            INSERT INTO price_bar
              (id, asset_id, timeframe, ts, open, high, low, close,
               adjusted_close, volume, provider, created_at)
            VALUES
              (gen_random_uuid()::text,
               :aid, '1d', :ts, :p, :p, :p, :p, :p,
               1000000, 'tiingo', now())
            ON CONFLICT DO NOTHING
            """
        ), {"aid": asset_id, "ts": ts, "p": price})
    pg_session.commit()


# ---------------------------------------------------------------------------
# 1. Macro backfill — full FRED pipeline against PG
# ---------------------------------------------------------------------------

def test_backfill_macro_features_dry_run_writes_nothing(
    pg_session, session_factory,
):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={
            "observations": [
                {"date": "2024-01-02", "value": "4.05"},
                {"date": "2024-01-03", "value": "4.07"},
            ],
        }),
    )
    cfg = FredConfig(
        base_url="https://api.stlouisfed.org/fred",
        api_key="k", max_retries=0, rate_limit_qps=1000.0,
    )
    client = httpx.Client(
        transport=transport, base_url=cfg.base_url,
        headers={"Accept": "application/json"},
        timeout=cfg.timeout_seconds,
    )
    adapter = FredAdapter(
        config=cfg, http_client=client, sleeper=lambda _s: None,
    )
    bcfg = BackfillConfig(
        start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 5),
        series=("DGS10",),
        dry_run=True, commit=False,
        logic_version="v1.0.0", explain=False,
    )
    summary = run_backfill(bcfg, adapter=adapter,
                           session_factory=session_factory)
    assert summary["n_features_inserted"] == 0
    assert summary["n_context_inserted"] == 0
    n_features = pg_session.execute(text(
        "SELECT COUNT(*) FROM features_daily"
    )).scalar_one()
    assert n_features == 0


def test_backfill_macro_features_commit_writes(
    pg_session, session_factory, tmp_path,
):
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={
            "observations": [
                {"date": "2024-01-02", "value": "4.05"},
                {"date": "2024-01-03", "value": "4.07"},
                {"date": "2024-01-04", "value": "4.06"},
            ],
        }),
    )
    cfg = FredConfig(
        base_url="https://api.stlouisfed.org/fred",
        api_key="k", max_retries=0, rate_limit_qps=1000.0,
    )
    client = httpx.Client(
        transport=transport, base_url=cfg.base_url,
        headers={"Accept": "application/json"},
        timeout=cfg.timeout_seconds,
    )
    adapter = FredAdapter(
        config=cfg, http_client=client, sleeper=lambda _s: None,
    )
    bcfg = BackfillConfig(
        start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 4),
        series=("DGS10",),
        dry_run=False, commit=True,
        logic_version="v1.0.0", explain=False,
    )
    summary = run_backfill(
        bcfg, adapter=adapter,
        session_factory=session_factory,
        audit_log_dir=tmp_path,
    )
    assert summary["n_features_inserted"] == 3
    assert summary["n_context_inserted"] >= 4   # 4 contexts × N days
    n_features = pg_session.execute(text(
        "SELECT COUNT(*) FROM features_daily WHERE feature_name='DGS10'"
    )).scalar_one()
    assert n_features == 3
    # idempotency: second commit run inserts zero
    summary2 = run_backfill(
        bcfg, adapter=adapter,
        session_factory=session_factory,
        audit_log_dir=tmp_path,
    )
    assert summary2["n_features_inserted"] == 0


# ---------------------------------------------------------------------------
# 2. Exploratory runner — writes only to decision_log
# ---------------------------------------------------------------------------

def test_exploratory_runner_dry_run_writes_nothing(
    pg_session, session_factory, exploratory_enabled,
):
    days = _seed_context_daily(pg_session, days=3)
    cfg = ExploratoryConfig(
        date=days[-1],
        underlyings=("SPY",),
        backfill_from=days[0],
        dry_run=True, commit=False,
    )
    summary = run_exploratory(cfg, session_factory=session_factory)
    assert summary.n_decisions >= 3
    assert summary.n_committed == 0
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM decision_log "
        "WHERE source = :src"
    ), {"src": EXPLORATORY_SOURCE}).scalar_one()
    assert n == 0


def test_exploratory_runner_commit_writes_decision_log_only(
    pg_session, session_factory, exploratory_enabled,
):
    days = _seed_context_daily(pg_session, days=3)
    cfg = ExploratoryConfig(
        date=days[-1],
        underlyings=("SPY",),
        backfill_from=days[0],
        dry_run=False, commit=True,
    )
    summary = run_exploratory(cfg, session_factory=session_factory)
    assert summary.n_committed == 3
    rows = pg_session.execute(text(
        """
        SELECT source, ml_label_eligible, strict_gates_passed, action
        FROM decision_log WHERE source = :src
        """
    ), {"src": EXPLORATORY_SOURCE}).all()
    assert len(rows) == 3
    for r in rows:
        assert r.source == EXPLORATORY_SOURCE
        assert r.ml_label_eligible is True
    # Strict path tables MUST be unchanged
    n_pos = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_position"
    )).scalar_one()
    n_trade = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_trade"
    )).scalar_one()
    assert n_pos == 0
    assert n_trade == 0


def test_exploratory_runner_safety_blocks_when_disabled(
    pg_session, session_factory, monkeypatch,
):
    monkeypatch.setattr(
        settings, "EQUITY_EXPLORATORY_ENABLED", False,
    )
    days = _seed_context_daily(pg_session, days=2)
    cfg = ExploratoryConfig(
        date=days[-1], underlyings=("SPY",),
        backfill_from=days[0],
        dry_run=False, commit=True,
    )
    from apps.api.src.data.strategy.exploratory_runner import (
        ExploratorySafetyError,
    )
    with pytest.raises(ExploratorySafetyError):
        run_exploratory(cfg, session_factory=session_factory)


# ---------------------------------------------------------------------------
# 3. Labeller — equity domain end-to-end
# ---------------------------------------------------------------------------

def test_labeller_equity_writes_labels_for_decision_log_rows(
    pg_session, session_factory, exploratory_enabled,
):
    _seed_price_bars(pg_session, symbol="SPY")
    days = _seed_context_daily(pg_session, days=3)
    # Generate exploratory decisions (committed) so labeller has rows
    run_exploratory(
        ExploratoryConfig(
            date=days[-1], underlyings=("SPY",),
            backfill_from=days[0],
            dry_run=False, commit=True,
        ),
        session_factory=session_factory,
    )
    cfg = LabellerConfig(
        domain="equity",
        as_of_date=days[-1] + dt.timedelta(days=30),
        horizon_days=20,
        threshold_pct=Decimal("0.005"),
        dry_run=False, commit=True,
        reprocess_provisional=False,
        label_version=LABEL_VERSION,
    )
    summary = run_labeller(cfg, session_factory=session_factory)
    assert summary.n_inserted >= 3
    rows = pg_session.execute(text(
        """
        SELECT domain, source, label_version, outcome_class, is_provisional
        FROM paper_observation_label
        """
    )).all()
    assert all(r.domain == "equity" for r in rows)
    assert all(r.label_version == LABEL_VERSION for r in rows)


def test_labeller_idempotent_across_runs(
    pg_session, session_factory, exploratory_enabled,
):
    _seed_price_bars(pg_session, symbol="SPY")
    days = _seed_context_daily(pg_session, days=2)
    run_exploratory(
        ExploratoryConfig(
            date=days[-1], underlyings=("SPY",),
            backfill_from=days[0],
            dry_run=False, commit=True,
        ),
        session_factory=session_factory,
    )
    cfg = LabellerConfig(
        domain="equity",
        as_of_date=days[-1] + dt.timedelta(days=30),
        horizon_days=20,
        threshold_pct=Decimal("0.005"),
        dry_run=False, commit=True,
        reprocess_provisional=False,
        label_version=LABEL_VERSION,
    )
    s1 = run_labeller(cfg, session_factory=session_factory)
    n1 = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_observation_label"
    )).scalar_one()
    # Re-run: should insert zero new rows
    s2 = run_labeller(cfg, session_factory=session_factory)
    n2 = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_observation_label"
    )).scalar_one()
    assert n1 == n2
    assert s2.n_inserted == 0


def test_labeller_dry_run_writes_no_labels(
    pg_session, session_factory, exploratory_enabled,
):
    _seed_price_bars(pg_session, symbol="SPY")
    days = _seed_context_daily(pg_session, days=2)
    run_exploratory(
        ExploratoryConfig(
            date=days[-1], underlyings=("SPY",),
            backfill_from=days[0],
            dry_run=False, commit=True,
        ),
        session_factory=session_factory,
    )
    cfg = LabellerConfig(
        domain="equity",
        as_of_date=days[-1] + dt.timedelta(days=30),
        horizon_days=20,
        threshold_pct=Decimal("0.005"),
        dry_run=True, commit=False,
        reprocess_provisional=False,
        label_version=LABEL_VERSION,
    )
    run_labeller(cfg, session_factory=session_factory)
    n = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_observation_label"
    )).scalar_one()
    assert n == 0


# ---------------------------------------------------------------------------
# 4. Strict path untouched by 11P
# ---------------------------------------------------------------------------

def test_strict_paper_decision_rows_untouched_by_11p(
    pg_session, session_factory, exploratory_enabled,
):
    days = _seed_context_daily(pg_session, days=2)
    # Create a strict-paper row directly (simulating prior write)
    pg_session.execute(text(
        """
        INSERT INTO decision_log
          (as_of_date, engine, action, instrument,
           inputs_used, context_values, decision_version,
           source)
        VALUES
          (:d, 'A', 'enter_long', 'SPY',
           '{}'::jsonb, '{}'::jsonb, 'selector-v1.0.0',
           'strict_paper')
        """
    ), {"d": days[0]})
    pg_session.commit()
    initial_id = pg_session.execute(text(
        "SELECT id FROM decision_log "
        "WHERE source = 'strict_paper' ORDER BY id LIMIT 1"
    )).scalar_one()

    # Run exploratory commit
    run_exploratory(
        ExploratoryConfig(
            date=days[-1], underlyings=("SPY",),
            backfill_from=days[0],
            dry_run=False, commit=True,
        ),
        session_factory=session_factory,
    )

    # Strict row still present, untouched
    still = pg_session.execute(text(
        "SELECT id FROM decision_log WHERE id = :i"
    ), {"i": initial_id}).scalar_one()
    assert still == initial_id


# ---------------------------------------------------------------------------
# 5. paper_observation_label append-only contract
# ---------------------------------------------------------------------------

def test_paper_observation_label_unique_constraint_blocks_duplicates(
    pg_session, session_factory,
):
    decision_id = "00000000-0000-0000-0000-000000000001"
    pg_session.execute(text(
        """
        INSERT INTO paper_observation_label
          (domain, source, paper_decision_log_id,
           entry_date, symbol, label_version, is_provisional)
        VALUES
          ('equity', 'strict_paper', CAST(:id AS uuid),
           '2026-04-27', 'SPY', :lv, FALSE)
        """
    ), {"id": decision_id, "lv": LABEL_VERSION})
    pg_session.commit()
    with pytest.raises(Exception):
        pg_session.execute(text(
            """
            INSERT INTO paper_observation_label
              (domain, source, paper_decision_log_id,
               entry_date, symbol, label_version, is_provisional)
            VALUES
              ('equity', 'strict_paper', CAST(:id AS uuid),
               '2026-04-27', 'SPY', :lv, FALSE)
            """
        ), {"id": decision_id, "lv": LABEL_VERSION})
        pg_session.commit()
    pg_session.rollback()
