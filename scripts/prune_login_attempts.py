"""Prune old login_attempt rows (M1C auth ops).

Deletes login_attempt rows older than AUTH_LOGIN_ATTEMPT_RETENTION_DAYS, but
NEVER rows within the active window+lockout horizon (hard min-keep floor), so
current lockout/rate-limit calculations are unaffected. Manual/admin command —
no scheduler. Run via `make prune-login-attempts`.
"""

from __future__ import annotations

from apps.api.src.auth import identity as ident
from apps.api.src.config import settings
from apps.api.src.db import SessionLocal


def main() -> None:
    min_keep = float(settings.AUTH_LOGIN_WINDOW_SECONDS + settings.AUTH_LOGIN_LOCKOUT_SECONDS)
    with SessionLocal() as s:
        deleted = ident.prune_login_attempts(
            s,
            retention_days=settings.AUTH_LOGIN_ATTEMPT_RETENTION_DAYS,
            min_keep_seconds=min_keep,
        )
        s.commit()
    print(
        f"pruned {deleted} login_attempt rows "
        f"(retention={settings.AUTH_LOGIN_ATTEMPT_RETENTION_DAYS}d, min_keep={int(min_keep)}s)"
    )


if __name__ == "__main__":
    main()
