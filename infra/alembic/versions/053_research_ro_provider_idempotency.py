"""Phase 11W (Phase D.3) — widen research_run idempotency key with `provider`.

The Phase B unique key on research_run was
  (symbol, as_of, prompt_bundle_hash, input_snapshot_hash,
   schema_version)

This blocks the Phase D.3 provider-comparison use case where the
SAME symbol/as_of is researched by multiple providers in turn. The
fix widens the key to include `provider` so each (symbol, as_of)
can have one row per provider.

NO data is mutated. NO public-table changes. Only the unique
constraint on research_ro.research_run is dropped + recreated.

Revision ID: 053_research_provider_idemp
Revises: 052_research_ro_init
"""

from __future__ import annotations

from alembic import op


revision = "053_research_provider_idemp"
down_revision = "052_research_ro_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE research_ro.research_run "
        "DROP CONSTRAINT IF EXISTS research_run_idempotency"
    )
    op.execute(
        """
        ALTER TABLE research_ro.research_run
        ADD CONSTRAINT research_run_idempotency UNIQUE
            (symbol, as_of, provider,
             prompt_bundle_hash, input_snapshot_hash, schema_version)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE research_ro.research_run "
        "DROP CONSTRAINT IF EXISTS research_run_idempotency"
    )
    op.execute(
        """
        ALTER TABLE research_ro.research_run
        ADD CONSTRAINT research_run_idempotency UNIQUE
            (symbol, as_of,
             prompt_bundle_hash, input_snapshot_hash, schema_version)
        """
    )
