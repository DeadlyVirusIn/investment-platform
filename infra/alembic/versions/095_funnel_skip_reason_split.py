"""P6D.36C — funnel skip-reason split (additive columns).

The canary selector skips candidates for stale quotes (P6D.34D),
economic non-viability (P6D.33A), and the confidence gate — but those
skips never reached `options_execution_funnel`: they were invisible
(or only re-derived read-side by the promotion audit). Before scaling
max_open beyond 1 these must be RECORDED counters.

upgrade:
  Add three nullable integer counters (server_default '0' so existing
  rows read 0, not NULL) to options_execution_funnel:
    * skip_stale_quotes          — P6D.34D promotion freshness gate
    * skip_uneconomic            — P6D.33A economic viability gate
    * skip_confidence_below_gate — OPTIONS_CANARY_MIN_CONFIDENCE gate

downgrade:
  Drop the three columns. Safe: writers tolerate their absence only
  on the matching code revision — pair the downgrade with a code
  rollback (standard additive-column contract).

Revision ID: 095_funnel_skip_reason_split
Revises: 094_paper_snapshot_dedup
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "095_funnel_skip_reason_split"
down_revision = "094_paper_snapshot_dedup"
branch_labels = None
depends_on = None

_COLUMNS = (
    "skip_stale_quotes",
    "skip_uneconomic",
    "skip_confidence_below_gate",
)


def upgrade() -> None:
    for col in _COLUMNS:
        op.add_column(
            "options_execution_funnel",
            sa.Column(col, sa.Integer(), nullable=True, server_default="0"),
        )


def downgrade() -> None:
    for col in reversed(_COLUMNS):
        op.drop_column("options_execution_funnel", col)
