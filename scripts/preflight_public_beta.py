"""M6 — public-beta / Oracle deploy preflight (READ-ONLY, safe).

Checks deploy-unsafe config flags, required env, DB reachability, migration
version, and the key tables. Does NOT deploy, mutate, or require real secrets.

Usage:
  python scripts/preflight_public_beta.py [--mode dev|prod] [--json]
  make public-beta-preflight        # dev (never blocks local dev)
  make public-beta-preflight-prod   # prod (errors -> exit 1)

Modes:
  dev  (default) — unsafe flags are warnings; exit 0 (local dev not blocked).
  prod           — unsafe flags / missing env / missing tables are errors;
                   exit 1 if any error so a deploy gate can fail fast.

CORS origins: read from CORS_ALLOWED_ORIGINS (comma-separated) if set; otherwise
the current hardcoded dev default (http://localhost:5173) is reported, which is
intentionally flagged in prod so the hardcoded origin gets replaced.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from apps.api.src.api.preflight import (
    check_tables,
    config_ok,
    evaluate_config,
    migration_version,
)
from apps.api.src.config import settings
from apps.api.src.db import SessionLocal


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:5173"]  # current hardcoded default in main.py


def main() -> None:
    ap = argparse.ArgumentParser(description="ArthOS public-beta deploy preflight")
    ap.add_argument("--mode", choices=["dev", "prod"], default="dev")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = {
        "DATABASE_URL": (settings.DATABASE_URL or os.environ.get("DATABASE_URL")) or None,
        "FERNET_KEY": (settings.FERNET_KEY or os.environ.get("FERNET_KEY")) or None,
    }
    issues = evaluate_config(
        mode=args.mode,
        auth_disabled_local=bool(settings.AUTH_DISABLED_LOCAL),
        demo_device_mode=bool(settings.DEMO_DEVICE_MODE),
        session_cookie_secure=bool(settings.SESSION_COOKIE_SECURE),
        cors_origins=_cors_origins(),
        env=env,
    )

    db_reachable = True
    tables: dict[str, bool] = {}
    version: str | None = None
    try:
        with SessionLocal() as s:
            tables = check_tables(s)
            version = migration_version(s)
    except Exception:  # noqa: BLE001 — read-only probe; any failure = unreachable
        db_reachable = False

    missing_tables = [t for t, present in tables.items() if not present]
    overall_ok = config_ok(issues, mode=args.mode) and db_reachable and not missing_tables

    result = {
        "mode": args.mode,
        "ok": overall_ok,
        "migration_version": version,
        "db_reachable": db_reachable,
        "tables": tables,
        "missing_tables": missing_tables,
        "issues": [{"level": i.level, "key": i.key, "message": i.message} for i in issues],
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=== ArthOS — public-beta preflight ===")
        print(f"mode: {args.mode}   overall: {'OK' if overall_ok else 'NOT READY'}")
        print(f"migration_version: {version}   db_reachable: {db_reachable}")
        print("tables:")
        for t, present in tables.items():
            print(f"  {'OK ' if present else 'MISSING'} {t}")
        if issues:
            print("config issues:")
            for i in issues:
                print(f"  [{i.level}] {i.key}: {i.message}")
        else:
            print("config issues: none")

    # dev never blocks; prod exits 1 on any error so a CI/deploy gate fails fast.
    sys.exit(0 if (args.mode != "prod" or overall_ok) else 1)


if __name__ == "__main__":
    main()
