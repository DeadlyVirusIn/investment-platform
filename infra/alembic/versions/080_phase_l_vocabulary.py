"""Phase L M080 — vocabulary registry tables.

Implements the governance substrate from PHASE_L_3_V_VOCABULARY.md:
  * vocabulary_entry      — canonical names for signals, regimes, etc.
  * vocabulary_relation   — mutually-exclusive / conflicting / derived pairs
  * vocabulary_bundle     — composable signal groups
  * vocabulary_phrase     — approved user-facing phrasings per entry/context
  * vocabulary_version    — version tracking

Constraints:
  * canonical_name unique within vocabulary_type
  * status enum: active | deprecated | retired | frozen
  * additive only — never drops entries

Revision ID: 080_phase_l_vocabulary
Revises: 079_phase_l_equity_immutability
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "080_phase_l_vocabulary"
down_revision = "079_phase_l_equity_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocabulary_entry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vocabulary_type", sa.String(32), nullable=False),
        sa.Column("canonical_name", sa.String(64), nullable=False),
        sa.Column("display_label", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(32), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("computation_spec", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("replaced_by", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "introduced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("introduced_version", sa.String(16), nullable=False),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint(
            "vocabulary_type", "canonical_name",
            name="uq_vocabulary_entry_type_name",
        ),
        sa.CheckConstraint(
            "status IN ('active','deprecated','retired','frozen')",
            name="ck_vocabulary_entry_status",
        ),
    )
    op.create_index(
        "idx_vocab_type_status",
        "vocabulary_entry",
        ["vocabulary_type", "status"],
    )

    op.create_table(
        "vocabulary_relation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "vocabulary_a",
            sa.String(36),
            sa.ForeignKey("vocabulary_entry.id"),
            nullable=False,
        ),
        sa.Column(
            "vocabulary_b",
            sa.String(36),
            sa.ForeignKey("vocabulary_entry.id"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "introduced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "relation_type IN ('mutually_exclusive','conflicting','requires','suggests','derived_from')",
            name="ck_vocabulary_relation_type",
        ),
    )

    op.create_table(
        "vocabulary_bundle",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("bundle_name", sa.String(64), nullable=False, unique=True),
        sa.Column("display_label", sa.String(128), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column(
            "members",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="active",
        ),
    )

    op.create_table(
        "vocabulary_phrase",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "vocabulary_entry_id",
            sa.String(36),
            sa.ForeignKey("vocabulary_entry.id"),
            nullable=False,
        ),
        sa.Column("phrase_text", sa.Text(), nullable=False),
        sa.Column("context", sa.String(32), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("approved_by", sa.String(64), nullable=False),
    )
    op.create_index(
        "idx_vocab_phrase_entry_context",
        "vocabulary_phrase",
        ["vocabulary_entry_id", "context"],
    )

    op.create_table(
        "vocabulary_version",
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column(
            "active_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # Seed the first version
    op.execute(
        "INSERT INTO vocabulary_version (version, notes) "
        "VALUES ('v1.0', 'MVP launch vocabulary — Phase L freeze')"
    )


def downgrade() -> None:
    op.drop_table("vocabulary_version")
    op.drop_index("idx_vocab_phrase_entry_context", table_name="vocabulary_phrase")
    op.drop_table("vocabulary_phrase")
    op.drop_table("vocabulary_bundle")
    op.drop_table("vocabulary_relation")
    op.drop_index("idx_vocab_type_status", table_name="vocabulary_entry")
    op.drop_table("vocabulary_entry")
