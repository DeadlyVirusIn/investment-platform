"""JSONL-backed pending store for options paper trades.

Mirrors the stock-side `artifacts/paper_trading_skips/<date>.jsonl`
pattern. Each row captures a strategy decision that was generated
on day D but could not fill on day D (no chain snapshot strictly
after submitted_at::date). Subsequent runs scan these files to
retry. Same-bar fills remain forbidden — replay preserves the
original submitted_at and relies on the existing
`bar.ts > submitted_at` guard.

Two file shapes per date:
  artifacts/options_paper_skips/<date>.jsonl          (pending rows)
  artifacts/options_paper_skips/<date>.replayed.jsonl (replay marker)
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


SKIPS_DIR = Path("artifacts/options_paper_skips")
REPLAYED_SUFFIX = ".replayed.jsonl"
PENDING_REASON = "no_next_bar_chain"


def append_pending(
    *, as_of: dt.date, underlying: str, strategy: str,
    legs: list[dict[str, Any]],
    submitted_at: dt.datetime,
    confidence: float | None = None,
    reason: str = PENDING_REASON,
    extra: dict[str, Any] | None = None,
    skips_dir: Path = SKIPS_DIR,
) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{as_of.isoformat()}.jsonl"
    row = {
        "as_of_date": as_of.isoformat(),
        "underlying": underlying,
        "strategy": strategy,
        "legs": legs,
        "submitted_at": submitted_at.isoformat(),
        "confidence": confidence,
        "reason": reason,
        "detail": extra or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def read_pending_for_date(
    *, as_of: dt.date, skips_dir: Path = SKIPS_DIR,
) -> list[dict[str, Any]]:
    path = skips_dir / f"{as_of.isoformat()}.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def collect_pending_dates(
    *, before: dt.date,
    skips_dir: Path = SKIPS_DIR,
    from_date: dt.date | None = None,
    force: bool = False,
) -> list[dt.date]:
    """Return sorted dates with at least one pending entry where
    (from_date <= D < before) AND (force OR no .replayed marker).
    `from_date=None` => no lower bound."""
    if not skips_dir.exists():
        return []
    out: list[dt.date] = []
    for p in skips_dir.iterdir():
        if p.suffix != ".jsonl":
            continue
        if p.name.endswith(REPLAYED_SUFFIX):
            continue
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d >= before:
            continue
        if from_date is not None and d < from_date:
            continue
        if not force:
            marker = skips_dir / f"{d.isoformat()}{REPLAYED_SUFFIX}"
            if marker.exists():
                continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("reason") == PENDING_REASON:
                    out.append(d)
                    break
        except OSError:
            continue
    return sorted(out)


def write_marker(
    *, as_of: dt.date, summary: dict[str, Any],
    skips_dir: Path = SKIPS_DIR,
) -> None:
    skips_dir.mkdir(parents=True, exist_ok=True)
    path = skips_dir / f"{as_of.isoformat()}{REPLAYED_SUFFIX}"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "replayed_at_utc": dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),
            "original_date": as_of.isoformat(),
            **summary,
        }) + "\n")


def count_pending(
    *, skips_dir: Path = SKIPS_DIR,
    from_date: dt.date | None = None,
    before: dt.date | None = None,
) -> dict[str, int]:
    """Total pending rows in [from_date, before), grouped by date."""
    if not skips_dir.exists():
        return {"total": 0, "by_date": {}}
    by_date: dict[str, int] = {}
    for p in skips_dir.iterdir():
        if p.suffix != ".jsonl" or p.name.endswith(REPLAYED_SUFFIX):
            continue
        try:
            d = dt.date.fromisoformat(p.stem)
        except ValueError:
            continue
        if before is not None and d >= before:
            continue
        if from_date is not None and d < from_date:
            continue
        try:
            n = sum(
                1 for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip()
                and json.loads(line).get("reason") == PENDING_REASON
            )
        except (OSError, json.JSONDecodeError):
            continue
        if n:
            by_date[d.isoformat()] = n
    return {"total": sum(by_date.values()), "by_date": by_date}
