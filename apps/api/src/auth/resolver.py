"""Phase G — server-side auth + effective-tier resolver.

Authentication: minimal placeholder that reads `X-Auth-User-Id` from
the request header and looks up the user in `public.app_user`. When
`AUTH_DISABLED_LOCAL=true`, falls back to a synthetic dev user
named `local-dev` (auto-created on first call). Real JWT/session
auth is intentionally deferred — the abstraction lives here so a
future swap is one-file.

Tier resolution priority (deterministic):
  1. effective tier from active org subscription that grants
     enterprise (caller must be active member of that org)
  2. effective tier from active user subscription
  3. 'free'

Subscription `status` rules:
  * `active`, `trialing` → tier honored
  * `past_due`, `canceled`, `expired` →
       grace mode: tier honored if `RESEARCH_GRACE_ENABLED` AND
       `now < current_period_end + RESEARCH_GRACE_HOURS`
       strict (default): downgrade to free

Disabled user (`disabled_at IS NOT NULL`) → all access denied
(returns AuthDecision with `denied=True`).

NEVER imports execution / scoring / ML / candidate / paper /
options modules. NEVER trusts client-provided tier hints.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


_TIER_PRIORITY = {"free": 0, "pro": 1, "enterprise": 2}


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    display_name: str | None
    auth_provider: str
    disabled: bool


@dataclass(frozen=True)
class AuthDecision:
    user: AuthUser | None
    effective_tier: str
    denied: bool
    reason: str


# ---------------------------------------------------------------------------
# DB lookups
# ---------------------------------------------------------------------------


def _get_user_by_id(s: Session, user_id: str) -> AuthUser | None:
    row = s.execute(text(
        """
        SELECT id, email, display_name, auth_provider, disabled_at
        FROM public.app_user WHERE id = :id
        """
    ), {"id": user_id}).mappings().first()
    if row is None:
        return None
    return AuthUser(
        id=row["id"], email=row["email"],
        display_name=row["display_name"],
        auth_provider=row["auth_provider"],
        disabled=row["disabled_at"] is not None,
    )


def _ensure_local_dev_user(s: Session) -> AuthUser:
    """Idempotent insert-or-return for the local-dev synthetic user.
    Used only when `AUTH_DISABLED_LOCAL=true`."""
    s.execute(text(
        """
        INSERT INTO public.app_user
          (id, email, display_name, auth_provider)
        VALUES ('local-dev', 'local-dev@local',
                'Local Dev', 'placeholder')
        ON CONFLICT (id) DO NOTHING
        """
    ))
    s.commit()
    user = _get_user_by_id(s, "local-dev")
    assert user is not None
    return user


def _user_subscription_tier(
    s: Session, *, user_id: str, now: dt.datetime,
) -> str:
    """Best (highest) tier from active user-scope subscriptions."""
    rows = s.execute(text(
        """
        SELECT tier, status, current_period_end
        FROM public.subscription
        WHERE subject_type = 'user' AND subject_id = :uid
        """
    ), {"uid": user_id}).mappings().all()
    return _best_tier_from_rows(rows, now=now)


def _org_subscription_tier(
    s: Session, *, user_id: str, now: dt.datetime,
) -> str:
    """Best tier from any active org membership the user holds."""
    rows = s.execute(text(
        """
        SELECT sub.tier, sub.status, sub.current_period_end
        FROM public.subscription sub
        JOIN public.organization_member m
          ON m.org_id = sub.subject_id
         AND m.user_id = :uid
         AND m.status = 'active'
        WHERE sub.subject_type = 'org'
        """
    ), {"uid": user_id}).mappings().all()
    return _best_tier_from_rows(rows, now=now)


def _best_tier_from_rows(rows, *, now: dt.datetime) -> str:
    best = "free"
    for r in rows:
        tier = r["tier"]
        status = r["status"]
        period_end = r["current_period_end"]
        if not _subscription_active(status, period_end, now):
            continue
        if _TIER_PRIORITY[tier] > _TIER_PRIORITY[best]:
            best = tier
    return best


def _subscription_active(
    status: str, period_end: dt.datetime | None, now: dt.datetime,
) -> bool:
    if status in ("active", "trialing"):
        return True
    if status in ("past_due", "canceled", "expired"):
        if not bool(settings.RESEARCH_GRACE_ENABLED):
            return False
        if period_end is None:
            return False
        grace = dt.timedelta(hours=int(settings.RESEARCH_GRACE_HOURS))
        return now <= period_end + grace
    return False


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------


def resolve_auth_decision(
    session: Session, *,
    user_id_header: str | None,
    now: dt.datetime | None = None,
) -> AuthDecision:
    """Pure-fn (no HTTP). Caller passes the header value (or None)
    and gets a structured decision back."""
    cur_now = now or dt.datetime.now(dt.timezone.utc)
    if bool(settings.AUTH_DISABLED_LOCAL):
        # Local dev: synthetic user; tier from env.
        user = _ensure_local_dev_user(session)
        env_tier = (settings.RESEARCH_PREMIUM_TIER or "free").strip().lower()
        if env_tier not in ("free", "pro", "enterprise"):
            env_tier = "free"
        return AuthDecision(
            user=user,
            effective_tier=env_tier,
            denied=False,
            reason="auth_disabled_local",
        )

    if not user_id_header:
        # Anonymous → free, not denied (read-only Free surfaces).
        return AuthDecision(
            user=None, effective_tier="free",
            denied=False, reason="anonymous",
        )
    user = _get_user_by_id(session, user_id_header)
    if user is None:
        return AuthDecision(
            user=None, effective_tier="free",
            denied=False, reason="user_not_found",
        )
    if user.disabled:
        return AuthDecision(
            user=user, effective_tier="free",
            denied=True, reason="user_disabled",
        )

    org_tier = _org_subscription_tier(session, user_id=user.id, now=cur_now)
    user_tier = _user_subscription_tier(session, user_id=user.id, now=cur_now)
    if _TIER_PRIORITY[org_tier] >= _TIER_PRIORITY[user_tier]:
        effective = org_tier
    else:
        effective = user_tier
    return AuthDecision(
        user=user, effective_tier=effective,
        denied=False,
        reason="resolved",
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_current_user(
    request: Request,
    x_auth_user_id: str | None = Header(default=None, alias="X-Auth-User-Id"),
) -> AuthDecision:
    """FastAPI dependency. Opens its own session for the lookup."""
    from apps.api.src.db import SessionLocal
    with SessionLocal() as s:
        decision = resolve_auth_decision(
            s, user_id_header=x_auth_user_id,
        )
    if decision.denied:
        raise HTTPException(status_code=403, detail={
            "code": "auth_denied", "reason": decision.reason,
        })
    return decision


def get_effective_research_tier(
    decision: AuthDecision,
) -> str:
    return decision.effective_tier


def require_enterprise(
    decision: AuthDecision,
) -> AuthDecision:
    if decision.effective_tier != "enterprise":
        raise HTTPException(403, "enterprise tier required")
    return decision
