"""Agent Gateway v0 — agent_token + agent_audit (Elite ArthOS, Priority 7 / P7).

Generated per docs/architecture/AGENT_GATEWAY_V0_SPEC.md §2 (token model) and
§5 (audit). NOT applied to any database (orchestrator applies; validated on an
ephemeral container only). Additive only; downgrade drops both tables.

Security posture is structural, not stylistic (spec §2, §5, §7):
  * tokens are HASHED at rest — `token_hash` = sha256(full_token); the secret
    is shown exactly once at creation and never persisted (spec §2). A DB dump
    therefore never yields a usable token.
  * `token_prefix` (8 chars) is plaintext for O(1) candidate lookup + audit/UI
    display; the full hash is compared in constant time in the service.
  * `expires_at` is NOT NULL — there is no non-expiring token (spec §2).
  * scopes are a comma-joined subset of {R,P,B,D}, grammar-checked at write time
    (`ck_agent_token_scopes`) so an unknown/`T` letter can never be stored —
    there is no live-trading scope (spec §3).
  * `agent_audit` is append-only (no UPDATE/DELETE path in the service —
    reasoning_audit precedent) and stores HASHES, not payloads (spec §5): no
    market data, draft bodies, or secrets are duplicated into the audit trail.

`created_by` is app_user.id (owner, v0) — soft reference, no hard FK so the
audit/token history is never cascaded away if a user row is ever removed
(login_attempt / reasoning_audit precedent: audit outlives its subject).

Revision ID: 114_agent_gateway
Revises: 113_lesson
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "114_agent_gateway"
down_revision = "113_lesson"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # agent_token — bearer tokens for the /agent gateway (spec §2)
    # ------------------------------------------------------------------
    op.create_table(
        "agent_token",
        sa.Column("id", sa.String(36), primary_key=True),
        # human label, e.g. 'research-claude'
        sa.Column("agent_name", sa.String(64), nullable=False),
        # first 8 chars after the namespace — plaintext, unique, for lookup+UI
        sa.Column("token_prefix", sa.String(8), nullable=False),
        # sha256 hex of the full token — the secret itself is never stored
        sa.Column("token_hash", sa.String(64), nullable=False),
        # comma-joined subset of R,P,B,D (grammar enforced below)
        sa.Column("scopes", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="active"),
        # mandatory expiry — no non-expiring token exists (spec §2)
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer, nullable=False,
                  server_default="60"),
        sa.Column("max_request_bytes", sa.Integer, nullable=False,
                  server_default="65536"),
        # app_user.id of the owner who created it (soft ref — no FK cascade)
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text),
        sa.UniqueConstraint("token_prefix", name="uq_agent_token_prefix"),
        sa.UniqueConstraint("token_hash", name="uq_agent_token_hash"),
        sa.CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_agent_token_status",
        ),
        # only R,P,B,D letters, 1-4 of them, comma-joined — no 'T', no unknown
        sa.CheckConstraint(
            r"scopes ~ '^[RPBD](,[RPBD]){0,3}$'",
            name="ck_agent_token_scopes",
        ),
        sa.CheckConstraint(
            "rate_limit_per_min BETWEEN 1 AND 240",
            name="ck_agent_token_rate",
        ),
        # a revoked token must carry the revocation timestamp
        sa.CheckConstraint(
            "status <> 'revoked' OR revoked_at IS NOT NULL",
            name="ck_agent_token_revoked",
        ),
    )
    op.create_index("ix_agent_token_status_expires", "agent_token",
                    ["status", "expires_at"])

    # ------------------------------------------------------------------
    # agent_audit — one row per gateway request (spec §5). Append-only.
    # agent_name NULL when the token is unknown/invalid; token_prefix is the
    # candidate prefix as presented (so auth failures are auditable too).
    # ------------------------------------------------------------------
    op.create_table(
        "agent_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_name", sa.String(64)),
        sa.Column("token_prefix", sa.String(8)),
        # templated path, never the raw URL ('/agent/recommendations/{rec_uid}')
        sa.Column("route", sa.String(128), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        # R|P|B|D — NULL on pre-scope rejection (auth failure, 404)
        sa.Column("scope_used", sa.String(4)),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("idempotency_key", sa.String(64)),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        # sha256 of canonical(method,path,sorted query,body) — correlation
        # without storing the payload itself
        sa.Column("request_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_audit_prefix_created", "agent_audit",
                    ["token_prefix", sa.text("created_at DESC")])
    op.create_index("ix_agent_audit_route_status", "agent_audit",
                    ["route", "status_code", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_agent_audit_route_status", table_name="agent_audit")
    op.drop_index("ix_agent_audit_prefix_created", table_name="agent_audit")
    op.drop_table("agent_audit")
    op.drop_index("ix_agent_token_status_expires", table_name="agent_token")
    op.drop_table("agent_token")
