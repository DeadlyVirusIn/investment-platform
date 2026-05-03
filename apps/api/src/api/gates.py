"""Gates diagnostic API — plain-English status per gate + engine arming."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy.orm import Session

from apps.api.src.alpha.gate_inventory import build_gate_status
from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/gates", tags=["gates"])


def _s() -> Session:
    return SessionLocal()


@router.get("/status")
async def gate_status() -> dict[str, Any]:
    with _s() as s:
        return build_gate_status(s)
