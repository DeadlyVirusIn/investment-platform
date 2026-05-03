"""Tiny CSV helpers used by diagnostics endpoints + bundle exporter.

Pure stdlib. Deterministic column order. Decimal → str, None → '',
datetime/date → ISO string.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal
from typing import Any, Iterable, Sequence


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        # Flatten nested to avoid ragged CSVs — rarely needed for our shapes.
        return str(v)
    return str(v)


def rows_to_csv(rows: Iterable[dict[str, Any]], columns: Sequence[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return buf.getvalue()
