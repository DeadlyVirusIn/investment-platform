"""Phase L M085 — granular skip-reason columns on envelope_generation_run.

Splits skip_generator_returned_none into three discrete reasons:
  * skip_min_signals          — extractor produced fewer than 2 canonical signals
  * skip_no_skeleton_match    — selector found no matching rule
  * skip_empty_slot_fills     — selector matched but slot builder
                                couldn't populate from active signals

skip_generator_returned_none stays as a backward-compat aggregate column
(sum of the three new columns). New code populates the granular columns.

Revision ID: 085_phase_l_envelope_skip_reasons
Revises: 084_phase_l_envelope_gen_run
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "085_phase_l_env_skip_reasons"
down_revision = "084_phase_l_envelope_gen_run"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "envelope_generation_run",
        sa.Column(
            "skip_min_signals", sa.Integer, nullable=False, server_default="0",
        ),
    )
    op.add_column(
        "envelope_generation_run",
        sa.Column(
            "skip_no_skeleton_match", sa.Integer, nullable=False, server_default="0",
        ),
    )
    op.add_column(
        "envelope_generation_run",
        sa.Column(
            "skip_empty_slot_fills", sa.Integer, nullable=False, server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("envelope_generation_run", "skip_empty_slot_fills")
    op.drop_column("envelope_generation_run", "skip_no_skeleton_match")
    op.drop_column("envelope_generation_run", "skip_min_signals")
