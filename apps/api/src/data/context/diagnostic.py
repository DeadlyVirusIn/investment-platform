"""DIAGNOSTIC context labels — logged only, NEVER wired to strategy."""

from __future__ import annotations

from dataclasses import dataclass

LOGIC_VERSION = "v0.1.0"


@dataclass(frozen=True)
class DiagnosticContext:
    gex_context_flag: bool | None   # True when gex_sign < 0 (Phase X3 failed)
    cot_context_flag: bool | None
    logic_version: str


def classify_diagnostic(
    gex_sign: int | None,
    cot_extreme_flag: bool | None,
) -> DiagnosticContext:
    gex_flag = None if gex_sign is None else (gex_sign < 0)
    return DiagnosticContext(
        gex_context_flag=gex_flag,
        cot_context_flag=cot_extreme_flag,
        logic_version=LOGIC_VERSION,
    )
