"""Phase B7.2 — market_event_calendar + 90-day macro seed.

Canonical macro/catalyst calendar for the Options AI strategist.
Seeded with scheduled US macro releases (FOMC / CPI / NFP) that affect
the ETF options universe (SPY / QQQ / IWM / GLD / TLT).

Discipline:
  * Additive only.
  * Each row carries `source` so manual seeds + future provider
    ingests stay distinguishable.
  * Each row has an `explanation` field — the AI strategist uses
    this text verbatim; never composes new narrative at run time.
  * Future dates are SCHEDULED — Fed may reschedule. Operators
    update by `INSERT ... ON CONFLICT DO UPDATE` keyed on
    (event_type, event_date).

Strictly additive.

Revision ID: 074_market_event_calendar
Revises: 073_options_strategy_candidate
"""

from __future__ import annotations

import datetime as dt

from alembic import op
import sqlalchemy as sa


revision = "074_market_event_calendar"
down_revision = "073_options_strategy_candidate"
branch_labels = None
depends_on = None


# 90-day window from 2026-05-14 (Phase B7 commit date) → 2026-08-12.
# Dates that fall AFTER the window are still seeded for safety so a
# small operator-time skew doesn't blank the catalyst chip overnight.
SEED_EVENTS: list[dict] = [
    # ---- FOMC schedule (US Federal Reserve meetings) ----
    {
        "event_type": "FOMC",
        "event_date": dt.date(2026, 6, 17),
        "event_time": "14:00 ET",
        "title": "FOMC Meeting Decision (June 2026)",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "FOMC rate decision + press conference. Implied vol "
            "across rate-sensitive ETFs typically expands into the "
            "event and contracts shortly after; defined-risk vol "
            "expansion plays often setup well 2-5 sessions before.",
    },
    {
        "event_type": "FOMC",
        "event_date": dt.date(2026, 7, 29),
        "event_time": "14:00 ET",
        "title": "FOMC Meeting Decision (July 2026)",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "Mid-summer FOMC; markets digest Q2 earnings + Fed "
            "trajectory. Premium tends to be richer due to data "
            "uncertainty around growth + inflation prints.",
    },
    # ---- CPI release schedule (monthly, ~mid-month) ----
    {
        "event_type": "CPI",
        "event_date": dt.date(2026, 6, 11),
        "event_time": "08:30 ET",
        "title": "May CPI Release",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT", "GLD"],
        "explanation":
            "Headline + core CPI print. Drives intraday vol in "
            "rate-sensitive ETFs; the print itself is a binary-style "
            "event for short-DTE structures.",
    },
    {
        "event_type": "CPI",
        "event_date": dt.date(2026, 7, 15),
        "event_time": "08:30 ET",
        "title": "June CPI Release",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT", "GLD"],
        "explanation":
            "First CPI after the June FOMC; signal-rich for the "
            "Fed's trajectory into the July meeting.",
    },
    {
        "event_type": "CPI",
        "event_date": dt.date(2026, 8, 12),
        "event_time": "08:30 ET",
        "title": "July CPI Release",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT", "GLD"],
        "explanation":
            "Mid-summer print; thin late-summer liquidity often "
            "amplifies move size on surprises.",
    },
    # ---- NFP / Jobs report (first Friday) ----
    {
        "event_type": "NFP",
        "event_date": dt.date(2026, 6, 5),
        "event_time": "08:30 ET",
        "title": "May Non-Farm Payrolls",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "Monthly jobs report. Wage growth + unemployment drive "
            "rate expectations. SPY/QQQ premium expands 1-2 sessions "
            "before; short-DTE vol plays setup well.",
    },
    {
        "event_type": "NFP",
        "event_date": dt.date(2026, 7, 3),
        "event_time": "08:30 ET",
        "title": "June Non-Farm Payrolls",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "Holiday-week NFP; thin trading often amplifies the "
            "post-print move.",
    },
    {
        "event_type": "NFP",
        "event_date": dt.date(2026, 8, 7),
        "event_time": "08:30 ET",
        "title": "July Non-Farm Payrolls",
        "importance": "high",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "First NFP after July FOMC; markets reassess pace of "
            "future cuts/holds based on labor strength.",
    },
    # ---- FOMC Minutes (3 weeks after each meeting) ----
    {
        "event_type": "FOMC_MINUTES",
        "event_date": dt.date(2026, 7, 8),
        "event_time": "14:00 ET",
        "title": "FOMC June Minutes Release",
        "importance": "medium",
        "affected_symbols": ["SPY", "QQQ", "IWM", "TLT"],
        "explanation":
            "Minutes of the June meeting. Lower-importance than the "
            "meeting itself but can move rates if internal dissent "
            "or hawkish/dovish nuance surfaces.",
    },
    # ---- PPI release ----
    {
        "event_type": "PPI",
        "event_date": dt.date(2026, 6, 12),
        "event_time": "08:30 ET",
        "title": "May Producer Price Index",
        "importance": "medium",
        "affected_symbols": ["SPY", "TLT"],
        "explanation":
            "Producer Price Index. Trails CPI for impact but "
            "matters for the Fed's preferred inflation read (PCE).",
    },
    {
        "event_type": "PPI",
        "event_date": dt.date(2026, 7, 14),
        "event_time": "08:30 ET",
        "title": "June Producer Price Index",
        "importance": "medium",
        "affected_symbols": ["SPY", "TLT"],
        "explanation":
            "Companion print to CPI; combined view informs the "
            "Fed's policy stance going into the July meeting.",
    },
]


def upgrade() -> None:
    op.create_table(
        "market_event_calendar",
        sa.Column(
            "id", sa.BigInteger(),
            sa.Identity(always=False), primary_key=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Text(), nullable=True),
        sa.Column("title",       sa.Text(), nullable=False),
        sa.Column("importance",  sa.Text(), nullable=False),
        sa.Column("source",      sa.Text(), nullable=False,
                  server_default=sa.text("'manual_seed_2026_05'")),
        sa.Column(
            "affected_symbols", sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False, server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "event_type", "event_date",
            name="ux_market_event_calendar_type_date",
        ),
        sa.CheckConstraint(
            "importance IN ('high','medium','low')",
            name="ck_market_event_calendar_importance",
        ),
    )
    op.create_index(
        "ix_market_event_calendar_date_imp",
        "market_event_calendar",
        [sa.text("event_date ASC"), "importance"],
    )

    # Seed.
    insert_sql = sa.text(
        """
        INSERT INTO market_event_calendar
          (event_type, event_date, event_time, title, importance,
           source, affected_symbols, explanation)
        VALUES
          (:event_type, :event_date, :event_time, :title, :importance,
           :source, CAST(:affected_symbols AS text[]), :explanation)
        ON CONFLICT (event_type, event_date) DO NOTHING
        """
    )
    for row in SEED_EVENTS:
        # PG ARRAY literal — use the {}-form string so psycopg passes through.
        symbols_arr = "{" + ",".join(row["affected_symbols"]) + "}"
        op.execute(insert_sql.bindparams(
            event_type=row["event_type"],
            event_date=row["event_date"],
            event_time=row["event_time"],
            title=row["title"],
            importance=row["importance"],
            source="manual_seed_2026_05_macro",
            affected_symbols=symbols_arr,
            explanation=row["explanation"],
        ))


def downgrade() -> None:
    op.drop_index(
        "ix_market_event_calendar_date_imp",
        table_name="market_event_calendar",
    )
    op.drop_table("market_event_calendar")
