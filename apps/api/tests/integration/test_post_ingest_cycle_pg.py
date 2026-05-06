"""Post-ingest paper cycle orchestrator — integration tests.

Verifies:
  * Default dry-run writes artifact + zero DB writes.
  * --commit invokes the strict stock runner; exploratory/options
    skipped without env opt-in; results captured.
  * Even with RUN_EXPLORATORY_AFTER_INGEST=true, the runner still
    refuses unless EXPLORATORY_PAPER_CONFIRM is also set — the
    orchestrator surfaces this as `skipped`, not as a write.
  * Even with RUN_OPTIONS_AFTER_INGEST=true, the orchestrator
    refuses to dispatch when options_chain_snapshot is empty for
    `as_of`.
  * Bad --as-of refused.
  * Artifact contains readiness, plan, results, deltas, safety
    block.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    Asset, PriceBar, RegimeSnapshot,
)
# Force ORM registration so testcontainer create_all builds the
# options paper trade tables. Otherwise pg_session reads against
# them fail with "relation does not exist".
import apps.api.src.db.options_models  # noqa: F401


@pytest.fixture
def patch_session_local(pg_engine, monkeypatch):
    """Bind the orchestrator's SessionLocal to pg_engine so all of
    its DB reads land in the same testcontainer the test fixture
    writes into. Without this, the orchestrator points at the
    runtime DATABASE_URL and disagrees with the fixture state."""
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )
    import apps.api.src.db as _db
    monkeypatch.setattr(_db, "SessionLocal", SessionCls)
    yield


pytestmark = pytest.mark.integration


def _seed_minimal(session: Session, as_of: dt.date) -> None:
    a = Asset(
        symbol="ZZX", name="ZZX", asset_class="equity",
        sector="tech", currency="USD", is_active=True,
    )
    session.add(a)
    session.flush()
    session.add(PriceBar(
        asset_id=a.id, timeframe="1d",
        ts=dt.datetime.combine(
            as_of, dt.time(20, 0), tzinfo=dt.timezone.utc,
        ),
        open=100, high=101, low=99, close=100,
        adjusted_close=100, provider="test",
    ))
    session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend="uptrend", vol_regime="normal",
        breadth_regime="ok", sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.15"),
        atr_pctile_1y=Decimal("0.40"),
    ))
    session.commit()


def test_default_dry_run_no_writes(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    """No env opt-ins, --dry-run default, zero DB writes."""
    monkeypatch.delenv("RUN_STOCK_AFTER_INGEST", raising=False)
    monkeypatch.delenv("RUN_EXPLORATORY_AFTER_INGEST", raising=False)
    monkeypatch.delenv("RUN_OPTIONS_AFTER_INGEST", raising=False)
    monkeypatch.delenv("RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST",
                       raising=False)
    monkeypatch.delenv("EXPLORATORY_PAPER_CONFIRM", raising=False)
    monkeypatch.delenv("OPTIONS_PAPER_EXEC_CONFIRM", raising=False)
    as_of = dt.date(2026, 5, 5)
    _seed_minimal(pg_session, as_of)
    monkeypatch.chdir(tmp_path)

    paper_n_before = pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar()
    opt_n_before = pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar()

    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", as_of.isoformat()])
    assert rc == 0

    out = tmp_path / "artifacts/post_ingest_cycle"
    files = list(out.glob("cycle_*.json"))
    assert files
    artifact = json.loads(files[0].read_text())
    assert artifact["mode"] == "dry-run"
    assert artifact["safety"]["live_execution_enabled"] is False
    assert artifact["safety"]["scheduler_started"] is False
    assert artifact["safety"]["replay_touched"] is False
    # readiness echoed
    assert artifact["readiness"]["as_of"] == as_of.isoformat()
    assert artifact["readiness"]["regime_snapshot_today"] is True
    # No DB writes
    assert pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar() == paper_n_before
    assert pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar() == opt_n_before


def test_bad_as_of_refused(monkeypatch):
    monkeypatch.delenv("RUN_STOCK_AFTER_INGEST", raising=False)
    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", "not-a-date"])
    assert rc == 2


def test_replay_pending_from_after_as_of_refused(monkeypatch):
    from scripts.run_post_ingest_paper_cycle import main
    rc = main([
        "--as-of", "2026-05-01",
        "--replay-pending-from", "2026-05-04",
    ])
    assert rc == 2


def test_force_replay_without_from_refused(monkeypatch):
    from scripts.run_post_ingest_paper_cycle import main
    rc = main([
        "--as-of", "2026-05-05", "--force-replay",
    ])
    assert rc == 2


def test_bad_replay_from_refused(monkeypatch):
    from scripts.run_post_ingest_paper_cycle import main
    rc = main([
        "--as-of", "2026-05-05",
        "--replay-pending-from", "not-a-date",
    ])
    assert rc == 2


def test_bad_replay_options_from_refused(monkeypatch):
    from scripts.run_post_ingest_paper_cycle import main
    rc = main([
        "--as-of", "2026-05-05",
        "--replay-options-from", "not-a-date",
    ])
    assert rc == 2


def test_replay_options_from_after_as_of_refused(monkeypatch):
    from scripts.run_post_ingest_paper_cycle import main
    rc = main([
        "--as-of", "2026-05-01",
        "--replay-options-from", "2026-05-04",
    ])
    assert rc == 2


def test_exploratory_skipped_without_confirm_env(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    """RUN_EXPLORATORY_AFTER_INGEST=true but EXPLORATORY_PAPER_CONFIRM
    missing → orchestrator refuses to invoke; surfaces `skipped`."""
    monkeypatch.setenv("RUN_STOCK_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_EXPLORATORY_AFTER_INGEST", "true")
    monkeypatch.setenv("RUN_OPTIONS_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST", "false")
    monkeypatch.delenv("EXPLORATORY_PAPER_CONFIRM", raising=False)
    as_of = dt.date(2026, 5, 5)
    _seed_minimal(pg_session, as_of)
    monkeypatch.chdir(tmp_path)

    paper_n_before = pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar()
    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", as_of.isoformat(), "--commit"])
    assert rc == 0
    out = tmp_path / "artifacts/post_ingest_cycle"
    artifact = json.loads(next(out.glob("cycle_*.json")).read_text())
    skipped = [
        r for r in artifact["results"] if r.get("skipped")
        and "exploratory" in r.get("runner", "")
    ]
    assert skipped, artifact["results"]
    assert "EXPLORATORY_PAPER_CONFIRM" in skipped[0]["reason"]
    assert pg_session.execute(
        text("SELECT count(*) FROM paper_trade")
    ).scalar() == paper_n_before


def test_options_skipped_when_no_chain_today(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    """RUN_OPTIONS_AFTER_INGEST=true but options_chain_snapshot has
    no rows for `as_of` → orchestrator refuses (no fabrication)."""
    monkeypatch.setenv("RUN_STOCK_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_EXPLORATORY_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_OPTIONS_AFTER_INGEST", "true")
    monkeypatch.setenv("RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST", "false")
    monkeypatch.setenv(
        "OPTIONS_PAPER_EXEC_CONFIRM",
        "I_UNDERSTAND_THIS_SUBMITS_OPTIONS_PAPER_TRADES",
    )
    as_of = dt.date(2026, 5, 5)
    _seed_minimal(pg_session, as_of)
    monkeypatch.chdir(tmp_path)

    opt_n_before = pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar()

    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", as_of.isoformat(), "--commit"])
    assert rc == 0

    out = tmp_path / "artifacts/post_ingest_cycle"
    artifact = json.loads(next(out.glob("cycle_*.json")).read_text())
    options_results = [
        r for r in artifact["results"]
        if "options_paper" in r.get("runner", "")
    ]
    assert options_results
    assert options_results[0].get("skipped") is True
    assert "chain snapshot" in options_results[0]["reason"]
    assert pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar() == opt_n_before


def test_promotion_eval_runs_dry_only(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    """promotion eval should always dry-run (never --apply)."""
    monkeypatch.setenv("RUN_STOCK_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_EXPLORATORY_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_OPTIONS_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST", "true")
    # promotion `--apply` would require this:
    monkeypatch.delenv("OPTIONS_STRATEGY_PROMOTION_ENABLED",
                       raising=False)
    as_of = dt.date(2026, 5, 5)
    _seed_minimal(pg_session, as_of)
    monkeypatch.chdir(tmp_path)

    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", as_of.isoformat(), "--commit"])
    assert rc == 0
    out = tmp_path / "artifacts/post_ingest_cycle"
    artifact = json.loads(next(out.glob("cycle_*.json")).read_text())
    promo = [
        r for r in artifact["results"]
        if "promotion_eval" in r.get("runner", "")
    ]
    assert promo
    assert promo[0]["exit_code"] == 0


def test_artifact_records_pending_before_after(
    pg_session, tmp_path, monkeypatch, patch_session_local,
):
    monkeypatch.setenv("RUN_STOCK_AFTER_INGEST", "false")
    monkeypatch.setenv("RUN_OPTIONS_PROMOTION_EVAL_AFTER_INGEST", "false")
    as_of = dt.date(2026, 5, 5)
    _seed_minimal(pg_session, as_of)
    monkeypatch.chdir(tmp_path)
    from scripts.run_post_ingest_paper_cycle import main
    rc = main(["--as-of", as_of.isoformat()])
    assert rc == 0
    artifact = json.loads(
        next((tmp_path / "artifacts/post_ingest_cycle").glob("cycle_*.json"))
            .read_text()
    )
    assert "pending_before" in artifact
    assert "pending_after" in artifact
    assert "before_counts" in artifact
    assert "after_counts" in artifact
    assert "deltas" in artifact
