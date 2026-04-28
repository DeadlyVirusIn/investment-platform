"""Phase 11O / 11O.1 - Manual options paper evaluation runner CLI.

Usage:
    python -m scripts.run_options_paper_eval --date YYYY-MM-DD ...
    python -m scripts.run_options_paper_eval --check-provider
    python -m scripts.run_options_paper_eval --mock-chain-from data/test/foo.json --dry-run

Default mode is --dry-run (no DB writes). The --commit flag requires
either --confirm-commit YES on the command line OR an interactive TTY
prompt typed YES.

Hard guarantees enforced by apps.api.src.options.paper.eval_runner:
  * OPTIONS_ENABLED must be True
  * OPTIONS_PAPER_ONLY must be True
  * OPTIONS_ML_CAN_AFFECT_TRADES must be False
  * No broker / live / execution module may be loaded
  * The worker job registry must not contain any options job

Exit codes (per spec):
  0  success (dry-run or commit, or --check-provider OK)
  2  precondition / safety / config failure
  3  chain ingest failure (incl. --check-provider FAIL)
  4  zero qualified observations
  5  open_trade rejection during commit
  9  internal error
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.options.data.chain_ingest import DEFAULT_UNIVERSE
from apps.api.src.options.paper.eval_runner import (
    EvalRunnerCommitError,
    EvalRunnerIngestError,
    EvalRunnerSafetyError,
    assert_no_scheduler_drift,
    assert_safety_invariants,
    run,
)
from apps.api.src.options.paper.eval_runner_models import (
    RunnerConfig,
    RunnerSummary,
)


MOCK_PROVIDER_NAME = "mock_local"
MOCK_PROVIDER_VERSION = "11O.1-mock"


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def _csv_upper(s: str) -> tuple[str, ...]:
    return tuple(x.strip().upper() for x in s.split(",") if x.strip())


def _csv(s: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_options_paper_eval",
        description=(
            "Manual options paper evaluation runner. Default: dry-run. "
            "No live trading. No scheduler. No automation."
        ),
    )
    p.add_argument(
        "--date",
        type=lambda s: datetime.date.fromisoformat(s),
        default=datetime.date.today(),
        help="evaluation date (UTC); default = today",
    )
    p.add_argument(
        "--underlyings",
        type=_csv_upper,
        default=tuple(DEFAULT_UNIVERSE),
        help="comma-separated underlyings; default = SPY,QQQ,IWM,GLD,TLT",
    )
    p.add_argument(
        "--strategies",
        type=_csv,
        default=None,
        help="optional comma-separated rule_id filter",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="default; no DB writes")
    mode.add_argument("--commit", action="store_true",
                      help="open paper trades; requires --confirm-commit YES")
    p.add_argument("--max-open", type=int, default=5,
                   help="hard cap on planned trades (1..25); default=5")
    p.add_argument("--explain", action="store_true",
                   help="verbose per-observation log")
    p.add_argument("--skip-ingest", action="store_true",
                   help="skip the chain snapshot step")
    p.add_argument("--confirm-commit", default=None,
                   help='must be the literal string "YES" to commit')
    # Phase 11O.1
    p.add_argument(
        "--check-provider", action="store_true",
        help="run provider health check only; no DB session, no ingest",
    )
    p.add_argument(
        "--mock-chain-from", default=None,
        help=(
            "path to JSON file of OptionChainQuote rows; INSERTs into "
            "options_chain_snapshot tagged provider=mock_local then "
            "skips the live adapter call"
        ),
    )
    p.add_argument(
        "--allow-mock-commit", action="store_true",
        help=(
            "permit --mock-chain-from with --commit; off by default to "
            "prevent accidentally seeding fake data into a commit run"
        ),
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
        line = sys.stdin.readline().strip()
        return line == "YES"
    return False


# ---------------------------------------------------------------------------
# --check-provider
# ---------------------------------------------------------------------------

def _check_provider() -> int:
    """Run provider health check and print result. NEVER opens a DB
    session and NEVER calls step_ingest_chain."""
    try:
        assert_safety_invariants()
        assert_no_scheduler_drift()
    except EvalRunnerSafetyError as exc:
        sys.stderr.write(f"[safety] {exc}\n")
        return 2

    from apps.api.src.options.data_provider.thetadata_adapter import (
        ThetaDataAdapter,
        ThetaDataConfigError,
        assert_settings_provided,
    )
    try:
        assert_settings_provided()
        adapter = ThetaDataAdapter()
    except ThetaDataConfigError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    try:
        result = adapter.health_check_detail()
    finally:
        adapter.close()

    if result["ok"]:
        sys.stdout.write(
            f"[provider] base_url={result['base_url_host']} "
            f"auth_mode={result['auth_mode']} "
            f"ok=true status={result['status_code']} "
            f"latency={result['latency_ms']}ms\n"
        )
        return 0
    sys.stderr.write(
        f"[provider] base_url={result['base_url_host']} "
        f"auth_mode={result['auth_mode']} "
        f"ok=false status={result['status_code']} "
        f"reason={result['reason']!r}\n"
    )
    return 3


# ---------------------------------------------------------------------------
# --mock-chain-from
# ---------------------------------------------------------------------------

_MOCK_REQUIRED_FIELDS = (
    "underlying", "expiry", "strike", "option_type", "option_symbol",
    "bid", "ask",
)


def _validate_mock_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("mock chain JSON must be an object at top-level")
    if "snapshot_at_utc" not in payload:
        raise ValueError("mock chain JSON missing key: snapshot_at_utc")
    if "rows" not in payload or not isinstance(payload["rows"], list):
        raise ValueError("mock chain JSON missing key: rows (list)")
    snap_raw = payload["snapshot_at_utc"]
    try:
        # Strip Z suffix; fromisoformat does not accept it on Python <3.11
        snap = datetime.datetime.fromisoformat(
            snap_raw.replace("Z", "+00:00") if isinstance(snap_raw, str)
            else snap_raw
        )
    except Exception as exc:
        raise ValueError(
            f"snapshot_at_utc not parseable as ISO datetime: {snap_raw!r} "
            f"({exc})"
        )
    if snap.tzinfo is None:
        snap = snap.replace(tzinfo=datetime.timezone.utc)
    for i, row in enumerate(payload["rows"]):
        if not isinstance(row, dict):
            raise ValueError(f"row {i}: must be object")
        missing = [f for f in _MOCK_REQUIRED_FIELDS if f not in row]
        if missing:
            raise ValueError(
                f"row {i}: missing required fields: {missing}"
            )
        if str(row["option_type"]).upper() not in ("CALL", "PUT", "C", "P"):
            raise ValueError(
                f"row {i}: option_type must be CALL or PUT"
            )
        try:
            datetime.date.fromisoformat(str(row["expiry"]))
        except Exception:
            raise ValueError(
                f"row {i}: expiry not parseable as ISO date: "
                f"{row['expiry']!r}"
            )
    return {"snapshot_at_utc": snap, "rows": payload["rows"]}


_MOCK_INSERT_SQL = text(
    """
    INSERT INTO options_chain_snapshot
      (snapshot_at_utc, underlying, expiry, strike, option_type,
       option_symbol, bid, ask, mid, last,
       volume, open_interest,
       delta, gamma, theta, vega, iv,
       quote_age_seconds, provider, provider_version)
    VALUES
      (:snapshot_at_utc, :underlying, :expiry, :strike, :option_type,
       :option_symbol, :bid, :ask, :mid, :last,
       :volume, :open_interest,
       :delta, :gamma, :theta, :vega, :iv,
       :quote_age_seconds, :provider, :provider_version)
    ON CONFLICT ON CONSTRAINT ux_options_chain_snapshot_natural_key
        DO NOTHING
    """
)


def _seed_mock_chain(
    payload: dict[str, Any],
    *,
    session_factory=None,
) -> int:
    # Resolve module-global at call time so monkeypatch on
    # `cli.SessionLocal` is honored by tests.
    sf = session_factory or SessionLocal
    snap = payload["snapshot_at_utc"]
    inserted = 0
    with sf() as session:
        for row in payload["rows"]:
            opt_type = str(row["option_type"]).upper()
            opt_type = "CALL" if opt_type in ("C", "CALL") else "PUT"
            bid = Decimal(str(row["bid"]))
            ask = Decimal(str(row["ask"]))
            mid_v = row.get("mid")
            mid = (
                Decimal(str(mid_v))
                if mid_v is not None
                else (bid + ask) / Decimal("2")
            )
            params = {
                "snapshot_at_utc": snap,
                "underlying": str(row["underlying"]).upper(),
                "expiry": datetime.date.fromisoformat(str(row["expiry"])),
                "strike": Decimal(str(row["strike"])),
                "option_type": opt_type,
                "option_symbol": str(row["option_symbol"]),
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": (
                    Decimal(str(row["last"]))
                    if row.get("last") is not None else None
                ),
                "volume": (
                    int(row["volume"]) if row.get("volume") is not None
                    else None
                ),
                "open_interest": (
                    int(row["open_interest"])
                    if row.get("open_interest") is not None else None
                ),
                "delta": (
                    Decimal(str(row["delta"]))
                    if row.get("delta") is not None else None
                ),
                "gamma": (
                    Decimal(str(row["gamma"]))
                    if row.get("gamma") is not None else None
                ),
                "theta": (
                    Decimal(str(row["theta"]))
                    if row.get("theta") is not None else None
                ),
                "vega": (
                    Decimal(str(row["vega"]))
                    if row.get("vega") is not None else None
                ),
                "iv": (
                    Decimal(str(row["iv"]))
                    if row.get("iv") is not None else None
                ),
                "quote_age_seconds": int(row.get("quote_age_seconds", 0)),
                "provider": MOCK_PROVIDER_NAME,
                "provider_version": MOCK_PROVIDER_VERSION,
            }
            result = session.execute(_MOCK_INSERT_SQL, params)
            if result.rowcount and result.rowcount > 0:
                inserted += 1
        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _fmt_money(d: Decimal | None) -> str:
    if d is None:
        return "n/a"
    return f"${d:.2f}"


def _render(summary: RunnerSummary) -> str:
    cfg = summary.config
    lines: list[str] = []
    lines.append(
        f"[ingest] inserted={summary.n_chain_inserted}"
    )
    lines.append(
        "[collect] observations total="
        f"{summary.n_observations_total} qualified={summary.n_qualified}"
    )
    lines.append(
        f"[plan] planned={summary.n_planned} "
        f"rejected={summary.n_planned_rejected}"
    )
    lines.append(
        "[dedupe] duplicate_open_today="
        f"{summary.n_existing_open_trade_dedup}"
    )
    lines.append(f"[cap] max_open={cfg.max_open}")
    lines.append("")

    label = (
        "DRY-RUN -- no DB writes"
        if cfg.dry_run else
        "COMMIT -- opening paper trades"
    )
    lines.append(label)
    lines.append("-" * 76)

    if cfg.commit:
        lines.append(
            " # | underlying | rule_id                       "
            "| trade_id | net_credit | max_loss"
        )
    else:
        lines.append(
            " # | underlying | rule_id                       "
            "| legs | net_credit | max_loss | qual"
        )
    lines.append("-" * 76)

    for i, p in enumerate(summary.planned_trades, start=1):
        credit = _fmt_money(p.entry_credit_dollars)
        max_loss = _fmt_money(
            p.risk.max_loss_dollars if p.risk is not None else None
        )
        if cfg.commit:
            tid = (
                str(summary.committed_trade_ids[i - 1])
                if i - 1 < len(summary.committed_trade_ids)
                else "--"
            )
            lines.append(
                f"{i:2d} | {p.underlying:<10} | {p.rule_id:<28} "
                f"| {tid:>8} | {credit:>10} | {max_loss:>8}"
            )
        else:
            lines.append(
                f"{i:2d} | {p.underlying:<10} | {p.rule_id:<28} "
                f"| {len(p.legs):>4} | {credit:>10} | {max_loss:>8} "
                f"| {'yes' if p.qualified else 'no'}"
            )

    if cfg.dry_run:
        lines.append("")
        lines.append(
            "next step: re-run with --commit --confirm-commit YES"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]
    args = _parse_args(raw)

    if args.check_provider:
        return _check_provider()

    commit = bool(args.commit)
    dry_run = not commit

    # Mock + commit guard. Off by default; explicit opt-in required.
    if args.mock_chain_from and commit and not args.allow_mock_commit:
        sys.stderr.write(
            "[mock] cannot mix --mock-chain-from with --commit unless "
            "--allow-mock-commit is also set\n"
        )
        return 2

    if commit and not _confirm(args):
        sys.stderr.write(
            "commit confirmation required: pass --confirm-commit YES "
            "or type YES at the interactive prompt\n"
        )
        return 2

    # Optional mock chain seed. Forces --skip-ingest so the live adapter
    # is never called when a mock is in play.
    skip_ingest = bool(args.skip_ingest) or bool(args.mock_chain_from)
    mock_inserted = 0
    if args.mock_chain_from:
        path = Path(args.mock_chain_from)
        if not path.exists():
            sys.stderr.write(
                f"[mock] file not found: {path}\n"
            )
            return 2
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload = _validate_mock_payload(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"[mock] invalid schema: {exc}\n")
            return 2
        try:
            mock_inserted = _seed_mock_chain(payload)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[mock] insert failed: {exc}\n")
            return 9
        sys.stdout.write(
            f"[mock] inserted {mock_inserted} rows tagged "
            f"provider={MOCK_PROVIDER_NAME}\n"
        )

    try:
        config = RunnerConfig(
            date=args.date,
            underlyings=tuple(args.underlyings),
            strategy_filter=args.strategies,
            dry_run=dry_run,
            commit=commit,
            max_open=int(args.max_open),
            explain=bool(args.explain),
            skip_ingest=skip_ingest,
        )
    except ValueError as exc:
        sys.stderr.write(f"config error: {exc}\n")
        return 2

    try:
        summary = run(config, session_factory=SessionLocal)
    except EvalRunnerSafetyError as exc:
        sys.stderr.write(f"[safety] {exc}\n")
        return 2
    except EvalRunnerIngestError as exc:
        sys.stderr.write(f"[ingest] {exc}\n")
        return 3
    except EvalRunnerCommitError as exc:
        sys.stderr.write(f"[commit] {exc}\n")
        return 5
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[error] {exc}\n")
        return 9

    if summary.n_qualified == 0:
        sys.stdout.write(
            "no qualified observations for date "
            f"{config.date.isoformat()}\n"
        )
        return 4

    sys.stdout.write(_render(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
