"""Options Trade History (Phase 1) — read-only contract tests.

Pins (source + route, no DB required — testcontainer not needed):
  1. service_readonly + routes_readonly import without a live DB.
  2. The enhanced trade-history DTO keys are present in service source
     (proposal_hash, position_id, released_at, release_reason) so the
     WebUI hook stays in sync.
  3. list_paper_trades exposes the additive `strategy` param.
  4. The /paper-trades route exposes the `strategy` query param.
  5. The options read-only router is GET-only (no mutation verbs).
  6. The touched functions contain no INSERT/UPDATE/DELETE (read-only).
  7. The LEFT JOIN onto options_paper_position is present (so non-canary
     trades still surface with NULL position fields).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

_SERVICE = Path("apps/api/src/options/service_readonly.py")
_ROUTES = Path("apps/api/src/options/routes_readonly.py")


def test_modules_import_without_db():
    import apps.api.src.options.service_readonly as svc  # noqa: F401
    import apps.api.src.options.routes_readonly as routes  # noqa: F401


def test_dto_keys_pinned_in_service_source():
    src = _SERVICE.read_text(encoding="utf-8")
    for key in (
        '"proposal_hash"', '"position_id"',
        '"released_at"', '"release_reason"',
    ):
        assert key in src, f"trade-history DTO missing key: {key}"


def test_left_join_position_present():
    src = _SERVICE.read_text(encoding="utf-8")
    assert "options_paper_position" in src
    assert re.search(
        r"LEFT JOIN\s+options_paper_position\s+p\s+ON\s+p\.trade_id\s*=\s*t\.id",
        src,
    ), "expected LEFT JOIN options_paper_position p ON p.trade_id = t.id"


def test_service_has_strategy_param():
    from apps.api.src.options.service_readonly import list_paper_trades
    sig = inspect.signature(list_paper_trades)
    assert "strategy" in sig.parameters, "list_paper_trades missing strategy"
    # additive + backward-compatible: keyword-only, defaults None
    p = sig.parameters["strategy"]
    assert p.default is None
    # existing params preserved
    for existing in ("status", "underlying", "limit"):
        assert existing in sig.parameters


def test_route_has_strategy_param():
    from apps.api.src.options.routes_readonly import list_paper_trades
    sig = inspect.signature(list_paper_trades)
    assert "strategy" in sig.parameters, "/paper-trades route missing strategy"


def test_options_router_is_get_only():
    import apps.api.src.options.routes_readonly as routes
    bad: list[str] = []
    for r in routes.router.routes:
        methods = getattr(r, "methods", set()) or set()
        for m in methods:
            if m.upper() not in ("GET", "HEAD", "OPTIONS"):
                bad.append(f"{getattr(r, 'path', '?')} -> {m}")
    assert not bad, f"non-GET methods registered: {bad}"


def test_paper_trades_route_registered():
    import apps.api.src.options.routes_readonly as routes
    paths = {getattr(r, "path", "") for r in routes.router.routes}
    assert any(p.endswith("/paper-trades") for p in paths), (
        f"/paper-trades route missing; have {sorted(paths)}"
    )


def test_no_writes_in_service_source():
    src = _SERVICE.read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        stripped = line.lstrip()
        if (stripped.startswith('"') or stripped.startswith("#")
                or stripped.startswith("'")):
            continue
        for pat in write_patterns:
            assert not pat.search(line), (
                f"write found in read-only service: {line.strip()}"
            )


def test_no_mutation_verbs_on_routes():
    src = _ROUTES.read_text(encoding="utf-8")
    for verb in ("@router.post", "@router.put", "@router.delete",
                 "@router.patch"):
        assert verb not in src, f"forbidden HTTP verb in routes: {verb}"
