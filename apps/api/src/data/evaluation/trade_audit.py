"""Trade audit — reconcile decision_log entries vs realized trades.

For each decision_log row with action=enter_long, look up the subsequent
close fill in broker/trade records and verify the position matched intent.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass
class AuditRow:
    decision_id: str
    as_of_date: dt.date
    engine: str
    intended_action: str
    realized_entry_fill: float | None
    realized_exit_fill: float | None
    net_return_pct: float | None
    discrepancy: str | None


# TODO: implement when broker-fill data wired (interactive-brokers / tradovate)
