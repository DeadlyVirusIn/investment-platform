"""Operator-only options chain ingestion (CSV or provider).

INSERT-only into `options_chain_snapshot`. Idempotent via natural key
`(snapshot_at_utc, underlying, expiry, strike, option_type)` using
`ON CONFLICT DO NOTHING` against constraint
`ux_options_chain_snapshot_natural_key`.

Hard rules (Phase 11Z):
  * Default is DRY-RUN. `--commit` requires env var
    `OPTIONS_CHAIN_INGEST_CONFIRM=I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA`.
  * NEVER writes to `options_paper_trade`, `options_paper_trade_leg`,
    `options_shadow_decision_log`, `paper_trade`, `paper_trade_log`,
    or any non-`options_chain_snapshot` table.
  * No scheduler / worker entry. This script is invoked by an
    operator manually with full inputs.
  * Validates expiry > snapshot_at_utc::date, strike > 0, bid <= ask,
    bid/ask/mid >= 0, open_interest >= 0, volume >= 0, quote_age_seconds
    >= 0.
  * CSV is the only supported source in v1. Provider mode is reserved
    (`--source provider` exits with a clear message until a provider
    adapter is wired in).

Usage:

  # Dry-run (default). Writes 0 rows. Prints what *would* insert.
  python -m scripts.ingest_options_chain \\
      --symbol SPY \\
      --as-of 2026-05-03 \\
      --source csv \\
      --csv apps/api/tests/fixtures/options_chain_sample.csv

  # Commit. REQUIRES env var.
  OPTIONS_CHAIN_INGEST_CONFIRM=I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA \\
  python -m scripts.ingest_options_chain \\
      --symbol SPY --as-of 2026-05-03 \\
      --source csv \\
      --csv apps/api/tests/fixtures/options_chain_sample.csv \\
      --commit

Exit codes:
  0  success (dry-run or commit)
  1  validation error (bad row, missing column, bid > ask, ...)
  2  refused (no env confirmation, unknown source, missing CSV)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import text


CONFIRM_ENV = "OPTIONS_CHAIN_INGEST_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_WRITES_OPTIONS_CHAIN_DATA"

# The only target table this script may write to.
ALLOWED_TARGET_TABLE = "options_chain_snapshot"

REQUIRED_COLUMNS = (
    "expiry", "strike", "option_type", "option_symbol",
    "bid", "ask", "mid",
    "volume", "open_interest", "quote_age_seconds",
)
OPTIONAL_COLUMNS = (
    "last", "delta", "gamma", "theta", "vega", "iv",
)
VALID_OPTION_TYPES = ("CALL", "PUT")


@dataclass
class ChainRow:
    expiry: dt.date
    strike: Decimal
    option_type: str
    option_symbol: str
    bid: Decimal
    ask: Decimal
    mid: Decimal
    last: Decimal | None
    volume: int
    open_interest: int
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    quote_age_seconds: int


# ---------------------------------------------------------------------------
# Parsing + validation
# ---------------------------------------------------------------------------
def _parse_decimal(name: str, raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name}: not a number: {raw!r}") from exc


def _parse_int(name: str, raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{name}: not an integer: {raw!r}") from exc


def _parse_date(name: str, raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name}: not an ISO date: {raw!r}") from exc


def _validate_columns(header: list[str]) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {missing}. "
            f"Required: {list(REQUIRED_COLUMNS)}"
        )


def _row_from_csv(idx: int, raw: dict[str, str]) -> ChainRow:
    """Convert one CSV dict row into a typed ChainRow with validation."""
    try:
        expiry = _parse_date("expiry", raw["expiry"])
        strike = _parse_decimal("strike", raw["strike"])
        if strike is None or strike <= 0:
            raise ValueError(f"strike must be > 0: {raw['strike']!r}")
        option_type = (raw["option_type"] or "").strip().upper()
        if option_type not in VALID_OPTION_TYPES:
            raise ValueError(
                f"option_type must be one of {VALID_OPTION_TYPES}: "
                f"{option_type!r}"
            )
        option_symbol = (raw["option_symbol"] or "").strip()
        if not option_symbol:
            raise ValueError("option_symbol must be non-empty")

        bid = _parse_decimal("bid", raw["bid"])
        ask = _parse_decimal("ask", raw["ask"])
        mid = _parse_decimal("mid", raw["mid"])
        if bid is None or ask is None or mid is None:
            raise ValueError("bid, ask, mid are required and non-empty")
        for tag, val in (("bid", bid), ("ask", ask), ("mid", mid)):
            if val < 0:
                raise ValueError(f"{tag} must be >= 0: {val}")
        if bid > ask:
            raise ValueError(f"bid > ask: bid={bid}, ask={ask}")
        # Loose tolerance for mid (provider-dependent rounding).
        if not (bid - Decimal("0.0001") <= mid <= ask + Decimal("0.0001")):
            raise ValueError(
                f"mid out of [bid, ask] range: "
                f"bid={bid}, mid={mid}, ask={ask}"
            )

        volume = _parse_int("volume", raw["volume"]) or 0
        open_interest = _parse_int("open_interest", raw["open_interest"]) or 0
        if volume < 0:
            raise ValueError(f"volume must be >= 0: {volume}")
        if open_interest < 0:
            raise ValueError(f"open_interest must be >= 0: {open_interest}")

        quote_age_seconds = _parse_int(
            "quote_age_seconds", raw["quote_age_seconds"]
        )
        if quote_age_seconds is None or quote_age_seconds < 0:
            raise ValueError(
                f"quote_age_seconds must be >= 0: {quote_age_seconds!r}"
            )

        last = _parse_decimal("last", raw.get("last", ""))
        delta = _parse_decimal("delta", raw.get("delta", ""))
        gamma = _parse_decimal("gamma", raw.get("gamma", ""))
        theta = _parse_decimal("theta", raw.get("theta", ""))
        vega = _parse_decimal("vega", raw.get("vega", ""))
        iv = _parse_decimal("iv", raw.get("iv", ""))

        return ChainRow(
            expiry=expiry, strike=strike, option_type=option_type,
            option_symbol=option_symbol,
            bid=bid, ask=ask, mid=mid, last=last,
            volume=volume, open_interest=open_interest,
            delta=delta, gamma=gamma, theta=theta, vega=vega, iv=iv,
            quote_age_seconds=quote_age_seconds,
        )
    except ValueError as exc:
        raise ValueError(f"row {idx + 2}: {exc}") from exc


def load_csv(path: Path) -> list[ChainRow]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header row: {path}")
        _validate_columns(list(reader.fieldnames))
        rows = [_row_from_csv(i, r) for i, r in enumerate(reader)]
    return rows


# ---------------------------------------------------------------------------
# Snapshot insertion
# ---------------------------------------------------------------------------
_INSERT_SQL = text(
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


def _row_params(
    *, row: ChainRow, snapshot_at_utc: dt.datetime,
    underlying: str, provider: str, provider_version: str | None,
) -> dict[str, Any]:
    if row.expiry <= snapshot_at_utc.date():
        raise ValueError(
            f"expiry {row.expiry} is not after snapshot date "
            f"{snapshot_at_utc.date()}"
        )
    return {
        "snapshot_at_utc": snapshot_at_utc,
        "underlying": underlying,
        "expiry": row.expiry,
        "strike": row.strike,
        "option_type": row.option_type,
        "option_symbol": row.option_symbol,
        "bid": row.bid, "ask": row.ask, "mid": row.mid, "last": row.last,
        "volume": row.volume, "open_interest": row.open_interest,
        "delta": row.delta, "gamma": row.gamma, "theta": row.theta,
        "vega": row.vega, "iv": row.iv,
        "quote_age_seconds": row.quote_age_seconds,
        "provider": provider,
        "provider_version": provider_version,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ingest_options_chain",
        description="Operator-only options-chain ingester (CSV or provider).",
    )
    p.add_argument("--symbol", default=None,
                   help="Underlying ticker (e.g. SPY). Not required when "
                        "--batch is used.")
    p.add_argument("--as-of", required=True,
                   help="ISO date (YYYY-MM-DD) for snapshot_at_utc.")
    p.add_argument("--source", choices=("csv", "provider"), default="csv",
                   help="Source of chain data. v1 supports csv only.")
    p.add_argument("--csv", default=None,
                   help="Path to CSV (required when --source csv "
                        "without --batch).")
    p.add_argument(
        "--batch", default=None,
        help="Directory of CSVs named '<SYMBOL>_<expiration>.csv'. "
             "Each file is ingested under its symbol. Mutually "
             "exclusive with --csv/--symbol.",
    )
    p.add_argument("--provider", default="csv-fixture",
                   help="Provider tag stored on each row.")
    p.add_argument("--provider-version", default=None,
                   help="Optional provider-version tag.")
    p.add_argument("--commit", action="store_true",
                   help="Actually INSERT. Requires "
                        f"{CONFIRM_ENV}={CONFIRM_VALUE} in env.")
    return p


def _ingest_one(
    csv_path: Path, symbol: str, snapshot_at_utc: dt.datetime,
    provider: str, provider_version: str | None, commit: bool,
) -> dict[str, Any]:
    """Ingest one CSV. Returns summary dict. Raises on validation errors."""
    rows = load_csv(csv_path)
    params_list: list[dict[str, Any]] = []
    for r in rows:
        params_list.append(_row_params(
            row=r, snapshot_at_utc=snapshot_at_utc, underlying=symbol,
            provider=provider, provider_version=provider_version,
        ))
    if not commit:
        return {
            "csv": str(csv_path), "symbol": symbol,
            "rows_processed": len(params_list),
            "inserted": 0, "skipped_existing": 0, "dry_run": True,
        }
    from apps.api.src.db import SessionLocal  # lazy
    inserted = 0
    skipped_existing = 0
    with SessionLocal() as session:
        before = session.execute(
            text("SELECT count(*) FROM options_chain_snapshot")
        ).scalar() or 0
        for params in params_list:
            res = session.execute(_INSERT_SQL, params)
            if res.rowcount and res.rowcount > 0:
                inserted += 1
            else:
                skipped_existing += 1
        session.commit()
        after = session.execute(
            text("SELECT count(*) FROM options_chain_snapshot")
        ).scalar() or 0
    return {
        "csv": str(csv_path), "symbol": symbol,
        "rows_processed": len(params_list),
        "inserted": inserted, "skipped_existing": skipped_existing,
        "before": int(before), "after": int(after),
        "dry_run": False,
    }


def _parse_batch_filename(path: Path) -> str | None:
    """Extract underlying from '<SYMBOL>_<expiration>.csv'. Returns
    None if filename does not match the expected pattern."""
    stem = path.stem
    if "_" not in stem:
        return None
    sym = stem.split("_", 1)[0].upper()
    if not sym or not all(c.isalnum() or c == "-" for c in sym):
        return None
    return sym


def _resolve_snapshot_at_utc(as_of: str) -> dt.datetime:
    d = _parse_date("--as-of", as_of)
    # Use 21:00 UTC ≈ US market close so the snapshot has a deterministic
    # natural key per (date, underlying, ...).
    return dt.datetime(
        d.year, d.month, d.day, 21, 0, 0, tzinfo=dt.timezone.utc,
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    snapshot_at_utc = _resolve_snapshot_at_utc(args.as_of)

    if args.source == "provider":
        sys.stderr.write(
            "REFUSED: --source provider is reserved. v1 supports only "
            "--source csv. Use a CSV fixture or wire a provider adapter "
            "in chain_ingest.py and call that path instead.\n"
        )
        return 2

    if args.commit:
        confirm = os.environ.get(CONFIRM_ENV, "")
        if confirm != CONFIRM_VALUE:
            sys.stderr.write(
                f"REFUSED: --commit requires env var "
                f"{CONFIRM_ENV}={CONFIRM_VALUE} (got {confirm!r}).\n"
            )
            return 2

    # ----- Batch mode -----
    if args.batch:
        if args.csv or args.symbol:
            sys.stderr.write(
                "REFUSED: --batch is mutually exclusive with "
                "--csv / --symbol\n"
            )
            return 2
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            sys.stderr.write(
                f"REFUSED: --batch directory not found: {batch_dir}\n"
            )
            return 2
        files = sorted(batch_dir.glob("*.csv"))
        if not files:
            sys.stderr.write(
                f"REFUSED: --batch directory has no .csv files: "
                f"{batch_dir}\n"
            )
            return 2
        total_inserted = 0
        total_skipped = 0
        per_file: list[dict[str, Any]] = []
        per_symbol: dict[str, dict[str, int]] = {}
        for csv_path in files:
            sym = _parse_batch_filename(csv_path)
            if sym is None:
                sys.stdout.write(
                    f"[batch] skip {csv_path.name}: bad filename "
                    "(expected '<SYMBOL>_<expiration>.csv')\n"
                )
                continue
            try:
                summary = _ingest_one(
                    csv_path, sym, snapshot_at_utc,
                    args.provider, args.provider_version, args.commit,
                )
            except (FileNotFoundError, ValueError) as exc:
                sys.stderr.write(
                    f"VALIDATION ERROR for {csv_path}: {exc}\n"
                )
                continue
            per_file.append(summary)
            sb = per_symbol.setdefault(sym, {
                "files": 0, "rows_processed": 0,
                "inserted": 0, "skipped_existing": 0,
            })
            sb["files"] += 1
            sb["rows_processed"] += summary["rows_processed"]
            sb["inserted"] += summary["inserted"]
            sb["skipped_existing"] += summary["skipped_existing"]
            total_inserted += summary["inserted"]
            total_skipped += summary["skipped_existing"]
            sys.stdout.write(
                f"[batch] {csv_path.name} symbol={sym} "
                f"rows={summary['rows_processed']} "
                f"inserted={summary['inserted']} "
                f"skipped_existing={summary['skipped_existing']}\n"
            )
        sys.stdout.write("=" * 68 + "\n")
        sys.stdout.write(
            f"[batch] mode={'commit' if args.commit else 'dry-run'} "
            f"as_of={args.as_of} files={len(per_file)} "
            f"total_inserted={total_inserted} "
            f"total_skipped_existing={total_skipped}\n"
        )
        for sym, sb in sorted(per_symbol.items()):
            sys.stdout.write(f"  {sym}: {sb}\n")
        sys.stdout.write("=" * 68 + "\n")
        return 0

    # ----- Single-file mode (legacy) -----
    if not args.symbol:
        sys.stderr.write(
            "REFUSED: --symbol is required when --batch is not used\n"
        )
        return 2
    underlying = args.symbol.strip().upper()
    if args.source == "csv":
        if not args.csv:
            sys.stderr.write(
                "REFUSED: --csv is required with --source csv\n"
            )
            return 2
        try:
            rows = load_csv(Path(args.csv))
        except (FileNotFoundError, ValueError) as exc:
            sys.stderr.write(f"VALIDATION ERROR: {exc}\n")
            return 1

    # Build params + validate semantically (expiry > as-of).
    params_list: list[dict[str, Any]] = []
    try:
        for r in rows:
            params_list.append(_row_params(
                row=r, snapshot_at_utc=snapshot_at_utc,
                underlying=underlying,
                provider=args.provider,
                provider_version=args.provider_version,
            ))
    except ValueError as exc:
        sys.stderr.write(f"VALIDATION ERROR: {exc}\n")
        return 1

    if not args.commit:
        # Dry-run only; print plan.
        sys.stdout.write(
            f"[dry-run] {underlying} as_of={args.as_of} "
            f"source={args.source} rows={len(params_list)} "
            f"target_table={ALLOWED_TARGET_TABLE}\n"
        )
        sys.stdout.write(
            "[dry-run] no DB writes performed. To commit, set "
            f"{CONFIRM_ENV}={CONFIRM_VALUE} and re-run with --commit.\n"
        )
        return 0

    # Commit path — single bulk insert under one transaction.
    from apps.api.src.db import SessionLocal  # lazy import; allows
    # `--source provider` refusal & dry-run without DB connection.

    inserted = 0
    skipped_existing = 0
    with SessionLocal() as session:
        before = session.execute(
            text("SELECT count(*) FROM options_chain_snapshot")
        ).scalar() or 0
        for params in params_list:
            res = session.execute(_INSERT_SQL, params)
            # rowcount is 1 on insert, 0 on conflict (DO NOTHING).
            if res.rowcount and res.rowcount > 0:
                inserted += 1
            else:
                skipped_existing += 1
        session.commit()
        after = session.execute(
            text("SELECT count(*) FROM options_chain_snapshot")
        ).scalar() or 0

    sys.stdout.write(
        f"[commit] {underlying} as_of={args.as_of} source={args.source} "
        f"rows_processed={len(params_list)} inserted={inserted} "
        f"skipped_existing={skipped_existing} "
        f"options_chain_snapshot before={before} after={after}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
