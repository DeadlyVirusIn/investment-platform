"""Frozen human-review checklist (Phase 11J).

Action-safe wording only. NEVER says enter / exit / buy / sell /
execute / place order / trade now. Pure-fn module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


@dataclass(frozen=True)
class ChecklistItem:
    code: str
    label: str
    description: str


# ---------------------------------------------------------------------------
# Always-present items (frozen v1 list)
# ---------------------------------------------------------------------------

CHECKLIST_ALWAYS: tuple[ChecklistItem, ...] = (
    ChecklistItem(
        code="VERIFY_DATA_FRESHNESS",
        label="Verify data freshness",
        description=(
            "Confirm chain snapshot timestamps and quote ages reflect "
            "current market data, not stale data from a previous "
            "session."
        ),
    ),
    ChecklistItem(
        code="VERIFY_OPTION_CHAIN_LIQUIDITY",
        label="Verify option chain liquidity",
        description=(
            "Confirm the candidate legs still satisfy the liquidity "
            "filter (open interest >= 500, spread <= $0.10, age <= 60s, "
            "ask > bid > 0) using a fresh chain pull."
        ),
    ),
    ChecklistItem(
        code="VERIFY_SPREAD_OI_VOLUME",
        label="Verify spread / OI / volume",
        description=(
            "Cross-check spread, open interest, and volume on each "
            "selected leg against current market data."
        ),
    ),
    ChecklistItem(
        code="REVIEW_MODEL_LIMITATION_FLAGS",
        label="Review model limitation flags",
        description=(
            "Inspect every flag attached to this row. Confirm the "
            "engine's simplified-exit and pin-risk modelling are "
            "acceptable for the review purpose."
        ),
    ),
    ChecklistItem(
        code="REVIEW_PIN_ASSIGNMENT_SETTLEMENT_FLAGS",
        label="Review pin risk / assignment / settlement flags",
        description=(
            "If PIN_RISK_UNCERTAIN_OUTCOME, ASSIGNMENT_SIMPLIFIED_EXIT, "
            "or MISSING_SETTLEMENT is present, treat the recorded "
            "payoff as a model approximation and not a final outcome."
        ),
    ),
    ChecklistItem(
        code="REVIEW_CURRENT_MARKET_CONTEXT_MANUALLY",
        label="Review current market context manually",
        description=(
            "Compare the historical observation's IV regime, "
            "underlying spot, and event calendar against current "
            "market state outside of this system."
        ),
    ),
    ChecklistItem(
        code="CONFIRM_PAPER_ONLY_ANALYSIS",
        label="Confirm this is paper-only analysis",
        description=(
            "Reaffirm: scores and rankings are paper-only analytics "
            "over historical observations. They are not real-time "
            "trading signals and not execution guidance."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Conditional items based on flags
# ---------------------------------------------------------------------------

_CONDITIONAL_BY_FLAG: dict[str, ChecklistItem] = {
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME: ChecklistItem(
        code="EXTRA_VERIFY_PIN_RISK_BAND",
        label="Extra: verify pin-risk band assumption",
        description=(
            "Pin risk flag present. Re-examine settlement assumptions "
            "and whether the $0.05 pin band fits the current "
            "underlying tick structure."
        ),
    ),
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT: ChecklistItem(
        code="EXTRA_VERIFY_ASSIGNMENT_HANDLING",
        label="Extra: verify assignment-handling assumptions",
        description=(
            "Assignment simplified-exit flag present. v1 paper engine "
            "does not create synthetic equity positions; verify this "
            "approximation is acceptable for the review purpose."
        ),
    ),
    FLAG_MISSING_SETTLEMENT: ChecklistItem(
        code="EXTRA_VERIFY_MISSING_SETTLEMENT",
        label="Extra: verify settlement gap",
        description=(
            "Missing-settlement flag present. Source settlement price "
            "from a separate authoritative reference before treating "
            "PnL as final."
        ),
    ),
}


def build_checklist(row: dict[str, Any]) -> list[dict[str, str]]:
    items: list[ChecklistItem] = list(CHECKLIST_ALWAYS)
    seen_codes = {it.code for it in items}
    for f in row.get("flags") or []:
        extra = _CONDITIONAL_BY_FLAG.get(f)
        if extra and extra.code not in seen_codes:
            items.append(extra)
            seen_codes.add(extra.code)
    return [
        {"code": it.code, "label": it.label, "description": it.description}
        for it in items
    ]
