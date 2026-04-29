"""Phase 11T.1 - manual model-registry CRUD CLI.

Subcommands:
  list                      print every entry
  show MODEL_ID             print a single entry
  register                  append a new entry (dry-run by default)

`register` requires --commit and --confirm-commit YES (or interactive
TTY YES). Refuses to overwrite existing entries.

NEVER mutates pickle / report files. NEVER writes to the DB. NEVER
imports broker / live / execution modules.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from apps.api.src.ml.model_registry import (
    DuplicateModelIdError,
    ModelRegistryError,
    REGISTRY_PATH,
    RegistrationRequest,
    list_entries,
    register,
    show_entry,
)


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="manage_model_registry",
        description=(
            "Manual model registry CRUD. Read-only by default. "
            "Append-only writes; never overwrites."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list every entry")

    show = sub.add_parser("show", help="print one entry")
    show.add_argument("model_id")

    reg = sub.add_parser("register", help="append a new entry")
    reg.add_argument("--pickle-path", required=True,
                     type=lambda s: Path(s))
    reg.add_argument("--report-path", required=True,
                     type=lambda s: Path(s))
    reg.add_argument("--notes", default=None)
    grp = reg.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--commit", action="store_true")
    reg.add_argument("--confirm-commit", default=None)
    reg.add_argument(
        "--registry-path",
        type=lambda s: Path(s),
        default=REGISTRY_PATH,
    )
    return p.parse_args(argv)


def _confirm(args: argparse.Namespace) -> bool:
    if not args.commit:
        return True
    if args.confirm_commit == "YES":
        return True
    if sys.stdin.isatty():
        sys.stdout.write("Type YES to confirm commit: ")
        sys.stdout.flush()
        return sys.stdin.readline().strip() == "YES"
    return False


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _parse(raw)

    if args.cmd == "list":
        entries = list_entries()
        sys.stdout.write(
            json.dumps(entries, indent=2, default=str) + "\n",
        )
        return 0

    if args.cmd == "show":
        entry = show_entry(args.model_id)
        if entry is None:
            sys.stderr.write(
                f"model_id not found: {args.model_id}\n",
            )
            return 4
        sys.stdout.write(
            json.dumps(entry, indent=2, default=str) + "\n",
        )
        return 0

    if args.cmd == "register":
        commit = bool(args.commit)
        dry_run = not commit
        if commit and not _confirm(args):
            sys.stderr.write(
                "commit confirmation required: pass --confirm-commit "
                "YES or type YES at the interactive prompt\n",
            )
            return 2
        try:
            req = RegistrationRequest(
                pickle_path=args.pickle_path,
                report_path=args.report_path,
                notes=args.notes,
            )
            entry = register(
                req,
                registry_path=args.registry_path,
                dry_run=dry_run,
            )
        except DuplicateModelIdError as exc:
            sys.stderr.write(f"[register] duplicate: {exc}\n")
            return 2
        except ModelRegistryError as exc:
            sys.stderr.write(f"[register] {exc}\n")
            return 2
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[error] {exc}\n")
            return 9
        label = (
            "DRY-RUN -- no registry file write"
            if dry_run else
            "COMMIT -- entry appended"
        )
        sys.stdout.write(
            json.dumps(entry, indent=2, default=str) + "\n"
            f"{label}\n",
        )
        return 0

    return 9


if __name__ == "__main__":
    sys.exit(main())
