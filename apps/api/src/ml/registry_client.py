"""API-side entry point to the research-run registry (Sprint 5).

The spec's contract is "one write module, two entry points"
(RESEARCH_RUN_REGISTRY_SPEC.md §4): all validation and immutability rules
live in apps.ml.lab.registry; this module is the apps.api import surface
for it, so future admin routes and worker jobs never grow a second write
path with divergent semantics. Import from here inside apps/api; research
scripts may import apps.ml.lab.registry directly — both names resolve to
the same objects.
"""

from __future__ import annotations

from apps.ml.lab.registry import (
    ARTIFACT_KINDS,
    ERROR_SUMMARY_MAX_CHARS,
    RUN_TYPES,
    TERMINAL_STATUSES,
    InvalidTransitionError,
    MetricOverwriteError,
    RegistryClient,
    RegistryError,
    RunFrozenError,
    canonical_json,
    config_hash,
    data_hash,
    new_run_uid,
    registry_table_exists,
    resolve_git_sha,
    sha256_file,
)

__all__ = [
    "ARTIFACT_KINDS",
    "ERROR_SUMMARY_MAX_CHARS",
    "RUN_TYPES",
    "TERMINAL_STATUSES",
    "InvalidTransitionError",
    "MetricOverwriteError",
    "RegistryClient",
    "RegistryError",
    "RunFrozenError",
    "canonical_json",
    "config_hash",
    "data_hash",
    "new_run_uid",
    "registry_table_exists",
    "resolve_git_sha",
    "sha256_file",
]
