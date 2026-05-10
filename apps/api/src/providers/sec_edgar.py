"""SEC EDGAR provider — free, no API key required.

Provides recent filings per ticker. Resolves ticker→CIK via the
public ticker map (~10k rows, refreshed yearly), cached in process.

SEC requires a User-Agent header identifying the requester. Override
via the `SEC_EDGAR_USER_AGENT` env var; default is a generic value.

Endpoints used (all free, public):
- https://www.sec.gov/files/company_tickers.json    → ticker map
- https://data.sec.gov/submissions/CIK{10digit}.json → recent filings

This module never fakes data. On error or empty response it returns
an empty list. The caller decides how to surface that to the UI.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)


SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_INDEX_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=10"
)

DEFAULT_USER_AGENT = "AI Investing OS research-tool@example.com"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


_cik_lock = threading.Lock()
_cik_map: dict[str, str] | None = None  # ticker upper → CIK string (10 digits, padded)


def _user_agent() -> str:
    ua = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    return ua or DEFAULT_USER_AGENT


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


def _load_ticker_map() -> dict[str, str]:
    """Fetch + cache the ticker→CIK map. Safe to call concurrently."""
    global _cik_map
    if _cik_map is not None:
        return _cik_map
    with _cik_lock:
        if _cik_map is not None:
            return _cik_map
        try:
            with httpx.Client(timeout=TIMEOUT, headers=_headers()) as client:
                r = client.get(SEC_TICKER_MAP_URL)
                r.raise_for_status()
                raw: dict[str, dict[str, Any]] = r.json()
        except Exception as exc:
            logger.warning("SEC ticker map fetch failed: %s", exc)
            return {}
        # Shape: { "0": { "cik_str": 320193, "ticker": "AAPL", "title": "..." }, ... }
        out: dict[str, str] = {}
        for row in raw.values():
            ticker = str(row.get("ticker", "")).upper().strip()
            cik = row.get("cik_str")
            if ticker and cik is not None:
                out[ticker] = str(int(cik)).zfill(10)
        _cik_map = out
        logger.info("Loaded SEC ticker map: %d entries", len(out))
        return out


def resolve_cik(ticker: str) -> str | None:
    """Resolve a ticker symbol to a 10-digit zero-padded CIK string."""
    if not ticker:
        return None
    return _load_ticker_map().get(ticker.upper().strip())


def fetch_recent_filings(ticker: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return up to `limit` most recent filings for the given ticker.

    Each item:
        {
            "form":     "10-Q",
            "filed_at": "2025-08-04T00:00:00",
            "title":    "10-Q · Quarterly report",
            "url":      "https://www.sec.gov/Archives/edgar/data/.../primary-doc.htm"
        }

    Returns [] on any error or when the ticker is unknown.
    """
    cik = resolve_cik(ticker)
    if cik is None:
        return []

    url = SEC_SUBMISSIONS_URL.format(cik=cik)
    try:
        with httpx.Client(timeout=TIMEOUT, headers=_headers()) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("SEC submissions fetch failed for %s: %s", ticker, exc)
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms: list[str] = recent.get("form", [])
    dates: list[str] = recent.get("filingDate", [])
    accession_numbers: list[str] = recent.get("accessionNumber", [])
    primary_docs: list[str] = recent.get("primaryDocument", [])
    primary_descs: list[str] = recent.get("primaryDocDescription", [])

    cik_int = str(int(cik))  # un-padded for archive URL
    out: list[dict[str, Any]] = []
    for i in range(min(limit, len(forms))):
        form = forms[i]
        if not form:
            continue
        accession = accession_numbers[i] if i < len(accession_numbers) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""
        desc = primary_descs[i] if i < len(primary_descs) else ""
        accession_no_dashes = accession.replace("-", "")
        if accession_no_dashes and primary_doc:
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                f"{accession_no_dashes}/{primary_doc}"
            )
        else:
            doc_url = SEC_FILING_INDEX_URL.format(cik=cik, form=form)
        title = f"{form}" if not desc else f"{form} · {desc}"
        out.append({
            "form": form,
            "filed_at": (dates[i] + "T00:00:00") if i < len(dates) and dates[i] else "",
            "title": title,
            "url": doc_url,
        })
    return out


def is_available() -> bool:
    """SEC EDGAR is always available — no key required."""
    return True
