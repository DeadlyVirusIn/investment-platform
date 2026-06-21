"""M6 — public-beta / deploy preflight checks (read-only, safe).

`evaluate_config(...)` is a pure validator (unit-testable) for the deploy-unsafe
config flags + required env. The DB helpers (`check_tables`, `migration_version`)
are read-only. In `dev` mode unsafe flags are warnings (local dev must not be
blocked); in `prod` mode they are hard errors.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# Env that must be present (non-empty) for a real deployment.
REQUIRED_PROD_ENV = ("DATABASE_URL", "FERNET_KEY")

# Tables that must exist for the auth + profile + feedback stack.
REQUIRED_TABLES = (
    "app_user", "user_session", "user_profile", "login_attempt", "user_feedback_signal",
)


@dataclass(frozen=True)
class Issue:
    level: str   # "error" | "warn"
    key: str
    message: str


def evaluate_config(
    *,
    mode: str,
    auth_disabled_local: bool,
    demo_device_mode: bool,
    session_cookie_secure: bool,
    cors_origins: list[str],
    env: dict[str, str | None],
) -> list[Issue]:
    """Pure config validation. mode='prod' makes unsafe flags hard errors;
    mode='dev' downgrades them to warnings so local dev is never blocked."""
    prod = mode == "prod"
    lvl = "error" if prod else "warn"
    issues: list[Issue] = []

    if auth_disabled_local:
        issues.append(Issue(lvl, "AUTH_DISABLED_LOCAL", "must be False in production (currently True)"))
    if demo_device_mode:
        issues.append(Issue(lvl, "DEMO_DEVICE_MODE", "must be False in production (currently True)"))
    if not session_cookie_secure:
        issues.append(Issue(lvl, "SESSION_COOKIE_SECURE", "must be True behind HTTPS in production"))

    if prod:
        if not cors_origins:
            issues.append(Issue("error", "CORS", "no allowed origins configured"))
        else:
            local = [o for o in cors_origins if "localhost" in o or "127.0.0.1" in o]
            if local:
                issues.append(Issue("warn", "CORS", f"localhost origins present (replace with the prod origin): {local}"))

    for k in REQUIRED_PROD_ENV:
        if not env.get(k):
            issues.append(Issue(lvl, k, "required env is missing/empty"))

    return issues


def config_ok(issues: list[Issue], *, mode: str) -> bool:
    """In prod, any error blocks; in dev nothing blocks."""
    if mode != "prod":
        return True
    return not any(i.level == "error" for i in issues)


def check_tables(db: Session) -> dict[str, bool]:
    present: dict[str, bool] = {}
    for t in REQUIRED_TABLES:
        present[t] = bool(
            db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar()
        )
    return present


def migration_version(db: Session) -> str | None:
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None
