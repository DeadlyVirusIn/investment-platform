"""Phase G — auth + organization + subscription tables.

Schema-only. Adds the four tables required by the server-side tier
resolver. Stripe wiring intentionally deferred to G.1; subscription
rows can be inserted manually via `provider='manual'` or
`provider='internal'` until the webhook lands.

Tables live in `public` schema (auth is cross-cutting, not
research-only). NEVER linked from the research_ro schema (would
violate the public→research_ro FK direction rule). The auth tables
themselves do not link out to research_ro.

Revision ID: 060_auth_sub_org
Revises: 059_research_oper_cooldown
"""

from __future__ import annotations

from alembic import op


revision = "060_auth_sub_org"
down_revision = "059_research_oper_cooldown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- app_user --------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.app_user (
          id               text PRIMARY KEY,
          email            text NOT NULL,
          display_name     text,
          auth_provider    text NOT NULL DEFAULT 'placeholder',
          external_auth_id text,
          created_at       timestamptz NOT NULL DEFAULT now(),
          disabled_at      timestamptz,
          CONSTRAINT ux_app_user_email UNIQUE (email),
          CONSTRAINT ck_app_user_provider
            CHECK (auth_provider IN
                   ('placeholder','jwt','oauth_google','oauth_github','sso'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_user_external "
        "ON public.app_user (auth_provider, external_auth_id) "
        "WHERE external_auth_id IS NOT NULL"
    )

    # ---- organization ---------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.organization (
          id            text PRIMARY KEY,
          name          text NOT NULL,
          owner_user_id text NOT NULL REFERENCES public.app_user(id),
          created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_organization_owner "
        "ON public.organization (owner_user_id)"
    )

    # ---- organization_member --------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.organization_member (
          org_id     text NOT NULL REFERENCES public.organization(id)
                       ON DELETE CASCADE,
          user_id    text NOT NULL REFERENCES public.app_user(id),
          role       text NOT NULL DEFAULT 'member',
          status     text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (org_id, user_id),
          CONSTRAINT ck_org_member_role
            CHECK (role IN ('owner','admin','member','viewer')),
          CONSTRAINT ck_org_member_status
            CHECK (status IN ('active','invited','removed'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_org_member_user "
        "ON public.organization_member (user_id, status)"
    )

    # ---- subscription ---------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.subscription (
          id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          subject_type             text NOT NULL,
          subject_id               text NOT NULL,
          tier                     text NOT NULL DEFAULT 'free',
          status                   text NOT NULL DEFAULT 'active',
          provider                 text NOT NULL DEFAULT 'internal',
          provider_customer_id     text,
          provider_subscription_id text,
          current_period_end       timestamptz,
          created_at               timestamptz NOT NULL DEFAULT now(),
          updated_at               timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_sub_subject_type
            CHECK (subject_type IN ('user','org')),
          CONSTRAINT ck_sub_tier
            CHECK (tier IN ('free','pro','enterprise')),
          CONSTRAINT ck_sub_status
            CHECK (status IN ('active','trialing','past_due',
                              'canceled','expired')),
          CONSTRAINT ck_sub_provider
            CHECK (provider IN ('stripe','manual','internal'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscription_subject "
        "ON public.subscription (subject_type, subject_id, status)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_subscription_provider_sub "
        "ON public.subscription (provider, provider_subscription_id) "
        "WHERE provider_subscription_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS public.ux_subscription_provider_sub")
    op.execute("DROP INDEX IF EXISTS public.ix_subscription_subject")
    op.execute("DROP TABLE IF EXISTS public.subscription")
    op.execute("DROP INDEX IF EXISTS public.ix_org_member_user")
    op.execute("DROP TABLE IF EXISTS public.organization_member")
    op.execute("DROP INDEX IF EXISTS public.ix_organization_owner")
    op.execute("DROP TABLE IF EXISTS public.organization")
    op.execute("DROP INDEX IF EXISTS public.ix_app_user_external")
    op.execute("DROP TABLE IF EXISTS public.app_user")
