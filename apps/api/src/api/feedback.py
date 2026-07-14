"""M5 demand-validation — feedback signal capture (collect-only).

POST /api/feedback/signal. Works for authenticated users (session cookie ->
user_id) and anonymous/demo callers (user_id NULL; the X-Auth-User-Id header is
stored ONLY as opaque device context, never trusted as auth). Validates surface
+ signal_type, caps abuse per identity, stores payload safely. NO read endpoint
(no cross-user exposure). NO recommendation behavior.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.auth import identity as ident
from apps.api.src.db import get_session

router = APIRouter(tags=["feedback"])

SIGNAL_TYPES = {
    "trust_useful", "trust_not_useful", "would_use_again", "would_not_use_again",
    "confusing", "beta_interest", "investor_interest", "feedback_text",
}
SURFACES = {"pick_detail", "options_detail", "account", "profile", "discover"}

_WINDOW_SECONDS = 60
_MAX_PER_WINDOW = 60          # per identity (user or device) — light abuse guard
_MAX_VALUE_LEN = 2000
_MAX_PAYLOAD_BYTES = 4000


class SignalBody(BaseModel):
    surface: str
    signal_type: str
    value: str | None = None
    payload: dict[str, Any] | None = None


@router.post("/feedback/signal")
def post_signal(body: SignalBody, request: Request, db: Session = Depends(get_session)) -> dict[str, Any]:
    if body.surface not in SURFACES:
        raise HTTPException(status_code=422, detail="invalid surface")
    if body.signal_type not in SIGNAL_TYPES:
        raise HTTPException(status_code=422, detail="invalid signal_type")

    uid = ident.session_user_id(db, request.cookies.get(ident.SESSION_COOKIE))
    device = ((request.headers.get("X-Auth-User-Id") or "").strip()[:64]) or None

    # Light abuse guard: cap signals per identity (user_id if logged in, else
    # the device context) within the window.
    cnt = db.execute(
        text(
            """
            SELECT count(*) FROM user_feedback_signal
            WHERE created_at > now() - make_interval(secs => :w)
              AND (((:uid)::text IS NOT NULL AND user_id = (:uid)::text)
                OR ((:uid)::text IS NULL AND (:dev)::text IS NOT NULL AND session_or_device_id = (:dev)::text))
            """
        ),
        {"w": float(_WINDOW_SECONDS), "uid": uid, "dev": device},
    ).scalar() or 0
    if cnt >= _MAX_PER_WINDOW:
        raise HTTPException(status_code=429, detail="too many signals; slow down")

    value = body.value[:_MAX_VALUE_LEN] if body.value else None
    payload_json: str | None = None
    if body.payload is not None:
        s = json.dumps(body.payload)
        payload_json = s if len(s) <= _MAX_PAYLOAD_BYTES else json.dumps({"_truncated": True})

    db.execute(
        text(
            """
            INSERT INTO user_feedback_signal
              (user_id, session_or_device_id, surface, signal_type, value, payload)
            VALUES (:uid, :dev, :surface, :stype, :val, CAST(:payload AS jsonb))
            """
        ),
        {"uid": uid, "dev": device, "surface": body.surface, "stype": body.signal_type, "val": value, "payload": payload_json},
    )
    db.commit()
    return {"ok": True}
