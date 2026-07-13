"""System posture interface — the seam Recommendation Publication Preflight
consumes today and Research Safe Mode (Wave 1B) will implement tomorrow.

Wave 1A deliberately ships ONLY this interface (mission hard stop: no Safe
Mode logic beyond what preflight requires). Semantics are already fixed so
Wave 1B cannot silently change the contract:

* NORMAL     — publication unrestricted (subject to per-idea checks).
* RESTRICTED — new ideas may publish only as READY_WITH_LIMITATIONS.
* SAFE       — no NEW ideas publish (per-idea verdict: HOLD). Existing
  published ideas, portfolios, paper exits, and outcome processing are
  NEVER affected by posture — preflight gates publication only.

V0 resolution order (deterministic, no network):
1. ``settings.SYSTEM_POSTURE_OVERRIDE`` when set to a valid value — the
   dev/test lever and the owner's manual incident switch until Wave 1B.
2. Otherwise NORMAL.

Wave 1B replaces step 2 with signal-derived posture (freshness, contracts,
scheduler health, drift, incidents) + an audited event log; this function's
signature and return values must remain stable.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from apps.api.src.config import settings

Posture = Literal["NORMAL", "RESTRICTED", "SAFE"]

_VALID: tuple[Posture, ...] = ("NORMAL", "RESTRICTED", "SAFE")


def current_posture(db: Session | None = None) -> Posture:  # noqa: ARG001 — db reserved for Wave 1B
    """Return the current system posture. Pure read; never raises."""
    raw = (settings.SYSTEM_POSTURE_OVERRIDE or "").strip().upper()
    if raw in _VALID:
        return raw  # type: ignore[return-value]
    return "NORMAL"
