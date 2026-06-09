"""TESTS-ONLY options-canary lifecycle replay harness (helper module).

Builds an ISOLATED, alembic-migrated, ephemeral Postgres testcontainer and
drives the REAL canary promotion + lifecycle code (no duplicated lifecycle
math or thresholds) through deterministic QQQ SHORT_PUT_CREDIT_SPREAD
scenarios.

HARD ISOLATION (asserted, never assumed):
  * The engine URL is ALWAYS the testcontainer's (localhost/127.0.0.1 +
    container-assigned port). Never a production host.
  * os.environ['DATABASE_URL'] is NEVER read to build the engine. The
    container URL is passed straight to alembic via `-x url=...` and to
    SQLAlchemy create_engine; env.py's DATABASE_URL precedence is bypassed
    because we inject the URL on cmd_opts.x (higher precedence than env).
  * Every replay portfolio name starts with 'replay-sim-' and is never the
    real 'canary-spy-v1' seed.

The canary tables (options_paper_portfolio / _position /
options_strategy_candidate / options_candidate_leg / options_chain_snapshot)
are ALEMBIC-ONLY (not SQLAlchemy ORM `create_all`), so the schema is built by
running `alembic upgrade head` against the throwaway container.

Strictly additive: lives under apps/api/tests/**. Touches no production source.
"""

from __future__ import annotations

import argparse
import datetime as dt
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.options.canary import engine as canary_engine
from apps.api.src.options.canary import positions as pos
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.engine import TradeRequest
from apps.api.src.options.paper.strategies import (
    LegSpec,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)

# ---------------------------------------------------------------------------
# Deterministic QQQ SHORT_PUT_CREDIT_SPREAD shape (width $1)
# ---------------------------------------------------------------------------
UNDERLYING = "QQQ"
SHORT_STRIKE = Decimal("400")   # SELL higher-strike put
LONG_STRIKE = Decimal("399")    # BUY  lower-strike put  → width $1
SHORT_SYM = "QQQ260918P00400000"
LONG_SYM = "QQQ260918P00399000"

REPLAY_PREFIX = "replay-sim-"
FORBIDDEN_PORTFOLIO_NAME = "canary-spy-v1"

# Repo root → infra/alembic
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]   # .../investment-platform
_ALEMBIC_DIR = _REPO_ROOT / "infra" / "alembic"


# ===========================================================================
# Safety guards (called from fixtures AND inline at setup)
# ===========================================================================

def assert_ephemeral_url(url: str) -> None:
    """SAFETY GUARD 1: the engine URL must be the testcontainer/ephemeral one.

    Host must be localhost/127.0.0.1 on a container-assigned (non-default,
    non-5432) port — never a production/dev host. Refuses well-known
    dev/compose hostnames outright.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    assert host in ("localhost", "127.0.0.1"), (
        f"replay harness refuses non-local DB host {host!r}; "
        f"only an ephemeral testcontainer on localhost is allowed"
    )
    assert host not in ("db", "compose-db-1", "compose-db"), (
        f"replay harness refuses dev/compose host {host!r}"
    )
    assert port is not None and int(port) != 5432, (
        f"replay harness expects a container-assigned port (not 5432), got {port!r}; "
        f"the default port indicates a non-ephemeral target"
    )


def assert_not_database_url(container_url: str, os_environ) -> None:
    """SAFETY GUARD 2: the harness must NOT build the engine from
    os.environ['DATABASE_URL']. We assert the container URL we are about to
    use is NOT equal to DATABASE_URL (host+port+db tuple), proving the
    engine was built from the container URL only.
    """
    prod = (os_environ.get("DATABASE_URL") or "").strip()
    if not prod:
        return  # not set → trivially not used
    try:
        pu, cu = make_url(prod), make_url(container_url)
    except Exception:  # noqa: BLE001
        return
    prod_t = f"{(pu.host or '').lower()}:{pu.port or ''}:{(pu.database or '').lower()}"
    cont_t = f"{(cu.host or '').lower()}:{cu.port or ''}:{(cu.database or '').lower()}"
    assert prod_t != cont_t, (
        "replay container URL coincides with DATABASE_URL — refusing; "
        "the harness must use ONLY the ephemeral container URL"
    )


def assert_replay_portfolio_name(name: str) -> None:
    """SAFETY GUARD 3: every replay portfolio name must start with the
    'replay-sim-' prefix."""
    assert name.startswith(REPLAY_PREFIX), (
        f"replay portfolio name {name!r} must start with {REPLAY_PREFIX!r}"
    )


def assert_not_canary_seed(*, portfolio_id: str, name: str) -> None:
    """SAFETY GUARD 4: the replay portfolio id/name must never be the real
    'canary-spy-v1' seed."""
    assert name != FORBIDDEN_PORTFOLIO_NAME, (
        f"replay portfolio name must not be {FORBIDDEN_PORTFOLIO_NAME!r}"
    )
    assert portfolio_id != FORBIDDEN_PORTFOLIO_NAME, (
        f"replay portfolio id must not be {FORBIDDEN_PORTFOLIO_NAME!r}"
    )


# ===========================================================================
# Schema build — alembic upgrade head against the container URL
# ===========================================================================

def alembic_upgrade_head(url: str) -> None:
    """Run `alembic upgrade head` against `url` programmatically.

    The URL is injected via `-x url=...` (cmd_opts.x), which env.py treats as
    HIGHEST precedence — so DATABASE_URL is never consulted. This is the
    mechanism that satisfies SAFETY GUARD 2 at the schema-build layer too.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    # env.py reads the target from context.get_x_argument() first.
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url}"])
    command.upgrade(cfg, "head")


# ===========================================================================
# Fixtures — ephemeral container engine + alembic-migrated schema
# ===========================================================================

def make_alembic_engine(url: str, os_environ) -> Engine:
    """Validate isolation, migrate, and return an Engine bound to the
    ephemeral container ONLY."""
    assert_ephemeral_url(url)
    assert_not_database_url(url, os_environ)
    alembic_upgrade_head(url)
    return create_engine(url, pool_pre_ping=True, future=True)


# ===========================================================================
# Seed builders
# ===========================================================================

def make_portfolio(
    session: Session,
    *,
    cash: Decimal = Decimal("10000"),
    max_open_trades: int = 5,
    max_capital_per_trade: Decimal = Decimal("500"),
) -> tuple[str, str]:
    """Insert an isolated replay portfolio. Returns (portfolio_id, name).

    Enforces (and asserts) the replay-sim- name prefix and the not-canary-seed
    guard. cash_current=10000, max_capital_per_trade>=200, max_open_trades>=1.
    """
    assert max_capital_per_trade >= Decimal("200")
    assert max_open_trades >= 1
    pid = str(uuid.uuid4())
    name = f"{REPLAY_PREFIX}{pid[:8]}"
    assert_replay_portfolio_name(name)
    assert_not_canary_seed(portfolio_id=pid, name=name)
    session.execute(text(
        "INSERT INTO options_paper_portfolio "
        "(id, name, cash_initial, cash_current, max_open_trades, "
        " max_capital_per_trade, active, universe, strategy_family) "
        "VALUES (:id, :n, :ci, :cc, :mot, :mcpt, TRUE, :u, :sf)"
    ), {
        "id": pid, "n": name, "ci": cash, "cc": cash,
        "mot": max_open_trades, "mcpt": max_capital_per_trade,
        "u": UNDERLYING, "sf": STRATEGY_SHORT_PUT_CREDIT_SPREAD,
    })
    session.commit()
    return pid, name


def _quote(
    symbol: str, strike: Decimal, *, bid: Decimal, ask: Decimal,
    expiry: dt.date, snapshot_at: dt.datetime, age: int,
    oi: int = 2000, delta: Decimal = Decimal("-0.20"),
) -> OptionChainQuote:
    mid = (bid + ask) / Decimal("2")
    return OptionChainQuote(
        snapshot_at_utc=snapshot_at, underlying=UNDERLYING, expiry=expiry,
        strike=strike, option_type="PUT", option_symbol=symbol,
        bid=bid, ask=ask, mid=mid, last=bid, volume=500, open_interest=oi,
        delta=delta, gamma=Decimal("0.02"), theta=Decimal("-0.05"),
        vega=Decimal("0.10"), iv=Decimal("0.20"), quote_age_seconds=age,
        provider="thetadata", provider_version="thetadata",
    )


def make_spcs_request(
    *, expiry: dt.date, snapshot_at: dt.datetime,
    short_bid: Decimal = Decimal("0.60"), short_ask: Decimal = Decimal("0.65"),
    long_bid: Decimal = Decimal("0.20"), long_ask: Decimal = Decimal("0.25"),
) -> TradeRequest:
    """Build a QQQ SHORT_PUT_CREDIT_SPREAD promotion request priced from
    fresh, fillable entry quotes (OI>=500, spread<=$0.10, age<=60, valid
    bid/ask). SELL 400P / BUY 399P, width $1.

    Default entry: net credit ~ $0.40/contract → max_profit ~ $40,
    max_loss ~ $60 (width 100 - credit 40), well under the $500 cap.
    """
    short = _quote(SHORT_SYM, SHORT_STRIKE, bid=short_bid, ask=short_ask,
                   expiry=expiry, snapshot_at=snapshot_at, age=2,
                   delta=Decimal("-0.30"))
    long_ = _quote(LONG_SYM, LONG_STRIKE, bid=long_bid, ask=long_ask,
                   expiry=expiry, snapshot_at=snapshot_at, age=2,
                   delta=Decimal("-0.18"))
    legs = (
        LegSpec(side="SELL", option_type="PUT", strike=SHORT_STRIKE,
                expiry=expiry, qty=1, option_symbol=SHORT_SYM),
        LegSpec(side="BUY", option_type="PUT", strike=LONG_STRIKE,
                expiry=expiry, qty=1, option_symbol=LONG_SYM),
    )
    return TradeRequest(
        underlying=UNDERLYING, strategy_name=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        strategy_version="canary-v1", legs=legs,
        quotes_by_symbol={SHORT_SYM: short, LONG_SYM: long_},
    )


def seed_chain(
    session: Session, *, expiry: dt.date, snapshot_at: dt.datetime,
    short_bid: Decimal, short_ask: Decimal,
    long_bid: Decimal, long_ask: Decimal,
    age: int = 2, oi: int = 2000,
) -> None:
    """Insert the LATEST options_chain_snapshot rows the manage_one MTM reads
    (latest_chain_quotes → DISTINCT ON option_symbol ORDER BY snapshot_at_utc
    DESC). Each scenario controls the exit by these mids / age / expiry /
    snapshot recency.
    """
    rows = [
        (SHORT_SYM, SHORT_STRIKE, short_bid, short_ask),
        (LONG_SYM, LONG_STRIKE, long_bid, long_ask),
    ]
    for sym, strike, bid, ask in rows:
        mid = (bid + ask) / Decimal("2")
        session.execute(text(
            "INSERT INTO options_chain_snapshot "
            "(snapshot_at_utc, underlying, expiry, strike, option_type, "
            " option_symbol, bid, ask, mid, last, volume, open_interest, "
            " delta, gamma, theta, vega, iv, quote_age_seconds, provider, "
            " provider_version) "
            "VALUES (:t, :u, :e, :k, 'PUT', :sym, :b, :a, :m, :b, 500, :oi, "
            " -0.20, 0.02, -0.05, 0.10, 0.20, :age, 'thetadata', 'thetadata')"
        ), {
            "t": snapshot_at, "u": UNDERLYING, "e": expiry, "k": strike,
            "sym": sym, "b": bid, "a": ask, "m": mid, "oi": oi, "age": age,
        })
    session.commit()


def seed_settlement(session: Session, *, close_price: Decimal) -> None:
    """Seed the price_bar/asset row settlement_price() reads for the expiry
    path (selection.settlement_price → latest price_bar.close for QQQ)."""
    aid = session.execute(text(
        "SELECT id FROM asset WHERE symbol = :s"
    ), {"s": UNDERLYING}).scalar()
    if aid is None:
        aid = str(uuid.uuid4())
        session.execute(text(
            "INSERT INTO asset "
            "(id, symbol, asset_class, currency, is_active, created_at, updated_at) "
            "VALUES (:id, :s, 'equity', 'USD', TRUE, NOW(), NOW())"
        ), {"id": aid, "s": UNDERLYING})
    session.execute(text(
        "INSERT INTO price_bar "
        "(id, asset_id, timeframe, ts, open, high, low, close, volume, "
        " provider, created_at) "
        "VALUES (:id, :aid, '1d', :ts, :c, :c, :c, :c, 1000000, "
        " 'replay-sim', NOW())"
    ), {"id": str(uuid.uuid4()), "aid": aid,
        "ts": dt.datetime.now(dt.timezone.utc), "c": close_price})
    session.commit()


# ===========================================================================
# Scenario driver — promote then run the REAL lifecycle cycle
# ===========================================================================

def promote(
    session_factory, *, portfolio_id: str, request: TradeRequest,
    proposal_hash: str, now: dt.datetime,
):
    """Promote one request inside its own transaction (mirrors the worker)."""
    with session_factory() as s:
        r = canary_engine.promote_one(
            s, portfolio_id=portfolio_id, request=request,
            proposal_hash=proposal_hash, now=now,
        )
        s.commit()
    return r


def run_cycle(session_factory, *, portfolio_id: str, now: dt.datetime):
    """Run the REAL run_lifecycle_cycle (MTM + decide_exit + release + reconcile)."""
    return canary_engine.run_lifecycle_cycle(
        portfolio_id=portfolio_id, now=now, heal=True,
        session_factory=session_factory,
    )
