"""Smoke tests for market events providers.

Tests focus on:
- Empty responses when no API key is set (Polygon, Benzinga)
- Response shape correctness
- SEC EDGAR resolve_cik and fetch_recent_filings handle network
  errors without crashing or returning fake data

These tests do NOT make live network calls. SEC EDGAR calls are
mocked so the suite stays deterministic and offline-safe.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestPolygonProvider:
    def test_unavailable_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        from apps.api.src.providers import polygon
        assert polygon.is_available() is False
        assert polygon.fetch_news("AAPL") == []
        assert polygon.fetch_earnings("AAPL") == []

    def test_empty_ticker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLYGON_API_KEY", "fake-key")
        from apps.api.src.providers import polygon
        assert polygon.fetch_news("") == []
        assert polygon.fetch_earnings("") == []


class TestBenzingaProvider:
    def test_unavailable_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
        from apps.api.src.providers import benzinga
        assert benzinga.is_available() is False
        assert benzinga.fetch_news("AAPL") == []


class TestFirecrawlSummarizer:
    def test_noop_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        from apps.api.src.providers import firecrawl_summarizer as f
        assert f.is_available() is False
        assert f.summarize("https://x.com/a", existing="hello") == "hello"
        assert f.summarize("https://x.com/a") is None


class TestSecEdgarProvider:
    def test_user_agent_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
        from apps.api.src.providers import sec_edgar
        assert "AI Investing OS" in sec_edgar._user_agent()
        headers = sec_edgar._headers()
        assert headers["User-Agent"]
        assert headers["Accept"] == "application/json"

    def test_user_agent_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "MyApp me@example.com")
        from apps.api.src.providers import sec_edgar
        assert sec_edgar._user_agent() == "MyApp me@example.com"

    def test_resolve_cik_returns_none_when_map_fetch_fails(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = None
        with patch("apps.api.src.providers.sec_edgar.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("boom")
            assert sec_edgar.resolve_cik("AAPL") is None

    def test_fetch_filings_empty_for_unknown_ticker(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}
        result = sec_edgar.fetch_recent_filings("ZZZZUNKNOWN")
        assert result == []

    def test_fetch_filings_handles_submissions_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {"AAPL": "0000320193"}
        with patch("apps.api.src.providers.sec_edgar.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("fail")
            assert sec_edgar.fetch_recent_filings("AAPL") == []

    def test_fetch_filings_parses_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {"AAPL": "0000320193"}

        class MockResp:
            def raise_for_status(self): pass
            def json(self):
                return {
                    "filings": {
                        "recent": {
                            "form":             ["10-Q", "8-K"],
                            "filingDate":       ["2025-08-04", "2025-07-30"],
                            "accessionNumber":  ["0000320193-25-000088", "0000320193-25-000087"],
                            "primaryDocument":  ["aapl-20250628.htm", "aapl-20250730.htm"],
                            "primaryDocDescription": ["10-Q", "8-K"],
                        }
                    }
                }

        with patch("apps.api.src.providers.sec_edgar.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = MockResp()
            out = sec_edgar.fetch_recent_filings("AAPL", limit=5)
        assert len(out) == 2
        assert out[0]["form"] == "10-Q"
        assert out[0]["filed_at"] == "2025-08-04T00:00:00"
        assert "Archives/edgar/data/320193" in out[0]["url"]
        assert "aapl-20250628.htm" in out[0]["url"]


class TestMarketEventsService:
    def test_empty_symbols_returns_empty_map(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
        from apps.api.src.domain.market_events.service import (
            get_events_for_symbols,
        )
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}  # force unknown
        out = get_events_for_symbols([])
        assert out["symbols"] == {}
        assert "generated_at" in out
        assert out["providers"]["sec_edgar"] is True
        assert out["providers"]["polygon"] is False
        assert out["providers"]["benzinga"] is False

    def test_response_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
        from apps.api.src.domain.market_events.service import (
            get_events_for_symbols,
        )
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}  # all unknown → all empty arrays, no exceptions
        out = get_events_for_symbols(["AAPL", "MSFT"])
        assert set(out["symbols"].keys()) == {"AAPL", "MSFT"}
        for sym in ("AAPL", "MSFT"):
            ev = out["symbols"][sym]
            assert ev["earnings"] == []
            assert ev["news"] == []
            assert ev["filings"] == []
            assert ev["options_expirations"] == []

    def test_dedupes_news(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLYGON_API_KEY", "p")
        monkeypatch.setenv("BENZINGA_API_KEY", "b")
        from apps.api.src.domain.market_events import service
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}
        with patch.object(
            service.polygon, "fetch_news",
            return_value=[{"title": "A", "url": "u1", "published_at": "2025-01-02"}],
        ), patch.object(
            service.benzinga, "fetch_news",
            return_value=[
                {"title": "A", "url": "u1", "published_at": "2025-01-02"},
                {"title": "B", "url": "u2", "published_at": "2025-01-03"},
            ],
        ), patch.object(service.polygon, "fetch_earnings", return_value=[]):
            out = service.get_events_for_symbols(["AAPL"])
        news = out["symbols"]["AAPL"]["news"]
        urls = [n["url"] for n in news]
        assert urls == ["u2", "u1"]  # sorted desc by published_at, deduped

    def test_max_symbols_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
        from apps.api.src.domain.market_events.service import (
            MAX_SYMBOLS, get_events_for_symbols,
        )
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}
        many = [f"SYM{i}" for i in range(MAX_SYMBOLS + 10)]
        out = get_events_for_symbols(many)
        assert len(out["symbols"]) == MAX_SYMBOLS

    def test_single_symbol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POLYGON_API_KEY", raising=False)
        monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
        from apps.api.src.domain.market_events.service import (
            get_events_for_symbol,
        )
        from apps.api.src.providers import sec_edgar
        sec_edgar._cik_map = {}
        out = get_events_for_symbol("aapl")
        assert "events" in out
        assert "generated_at" in out
        assert out["events"]["filings"] == []
