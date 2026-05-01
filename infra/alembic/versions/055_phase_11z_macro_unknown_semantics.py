"""Phase 11Z — macro gate unknown semantics.

Extend `context_daily.ck_context_daily_status` to recognize three
new statuses for macro gates whose underlying inputs were missing,
insufficient, or stale at compute time. Allow `value_bool` to be
NULL for those new statuses.

Background (Phase 11Y audit):
  Single-day macro backfills fetched ≤1 obs/series, far below the
  minimum history required by every gate compute fn. Each fn
  returned `None`, which the persister silently coerced to
  `value_bool=False` and `status='production'`. There was no
  schema-level way to distinguish "macro unfavorable" from "data
  unavailable." This migration introduces that distinction.

Rules preserved:
  * Existing rows are unchanged (all current rows have status in
    {production, candidate, diagnostic} and non-NULL value_bool).
  * No strategy threshold or gate definition is touched.
  * Reversible: downgrade restores the old constraint and forces
    `value_bool NOT NULL`. Any rows added under the new statuses
    are *coerced* to `status='production'`, `value_bool=FALSE`
    during downgrade — matching the legacy persister behavior — so
    the downgrade does not violate the restored constraint.

Revision ID: 055_phase_11z_macro_unk
Revises: 054_safe_gate_evol_shadow
"""

from __future__ import annotations

from alembic import op


revision = "055_phase_11z_macro_unk"
down_revision = "054_safe_gate_evol_shadow"
branch_labels = None
depends_on = None


_NEW_STATUS_LIST = (
    "'production', 'candidate', 'diagnostic', "
    "'insufficient_data', 'missing_data', 'stale_data'"
)
_OLD_STATUS_LIST = "'production', 'candidate', 'diagnostic'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.context_daily "
        "DROP CONSTRAINT IF EXISTS ck_context_daily_status"
    )
    op.execute(
        f"ALTER TABLE public.context_daily "
        f"ADD CONSTRAINT ck_context_daily_status "
        f"CHECK (status IN ({_NEW_STATUS_LIST}))"
    )
    op.execute(
        "ALTER TABLE public.context_daily "
        "ALTER COLUMN value_bool DROP NOT NULL"
    )


def downgrade() -> None:
    # Coerce any rows added under the new statuses back to legacy
    # semantics (status='production', value_bool=FALSE) so the
    # restored constraints can be applied without conflict.
    op.execute(
        "UPDATE public.context_daily "
        "SET value_bool = FALSE "
        "WHERE value_bool IS NULL"
    )
    op.execute(
        "UPDATE public.context_daily "
        "SET status = 'production' "
        "WHERE status NOT IN (" + _OLD_STATUS_LIST + ")"
    )
    op.execute(
        "ALTER TABLE public.context_daily "
        "DROP CONSTRAINT IF EXISTS ck_context_daily_status"
    )
    op.execute(
        f"ALTER TABLE public.context_daily "
        f"ADD CONSTRAINT ck_context_daily_status "
        f"CHECK (status IN ({_OLD_STATUS_LIST}))"
    )
    op.execute(
        "ALTER TABLE public.context_daily "
        "ALTER COLUMN value_bool SET NOT NULL"
    )
