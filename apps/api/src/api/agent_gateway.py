"""Agent Gateway v0 — /agent router + Bearer auth dependency (spec §4).

Mounted ONLY when settings.AGENT_GATEWAY_ENABLED is True (fail-closed); when
False the router and its audit middleware are never added, so every /agent
path 404s and no token surface exists.

Security boundary (spec §1): every guarantee is enforced server-side here.
Auth is `Authorization: Bearer arthos_at_…` resolved by `require_agent_scope`
— never the `arthos_session` cookie (agent tokens and browser sessions are
non-interchangeable in both directions). A token missing the route's scope
gets 403; a bad/expired/revoked token gets 401; the DB being unreachable gets
503 (fail closed, never fail open); and all of them — like every request —
are written to `agent_audit` by the middleware, which no route can bypass
(spec §5).

Implemented scopes:
  R — bounded read-only recommendations (list + detail with evidence).
      Serves ONLY the already-public recommendation corpus (SECURITY_AUDIT:
      /api/recommendations is a public surface); no research_report, thesis,
      admin, or model-internal fields cross this boundary.
  P — the token owner's OWN paper book (user:<created_by>:stock), resolved
      server-side from the token (spec §7.4). Read-only: positions, cash,
      trades, live snapshots. No mutation path exists.
  B/D — scope-gated, audited, bounded 501 stubs until their server-side
      job/report contracts land (separate approval-gated slices).

Abuse bounds (spec §8 T5): per-token fixed-window rate limit + a global
gateway budget (in-memory — correct for the one-VM deployment; a second
process would need a shared store, noted in the module for that future),
Content-Length precheck (413 before body parse), query-string cap, strict
pagination ceilings.
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from apps.api.src.config import settings
from apps.api.src.domain.agent_gateway import audit, tokens

router = APIRouter(prefix="/agent", tags=["agent-gateway"])

# ---------------------------------------------------------------------------
# Bounds (spec §4/§8) — constants, not configuration: nothing to misconfigure.
# ---------------------------------------------------------------------------
MAX_PAGE_SIZE = 50          # recommendations list
MAX_TRADES_PAGE = 100       # portfolio trades list
MAX_OFFSET = 10_000         # pagination abuse ceiling
MAX_EVIDENCE_PER_REC = 20   # evidence items serialized per recommendation
MAX_TEXT_LEN = 2_000        # rationale/summary truncation in responses
MAX_QUERY_BYTES = 2_048     # raw query-string cap → 414
GLOBAL_BUDGET_PER_MIN = 600  # all tokens combined (spec §2 global budget)
_DEFAULT_MAX_REQUEST_BYTES = 65_536  # pre-auth Content-Length cap → 413


# ---------------------------------------------------------------------------
# Rate limiting — fixed-window per token_prefix + global window (in-memory).
# One-VM deployment: process-local state is the deployment reality; if the
# API ever runs >1 replica this moves to the DB/redis (documented residual).
# ---------------------------------------------------------------------------
class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (window_start_min, count)

    def hit(self, key: str, limit: int, *, now: float | None = None) -> bool:
        """Count one request. True if within limit, False if over."""
        minute = int((now if now is not None else time.time()) // 60)
        with self._lock:
            start, count = self._windows.get(key, (minute, 0))
            if start != minute:
                start, count = minute, 0
            count += 1
            self._windows[key] = (start, count)
            return count <= limit

    def reset(self) -> None:  # test hook
        with self._lock:
            self._windows.clear()


_limiter = _FixedWindowLimiter()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def _resolve_session_identity(authorization: str | None) -> dict | None:
    """Open a short-lived session, resolve the bearer token. Raises
    HTTPException(503) if the DB is unreachable — fail closed, never open."""
    from apps.api.src.db import SessionLocal

    full = tokens.parse_bearer(authorization)
    try:
        with SessionLocal() as s:
            ident = tokens.resolve_token(s, full)
            if ident is not None:
                s.commit()  # persist last_used_at touch
            return ident
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("agent_gateway_db_unavailable err={}", exc)
        raise HTTPException(status_code=503, detail="gateway unavailable")


def require_agent_scope(scope: str):
    """Dependency factory: require an active token carrying `scope`. Stashes
    audit context on request.state for the middleware, then raises 401 (no/bad
    token), 403 (valid token, missing scope), 429 (rate limit), or 503 (DB
    down). Cookie auth is ignored entirely — a valid arthos_session cookie
    presented without a Bearer token is anonymous here."""

    def _dep(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict:
        # record the presented prefix even on failure (auditable auth attempts)
        presented_prefix = tokens.prefix_of(tokens.parse_bearer(authorization) or "")
        request.state.agent_prefix = presented_prefix
        request.state.agent_name = None
        request.state.agent_scope_used = None

        ident = _resolve_session_identity(authorization)
        if ident is None:
            raise HTTPException(status_code=401, detail="invalid or expired token")

        # identity is known from here on — audit rows carry it even on 403/429
        request.state.agent_prefix = ident["token_prefix"]
        request.state.agent_name = ident["agent_name"]

        # rate limits: global budget first (T5), then the per-token window
        if not _limiter.hit("__global__", GLOBAL_BUDGET_PER_MIN):
            raise HTTPException(status_code=429, detail="gateway budget exceeded")
        if not _limiter.hit(ident["token_prefix"], int(ident["rate_limit_per_min"])):
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        if not tokens.has_scope(ident["scopes"], scope):
            raise HTTPException(status_code=403, detail=f"scope '{scope}' required")

        request.state.agent_scope_used = scope
        return ident

    return _dep


# ---------------------------------------------------------------------------
# Audit middleware — one row per /agent request, success or failure (spec §5),
# plus pre-auth size guards (413/414 before any parsing or DB work).
# ---------------------------------------------------------------------------
class AgentAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/agent"):
            return await call_next(request)
        started = time.monotonic()

        # -- pre-auth guards (no body parse, no DB) --
        response = None
        qs = request.url.query or ""
        if len(qs.encode("utf-8", "ignore")) > MAX_QUERY_BYTES:
            response = JSONResponse({"detail": "query string too long"}, status_code=414)
        else:
            clen = request.headers.get("content-length")
            try:
                if clen is not None and int(clen) > _DEFAULT_MAX_REQUEST_BYTES:
                    response = JSONResponse({"detail": "request too large"}, status_code=413)
            except ValueError:
                response = JSONResponse({"detail": "bad content-length"}, status_code=400)

        if response is None:
            response = await call_next(request)
        duration_ms = int((time.monotonic() - started) * 1000)

        try:
            st = request.state
            route_obj = request.scope.get("route")
            # templated path, never the raw URL. Nested-router route objects
            # carry the un-prefixed template ("/agent/whoami"); normalize the
            # raw-URL fallback to the same shape so audit rows are uniform.
            route_tmpl = getattr(route_obj, "path", None) or request.url.path
            if route_tmpl.startswith("/api/"):
                route_tmpl = route_tmpl[4:]
            from apps.api.src.db import SessionLocal

            with SessionLocal() as s:
                audit.record(
                    s,
                    route=route_tmpl,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    agent_name=getattr(st, "agent_name", None),
                    token_prefix=getattr(st, "agent_prefix", None),
                    scope_used=getattr(st, "agent_scope_used", None),
                    idempotency_key=request.headers.get("Idempotency-Key"),
                    request_hash=audit.canonical_request_hash(
                        request.method, request.url.path, qs, None
                    ),
                )
        except Exception as exc:  # audit must never break the response
            logger.warning("agent_audit_middleware_failed err={}", exc)
        return response


# ---------------------------------------------------------------------------
# Serialization helpers — public-safe shapes only. No model_version,
# snapshot_hash, internal ids beyond the already-public rec/asset uids.
# ---------------------------------------------------------------------------
def _clip(s: str | None, n: int = MAX_TEXT_LEN) -> str | None:
    if s is None:
        return None
    return s if len(s) <= n else s[: n - 1] + "…"


def _rec_row_payload(r) -> dict:
    return {
        "rec_id": r["id"],  # already-public identifier (random v4, /api/recommendations surface)
        "symbol": r["symbol"],
        "action": r["action"],
        "conviction": float(r["conviction"]) if r["conviction"] is not None else None,
        "rationale": _clip(r["rationale"]),
        "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
        "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
    }


# ---------------------------------------------------------------------------
# Routes — R scope (read-only recommendation corpus)
# ---------------------------------------------------------------------------
@router.get("/whoami")
def whoami(ident: dict = Depends(require_agent_scope("R"))) -> dict:
    """Token introspection — no hash, no secret (spec §4)."""
    return {
        "agent_name": ident["agent_name"],
        "token_prefix": ident["token_prefix"],
        "scopes": sorted(ident["scopes"]),
        "rate_limit_per_min": ident["rate_limit_per_min"],
    }


@router.get("/recommendations")
def list_recommendations(
    ident: dict = Depends(require_agent_scope("R")),
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
    action: str | None = Query(default=None, pattern="^(buy|sell|hold)$"),
    include_expired: bool = Query(default=False),
) -> dict:
    """Bounded list of the public recommendation corpus, newest first.
    No symbol fan-out parameter by design — the corpus is served as pages,
    not as an arbitrary-symbol query surface."""
    from apps.api.src.db import SessionLocal

    where = ["1=1"]
    params: dict = {"lim": limit, "off": offset}
    if action:
        where.append("r.action = :action")
        params["action"] = action
    if not include_expired:
        where.append("(r.expires_at IS NULL OR r.expires_at > now())")
    with SessionLocal() as s:
        rows = s.execute(
            text(
                f"""
                SELECT r.id, a.symbol, r.action, r.conviction, r.rationale,
                       r.generated_at, r.expires_at
                FROM recommendation r
                JOIN asset a ON a.id = r.asset_id
                WHERE {' AND '.join(where)}
                ORDER BY r.generated_at DESC
                LIMIT :lim OFFSET :off
                """
            ),
            params,
        ).mappings().all()
    return {
        "recommendations": [_rec_row_payload(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "disclaimer": "Paper research output — not investment advice, no guaranteed returns.",
    }


@router.get("/recommendations/{rec_id}")
def get_recommendation(
    rec_id: str,
    ident: dict = Depends(require_agent_scope("R")),
) -> dict:
    """One recommendation + its evidence. Unknown id → 404 (no existence
    oracle beyond the already-public corpus)."""
    from apps.api.src.db import SessionLocal

    with SessionLocal() as s:
        row = s.execute(
            text(
                """
                SELECT r.id, a.symbol, r.action, r.conviction, r.rationale,
                       r.generated_at, r.expires_at
                FROM recommendation r
                JOIN asset a ON a.id = r.asset_id
                WHERE r.id = :rid
                """
            ),
            {"rid": rec_id[:36]},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404)
        ev = s.execute(
            text(
                """
                SELECT evidence_type, source, summary, weight
                FROM recommendation_evidence
                WHERE recommendation_id = :rid
                ORDER BY created_at ASC
                LIMIT :cap
                """
            ),
            {"rid": rec_id[:36], "cap": MAX_EVIDENCE_PER_REC},
        ).mappings().all()
    payload = _rec_row_payload(row)
    payload["evidence"] = [
        {
            "type": e["evidence_type"],
            "source": _clip(e["source"], 256),
            "summary": _clip(e["summary"]),
            "weight": float(e["weight"]) if e["weight"] is not None else None,
        }
        for e in ev
    ]
    return payload


# ---------------------------------------------------------------------------
# Routes — P scope (the token owner's OWN paper book; read-only)
# ---------------------------------------------------------------------------
def _own_book_id(s, ident: dict) -> str | None:
    """Resolve the caller's own book from the TOKEN identity (spec §7.4) —
    user:<created_by>:stock. Never from a client-supplied id. Read-only:
    absent book is NOT created here."""
    from apps.api.src.domain.paper_trading.paper_service import (
        user_stock_portfolio_name,
    )

    row = s.execute(
        text("SELECT id FROM paper_portfolio WHERE name = :n"),
        {"n": user_stock_portfolio_name(ident["created_by"])},
    ).mappings().first()
    return row["id"] if row else None


@router.get("/portfolio")
def get_portfolio(ident: dict = Depends(require_agent_scope("P"))) -> dict:
    """The caller's own paper book: cash, open positions, latest live
    snapshot. Owner identity comes from the token; no portfolio id crosses
    the boundary in either direction."""
    from apps.api.src.db import SessionLocal

    with SessionLocal() as s:
        pid = _own_book_id(s, ident)
        if pid is None:
            return {"exists": False, "positions": [], "note": "no paper book yet"}
        book = s.execute(
            text("SELECT cash, starting_cash FROM paper_portfolio WHERE id = :p"),
            {"p": pid},
        ).mappings().first()
        pos = s.execute(
            text(
                """
                SELECT a.symbol, pp.quantity, pp.avg_cost, pp.opened_at
                FROM paper_position pp JOIN asset a ON a.id = pp.asset_id
                WHERE pp.portfolio_id = :p AND pp.is_open = true
                ORDER BY pp.opened_at DESC
                LIMIT 200
                """
            ),
            {"p": pid},
        ).mappings().all()
        snap = s.execute(
            text(
                """
                SELECT snapshot_date, cash, positions_value, total_equity
                FROM paper_equity_snapshot
                WHERE portfolio_id = :p AND source = 'live'
                ORDER BY snapshot_date DESC LIMIT 1
                """
            ),
            {"p": pid},
        ).mappings().first()
    return {
        "exists": True,
        "cash": float(book["cash"]),
        "starting_cash": float(book["starting_cash"]),
        "positions": [
            {
                "symbol": p["symbol"],
                "quantity": float(p["quantity"]),
                "avg_cost": float(p["avg_cost"]),
                "opened_at": p["opened_at"].isoformat() if p["opened_at"] else None,
            }
            for p in pos
        ],
        "latest_snapshot": (
            {
                "date": snap["snapshot_date"].isoformat(),
                "cash": float(snap["cash"]),
                "positions_value": float(snap["positions_value"]),
                "total_equity": float(snap["total_equity"]),
            }
            if snap
            else None
        ),
        "disclaimer": "Paper (practice) book — simulated fills, not real money.",
    }


@router.get("/portfolio/trades")
def get_portfolio_trades(
    ident: dict = Depends(require_agent_scope("P")),
    limit: int = Query(default=50, ge=1, le=MAX_TRADES_PAGE),
    offset: int = Query(default=0, ge=0, le=MAX_OFFSET),
) -> dict:
    """Paginated trades from the caller's own book only."""
    from apps.api.src.db import SessionLocal

    with SessionLocal() as s:
        pid = _own_book_id(s, ident)
        if pid is None:
            return {"trades": [], "limit": limit, "offset": offset}
        rows = s.execute(
            text(
                """
                SELECT a.symbol, t.side, t.quantity, t.fill_price, t.fill_ts,
                       t.realized_pnl, t.commission
                FROM paper_trade t JOIN asset a ON a.id = t.asset_id
                WHERE t.portfolio_id = :p
                ORDER BY t.fill_ts DESC
                LIMIT :lim OFFSET :off
                """
            ),
            {"p": pid, "lim": limit, "off": offset},
        ).mappings().all()
    return {
        "trades": [
            {
                "symbol": r["symbol"],
                "side": r["side"],
                "quantity": float(r["quantity"]),
                "fill_price": float(r["fill_price"]),
                "fill_ts": r["fill_ts"].isoformat() if r["fill_ts"] else None,
                "realized_pnl": float(r["realized_pnl"]) if r["realized_pnl"] is not None else None,
                "commission": float(r["commission"]) if r["commission"] is not None else None,
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Routes — B/D scopes: bounded stubs until their server-side contracts land.
# Scope-gated + audited; 501 (not 404) so a correctly-scoped client learns
# the surface exists but is not yet implemented.
# ---------------------------------------------------------------------------
def _not_yet(what: str):
    raise HTTPException(status_code=501, detail=f"{what} not implemented in gateway v0")


@router.post("/jobs")
def submit_job(_: dict = Depends(require_agent_scope("B"))):
    _not_yet("offline job submission")


@router.post("/drafts")
def create_draft(_: dict = Depends(require_agent_scope("D"))):
    _not_yet("draft report creation")
