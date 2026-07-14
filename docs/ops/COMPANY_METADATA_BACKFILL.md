# TODO — Company Metadata Backfill (name + description)

Status: **NOT STARTED** (blocks beginner-UX Phase 2 + Phase 3)
Created: 2026-06-18

## Why

Beginner surfaces should show **Company Name (TICKER)**, sector, and a plain
description so a first-time investor doesn't need to Google the ticker.
Phase 1 (sector chip) and Phase 4 (jargon cleanup) shipped. Name and
description are blocked on data that does not exist yet.

## Current data state (dev DB, `asset` table, 1008 rows)

| Field | Column | Populated | Notes |
|---|---|---|---|
| sector | `asset.sector` `String(32)` | **100%** | coded (`tech`, `consumer_disc`, …); humanized client-side via `sectorLabel` |
| name | `asset.name` `String(256)` | **0% (all NULL)** | column exists, never backfilled |
| description | — | **no column** | needs schema migration |

Honest-data rule: until real data lands, the UI shows the ticker alone and
omits name/description. **Do not fabricate names or generic descriptions.**

## Phase 2 — Company name backfill

1. Source: **Polygon ticker-details** (`/v3/reference/tickers/{ticker}`) →
   `results.name`. (Provider already used elsewhere — see the Polygon
   provider under `apps/api/src`.)
2. One-off backfill script: iterate active equities, fetch name, write
   `asset.name`. Rate-limit aware; idempotent (skip rows already named).
3. Nightly refresh job for new listings / renames.
4. Serialize `name` on `/recommendations` (add to `_rec_payload`, mirror the
   sector change) — already serialized on `/assets`.
5. Frontend: `CompanyTitle` component → `Company Name (TICKER)`, falling back
   to `TICKER` when name is null. Apply to LiveTodayHero, RecCard, PickPage,
   Watchlist, ModelPortfolioDetail, TrackRecord, PaperBook.

## Phase 3 — Beginner description

1. Migration: add `asset.description` (text) — or a separate `asset_profile`
   table (description, industry, hq, employees, website).
2. Source: Polygon ticker-details (`results.description`, `sic_description`).
3. Backfill + nightly refresh (as Phase 2).
4. Serialize on `/recommendations` + `/assets`.
5. Frontend: render a short, plain description on PickPage (idea detail);
   optional one-liner on cards. Truncate provider text; never invent.

## Acceptance

- ≥95% of the active equity universe has a non-null `name`.
- Beginner surfaces render `Company Name (TICKER)` + sector + description.
- Zero fabricated values; missing data degrades to ticker-only gracefully.
