"""Phase 11W (Phase B) — research_ro schema, roles, and 5 append-only tables.

Read-only research intelligence layer. Hard-isolated from execution:
  * Separate schema research_ro.
  * Separate roles research_writer (INSERT-only on research_ro) and
    research_reader (SELECT-only on research_ro).
  * FK direction: research_ro -> public allowed; public -> research_ro
    forbidden (CI-scanned).
  * CHECK constraints on every body/text column block forbidden tokens.
  * Mandatory provenance columns NOT NULL.
  * Idempotency unique key on research_run.

This migration creates structure only. NO data is inserted, NO worker job
is registered, NO scheduler entry is added. Phase A audit signed off
2026-04-30 by Kunal Khurana.

Revision ID: 052_research_ro_init
Revises: 051_research_fast_fill
"""

from __future__ import annotations

from alembic import op


revision = "052_research_ro_init"
down_revision = "051_research_fast_fill"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Forbidden-token regex shared across body CHECK constraints.
# Postgres \m...\M = word boundaries; permits substrings like
# 'household', 'longitude', 'shortlist'.
# ---------------------------------------------------------------------------

_FORBIDDEN_WORDS = (
    "buy|sell|hold|long|short|recommend|recommends|recommended|"
    "recommending|recommendation|recommendations|signal|signals|"
    "signaled|signaling|allocate|allocates|allocated|allocating|"
    "allocation|execute|executes|executed|executing|execution|"
    "position|positions|entry|exit|leverage|leveraged|leveraging"
)

_FORBIDDEN_PHRASES_SQL = (
    " AND {col} !~* 'target\\s+price'"
    " AND {col} !~* 'stop[\\s-]?loss'"
    " AND {col} !~* 'take[\\s-]?profit'"
    " AND {col} !~* 'portfolio\\s+manager'"
    " AND {col} !~* 'copy[\\s-]?trade'"
)


def _body_check(col: str) -> str:
    """Build a CHECK clause for a body column."""
    word_re = f"'\\m({_FORBIDDEN_WORDS})\\M'"
    return (
        f"{col} !~* {word_re}"
        + _FORBIDDEN_PHRASES_SQL.format(col=col)
    )


def upgrade() -> None:
    # ---- schema -------------------------------------------------------
    op.execute("CREATE SCHEMA IF NOT EXISTS research_ro")

    # ---- enums --------------------------------------------------------
    op.execute(
        "CREATE TYPE research_ro.research_run_status AS ENUM ("
        "'pending','running','succeeded','failed','partial',"
        "'token_violation','cost_exceeded','provider_error',"
        "'timeout','schema_violation')"
    )
    op.execute(
        "CREATE TYPE research_ro.research_agent_role AS ENUM ("
        "'fundamentals','sentiment','news','technical',"
        "'bull_researcher','bear_researcher','risk_analyst',"
        "'reflector')"
    )

    # ---- research_run -------------------------------------------------
    op.execute(
        f"""
        CREATE TABLE research_ro.research_run (
            id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol                   text NOT NULL,
            as_of                    date NOT NULL,
            candidate_idea_id        text NULL,
            decision_id              text NULL,
            schema_version           text NOT NULL,
            prompt_bundle_hash       text NOT NULL,
            input_snapshot_hash      text NOT NULL,
            provider                 text NOT NULL,
            model_id                 text NOT NULL,
            model_version            text NOT NULL,
            prompt_template_id       text NOT NULL,
            prompt_template_version  int NOT NULL,
            prompt_hash              text NOT NULL,
            temperature              numeric(4,3) NOT NULL,
            seed                     bigint NOT NULL,
            tokens_in                integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out               integer NOT NULL CHECK (tokens_out >= 0),
            cost_usd                 numeric(12,6) NOT NULL CHECK (cost_usd >= 0),
            status                   research_ro.research_run_status NOT NULL
                                        DEFAULT 'pending',
            error_code               text,
            error_message            text,
            triggered_by             text NOT NULL
                                        CHECK (triggered_by IN ('manual','operator')),
            operator_id              text NOT NULL,
            started_at               timestamptz NOT NULL DEFAULT now(),
            finished_at              timestamptz,
            is_research_artifact     boolean NOT NULL DEFAULT TRUE
                                        CHECK (is_research_artifact = TRUE),
            CONSTRAINT research_run_idempotency UNIQUE
                (symbol, as_of, prompt_bundle_hash,
                 input_snapshot_hash, schema_version)
        )
        """
    )
    op.create_index(
        "idx_research_run_symbol_as_of",
        "research_run",
        ["symbol", "as_of"],
        schema="research_ro",
    )

    # ---- research_agent_output ---------------------------------------
    op.execute(
        f"""
        CREATE TABLE research_ro.research_agent_output (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id              uuid NOT NULL
                                  REFERENCES research_ro.research_run(id)
                                  ON DELETE CASCADE,
            agent_role          research_ro.research_agent_role NOT NULL,
            sequence_no         integer NOT NULL,
            body                text NOT NULL,
            body_hash           text NOT NULL,
            structured_output   jsonb,
            evidence_refs       jsonb NOT NULL DEFAULT '[]'::jsonb,
            provider            text NOT NULL,
            model_id            text NOT NULL,
            model_version       text NOT NULL,
            prompt_hash         text NOT NULL,
            tokens_in           integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out          integer NOT NULL CHECK (tokens_out >= 0),
            cost_usd            numeric(12,6) NOT NULL CHECK (cost_usd >= 0),
            status              research_ro.research_run_status NOT NULL,
            latency_ms          integer,
            created_at          timestamptz NOT NULL DEFAULT now(),
            UNIQUE (run_id, agent_role, sequence_no),
            CONSTRAINT body_no_action_tokens CHECK (
                {_body_check("body")}
            )
        )
        """
    )
    op.create_index(
        "idx_research_agent_output_run",
        "research_agent_output",
        ["run_id"],
        schema="research_ro",
    )

    # ---- research_debate_summary -------------------------------------
    op.execute(
        f"""
        CREATE TABLE research_ro.research_debate_summary (
            id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id                  uuid NOT NULL UNIQUE
                                      REFERENCES research_ro.research_run(id)
                                      ON DELETE CASCADE,
            bullish_summary         text NOT NULL,
            bearish_summary         text NOT NULL,
            tension_note            text NOT NULL,
            bullish_evidence_refs   jsonb NOT NULL DEFAULT '[]'::jsonb,
            bearish_evidence_refs   jsonb NOT NULL DEFAULT '[]'::jsonb,
            provider                text NOT NULL,
            model_id                text NOT NULL,
            model_version           text NOT NULL,
            prompt_hash             text NOT NULL,
            tokens_in               integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out              integer NOT NULL CHECK (tokens_out >= 0),
            cost_usd                numeric(12,6) NOT NULL CHECK (cost_usd >= 0),
            status                  research_ro.research_run_status NOT NULL,
            body_hash               text NOT NULL,
            created_at              timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT debate_no_action_tokens CHECK (
                {_body_check("bullish_summary")}
                AND {_body_check("bearish_summary")}
                AND {_body_check("tension_note")}
            )
        )
        """
    )

    # ---- research_reflection -----------------------------------------
    op.execute(
        f"""
        CREATE TABLE research_ro.research_reflection (
            id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id                  uuid NOT NULL
                                      REFERENCES research_ro.research_run(id)
                                      ON DELETE CASCADE,
            decision_id             text NOT NULL,
            outcome_window          text NOT NULL,
            realized_return         numeric(10,6) NULL,
            benchmark_return        numeric(10,6) NULL,
            alpha_vs_benchmark      numeric(10,6) NULL,
            body                    text NOT NULL,
            body_hash               text NOT NULL,
            provider                text NOT NULL,
            model_id                text NOT NULL,
            model_version           text NOT NULL,
            prompt_hash             text NOT NULL,
            tokens_in               integer NOT NULL CHECK (tokens_in >= 0),
            tokens_out              integer NOT NULL CHECK (tokens_out >= 0),
            cost_usd                numeric(12,6) NOT NULL CHECK (cost_usd >= 0),
            status                  research_ro.research_run_status NOT NULL,
            created_at              timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT reflection_no_action_tokens CHECK (
                {_body_check("body")}
            )
        )
        """
    )
    op.create_index(
        "idx_research_run_decision_id",
        "research_run",
        ["decision_id"],
        schema="research_ro",
        postgresql_where="decision_id IS NOT NULL",
    )

    # ---- research_checkpoint -----------------------------------------
    op.execute(
        """
        CREATE TABLE research_ro.research_checkpoint (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id      uuid NOT NULL
                          REFERENCES research_ro.research_run(id)
                          ON DELETE CASCADE,
            node_name   text NOT NULL,
            step_no     integer NOT NULL,
            state       jsonb NOT NULL,
            state_hash  text NOT NULL,
            status      research_ro.research_run_status NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (run_id, node_name, step_no)
        )
        """
    )
    op.create_index(
        "idx_research_checkpoint_run",
        "research_checkpoint",
        ["run_id"],
        schema="research_ro",
    )

    # ---- roles + grants ----------------------------------------------
    # Use idempotent role creation so re-runs (e.g., shared test DB) do
    # not fail.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_writer'
            ) THEN
                CREATE ROLE research_writer NOLOGIN;
            END IF;
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_reader'
            ) THEN
                CREATE ROLE research_reader NOLOGIN;
            END IF;
        END
        $$
        """
    )

    op.execute("REVOKE ALL ON SCHEMA research_ro FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA research_ro FROM PUBLIC"
    )

    # research_writer: INSERT only on research_ro; whitelisted SELECT on
    # public input tables; explicit revoke of every other public mutation.
    op.execute("GRANT USAGE ON SCHEMA research_ro TO research_writer")
    op.execute(
        "GRANT INSERT ON ALL TABLES IN SCHEMA research_ro TO research_writer"
    )
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA research_ro "
        "TO research_writer"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA research_ro "
        "GRANT INSERT ON TABLES TO research_writer"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA research_ro "
        "GRANT USAGE, SELECT ON SEQUENCES TO research_writer"
    )
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES "
        "IN SCHEMA research_ro FROM research_writer"
    )
    # Whitelisted reads on public for evidence/reflection. Mutations
    # explicitly revoked.
    op.execute("GRANT SELECT ON public.candidate_idea TO research_writer")
    op.execute("GRANT SELECT ON public.context_daily TO research_writer")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES "
        "IN SCHEMA public FROM research_writer"
    )

    # research_reader: SELECT only on research_ro; explicit zero access
    # to public.
    op.execute("GRANT USAGE ON SCHEMA research_ro TO research_reader")
    op.execute(
        "GRANT SELECT ON ALL TABLES IN SCHEMA research_ro TO research_reader"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA research_ro "
        "GRANT SELECT ON TABLES TO research_reader"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES "
        "IN SCHEMA research_ro FROM research_reader"
    )
    op.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM research_reader"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM research_reader")


def downgrade() -> None:
    """Drop everything created by upgrade(). Reversible."""
    # Roles first lose grants, then schema, then types, then roles.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_writer'
            ) THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA research_ro
                    FROM research_writer;
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA research_ro
                    FROM research_writer;
                REVOKE ALL ON SCHEMA research_ro FROM research_writer;
                REVOKE ALL ON public.candidate_idea FROM research_writer;
                REVOKE ALL ON public.context_daily FROM research_writer;
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM research_writer;
            END IF;
            IF EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_reader'
            ) THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA research_ro
                    FROM research_reader;
                REVOKE ALL ON SCHEMA research_ro FROM research_reader;
            END IF;
        END
        $$
        """
    )
    op.execute("DROP TABLE IF EXISTS research_ro.research_checkpoint")
    op.execute("DROP TABLE IF EXISTS research_ro.research_reflection")
    op.execute("DROP TABLE IF EXISTS research_ro.research_debate_summary")
    op.execute("DROP TABLE IF EXISTS research_ro.research_agent_output")
    op.execute("DROP TABLE IF EXISTS research_ro.research_run")
    op.execute("DROP TYPE IF EXISTS research_ro.research_agent_role")
    op.execute("DROP TYPE IF EXISTS research_ro.research_run_status")
    op.execute("DROP SCHEMA IF EXISTS research_ro CASCADE")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_writer'
            ) THEN
                DROP ROLE research_writer;
            END IF;
            IF EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname='research_reader'
            ) THEN
                DROP ROLE research_reader;
            END IF;
        END
        $$
        """
    )
