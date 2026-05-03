"""Alert types + pluggable sinks.

Severity:
  - INFO:     informational events (market closed, zero-but-healthy day)
  - WARNING:  degraded but non-blocking (retryable data miss, missing log)
  - CRITICAL: blocks daily pipeline integrity (crash, stale data, duplicate run)

Default sink = loguru. Optional webhook sink reads DAILY_ALERT_WEBHOOK_URL env;
if unset, the webhook sink is a no-op.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable

from loguru import logger

SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_CRITICAL = "CRITICAL"


@dataclass
class Alert:
    severity: str
    code: str
    message: str
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------


def logger_sink(alert: Alert) -> None:
    level_map = {
        SEV_INFO: "INFO",
        SEV_WARNING: "WARNING",
        SEV_CRITICAL: "ERROR",
    }
    level = level_map.get(alert.severity, "INFO")
    logger.log(
        level,
        "[alert] [{}] {} {} details={}",
        alert.severity, alert.code, alert.message,
        json.dumps(alert.details, default=str, sort_keys=True),
    )


def webhook_sink(alert: Alert) -> None:
    url = os.environ.get("DAILY_ALERT_WEBHOOK_URL", "")
    if not url:
        return
    try:
        import httpx
        payload = {
            "severity": alert.severity,
            "code": alert.code,
            "message": alert.message,
            "details": alert.details,
        }
        httpx.post(url, json=payload, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[alert] webhook_sink failed: {}", exc)


DEFAULT_SINKS: list[Callable[[Alert], None]] = [logger_sink, webhook_sink]


def dispatch(
    alerts: list[Alert], sinks: list[Callable[[Alert], None]] | None = None,
) -> None:
    sinks = sinks if sinks is not None else DEFAULT_SINKS
    for a in alerts:
        for s in sinks:
            try:
                s(a)
            except Exception as exc:  # noqa: BLE001
                logger.error("[alert] sink {} threw: {}", s.__name__, exc)
