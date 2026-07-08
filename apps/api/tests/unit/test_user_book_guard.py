"""P1 incident 2026-07-08 — engine jobs must never trade per-user books.

Root cause: the nightly auto-trader (run_paper_trading) selected EVERY
active PaperPortfolio, including per-user practice books
(``user:<id>:stock``). It deployed each new user's full $100k starting
cash into engine picks, so "Add to paper ($1,000)" then failed 409
"insufficient cash: have 0".

Pins:
  1. ``is_user_paper_book`` recognizes per-user book names.
  2. The shared engine-portfolio selector statement excludes user books
     (compiled SQL contains the NOT LIKE 'user:%' guard).
"""

from __future__ import annotations

from apps.api.src.domain.paper_trading.paper_service import (
    USER_BOOK_PREFIX,
    engine_tradable_portfolios_stmt,
    is_user_paper_book,
    user_stock_portfolio_name,
)


def test_user_book_names_are_recognized() -> None:
    assert is_user_paper_book(user_stock_portfolio_name("abc-123"))
    assert is_user_paper_book("user:3f6264df-9094-4356-a201-bf639d7540bf:stock")
    assert USER_BOOK_PREFIX == "user:"


def test_engine_book_names_are_not_user_books() -> None:
    assert not is_user_paper_book("Replay Recovery")
    assert not is_user_paper_book("Default Paper")
    assert not is_user_paper_book("")
    assert not is_user_paper_book(None)


def test_engine_selector_excludes_user_books_in_sql() -> None:
    sql = str(
        engine_tradable_portfolios_stmt().compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "user:%" in sql
    assert "NOT" in sql.upper() and "LIKE" in sql.upper()
    assert "is_active" in sql
