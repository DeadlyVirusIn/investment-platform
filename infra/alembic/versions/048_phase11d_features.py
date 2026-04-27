"""Phase 11D — additive columns on options_feature_daily for the
feature engine. NO new tables, NO foreign keys, NO touches to non-
`options_*` schema. Pure additive migration.

Adds the operator-locked Phase 11D feature set:
  * atm_iv                — ATM implied vol (~30d) at as_of_date
  * realized_vol_20d      — annualized 20-day realized vol of underlying
  * term_structure_30_90  — 30d ATM IV / 90d ATM IV ratio
  * unusual_call_volume_z — z-score of today's call volume vs trailing
  * unusual_put_volume_z  — z-score of today's put volume vs trailing
  * gamma_exposure_proxy  — Σ(gamma · open_interest · 100 · sign) proxy
  * call_wall_strike      — strike with max call OI
  * put_wall_strike       — strike with max put OI
  * data_quality_flags    — JSONB list of warnings (no-spot, no-history…)

The pre-existing 11B columns (iv_rank_252d, iv_percentile_252d,
realized_vol_30d, vrp_30d, term_structure_30_60, skew_25d, put/call
OI/volume ratios) are retained unchanged.

Revision ID: 048_phase11d_features
Revises: 047_phase11b_options_schema
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "048_phase11d_features"
down_revision = "047_phase11b_options_schema"
branch_labels = None
depends_on = None


_NEW_COLUMNS: list[tuple[str, sa.types.TypeEngine, bool]] = [
    ("atm_iv",                  sa.Numeric(10, 6), True),
    ("realized_vol_20d",        sa.Numeric(10, 6), True),
    ("term_structure_30_90",    sa.Numeric(10, 6), True),
    ("unusual_call_volume_z",   sa.Numeric(10, 4), True),
    ("unusual_put_volume_z",    sa.Numeric(10, 4), True),
    ("gamma_exposure_proxy",    sa.Numeric(20, 4), True),
    ("call_wall_strike",        sa.Numeric(12, 4), True),
    ("put_wall_strike",         sa.Numeric(12, 4), True),
]


def upgrade() -> None:
    for name, type_, nullable in _NEW_COLUMNS:
        op.add_column(
            "options_feature_daily",
            sa.Column(name, type_, nullable=nullable),
        )
    op.add_column(
        "options_feature_daily",
        sa.Column(
            "data_quality_flags", JSONB,
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("options_feature_daily", "data_quality_flags")
    for name, _t, _n in reversed(_NEW_COLUMNS):
        op.drop_column("options_feature_daily", name)
