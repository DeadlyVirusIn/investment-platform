"""P0-4 — build provenance: tie every running container to a git state.

Two incidents were traced to image/code drift the platform could not
see: the 06-04..06-10 paper double-fill corruption (worker image whose
code never existed in git) and the 06-12 candidate-generation outage.
This module is the single runtime reader for the provenance baked into
images at build time (Dockerfile ARG -> ENV, values supplied by the
compose build args / Makefile build target):

    GIT_SHA     full commit sha            (default "unknown")
    GIT_BRANCH  branch name at build       (default "unknown")
    GIT_DIRTY   "true"|"false"             (default "unknown")
    BUILD_TS    ISO-8601 UTC build instant (default "unknown")

Flags raised in the payload:
    dirty_build  — image built from an uncommitted working tree
    unknown_sha  — image built without provenance args (old image, or
                   compose build run without the Makefile/env wrapper)

"SHA not on origin" is deliberately NOT a runtime check (images carry
no git); it is an ops/CI step documented in the deploy runbook:
    git fetch && git branch -r --contains <GIT_SHA>

Pure stdlib. Distinct from research/provenance.py (research-data
lineage — unrelated domain).
"""

from __future__ import annotations

import os

_UNKNOWN = "unknown"


def get_build_provenance() -> dict:
    """Return the image's build provenance + derived flags."""
    sha = os.environ.get("GIT_SHA", _UNKNOWN) or _UNKNOWN
    branch = os.environ.get("GIT_BRANCH", _UNKNOWN) or _UNKNOWN
    dirty = (os.environ.get("GIT_DIRTY", _UNKNOWN) or _UNKNOWN).lower()
    build_ts = os.environ.get("BUILD_TS", _UNKNOWN) or _UNKNOWN

    flags: list[str] = []
    if sha == _UNKNOWN:
        flags.append("unknown_sha")
    if dirty == "true":
        flags.append("dirty_build")

    return {
        "git_sha": sha,
        "git_branch": branch,
        "git_dirty": dirty,
        "build_ts": build_ts,
        "flags": flags,
    }


def provenance_log_line() -> str:
    """One-line startup banner."""
    p = get_build_provenance()
    flag_txt = f" FLAGS={','.join(p['flags'])}" if p["flags"] else ""
    return (
        f"build-provenance sha={p['git_sha'][:12]} branch={p['git_branch']} "
        f"dirty={p['git_dirty']} built={p['build_ts']}{flag_txt}"
    )
