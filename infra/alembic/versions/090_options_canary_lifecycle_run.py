"""Canary-1 Gate 2 — telemetry-of-truth for canary lifecycle jobs.

Adds `options_canary_lifecycle_run` as the per-invocation truth table
for the Canary-1 lifecycle jobs (`options_canary_proposal` and
`options_canary_lifecycle`).

Mirror of `options_chain_ingest_run` (M089) and `envelope_generation_run`
(M084) from the stocks side. One row per invocation regardless of
outcome. tick_loop's job_run table is *not* the source of truth — this
table is, because it captures the work done (or honestly not done) by
each invocation including operator-initiated actions.

Design points (see docs/research/OPTIONS_CANARY_1_EXECUTION_PLAN.md §6a):

  - Closed-enum `classification`:
      success | no_op | paused | error | operator_action
  - Closed-enum `failure_code`:
      F1_stale_chain | F2_no_fill | F3_pricing_invalid |
      F4_lifecycle_stall | F5_expiry_edge | F6_deployment_drift |
      F7_telemetry_mismatch
      (NULL when not a failure path)
  - Operator action evidence captured inline:
      operator_id, operator_reason (≥ 20 chars), incident_ref,
      quote_gates_overridden, referenced_event_id
  - CHECK constraints enforce that operator fields appear only on
    operator_action rows, and that operator_action rows always carry
    a populated operator_id + operator_reason.

This migration creates table + indexes + check constraints. It does
NOT create any of the canary lifecycle jobs themselves — those are
Gate 3 (skeletons) and beyond.

Revision ID: 090_opt_canary_lifecycle_run
Revises: 089_opt_chain_ingest_run
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "090_opt_canary_lifecycle_run"
down_revision = "089_opt_chain_ingest_run"
branch_labels = None
depends_on = None


CLASSIFICATION_ENUM = (
    "'success', 'no_op', 'paused', 'error', 'operator_action'"
)

FAILURE_CODE_ENUM = (
    "'F1_stale_chain', 'F2_no_fill', 'F3_pricing_invalid', "
    "'F4_lifecycle_stall', 'F5_expiry_edge', 'F6_deployment_drift', "
    "'F7_telemetry_mismatch'"
)

JOB_NAME_ENUM = "'canary_proposal', 'canary_lifecycle'"


def upgrade() -> None:
    op.create_table(
        "options_canary_lifecycle_run",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("job_name", sa.Text, nullable=False),
        sa.Column(
            "portfolio_id",
            sa.Text,
            nullable=False,
            server_default=sa.text("'canary-spy-v1'"),
        ),
        sa.Column(
            "universe",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        # Per-invocation work counts.
        sa.Column(
            "n_proposals_generated",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column(
            "n_fills_executed",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column(
            "n_monitors_written",
            sa.Integer, nullable=False, server_default="0",
        ),
        sa.Column(
            "n_exits_executed",
            sa.Integer, nullable=False, server_default="0",
        ),
        # Outcome classification (closed enum, see CHECK below).
        sa.Column("classification", sa.Text, nullable=False),
        # Failure code (closed enum, NULL when not a failure path).
        sa.Column("failure_code", sa.Text, nullable=True),
        # Free-form structured payload for both errors and operator actions.
        sa.Column(
            "error_summary",
            sa.dialects.postgresql.JSONB,
            nullable=True,
        ),
        # Operator action fields. NULL unless classification='operator_action'.
        sa.Column("operator_id", sa.Text, nullable=True),
        sa.Column("operator_reason", sa.Text, nullable=True),
        sa.Column("incident_ref", sa.Text, nullable=True),
        sa.Column(
            "quote_gates_overridden",
            sa.ARRAY(sa.Text),
            nullable=True,
        ),
        sa.Column("referenced_event_id", sa.BigInteger, nullable=True),
        # Runtime.
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
    )

    # --- CHECK constraints ---------------------------------------------------

    # Closed-enum: classification.
    op.create_check_constraint(
        "ck_canary_lifecycle_run_classification",
        "options_canary_lifecycle_run",
        f"classification IN ({CLASSIFICATION_ENUM})",
    )

    # Closed-enum: failure_code (NULL allowed).
    op.create_check_constraint(
        "ck_canary_lifecycle_run_failure_code",
        "options_canary_lifecycle_run",
        f"failure_code IS NULL OR failure_code IN ({FAILURE_CODE_ENUM})",
    )

    # Closed-enum: job_name.
    op.create_check_constraint(
        "ck_canary_lifecycle_run_job_name",
        "options_canary_lifecycle_run",
        f"job_name IN ({JOB_NAME_ENUM})",
    )

    # Single-portfolio guard. Canary-1 is intentionally scoped to one
    # portfolio ('canary-spy-v1'). The DB must refuse any accidental
    # widening; job code enforces the same value but the DB is the final
    # backstop. Lift this constraint deliberately if/when a second
    # canary portfolio is approved.
    op.create_check_constraint(
        "ck_canary_lifecycle_run_portfolio_id_single",
        "options_canary_lifecycle_run",
        "portfolio_id = 'canary-spy-v1'",
    )

    # Operator fields appear ONLY on operator_action rows, and operator_action
    # rows ALWAYS carry operator_id + operator_reason (≥ 20 chars).
    op.create_check_constraint(
        "ck_canary_lifecycle_run_operator_action_shape",
        "options_canary_lifecycle_run",
        """
        (
          classification = 'operator_action'
          AND operator_id IS NOT NULL
          AND operator_reason IS NOT NULL
          AND char_length(operator_reason) >= 20
        )
        OR
        (
          classification <> 'operator_action'
          AND operator_id IS NULL
          AND operator_reason IS NULL
          AND incident_ref IS NULL
          AND quote_gates_overridden IS NULL
          AND referenced_event_id IS NULL
        )
        """,
    )

    # error classification must carry a failure_code.
    # operator_action and non-error paths must NOT carry one.
    op.create_check_constraint(
        "ck_canary_lifecycle_run_failure_code_shape",
        "options_canary_lifecycle_run",
        """
        (classification = 'error' AND failure_code IS NOT NULL)
        OR
        (classification <> 'error' AND failure_code IS NULL)
        """,
    )

    # --- Indexes -------------------------------------------------------------

    op.create_index(
        "ix_canary_lifecycle_run_started",
        "options_canary_lifecycle_run",
        ["started_at"],
    )
    op.create_index(
        "ix_canary_lifecycle_run_class",
        "options_canary_lifecycle_run",
        ["classification", "started_at"],
    )
    # Partial index: only failure rows for fast post-mortem queries.
    op.create_index(
        "ix_canary_lifecycle_run_failure",
        "options_canary_lifecycle_run",
        ["failure_code", "started_at"],
        postgresql_where=sa.text("failure_code IS NOT NULL"),
    )
    # Partial index: only operator rows for audit queries.
    op.create_index(
        "ix_canary_lifecycle_run_operator",
        "options_canary_lifecycle_run",
        ["operator_id", "started_at"],
        postgresql_where=sa.text("classification = 'operator_action'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_canary_lifecycle_run_operator",
        table_name="options_canary_lifecycle_run",
    )
    op.drop_index(
        "ix_canary_lifecycle_run_failure",
        table_name="options_canary_lifecycle_run",
    )
    op.drop_index(
        "ix_canary_lifecycle_run_class",
        table_name="options_canary_lifecycle_run",
    )
    op.drop_index(
        "ix_canary_lifecycle_run_started",
        table_name="options_canary_lifecycle_run",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_failure_code_shape",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_operator_action_shape",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_portfolio_id_single",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_job_name",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_failure_code",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_constraint(
        "ck_canary_lifecycle_run_classification",
        "options_canary_lifecycle_run",
        type_="check",
    )
    op.drop_table("options_canary_lifecycle_run")
