"""Phase 11T - shadow scoring end-to-end against Postgres."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import joblib
import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import PaperObservationLabel  # noqa: F401
from apps.api.src.ml.model_registry import (
    RegistrationRequest,
    register,
)
from apps.api.src.ml.shadow_report import (
    REPORTS_DIR,
    write_report,
)
from apps.api.src.ml.shadow_scorer import (
    BUCKET_EDGES_FROZEN,
    SHADOW_HIGH,
    SHADOW_LOW,
    SHADOW_MID,
    ScorerConfig,
    run as run_scorer,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Stub estimator (module-scope so joblib can resolve)
# ---------------------------------------------------------------------------

class _StubClassifier:
    classes_ = ["negative", "neutral", "positive"]

    def __init__(self, *, p_pos: float = 0.7):
        self.p_pos = p_pos

    def predict_proba(self, X):
        n = len(X)
        out = np.zeros((n, 3))
        out[:, 0] = (1 - self.p_pos) / 2
        out[:, 1] = (1 - self.p_pos) / 2
        out[:, 2] = self.p_pos
        return out


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
    """Create paper_observation_label so 11T can read from it.
    11T never writes to it."""
    ddl = """
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
            is_provisional boolean NOT NULL DEFAULT TRUE
        )
        """
    with pg_engine.begin() as conn:
        conn.execute(text(ddl))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE TABLE paper_observation_label "
            "RESTART IDENTITY CASCADE"
        ))


def _seed_labels(
    pg_session: Session,
    *,
    n_high: int = 3,
    n_low: int = 2,
    source: str = "research_fast_fill",
    domain: str = "equity",
    provisional: bool = False,
    id_prefix: str = "",
) -> None:
    base = dt.date(2026, 2, 1)
    prefix = id_prefix or ("prov" if provisional else "fin")
    for i in range(n_high):
        pg_session.execute(text(
            """
            INSERT INTO paper_observation_label
              (domain, source, options_observation_id, entry_date,
               symbol, rule_id, failed_gates, gate_snapshot,
               outcome_class, label_version, is_provisional)
            VALUES
              (:dom, :src, :id, :ed, 'SPY',
               'research_fast_fill_open_buy_v1',
               '{}'::text[],
               CAST(:gs AS jsonb),
               'positive',
               'label-v1.0.0', :prov)
            """
        ), {
            "dom": domain, "src": source,
            "id": f"{prefix}-obs-high-{i}",
            "ed": base + dt.timedelta(days=i),
            "gs": json.dumps({"ctx_rates_calm": True}),
            "prov": provisional,
        })
    for i in range(n_low):
        pg_session.execute(text(
            """
            INSERT INTO paper_observation_label
              (domain, source, options_observation_id, entry_date,
               symbol, rule_id, failed_gates, gate_snapshot,
               outcome_class, label_version, is_provisional)
            VALUES
              (:dom, :src, :id, :ed, 'SPY',
               'research_fast_fill_open_buy_v1',
               ARRAY['rates_calm','vrp_supportive']::text[],
               CAST(:gs AS jsonb),
               'negative',
               'label-v1.0.0', :prov)
            """
        ), {
            "dom": domain, "src": source,
            "id": f"{prefix}-obs-low-{i}",
            "ed": base + dt.timedelta(days=10 + i),
            "gs": json.dumps({"ctx_rates_calm": False}),
            "prov": provisional,
        })
    pg_session.commit()


def _seed_pickle(tmp_path: Path, *, p_pos: float = 0.9) -> Path:
    pkl = tmp_path / "model.pkl"
    payload = {
        "model": _StubClassifier(p_pos=p_pos),
        "preprocessor": None,
        "feature_names": ["ctx_rates_calm"],
        "task": "classification",
        "target": "outcome_class",
        "model_type": "logreg",
        "model_params": {"C": 1.0},
        "trained_on": {
            "dataset_path": str(tmp_path / "ds.parquet"),
            "dataset_checksum_sha256": "abc",
            "train_range": {"start": "2021-01-01", "end": "2024-12-31"},
        },
        "trained_at": "2026-04-30T03:30:00Z",
        "model_version": "ml-v1.0.0",
        "label_version": "label-v1.0.0",
        "dataset_version": "dataset-v1.0.0",
    }
    joblib.dump(payload, pkl)
    return pkl


def _seed_report(tmp_path: Path) -> Path:
    p = tmp_path / "report.json"
    p.write_text(json.dumps({
        "model_version": "ml-v1.0.0",
        "model_type": "logreg",
        "task": "classification",
        "target": "outcome_class",
        "trained_at": "2026-04-30T03:30:00Z",
        "dataset": {"id": "ds-1", "n_rows": 100, "checksum_sha256": "abc"},
        "splits": {
            "train":   {"end": "2024-12-31", "n": 80},
            "test":    {"start": "2025-01-01", "end": "2025-12-31",
                        "n": 15},
            "holdout": {"start": "2026-01-01", "end": "2026-04-08",
                        "n": 5},
        },
        "metrics": {
            "test":    {"auc_macro": 0.6, "accuracy": 0.55},
            "holdout": {"auc_macro": 0.58, "accuracy": 0.53},
        },
    }), encoding="utf-8")
    return p


def _registered(tmp_path: Path) -> tuple[str, Path]:
    pkl = _seed_pickle(tmp_path)
    rep = _seed_report(tmp_path)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=pkl, report_path=rep),
        registry_path=reg, dry_run=False,
        now_utc=dt.datetime(
            2026, 4, 30, 3, 30, tzinfo=dt.timezone.utc,
        ),
    )
    return entry["model_id"], reg


def _cfg(model_id: str, *, commit: bool = False, output_dir: str = "reports"):
    return ScorerConfig(
        model_id=model_id,
        start=dt.date(2026, 2, 1), end=dt.date(2026, 3, 1),
        sources=("research_fast_fill",),
        domain="equity",
        include_provisional=False,
        bucket_edges=BUCKET_EDGES_FROZEN,
        output_dir=output_dir,
        dry_run=not commit, commit=commit,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_full_shadow_scoring_dry_run_against_seeded_pg(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session, n_high=3, n_low=2)
    model_id, reg = _registered(tmp_path)
    summary = run_scorer(
        _cfg(model_id, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    assert summary.rows_input == 5
    assert summary.rows_scored == 5
    # No report written in dry-run
    assert list(tmp_path.glob("shadow_score_*.json")) == []


def test_full_shadow_scoring_commit_writes_report_only(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session)
    model_id, reg = _registered(tmp_path)
    cfg = _cfg(model_id, commit=True, output_dir=str(tmp_path))
    summary = run_scorer(
        cfg, session_factory=session_factory, registry_path=reg,
    )
    path = write_report(
        summary,
        sources_included=cfg.sources,
        domain=cfg.domain,
        output_dir=tmp_path,
    )
    assert path.exists()


def test_shadow_scoring_writes_no_paper_trade_or_position(
    pg_engine, pg_session, session_factory, tmp_path,
):
    with pg_engine.begin() as conn:
        # paper_trade / paper_position created via Base.metadata in
        # conftest. Only need to confirm count == 0 after run.
        pass
    _seed_labels(pg_session)
    model_id, reg = _registered(tmp_path)
    run_scorer(
        _cfg(model_id, commit=True, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    n_trade = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_trade"
    )).scalar_one()
    n_pos = pg_session.execute(text(
        "SELECT COUNT(*) FROM paper_position"
    )).scalar_one()
    assert n_trade == 0
    assert n_pos == 0


def test_shadow_scoring_does_not_modify_pickle(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session)
    pkl = _seed_pickle(tmp_path)
    rep = _seed_report(tmp_path)
    reg = tmp_path / "registry.json"
    entry = register(
        RegistrationRequest(pickle_path=pkl, report_path=rep),
        registry_path=reg, dry_run=False,
        now_utc=dt.datetime(2026, 4, 30, 3, 30,
                            tzinfo=dt.timezone.utc),
    )
    pkl_mtime = pkl.stat().st_mtime
    pkl_bytes = pkl.read_bytes()
    run_scorer(
        _cfg(entry["model_id"], commit=True,
             output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    assert pkl.stat().st_mtime == pkl_mtime
    assert pkl.read_bytes() == pkl_bytes


def test_shadow_scoring_idempotent_filename_collision_refused(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session)
    model_id, reg = _registered(tmp_path)
    cfg = _cfg(model_id, commit=True, output_dir=str(tmp_path))
    summary = run_scorer(
        cfg, session_factory=session_factory, registry_path=reg,
    )
    write_report(summary,
                 sources_included=cfg.sources,
                 domain=cfg.domain,
                 output_dir=tmp_path)
    from apps.api.src.ml.shadow_report import ShadowReportError
    summary2 = run_scorer(
        cfg, session_factory=session_factory, registry_path=reg,
    )
    with pytest.raises(ShadowReportError, match="already exists"):
        write_report(summary2,
                     sources_included=cfg.sources,
                     domain=cfg.domain,
                     output_dir=tmp_path)


def test_shadow_scoring_excludes_provisional(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session, n_high=2, n_low=0, provisional=True)
    _seed_labels(pg_session, n_high=2, n_low=0, provisional=False)
    model_id, reg = _registered(tmp_path)
    summary = run_scorer(
        _cfg(model_id, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    # Provisional rows excluded by default, non-provisional scored.
    assert summary.rows_input == 4
    # The 2 provisional rows should be excluded
    assert (
        summary.rows_excluded_by_reason.get("is_provisional", 0) == 2
    )
    assert summary.rows_scored == 2


def test_shadow_scoring_handles_missing_features_path(
    pg_session, session_factory, tmp_path,
):
    """Insert a row whose gate_snapshot has no `ctx_rates_calm` key —
    it should be excluded as missing_features."""
    pg_session.execute(text(
        """
        INSERT INTO paper_observation_label
          (domain, source, options_observation_id, entry_date,
           symbol, rule_id, failed_gates, gate_snapshot,
           outcome_class, label_version, is_provisional)
        VALUES
          ('equity', 'research_fast_fill', 'no-feat', '2026-02-15',
           'SPY', 'research_fast_fill_open_buy_v1',
           '{}'::text[],
           '{}'::jsonb,
           'neutral',
           'label-v1.0.0', FALSE)
        """
    ))
    pg_session.commit()
    model_id, reg = _registered(tmp_path)
    summary = run_scorer(
        _cfg(model_id, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    assert summary.rows_input == 1
    assert summary.rows_scored == 0
    assert (
        summary.rows_excluded_by_reason.get("missing_features", 0)
        == 1
    )


def test_shadow_scoring_includes_realized_label_when_present(
    pg_session, session_factory, tmp_path,
):
    _seed_labels(pg_session, n_high=2, n_low=0)
    model_id, reg = _registered(tmp_path)
    summary = run_scorer(
        _cfg(model_id, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    assert summary.rows_with_realized_label == 2


def test_shadow_scoring_classification_pickle_end_to_end(
    pg_session, session_factory, tmp_path,
):
    """Stub classifier returns p_pos=0.9 → all rows in SHADOW_HIGH."""
    _seed_labels(pg_session, n_high=3, n_low=2)
    model_id, reg = _registered(tmp_path)
    summary = run_scorer(
        _cfg(model_id, output_dir=str(tmp_path)),
        session_factory=session_factory, registry_path=reg,
    )
    buckets = [r.model_bucket for r in summary.rows]
    assert all(b == SHADOW_HIGH for b in buckets)


def test_shadow_scoring_does_not_register_into_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert all(
        "shadow" not in k.lower() for k in REGISTRY.keys()
    )
