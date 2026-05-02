"""Phase 11W (Phase E.2) — research admin CLI.

Operator-only commands for enforcing state and listing alerts.
NEVER triggers a research run. NEVER calls a provider. Refuses
unless `RESEARCH_MANUAL_RUN_ENABLED=true` so the admin surface
shares the same enablement gate as the manual run path.

Subcommands:
  block      <operator_id> --reason TEXT [--blocked-until ISO]
  unblock    <operator_id>
  set-state  <operator_id> <clear|watch|restricted|blocked> --reason TEXT
  list-alerts [--severity ...] [--limit N]
  list-operators

Exit codes:
  0   ok
  2   precondition / arg error
  3   not enabled (RESEARCH_MANUAL_RUN_ENABLED=false)
  9   unexpected error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from typing import Sequence

from loguru import logger
from sqlalchemy import text

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.research.manual_run_enforcement import (
    emit_alert,
    get_operator_control,
    set_operator_state,
)


def _require_enabled() -> int:
    if not bool(settings.RESEARCH_MANUAL_RUN_ENABLED):
        sys.stderr.write(
            "[research_admin] RESEARCH_MANUAL_RUN_ENABLED is false; "
            "refuse to run admin commands\n"
        )
        return 3
    return 0


def _audit_admin_action(
    *, command: str, target_op: str, admin_id: str,
    detail: dict,
) -> None:
    """Audit log entry as an alert row so it is operator-visible."""
    try:
        with SessionLocal() as s:
            emit_alert(
                s,
                severity="info",
                alert_type=f"admin.{command}",
                message=f"admin={admin_id} cmd={command} target={target_op}",
                operator_id=target_op,
                metadata={"detail": detail, "admin_id": admin_id},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin audit emit failed: {}", exc)


def cmd_block(args) -> int:
    if (rc := _require_enabled()):
        return rc
    blocked_until = None
    if args.blocked_until:
        blocked_until = dt.datetime.fromisoformat(args.blocked_until)
    with SessionLocal() as s:
        out = set_operator_state(
            s, operator_id=args.operator_id, state="blocked",
            reason=args.reason, updated_by=args.admin_id,
            blocked_until=blocked_until,
            notes=f"blocked via CLI by {args.admin_id}",
        )
    _audit_admin_action(
        command="block", target_op=args.operator_id,
        admin_id=args.admin_id,
        detail={
            "reason": args.reason,
            "blocked_until": (
                blocked_until.isoformat() if blocked_until else None
            ),
        },
    )
    sys.stdout.write(json.dumps({
        "operator_id": out.operator_id, "state": out.state,
        "reason": out.reason,
        "blocked_until": (
            out.blocked_until.isoformat() if out.blocked_until else None
        ),
    }) + "\n")
    return 0


def cmd_unblock(args) -> int:
    if (rc := _require_enabled()):
        return rc
    with SessionLocal() as s:
        out = set_operator_state(
            s, operator_id=args.operator_id, state="clear",
            reason="admin_unblock", updated_by=args.admin_id,
            notes=f"unblocked via CLI by {args.admin_id}",
        )
    _audit_admin_action(
        command="unblock", target_op=args.operator_id,
        admin_id=args.admin_id, detail={},
    )
    sys.stdout.write(json.dumps({
        "operator_id": out.operator_id, "state": out.state,
    }) + "\n")
    return 0


def cmd_set_state(args) -> int:
    if (rc := _require_enabled()):
        return rc
    with SessionLocal() as s:
        out = set_operator_state(
            s, operator_id=args.operator_id, state=args.state,
            reason=args.reason, updated_by=args.admin_id,
        )
    _audit_admin_action(
        command="set_state", target_op=args.operator_id,
        admin_id=args.admin_id,
        detail={"new_state": args.state, "reason": args.reason},
    )
    sys.stdout.write(json.dumps({
        "operator_id": out.operator_id, "state": out.state,
        "reason": out.reason,
    }) + "\n")
    return 0


def cmd_list_alerts(args) -> int:
    if (rc := _require_enabled()):
        return rc
    where: list[str] = []
    params: dict = {"lim": args.limit}
    if args.severity:
        where.append("severity = :sev")
        params["sev"] = args.severity
    if args.status:
        where.append("status = :st")
        params["st"] = args.status
    sql = (
        "SELECT id, created_at, severity, alert_type, operator_id, "
        "       symbol, status, message "
        "FROM research_ro.research_alert "
        + ("WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY created_at DESC LIMIT :lim"
    )
    with SessionLocal() as s:
        rows = s.execute(text(sql), params).mappings().all()
    out = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v)
         for k, v in dict(r).items()}
        for r in rows
    ]
    sys.stdout.write(json.dumps(out, default=str, indent=2) + "\n")
    return 0


def cmd_list_operators(_args) -> int:
    if (rc := _require_enabled()):
        return rc
    with SessionLocal() as s:
        rows = s.execute(text(
            "SELECT operator_id, state, reason, blocked_until, "
            "       updated_by, updated_at "
            "FROM research_ro.research_operator_control "
            "ORDER BY state, updated_at DESC"
        )).mappings().all()
    out = [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v)
         for k, v in dict(r).items()}
        for r in rows
    ]
    sys.stdout.write(json.dumps(out, default=str, indent=2) + "\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="research_admin",
        description=(
            "Operator enforcement + alert review CLI. Refuses to run "
            "unless RESEARCH_MANUAL_RUN_ENABLED is true. Every "
            "command writes an audit alert."
        ),
    )
    p.add_argument("--admin-id", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("block")
    b.add_argument("operator_id")
    b.add_argument("--reason", required=True)
    b.add_argument("--blocked-until", default=None)
    b.set_defaults(func=cmd_block)

    u = sub.add_parser("unblock")
    u.add_argument("operator_id")
    u.set_defaults(func=cmd_unblock)

    ss = sub.add_parser("set-state")
    ss.add_argument("operator_id")
    ss.add_argument("state", choices=("clear", "watch", "restricted", "blocked"))
    ss.add_argument("--reason", required=True)
    ss.set_defaults(func=cmd_set_state)

    la = sub.add_parser("list-alerts")
    la.add_argument("--severity", default=None)
    la.add_argument("--status", default=None)
    la.add_argument("--limit", type=int, default=20)
    la.set_defaults(func=cmd_list_alerts)

    lo = sub.add_parser("list-operators")
    lo.set_defaults(func=cmd_list_operators)

    args = p.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("admin command crashed: {}", exc)
        return 9


if __name__ == "__main__":
    sys.exit(main())
