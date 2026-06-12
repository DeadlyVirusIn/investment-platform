"""P0-4 — unit tests for build provenance (pure stdlib, runs anywhere)."""

from __future__ import annotations

from apps.api.src.build_provenance import (
    get_build_provenance,
    provenance_log_line,
)

_VARS = ("GIT_SHA", "GIT_BRANCH", "GIT_DIRTY", "BUILD_TS")


def _clear(monkeypatch):
    for v in _VARS:
        monkeypatch.delenv(v, raising=False)


def test_unset_env_flags_unknown_sha(monkeypatch):
    _clear(monkeypatch)
    p = get_build_provenance()
    assert p["git_sha"] == "unknown"
    assert p["flags"] == ["unknown_sha"]


def test_clean_build_has_no_flags(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_SHA", "a" * 40)
    monkeypatch.setenv("GIT_BRANCH", "phase-1/ledger")
    monkeypatch.setenv("GIT_DIRTY", "false")
    monkeypatch.setenv("BUILD_TS", "2026-06-12T18:30:00Z")
    p = get_build_provenance()
    assert p["flags"] == []
    assert p["git_sha"] == "a" * 40
    assert p["git_branch"] == "phase-1/ledger"
    assert p["git_dirty"] == "false"
    assert p["build_ts"] == "2026-06-12T18:30:00Z"


def test_dirty_build_flagged(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_SHA", "b" * 40)
    monkeypatch.setenv("GIT_DIRTY", "TRUE")  # case-insensitive
    p = get_build_provenance()
    assert "dirty_build" in p["flags"]
    assert "unknown_sha" not in p["flags"]


def test_unknown_and_dirty_can_combine(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_DIRTY", "true")
    p = get_build_provenance()
    assert set(p["flags"]) == {"unknown_sha", "dirty_build"}


def test_empty_string_env_treated_as_unknown(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_SHA", "")
    p = get_build_provenance()
    assert p["git_sha"] == "unknown"
    assert "unknown_sha" in p["flags"]


def test_log_line_contains_short_sha_and_flags(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_SHA", "c" * 40)
    monkeypatch.setenv("GIT_DIRTY", "true")
    line = provenance_log_line()
    assert "c" * 12 in line
    assert ("c" * 13) not in line  # short sha truncation
    assert "FLAGS=dirty_build" in line


def test_determinism(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GIT_SHA", "d" * 40)
    assert get_build_provenance() == get_build_provenance()
