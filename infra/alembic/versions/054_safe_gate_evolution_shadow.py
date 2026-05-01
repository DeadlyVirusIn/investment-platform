"""Phase 11X — safe_gate_evolution_shadow diagnostic table.

Append-only shadow log for the gate-evolution diagnostic. Records
one row per evaluated trading day. NEVER writes to paper_trade,
paper_position, paper_run_log, candidate_idea, or any execution
surface. NEVER influences production decisions.

Schema rules:
  * One row per `run_date` (UNIQUE constraint).
  * `would_trade=true` rows carry a candidate symbol + score; these
    represent days the shadow pilot would have opened a paper
    position.
  * `would_trade=false` rows are summary-only and explain why no
    shadow candidate was elected (e.g., favorable_count=0, or no
    eligible buy in top decile).

Revision ID: 054_safe_gate_evol_shadow
Revises: 053_research_provider_idemp
"""

from __future__ import annotations

from alembic import op


revision = "054_safe_gate_evol_shadow"
down_revision = "053_research_provider_idemp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.safe_gate_evolution_shadow (
            id                            uuid PRIMARY KEY
                                            DEFAULT gen_random_uuid(),
            run_date                      date NOT NULL,
            symbol                        text,
            side                          text,
            composite_score               numeric(20,6),
            confidence                    numeric(20,6),
            macro_favorable_count         int NOT NULL,
            failed_macro_gates            jsonb NOT NULL DEFAULT '[]'::jsonb,
            price_regime                  jsonb NOT NULL DEFAULT '{}'::jsonb,
            original_selector_reason      text,
            shadow_reason                 text NOT NULL,
            hypothetical_size_multiplier  numeric(6,4) NOT NULL
                                            DEFAULT 0.25,
            would_trade                   boolean NOT NULL,
            created_at                    timestamptz NOT NULL
                                            DEFAULT now(),
            CONSTRAINT ux_safe_gate_evolution_shadow_run_date
              UNIQUE (run_date),
            CONSTRAINT ck_safe_gate_shadow_macro_count_range
              CHECK (macro_favorable_count >= 0
                     AND macro_favorable_count <= 4),
            CONSTRAINT ck_safe_gate_shadow_size_mult_bounds
              CHECK (hypothetical_size_multiplier >= 0
                     AND hypothetical_size_multiplier <= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_safe_gate_shadow_run_date "
        "ON public.safe_gate_evolution_shadow (run_date DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_safe_gate_shadow_would_trade "
        "ON public.safe_gate_evolution_shadow (would_trade, run_date DESC)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS public.ix_safe_gate_shadow_would_trade"
    )
    op.execute(
        "DROP INDEX IF EXISTS public.ix_safe_gate_shadow_run_date"
    )
    op.execute(
        "DROP TABLE IF EXISTS public.safe_gate_evolution_shadow"
    )
