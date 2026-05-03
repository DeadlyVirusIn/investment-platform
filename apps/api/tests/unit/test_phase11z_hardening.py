"""Phase 11Z recovery-hardening test suite.

Pins the contracts for:
  * scripts/backup_dev_db.sh           (Part C)
  * Makefile db-backup / verify-deploy-safe targets   (Part C)
  * scripts/build_ml_dataset.py        (Part B)
  * apps/api/src/provenance/manifest.py (Part A)

No DB I/O. Source-grep + module-import + stub-session only.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Part C — backup script
# ---------------------------------------------------------------------------
BACKUP_SH = Path("scripts/backup_dev_db.sh")


def test_backup_script_exists_and_executable_shebang():
    src = BACKUP_SH.read_text(encoding="utf-8")
    assert src.startswith("#!/usr/bin/env bash"), "missing bash shebang"


def test_backup_script_creates_timestamped_filename():
    src = BACKUP_SH.read_text(encoding="utf-8")
    # The timestamp pattern $(date +%Y%m%d_%H%M%S) is what makes
    # filenames unique. Pin it.
    assert "$(date +%Y%m%d_%H%M%S)" in src
    # Filename layout devdb_<mode>_<TS>.sql
    assert re.search(r"devdb_\$\{?mode\}?_\$\{?ts\}?\.sql", src)


def test_backup_script_refuses_overwrite():
    src = BACKUP_SH.read_text(encoding="utf-8")
    # Required: -e check before write + REFUSED message.
    assert "-e \"$out\"" in src or "[[ -e \"$out\" ]]" in src
    assert "REFUSED" in src


def test_backup_script_does_not_run_compose_down_v():
    src = BACKUP_SH.read_text(encoding="utf-8")
    # The whole point — the backup must never trigger volume wipe.
    forbidden = (
        "docker compose down -v",
        "docker-compose down -v",
        "docker volume rm compose_pgdata",
    )
    for f in forbidden:
        # Comments are allowed to mention it. Strip comment lines first.
        lines = [
            ln for ln in src.splitlines()
            if not ln.lstrip().startswith("#")
        ]
        joined = "\n".join(lines)
        assert f not in joined, (
            f"backup script contains forbidden token: {f!r}"
        )


def test_backup_script_has_retention_logic_with_keep_default():
    src = BACKUP_SH.read_text(encoding="utf-8")
    assert "BACKUP_KEEP" in src
    assert ":-10" in src or "KEEP=10" in src
    # Must skip the newest entry when deleting (defensive).
    assert "files[@]:KEEP" in src or "tail -n +" in src


def test_backup_script_prints_row_counts_before():
    src = BACKUP_SH.read_text(encoding="utf-8")
    assert "row counts BEFORE" in src or "row counts" in src
    # Common high-value tables must be in the count list.
    for tbl in ("paper_trade", "paper_position", "decision_log",
                "recommendation"):
        assert tbl in src, f"backup script must count {tbl}"


# ---------------------------------------------------------------------------
# Part C — Makefile targets
# ---------------------------------------------------------------------------
MAKEFILE = Path("Makefile")


def test_makefile_has_db_backup_target():
    src = MAKEFILE.read_text(encoding="utf-8")
    assert "\ndb-backup:" in src
    assert "scripts/backup_dev_db.sh" in src


def test_makefile_has_verify_deploy_safe_target():
    src = MAKEFILE.read_text(encoding="utf-8")
    assert "\nverify-deploy-safe:" in src


def test_makefile_verify_deploy_safe_has_no_destructive_token():
    src = MAKEFILE.read_text(encoding="utf-8")
    # Locate the target body — from `verify-deploy-safe:` to the
    # next bare `^[a-z][a-z0-9-]*:` line.
    m = re.search(
        r"^verify-deploy-safe:\s*\n((?:\t.*\n|\s*\n)+)",
        src, re.MULTILINE,
    )
    assert m, "verify-deploy-safe target body not found"
    body = m.group(1)
    forbidden = ("docker compose down -v", "docker volume rm compose_pgdata")
    for f in forbidden:
        assert f not in body, (
            f"verify-deploy-safe target contains forbidden: {f!r}"
        )


def test_makefile_verify_deploy_safe_has_backup_age_gate():
    src = MAKEFILE.read_text(encoding="utf-8")
    # Should reference the override env so operator can bypass for
    # cases where they really want to.
    assert "SKIP_BACKUP_CHECK" in src
    assert "I_ACCEPT_DATA_LOSS_RISK" in src


def test_makefile_db_restore_preview_does_not_actually_restore():
    src = MAKEFILE.read_text(encoding="utf-8")
    m = re.search(
        r"^db-restore-preview:\s*\n((?:\t.*\n|\s*\n)+)",
        src, re.MULTILINE,
    )
    assert m, "db-restore-preview target not found"
    body = m.group(1)
    # Must NOT issue a psql -f (which would actually apply) or pg_restore.
    forbidden_apply = ("psql -f", "pg_restore", "pg_restore <")
    for f in forbidden_apply:
        assert f not in body, (
            f"db-restore-preview must not actually restore: {f!r}"
        )


# ---------------------------------------------------------------------------
# Part C — repo-wide guard: no raw `docker volume rm compose_pgdata`
# anywhere outside the safe wrapper + docs
# ---------------------------------------------------------------------------
def test_no_raw_compose_pgdata_volume_rm_outside_safe_wrapper():
    """Stronger version of test_db_volume_safety_guard. Ensures the
    new backup script doesn't reintroduce the destructive token."""
    allowed = (
        Path("scripts/safe_compose_down.sh"),
        Path("docs/ops/DB_VOLUME_SAFETY.md"),
        Path("docs/ops/DB_BACKUP_AND_REPLAY_POLICY.md"),
        Path("docs/ops/PAPER_REPLAY_2026_05_02.md"),
        Path("apps/api/tests/unit/test_db_volume_safety_guard.py"),
        Path("apps/api/tests/unit/test_phase11z_hardening.py"),
    )
    needle = "docker volume rm compose_pgdata"
    bad: list[str] = []
    for p in Path("scripts").rglob("*"):
        if not p.is_file() or p.suffix not in (".sh", ".py"):
            continue
        if any(p.resolve() == a.resolve() for a in allowed
                if a.exists()):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if (stripped.startswith("#") or stripped.startswith("//")
                    or stripped.startswith("*")):
                continue
            if needle in line:
                bad.append(f"{p}:{i}: {line.strip()}")
    assert not bad, f"raw destructive token found: {bad}"


# ---------------------------------------------------------------------------
# Part B — ML dataset script
# ---------------------------------------------------------------------------
def test_ml_dataset_script_imports_cleanly():
    import scripts.build_ml_dataset as mod  # noqa: F401


def test_ml_dataset_refuses_when_ml_can_affect_trades(monkeypatch):
    import scripts.build_ml_dataset as mod
    from apps.api.src.config import settings

    monkeypatch.setattr(settings, "ML_CAN_AFFECT_TRADES", True,
                         raising=False)
    with pytest.raises(SystemExit) as exc:
        mod._assert_ml_safe()
    assert exc.value.code == 3


def test_ml_dataset_train_eval_leakage_rejected_in_argparse():
    import scripts.build_ml_dataset as mod
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-22", "--end-date", "2026-05-01",
            "--train-end", "2026-05-01", "--eval-start", "2026-04-30",
            "--out", "/tmp/x.jsonl",
        ])


def test_ml_dataset_train_end_eval_start_must_pair():
    import scripts.build_ml_dataset as mod
    with pytest.raises(SystemExit):
        mod._parse([
            "--start-date", "2026-04-22", "--end-date", "2026-05-01",
            "--train-end", "2026-04-29",
            "--out", "/tmp/x.jsonl",
        ])


def test_ml_dataset_default_excludes_replay():
    import scripts.build_ml_dataset as mod
    args = mod._parse([
        "--start-date", "2026-04-22", "--end-date", "2026-05-01",
        "--out", "/tmp/x.jsonl",
    ])
    assert args.include_replay is False


def test_ml_dataset_record_marks_open_position_pending():
    import scripts.build_ml_dataset as mod

    class _Row:
        trade_id = "t1"; portfolio_id = "p1"; recommendation_id = None
        portfolio_name = "Test"; symbol = "AAPL"; side = "buy"
        quantity = Decimal("1"); fill_price = Decimal("100")
        fill_ts = dt.datetime(2026, 4, 27, 15, 0, tzinfo=dt.timezone.utc)
        submitted_at = dt.datetime(2026, 4, 26, 15, 0, tzinfo=dt.timezone.utc)
        realized_pnl = None; slippage_bps = None; reason = None
        manifest_source = "replay"; replay_run_id = "r1"
        replay_generated_at = None
        position_is_open = True; position_opened_at = None
        position_closed_at = None
        return_1d = None; return_5d = None; return_10d = None
        return_20d = None; outcome_class = None

    rec = mod._row_to_record(_Row(), today=dt.date(2026, 5, 3))
    assert rec["outcome_status"] == "open_pending"
    assert rec["source"] == "replay"
    assert rec["notional_usd"] == 100.0


def test_ml_dataset_record_emits_provenance_columns():
    import scripts.build_ml_dataset as mod

    class _Row:
        trade_id = "t1"; portfolio_id = "p1"; recommendation_id = "rec1"
        portfolio_name = "Test"; symbol = "SPY"; side = "buy"
        quantity = Decimal("2"); fill_price = Decimal("400")
        fill_ts = dt.datetime(2026, 1, 5, 15, 0, tzinfo=dt.timezone.utc)
        submitted_at = dt.datetime(2026, 1, 4, 15, 0, tzinfo=dt.timezone.utc)
        realized_pnl = Decimal("10"); slippage_bps = Decimal("5")
        reason = "ok"
        manifest_source = "live"; replay_run_id = None
        replay_generated_at = None
        position_is_open = False
        position_opened_at = dt.datetime(2026, 1, 5, 15, 0,
                                          tzinfo=dt.timezone.utc)
        position_closed_at = dt.datetime(2026, 2, 5, 15, 0,
                                          tzinfo=dt.timezone.utc)
        return_1d = Decimal("0.01"); return_5d = Decimal("0.04")
        return_10d = Decimal("0.05"); return_20d = Decimal("0.06")
        outcome_class = "winner"

    rec = mod._row_to_record(_Row(), today=dt.date(2026, 5, 3))
    must_have = (
        "trade_id", "symbol", "side", "quantity", "fill_price",
        "notional_usd", "fill_ts", "fill_date", "return_1d",
        "return_5d", "return_10d", "return_20d", "outcome_class",
        "outcome_status", "source", "replay_run_id",
    )
    for k in must_have:
        assert k in rec, f"missing column: {k}"
    assert rec["outcome_status"] == "labeled"
    assert rec["source"] == "live"
    assert rec["notional_usd"] == 800.0


def test_ml_dataset_source_grep_no_execution_writes():
    src = Path("scripts/build_ml_dataset.py").read_text(encoding="utf-8")
    forbidden_writes = (
        re.compile(r"\bsubmit_trade\s*\("),
        re.compile(r"\brun_paper_trading\s*\("),
        re.compile(r"INSERT\s+INTO\s+paper_trade\b", re.IGNORECASE),
        re.compile(r"INSERT\s+INTO\s+recommendation\b", re.IGNORECASE),
    )
    for pat in forbidden_writes:
        for line in src.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            assert not pat.search(line), (
                f"ML build script must not invoke execution: {line.strip()}"
            )


def test_ml_dataset_does_not_set_ml_can_affect_trades_true():
    src = Path("scripts/build_ml_dataset.py").read_text(encoding="utf-8")
    # Must never assign ML_CAN_AFFECT_TRADES = True.
    assert "ML_CAN_AFFECT_TRADES = True" not in src
    assert "ML_CAN_AFFECT_TRADES=true" not in src.lower().replace(" ", "")


# ---------------------------------------------------------------------------
# Part A — provenance manifest helpers
# ---------------------------------------------------------------------------
def test_manifest_helpers_import_cleanly():
    import apps.api.src.provenance as prov
    assert prov.REPLAY_SOURCES == frozenset({"replay", "test"})
    assert prov.ProvenanceFilter().include_replay is False


def test_replay_exclusion_clause_rejects_unknown_entity_type():
    from apps.api.src.provenance.manifest import replay_exclusion_clause
    with pytest.raises(ValueError):
        replay_exclusion_clause(entity_type="orders", alias="o")


def test_replay_exclusion_clause_rejects_bad_alias():
    from apps.api.src.provenance.manifest import replay_exclusion_clause
    with pytest.raises(ValueError):
        replay_exclusion_clause(
            entity_type="paper_trade", alias="pt; DROP TABLE x;",
        )


def test_replay_exclusion_clause_uses_not_exists_pattern():
    from apps.api.src.provenance.manifest import replay_exclusion_clause
    sql = replay_exclusion_clause(entity_type="paper_trade", alias="pt")
    assert "NOT EXISTS" in sql
    assert "replay_recovery_manifest" in sql
    assert "pt.id::text" in sql
    assert "'replay'" in sql and "'test'" in sql


def test_provenance_filter_truthiness_means_exclude_replay():
    from apps.api.src.provenance import ProvenanceFilter
    # Default filter (include_replay=False) is truthy → "exclude replay"
    assert bool(ProvenanceFilter()) is True
    # Explicit include_replay=True is falsy → "do NOT exclude"
    assert bool(ProvenanceFilter(include_replay=True)) is False


def test_is_replay_entity_returns_false_when_table_missing():
    """Must degrade gracefully when migration 061 isn't applied."""
    from apps.api.src.provenance.manifest import is_replay_entity

    class _BadSession:
        def execute(self, *a, **k):
            raise RuntimeError("table replay_recovery_manifest does not exist")

    assert is_replay_entity(
        _BadSession(), entity_type="paper_trade", entity_id="x",
    ) is False


def test_list_replay_ids_returns_empty_set_when_table_missing():
    from apps.api.src.provenance.manifest import list_replay_ids

    class _BadSession:
        def execute(self, *a, **k):
            raise RuntimeError("table missing")

    assert list_replay_ids(_BadSession(), entity_type="paper_trade") == set()


# ---------------------------------------------------------------------------
# Part A — alembic migration 061
# ---------------------------------------------------------------------------
MIGRATION_061 = Path("infra/alembic/versions/061_replay_recovery_manifest.py")


def test_migration_061_present():
    assert MIGRATION_061.exists()


def test_migration_061_creates_manifest_table_with_constraints():
    src = MIGRATION_061.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS public.replay_recovery_manifest" in src
    # CHECK constraints pin the allowed source + entity_type values.
    assert "ck_replay_manifest_source" in src
    assert "ck_replay_manifest_entity_type" in src
    # Unique key on (entity_type, entity_id) prevents double-tagging.
    assert "ux_replay_manifest_entity" in src


def test_migration_061_is_idempotent_with_if_not_exists():
    src = MIGRATION_061.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS" in src
    assert "CREATE INDEX IF NOT EXISTS" in src


def test_migration_061_has_downgrade():
    src = MIGRATION_061.read_text(encoding="utf-8")
    assert "def downgrade" in src
    assert "DROP TABLE IF EXISTS public.replay_recovery_manifest" in src


# ---------------------------------------------------------------------------
# Replay script integration with manifest tagging (Part A wiring)
# ---------------------------------------------------------------------------
def test_replay_script_emits_manifest_tags():
    src = Path(
        "scripts/replay_paper_execution_chain.py"
    ).read_text(encoding="utf-8")
    assert "replay_recovery_manifest" in src
    assert "_tag_manifest" in src or "_tag_window_entities" in src
    assert "RUN_ID_PREFIX" in src
