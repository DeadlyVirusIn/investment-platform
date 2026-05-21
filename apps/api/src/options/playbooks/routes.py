"""Phase F — Strategy Playbook HTTP routes.

GET-only. Read-only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.playbooks.service import (
    get_playbook,
    get_playbook_live,
    list_playbooks,
)


router = APIRouter(prefix="/options/playbooks", tags=["options-playbooks"])


@router.get("")
def list_all(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Library of every strategy playbook, grouped by bias."""
    rows = list_playbooks(session)
    return {"count": len(rows), "items": rows}


@router.get("/{rule_id}")
def get_one(
    rule_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Full playbook for one rule_id."""
    item = get_playbook(session, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="playbook not found")
    return item


@router.get("/{rule_id}/live")
def get_one_live(
    rule_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Playbook + live overlay (recent candidates + open trades)."""
    item = get_playbook_live(session, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="playbook not found")
    return item
