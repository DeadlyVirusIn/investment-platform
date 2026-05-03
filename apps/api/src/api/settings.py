"""Settings API — real, minimal key/value store.

Currently surfaces four knobs:
    * benchmark_symbol       (default: SPY)
    * default_portfolio_name (default: Default Paper)
    * data_refresh_enabled   (default: true)
    * tiingo_api_key_override (stored opaquely; never echoed in full)

GET returns the current merged view. PATCH accepts a partial object and
writes each key. No authentication (single-user system).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED_KEYS: tuple[str, ...] = (
    "benchmark_symbol",
    "default_portfolio_name",
    "data_refresh_enabled",
    "tiingo_api_key_override",
)

DEFAULTS: dict[str, str] = {
    "benchmark_symbol": "SPY",
    "default_portfolio_name": "Default Paper",
    "data_refresh_enabled": "true",
    "tiingo_api_key_override": "",
}

SENSITIVE_KEYS: frozenset[str] = frozenset({"tiingo_api_key_override"})


class SettingsPatch(BaseModel):
    benchmark_symbol: str | None = Field(None, max_length=16)
    default_portfolio_name: str | None = Field(None, max_length=64)
    data_refresh_enabled: bool | None = None
    tiingo_api_key_override: str | None = Field(None, max_length=128)


def _load_all(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(AppSetting.key, AppSetting.value)
    ).all()
    out = dict(DEFAULTS)
    for k, v in rows:
        if k in ALLOWED_KEYS:
            out[k] = v if v is not None else ""
    return out


def _mask(key: str, value: str) -> str:
    if key in SENSITIVE_KEYS and value:
        # Keep last 4 chars visible only
        return "***" + value[-4:] if len(value) >= 4 else "***"
    return value


def _payload(raw: dict[str, str]) -> dict[str, Any]:
    return {
        "benchmark_symbol": raw["benchmark_symbol"],
        "default_portfolio_name": raw["default_portfolio_name"],
        "data_refresh_enabled": raw["data_refresh_enabled"].lower() == "true",
        "tiingo_api_key_override_present": bool(raw["tiingo_api_key_override"]),
        "tiingo_api_key_override_masked": _mask(
            "tiingo_api_key_override", raw["tiingo_api_key_override"],
        ),
    }


@router.get("")
def get_settings(session: Session = Depends(get_session)) -> dict[str, Any]:
    return _payload(_load_all(session))


@router.patch("")
def update_settings(
    patch: SettingsPatch, session: Session = Depends(get_session),
) -> dict[str, Any]:
    data = patch.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="empty patch")

    for key, raw_value in data.items():
        if key not in ALLOWED_KEYS:
            raise HTTPException(status_code=400, detail=f"unknown key: {key}")
        if isinstance(raw_value, bool):
            value = "true" if raw_value else "false"
        elif raw_value is None:
            value = ""
        else:
            value = str(raw_value)
        stmt = (
            pg_insert(AppSetting)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value},
            )
        )
        session.execute(stmt)
    session.commit()

    return {
        "ok": True,
        "updated_keys": sorted(data.keys()),
        "settings": _payload(_load_all(session)),
    }
