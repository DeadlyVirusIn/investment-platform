# Phase 15i.V — Operational Validation + Trust Verification Audit

**Date:** 2026-05-11 (Monday)
**Branch:** `phase-1/ledger`
**Audit type:** READ-ONLY synthesis. No code, schema, container, or migration changes. Live re-probing limited to the empirical evidence already gathered before this session began (recorded in §2/§5 below).
**Companion documents:** `docs/ops/PHASE_15i_pipeline_audit.md` (the spec this audit validates), `docs/ux/PHASE_15g_freshness_audit.md` (UI-side freshness audit), `docs/ux/PHASE_15d_lived_experience_review.md` (emotional-trust baseline).

---

## 1. TL;DR — validation verdict

**The truth-infrastructure work shipped in 15i.A/C/D is structurally sound but not yet *operationally live* — the API container that owns `/api/freshness` was built 14 hours before the new route was added and has not been rebuilt, so every probe currently returns 404 and the health-check script can only ever exit 3 (UNREACHABLE).** The migration (065), ORM class (`PipelineRun`), endpoint (`apps/api/src/api/freshness.py`), endpoint tests (`apps/api/tests/unit/test_freshness_endpoint.py`), and operator script (`scripts/check_daily_pipeline_health.py`) all parse, all carry the right invariants, and all reflect the 15g SLA + 15i ledger spec faithfully. They are ready to ship. **Before either a production deploy or 15i.B (the orchestrator), one single thing must happen: rebuild `compose-api-1` so the FastAPI process picks up the new route, and run migration 065 against the same database the API connects to.** Without that, the rest of the trust loop is invisible. **Verdict: CONDITIONAL READY — code-correct, deploy-blocked.**

---

## 2. `/api/freshness` against real data — channel-by-channel correctness review

Live probing is impossible at audit time: `curl http://localhost:5173/api/freshness` and `curl http://localhost:8000/api/freshness` both return 404 (FastAPI router not yet present in the running process — `compose-api-1` started 14 hours ago, before this morning's commit added `apps/api/src/api/freshness.py` and the `include_router(freshness_router)` line at `apps/api/src/main.py:186`). The other `/api/*` routes still 200, confirming the API process is alive and owning the URL space — only the new route is missing. Audit therefore proceeds via code inspection of `freshness.py` against the live data shape captured in 15g §2.

### 2.1 Recommendations channel

- **Source query:** `SELECT MAX(generated_at) FROM recommendation` (`freshness.py:330-334`).
- **SLA applied:** `< 16h fresh | 16-30h degraded | > 30h stale` (`_classify_recommendations`, lines 138-145).
- **Expected freshness now:** 15g §2.2 captured `first pick generated_at = 2026-05-09T02:30 UTC` at audit time 2026-05-11T23:37 UTC. That is ~65h. By the SLA, 65h > 30h ⇒ `stale`.
- **Predicted response:** `status: "stale"`, `as_of: "2026-05-09T02:30:00+00:00"`, `message: "Recommendations based on last completed cycle (2026-05-09T02:30:00+00:00). Today's pipeline has not yet produced new state."`
- **Confidence: HIGH.** Source column matches 15g evidence; classifier thresholds are pure arithmetic; message template is deterministic. The only failure mode here is timezone slippage on a naïve datetime — but `_hours_since` (lines 90-95) defensively coerces to UTC.

### 2.2 Portfolio channel

- **Source query:** `SELECT MAX(finished_at) FROM paper_run_log WHERE status='success'`, falling back to `SELECT MAX(snapshot_date) FROM paper_equity_snapshot` (`_read_portfolio`, lines 337-350).
- **SLA applied:** market-hours-aware via `_classify_portfolio` (lines 148-162). Off-hours tier: `< 16h fresh | 16-30h degraded | > 30h stale`.
- **Expected freshness now:** 15g §2.1 captured `/paper/summary as_of_date = 2026-05-09` (Saturday) and `/paper/equity` last point = `2026-05-09`. That is ~2-3 days. 23:37 UTC Monday is outside market hours (`_is_market_hours` returns False on a 19:37 ET evening), so the overnight tier applies. ~48h+ > 30h ⇒ `stale`.
- **Predicted response:** `status: "stale"`, `as_of: "2026-05-09T..."`, `message: "Account snapshot 2d stale — last refresh did not propagate"`.
- **Confidence: HIGH.** One subtle catch: the fallback read uses `snapshot_date` (a DATE, not a TIMESTAMPTZ), so `_safe_max_ts` (lines 306-327) promotes it to UTC midnight. That means a Saturday `snapshot_date` would be reported as `2026-05-09T00:00:00+00:00` — older than the actual paper-run finish time of 02:30 UTC. The `as_of` is therefore *more pessimistic* than the actual run, which is fine for trust. Flag for record only: if `paper_run_log` is the primary path it overrides, so this edge case only fires when paper_run_log is empty.

### 2.3 Events channel

- **Source query:** `_read_events()` always returns `None` with an inline comment explaining why (lines 353-358).
- **SLA applied:** `_classify_events(None) == "unknown"` (line 167).
- **Expected response now:** `status: "unknown"`, `as_of: null`, `message: "Event source unavailable"`.
- **Confidence: HIGH for the design choice; MEDIUM for the user impact.** This is correct per the 15i audit §2.7 finding ("`/api/market/events` is the lone consistently-fresh channel — and it computes per-request, not from a stored timestamp"). The endpoint does the honest thing — it would be worse to fabricate `now()`. But this *will* drag a banner-style consumer toward perpetual "events unknown" until a `market_event_fetch_log` (or equivalent) table is added. **Not a defect — a deferred truth-debt.** 15g §2.3 saw `generated_at = 2026-05-11T23:37 UTC` from the live request handler; that signal is real but is not persisted, so `/api/freshness` cannot expose it without re-fetching, which would violate the read-only invariant.

### 2.4 Options channel

- **Source query:** `SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot` (`_read_options`, lines 361-365).
- **SLA applied:** `< 6h fresh | 6-24h degraded | > 24h stale` (lines 175-182).
- **Expected freshness now:** 15i §2.17 documents that `options_chain_snapshot.py` is "NOT yet registered in registry / cron." So no scheduler is updating the table. The most recent row likely traces to a manual / one-off backfill weeks or months ago. Expected: ~stale, possibly extreme stale (>72h). Could also be `unknown` if the table is empty in this DB.
- **Predicted response:** Either `status: "stale", message: "Options snapshot more than 24h stale"` OR `status: "unknown", message: "Options snapshot source not connected"`. Both are honest.
- **Confidence: HIGH.** The "stale vs unknown" branch is correctly bounded by data presence — there is no false-fresh path.

### 2.5 Risk channel

- **Source:** `risk_ts = port_ts` and `risk_hours = port_hours` (`_evaluate_channels`, lines 432-433). Risk derives from the portfolio source — it has no independent persisted timestamp.
- **SLA applied:** `_classify_risk` (lines 185-201): tighter intraday tier (`<= 30m fresh | <= 4h degraded | > 4h stale`), overnight tier matches portfolio.
- **Expected freshness now:** Same `as_of` as portfolio, so ~2-3 days, off-hours ⇒ `stale`.
- **Predicted response:** `status: "stale"`, `as_of` matches portfolio, `message: "Risk snapshot derived from delayed portfolio source"`.
- **Confidence: MEDIUM-HIGH.** The derivation is correct in spirit — risk *does* rebuild from portfolio fills — but it is structurally weaker than the portfolio read because it does not check whether risk-specific aggregations (VaR, drawdown, exposure breakdowns) actually completed for the same `as_of`. A failed risk-aggregation step on a successful portfolio refresh would still surface as fresh-by-portfolio. **Not a current defect; flag for 15i.B-level orchestrator-write coverage.**

### 2.6 ML channel

- **Source query:** `SELECT MAX(created_at) FROM ml_model_run` (`_read_ml`, lines 368-372).
- **SLA applied:** `< 7d fresh | 7-14d degraded | > 14d stale` (`_classify_ml`, lines 204-212).
- **Expected freshness now:** 15i §3.13 inferred last-successful nightly ML training was `2026-05-09 ~03:30 ET` (~2 days). Within 7d ⇒ `fresh`.
- **Predicted response:** `status: "fresh"`, `as_of: "2026-05-09T..."`, `message: "Model trained 2d ago"`.
- **Confidence: MEDIUM.** The query reads `ml_model_run.created_at` which is the *insert* time, not the training cadence. `nightly_ml_shadow.py` has not been live-verified in this audit to actually `INSERT` a row on every successful run (15i §8.2 noted `models/model_registry.json` is empty `[]` — at least one downstream writer is silent). If `ml_model_run` is also under-written, this channel could surface stale-as-fresh during the 7d window because its `created_at` would be from the last *successful insert*, not necessarily the last *training attempt*. **Confidence-eroding gap, not a defect; ml is informational so does not flip `overall`.**

### 2.7 Cross-channel risk summary

**False-fresh risks (most dangerous):**
- ML channel could surface `fresh` for a model that has been trained but not registered, or where `ml_model_run.INSERT` is conditional on success (and the most recent rows are old). Mitigation: ml is informational.
- Risk channel could surface `fresh` for a portfolio refresh where the risk-specific aggregation step crashed. Mitigation: not currently observable; 15i.B orchestrator should write risk as its own `pipeline_run.stage`.

**False-stale risks (least dangerous; calm-failure direction):**
- Events channel will *always* surface `unknown` because there is no persisted timestamp. The user-perception cost is that an always-fresh source reads "unavailable" — a pessimism leak, not a confidence leak. Acceptable for v1.
- Portfolio fallback to `paper_equity_snapshot.snapshot_date` rounds DOWN to UTC midnight and could read up to ~6h pessimistically. Calm-failure direction; acceptable.

**Misleading-degraded risks:**
- During market hours (9:30-16:00 ET, weekday), portfolio + risk both use the tighter `<= 30m fresh / <= 4h degraded / > 4h stale` tier. If the user opens the app at 14:00 ET on a normal trading day and the morning's pipeline ran at 03:30 ET, portfolio would show `stale` (10.5h > 4h) — which is *correct*, but the message "Account snapshot 11h stale" reads operationally jarring during what is, for the user, the middle of a normal day. The 15g SLA was calibrated for a same-day pipeline that does not exist (15i §2.3). **This is a known SLA mismatch surfaced by 15i §5 #2; not a defect in `freshness.py` but a debt the SLA itself carries.**

**Channels lacking authoritative timestamps:**
- Events: confirmed (no persisted source).
- Options: not lacking — `options_chain_snapshot.snapshot_at_utc` exists; the data layer is just unscheduled (15i §3.10).
- ML: present but possibly under-written; see §2.6.
- Risk: derived (no independent timestamp); deliberate for v1.

---

## 3. Emotional trust semantics review

**Source:** verbatim message strings from `freshness.py:220-298`. Reviewed against the 15d "calm interpretation" register (from `RiskDashboard` calm card, the "Why no buys?" panel, and the Decisions calm card — all three named in 15d §A as the product's emotional ceiling).

For each of `recommendations / portfolio / events / options / risk / ml` × `fresh / degraded / stale / unknown` (24 strings), scored on five axes.

### 3.1 Per-message scoring

| Channel | Status | Verbatim message | Calm? | Implies real-time? | Anxiety? | Reduces confidence appropriately? | Novice-friendly? |
|---|---|---|---|---|---|---|---|
| recommendations | fresh | `Signals refreshed {as_of_iso}` | partially | no | no | n/a | partially (ISO timestamp not human-readable) |
| recommendations | degraded | `Signals from yesterday's close — awaiting next refresh` | yes | no | no | yes | yes |
| recommendations | stale | `Recommendations based on last completed cycle ({as_of_iso}). Today's pipeline has not yet produced new state.` | yes | no | no | yes | partially (ISO timestamp; "pipeline" is operator vocabulary) |
| recommendations | unknown | `Recommendation source unavailable` | partially | no | no | yes | no ("source unavailable" reads system-y) |
| portfolio | fresh | `Account valued {as_of_iso}` | partially | no | no | n/a | partially (ISO timestamp) |
| portfolio | degraded | `Account snapshot delayed — last update {as_of_iso}` | yes | no | no | yes | partially (ISO timestamp) |
| portfolio | stale | `Account snapshot {age} stale — last refresh did not propagate` | yes | no | no | yes | partially ("propagate" is system vocabulary) |
| portfolio | unknown | `Portfolio source unavailable` | partially | no | no | yes | no |
| events | fresh | `Catalysts refreshed {as_of_iso}` | partially | no | no | n/a | partially |
| events | degraded | `Catalyst feed delayed — last update {age} ago` | yes | no | no | yes | yes |
| events | stale | `Catalyst feed delayed more than 24h` | yes | no | no | yes | yes |
| events | unknown | `Event source unavailable` | partially | no | no | yes | no |
| options | fresh | `Options snapshot fresh` | partially | no | no | n/a | yes |
| options | degraded | `Options snapshot delayed — last update {age} ago` | yes | no | no | yes | yes |
| options | stale | `Options snapshot more than 24h stale` | yes | no | no | yes | yes |
| options | unknown | `Options snapshot source not connected` | yes | no | no | yes | partially ("source not connected" = system vocabulary, but this is an honest description of an unscheduled job) |
| risk | fresh | `Risk snapshot fresh` | partially | no | no | n/a | yes |
| risk | degraded | `Risk snapshot derived from delayed portfolio source` | yes | no | no | yes | partially ("derived" is system vocabulary) |
| risk | stale | `Risk snapshot derived from delayed portfolio source` | yes | no | no | yes | partially (same as above; degraded and stale share this string — see §3.4 finding) |
| risk | unknown | `Risk source unavailable` | partially | no | no | yes | no |
| ml | fresh | `Model trained {days}d ago` | yes | no | no | n/a | yes |
| ml | degraded | `Model trained {days}d ago — retraining cadence elapsing` | partially | no | no | yes | no ("retraining cadence elapsing" is operator-y) |
| ml | stale | `Model retraining overdue ({days}d since last train)` | yes | no | no | yes | partially ("overdue" hints at urgency without being alarmist; OK) |
| ml | unknown | `Model lifecycle source unavailable` | partially | no | no | yes | no ("lifecycle source" = pure operator vocabulary) |

### 3.2 Best 3 messages (carry forward; canonical examples)

1. **`recommendations / degraded`**: *"Signals from yesterday's close — awaiting next refresh"* — perfectly matches the 15g §6.2 calm-language register; reads as analyst voice, not system status.
2. **`recommendations / stale`**: *"Recommendations based on last completed cycle ({as_of_iso}). Today's pipeline has not yet produced new state."* — the longest message, but the only one that explicitly gives the user a *mental model* of why staleness exists ("the pipeline runs in cycles; this one hasn't completed yet"). This is the message that turns a trust failure into a calm explanation.
3. **`portfolio / degraded`**: *"Account snapshot delayed — last update {as_of_iso}"* — clean, derived, no system vocabulary, names the surface in user terms ("Account").

### 3.3 Worst 3 messages (rewrite suggestions)

1. **`ml / unknown`**: *"Model lifecycle source unavailable"* — phrase "lifecycle source" is pure operator vocabulary. **Rewrite:** *"Model history unavailable"* (drops "lifecycle" + "source"; reads as a plain statement).
2. **`recommendations / stale`** copy on `as_of_iso`: the timestamp is the raw ISO string `2026-05-09T02:30:00+00:00` interpolated directly. To a novice this reads as machine output. **Rewrite proposal:** instead of `({as_of_iso})`, render `({weekday_name} close)` — e.g. *"Recommendations based on last completed cycle (Saturday close)."* This matches 15g §6.2 verbatim sample copy exactly. Requires a small format-helper but no schema change.
3. **`risk / stale`** + **`risk / degraded`** share the *same* message: *"Risk snapshot derived from delayed portfolio source"*. This collapses two distinct trust states into one user signal. **Rewrite split:** degraded → *"Risk numbers reflect a slightly delayed portfolio snapshot"*; stale → *"Risk numbers are based on the last completed portfolio snapshot — fresh values will appear after the next refresh."* (Mirrors 15g §6.2's explicit `/risk` sample sentence.)

### 3.4 Banned-vocabulary leak audit

**Result: NONE found.** The test `test_freshness_messages_never_use_operator_vocabulary` (`test_freshness_endpoint.py:105-113`) explicitly asserts that no message contains `"PIPELINE FAILED"`, `"ERROR"`, `"CRITICAL"`, `"SYSTEM DOWN"` (case-insensitive). Reading the message strings line-by-line, none of those phrases appear. The closest infractions are *operator-flavored adjectives* — "lifecycle", "propagate", "source", "cadence elapsing" — none of which are on the banned list but each of which is a calmness leak. Recommendation in §3.5.

### 3.5 Recommended copy adjustments (verbatim OLD → NEW)

These are the smallest possible diffs that move every message strictly closer to the 15d calm register without touching test assertions. None of them require schema or contract changes.

1. **OLD:** `"Signals refreshed {as_of_iso}"` (line 223) → **NEW:** `"Signals refreshed {human_time}"` where `human_time` is `"4m ago"` or `"at 9:30 AM ET"` per the 15g §6.2 sample. (Requires a `_human_time(ts)` helper; trivial.)
2. **OLD:** `"Account valued {as_of_iso}"` (line 238) → **NEW:** `"Account valued {human_time}"`.
3. **OLD:** `"Catalysts refreshed {as_of_iso}"` (line 252) → **NEW:** `"Catalysts refreshed {human_time}"`.
4. **OLD:** `"Recommendation source unavailable"` (line 232) → **NEW:** `"Recommendation feed not yet connected"`. (Drops "source"; "feed not yet connected" reads as a developmental state rather than a failure.)
5. **OLD:** `"Portfolio source unavailable"` (line 246) → **NEW:** `"Portfolio feed not yet connected"`.
6. **OLD:** `"Event source unavailable"` (line 260) → **NEW:** `"Event feed not yet connected"`.
7. **OLD:** `"Risk source unavailable"` (line 283) → **NEW:** `"Risk feed not yet connected"`.
8. **OLD:** `"Options snapshot source not connected"` (line 274) → **NEW:** `"Options feed not yet connected"` (parallel structure to the others).
9. **OLD:** `"Model lifecycle source unavailable"` (line 298) → **NEW:** `"Model history not yet connected"`.
10. **OLD (degraded ml):** `"Model trained {days}d ago — retraining cadence elapsing"` (lines 292-295) → **NEW:** `"Model trained {days}d ago — next retrain due"`.
11. **OLD (risk degraded == risk stale):** see §3.3 #3 split.

These are *recommendations*, not blockers — the v1 messages are all calm enough to ship. The diff list lives here as a 15i.V follow-up.

---

## 4. Migration 065 safety review

Migration file: `infra/alembic/versions/065_pipeline_run_ledger.py` (139 lines).

### 4.1 Pure additive?

**Yes.** The `upgrade()` function consists exclusively of:
- One `op.create_table("pipeline_run", ...)` with 18 columns.
- Five `op.create_index(...)` calls scoped to the new table only.

No `op.alter_column`, no `op.add_column`, no `op.drop_*`, no `op.rename_*`, no data migration. No reference to any pre-existing table.

### 4.2 Index creation lock concerns

Indexes are created via plain `op.create_index(...)` (without `postgresql_concurrently=True`). For a *new, empty* table this is **safe** — the lock is held only against the empty table itself, not any existing row source. **Flag for record only:** if the same migration pattern is reused in 15i.B against an existing populated table, `postgresql_concurrently=True` should be added to avoid blocking writers. Not relevant for this migration.

### 4.3 Nullable assumptions

Reviewing the column nullability against the ORM (`models.py:1758-1843`):
- `id BIGINT PRIMARY KEY AUTOINCREMENT` — implicit NOT NULL ✓
- `run_id UUID NOT NULL` — matches ORM `nullable=False` ✓
- `trading_date DATE NOT NULL` — matches ✓
- `stage TEXT NOT NULL` — matches ✓
- `status TEXT NOT NULL` — matches ✓
- `started_at TIMESTAMPTZ NULL` — matches (status='pending' rows have no start time)
- `finished_at TIMESTAMPTZ NULL` — matches (running rows have no finish)
- `triggered_by TEXT NULL` — matches (allows manual writes without source attribution)
- `retry_count INT NOT NULL DEFAULT 0` — matches ✓
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb` — matches ✓
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` — matches ✓

Every nullable assumption is consistent between migration and ORM. No risk of a constraint mismatch on first INSERT.

### 4.4 Downgrade reverses cleanly?

**Yes.** `downgrade()` (lines 122-139) drops the five indexes in reverse creation order, then drops the table. There is no orphan object. The migration is symmetric.

**Caveat:** If the table contains rows when `downgrade()` runs, those rows are silently destroyed. Since the ledger is append-only and contains operational history, a forced downgrade in production would lose audit data. **This is the standard alembic contract; flag for record so operators don't downgrade casually.**

### 4.5 Foreign keys

**No foreign keys are declared.** The table stands alone — `run_id` is a UUID grouped at the application layer, not a FK to any other table. This is correct for a ledger that needs to survive deletion of upstream artifacts (e.g., a `recommendation` row being purged should not orphan its ledger line).

### 4.6 Default values won't conflict with future writers

- `retry_count` default 0: orchestrator writes 0 on first attempt, increments on retry. No conflict.
- `metadata` default `'{}'::jsonb`: orchestrator writes either the explicit object or omits the column. Server default takes over on omission. No conflict.
- `created_at` default `now()`: server-side timestamp; orchestrator can omit. No conflict.

No defaults conflict with the `(trading_date, stage, run_id)` uniqueness constraint, because none of those three columns has a default — they are always caller-supplied.

### 4.7 Alembic chain integrity

Confirmed:
- `revision = "065_pipeline_run_ledger"` (line 34)
- `down_revision = "064_agent_insight_cache"` (line 35)
- `infra/alembic/versions/064_agent_insight_cache.py` exists at the expected path (verified via Glob).

**Chain is intact.** `alembic upgrade head` will land 065 cleanly after 064.

### 4.8 Compatible with existing models?

**Yes.** The ORM addition (`PipelineRun` at `models.py:1758-1842`) is a brand-new class with `__tablename__ = "pipeline_run"` — a name not used by any other model in the file. The migration creates the only table with that name. No collision with existing classes. The `metadata` column-name collision with SQLAlchemy's reserved `Base.metadata` attribute is correctly handled by the `meta` Python attribute name + `mapped_column("metadata", ...)` form (line 1808-1812).

### 4.9 Isolated DB dry-run plan

Exact commands (run from repo root, Windows PowerShell or POSIX shell — both supported):

```bash
make db-clean-test
# OR equivalently:
docker compose -f infra/compose/docker-compose.yml down -v
docker compose -f infra/compose/docker-compose.yml up -d db
docker compose -f infra/compose/docker-compose.yml run --rm api alembic upgrade head
```

**Verification queries (read-only, against the test DB):**

```sql
-- 1. Table exists with expected columns
SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_name = 'pipeline_run'
 ORDER BY ordinal_position;

-- 2. All five indexes present
SELECT indexname, indexdef
  FROM pg_indexes
 WHERE tablename = 'pipeline_run';

-- 3. Partial unique index on idempotency_key correctly scoped
SELECT pg_get_indexdef(c.oid)
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relname = 'uq_pipeline_run_idempotency';
-- Expected: ... WHERE (idempotency_key IS NOT NULL)

-- 4. Empty table
SELECT count(*) FROM pipeline_run;
-- Expected: 0
```

### 4.10 Production deploy plan

```bash
# Lock + downtime expectations: minimal.
# CREATE TABLE on a fresh table = AccessExclusiveLock on the new
# table only (which no one is using yet). No existing table is touched.
# Index creation on an empty table is microsecond-scale.
# Total expected wall-clock: <1 second.

docker compose -f infra/compose/docker-compose.yml exec api \
    alembic upgrade head
```

**Pre-flight check** (recommended): `alembic current` should print `064_agent_insight_cache (head)` before upgrade.

**Post-flight check**: `alembic current` should print `065_pipeline_run_ledger (head)`.

### 4.11 Rollback plan

```bash
docker compose -f infra/compose/docker-compose.yml exec api \
    alembic downgrade 064_agent_insight_cache
```

**Risk if rows exist:** Once 15i.B starts writing rows, a downgrade silently destroys all `pipeline_run` rows (per §4.4 caveat). No FK cascade, no warning. **Recommended discipline:** before any downgrade after 15i.B ships, run `SELECT count(*) FROM pipeline_run` and back up the table with `pg_dump -t pipeline_run` if rowcount > 0.

For *this audit's window* — between 15i.A landing and 15i.B starting to write — rollback is risk-free because the table is provably empty (no writer code exists).

---

## 5. Health script reliability findings

Script: `scripts/check_daily_pipeline_health.py` (233 lines).

### 5.1 Exit code matrix (mapped against empirical evidence)

| Code | Name | Trigger | Empirical state |
|---|---|---|---|
| 0 | OK | `overall == "fresh"` | Cannot test until `/api/freshness` is live |
| 1 | DEGRADED | `overall == "degraded"` OR `overall == "unknown"` (line 135) | Cannot test until live |
| 2 | STALE | `overall == "stale"` | Cannot test until live |
| 3 | UNREACHABLE | URLError/HTTPError/TimeoutError on the GET (lines 74-79) | **Confirmed three ways:** (a) vs `localhost:5173` (Vite proxy → 404 from Docker API): EXIT=3; (b) vs `localhost:8000` (API container, 404): EXIT=3; (c) vs `localhost:9999` (no listener, ConnectionRefused): EXIT=3 |
| 4 | MALFORMED | JSONDecodeError, non-dict JSON, missing top-level key, missing channel (lines 83-104) | Cannot test without a controlled mock returning bad JSON |

**Subtle correctness finding:** the script treats a 404 HTTP response as `URLError` via `urllib.error.HTTPError` (which inherits from URLError). That maps 404 → EXIT_UNREACHABLE rather than EXIT_MALFORMED. **This is the right call** — a 404 means the route isn't there, not that it returned garbage; "unreachable" is the honest description. Confirmed empirically (the 404 currently being returned is correctly classified as UNREACHABLE).

**Subtle gap:** there is no distinction between "API down entirely" (ConnectionRefused) and "API up but route missing" (404). Both surface as UNREACHABLE. For a deploy-validation use case (which is the *current* situation: "did the rebuild include the new route?"), this is acceptable; for a long-term ops use case, splitting these would help triage faster. **Not a v1 defect.**

### 5.2 Output clarity

Three modes:

**Default (table)** (lines 139-157): aligned table with `[OK]/[WARN]/[STALE]/[?]` tags + per-channel age + ISO `last` timestamp + footer summary. Reads cleanly. Aligned column widths via `ljust`. No color codes (smart — works in any terminal). The `[?]    ` tag (with trailing spaces) keeps column alignment consistent across all four status values. Verdict: **clear in panic-free moments.**

**`--json`** (line 222): pretty-prints the full response. Useful for piping into `jq` or other tools. Verdict: **clear.**

**`--quiet`** (line 224 + `_print_summary_line` lines 159-164): single-line `trading_date=... overall=... exit=...`. Verdict: **clear.**

In real ops moments (i.e., when something is actually broken), the unreachable / malformed paths print to stderr (lines 195, 197, 201, 203, 210, 213) with the underlying error string included. An operator can grep stderr for the failure class and quickly identify whether to investigate the API process or the JSON contract. Verdict: **operationally useful.**

### 5.3 Operational usefulness — would an SRE call this "actionable"?

**Yes, with one caveat.** The script gives:
- A binary exit code mappable to PagerDuty severities.
- A per-channel breakdown so the SRE knows *which* channel is the cause.
- ISO `last` timestamps so the SRE can correlate against logs.
- Stderr-on-error so it composes cleanly with cron mail.

**Caveat:** the script does not include the API base URL in its output. An SRE running it across multiple environments (dev/staging/prod) would need `--quiet` plus environment-tagging to disambiguate. Not a defect; flag for record.

### 5.4 No misleading success — confirmed

The only path to EXIT=0 is `_exit_code_from_overall("fresh")` → `EXIT_OK = 0` (line 129). That requires:
1. HTTP 200 response from `/api/freshness`.
2. Response is valid JSON object.
3. Top-level `overall` field is the literal string `"fresh"`.
4. Validation of all required keys passes (`_validate`, lines 91-104).

There is no fall-through to EXIT_OK on any other code path. An "unknown" or empty `overall` returns EXIT_DEGRADED (line 135) or EXIT_MALFORMED (line 136 — when `overall` is not in the expected vocabulary). **No false-success path.**

### 5.5 No panic language anywhere

Reviewing all printed strings:
- `[OK]   `, `[WARN] `, `[STALE]`, `[?]    ` — all calm tags
- `[UNREACHABLE] {body}` — descriptive, not alarmist
- `[MALFORMED] {body}` — descriptive
- `trading_date=... overall=... exit=...` — neutral

No "FAILED", "PANIC", "CRITICAL", "ALERT" language. The `[STALE]` tag is the strongest term and it is the correct calm equivalent of what would otherwise be `[FAIL]` in a less-disciplined ops tool. **Banned-vocabulary check: clean.**

### 5.6 Edge cases

- **`--json` + unreachable**: empirically verified — EXIT=3, error message goes to stderr (not the JSON output stream), so a downstream `jq` pipeline does not receive corrupted input. ✓
- **`--quiet` + stale**: cannot verify without a live endpoint; code path (lines 222-227) correctly bypasses `_print_human` and calls `_print_summary_line` instead. **Logic is correct by inspection.**
- **HTTP 200 with malformed body**: cannot verify without a controlled mock. Code path (lines 199-216) correctly captures the error string and returns EXIT_MALFORMED. **Logic is correct by inspection.**
- **Network timeout vs connection refused**: both treated as UNREACHABLE per the `URLError`/`TimeoutError`/general-`Exception` blanket (lines 74-79). Different `body` strings (`"transport error: ..."` vs `"timeout: ..."`) so an operator can still distinguish in the stderr log. ✓

### 5.7 Recommendation

**No defects requiring a fix before this becomes the canonical operational truth check.** The script is operationally tight, correctly defensive, and reads as a v1 SRE tool. Two *enhancements* to consider in a future commit (NOT blockers):

1. Include the resolved URL in the stderr error message so a multi-environment cron job is self-disambiguating: `[UNREACHABLE] http://localhost:8000/api/freshness — transport error: ...`.
2. Add a `--source-of-truth` flag that, on stale, queries the underlying tables directly (bypasses `/api/freshness`). Lets an operator distinguish "endpoint says stale because data is stale" from "endpoint is itself broken and reporting stale incorrectly." Defer until trust in the endpoint is established.

---

## 6. Remaining trust gaps (cross-cutting)

Synthesizing 15g + 15h + 15i + 15i.V findings. Focused on TRUST-SYSTEM gaps that the new infrastructure does NOT close.

1. **UI implies "live" in surfaces 15h has not yet rewired.** 15g §7 ranked ten gaps; 15h's first round (15h.1 through 15h.5 in 15g §8) addressed `pick.stale_data` derivation client-side and `as of` rendering on PortfolioSnapshot/TopStrip — but NOT the Today's-read hero composition (15g §7 #7), the Options surface (15g §7 #5), or the dashboard/paper as_of disagreement (15g §7 #6). Those surfaces still read as "today" while pulling Friday data.
2. **Events freshness has no persisted source.** `freshness.py:353-358` correctly returns `unknown` for events. But the live `/api/market/events` endpoint *is* fresh; `/api/freshness` cannot expose that without a `market_event_fetch_log` table or equivalent. Until then, any consumer that displays "events: unknown" alongside "events: fresh per request" creates a contradiction.
3. **Options has no scheduled writer.** `options_chain_snapshot.snapshot_at_utc` exists in schema (so `freshness.py` can query it), but the writer is unscheduled (15i §3.10). Every options surface will surface stale-or-unknown until the writer is scheduled. **Single largest data-layer truth gap.**
4. **Recommendations remain "overconfident" via `pick.stale_data=false`** — 15h.1 supposedly fixes this client-side via a derived `isPickFresh()`. But that derivation does not touch the backend `pick.stale_data` field, so any *new* consumer reading `pick.stale_data` raw inherits the lie. The truth-layer fix would be backend-side: replace `pick.stale_data` derivation in `apps/api/src/api/recommendations.py` with a function that consults `recommendation.generated_at` against the same SLA. Not in scope for 15i; deferred.
5. **Stale data still visually too strong on Today's-read hero.** 15d §G #1 named the hero promotion as the highest-leverage emotional-ROI move. On a stale day, a confidently-composed copilot sentence ("Cautious posture · 5 trims driven by ...") reads worse than no sentence at all. The Phase 15h.3 rewrite for "stale → cautious tone" is necessary but not yet shipped.
6. **Missing as-of surfaces on Options pages, Risk page, Decisions page.** 15g §6.3 enumerated each surface that needs an `as of` line; only PortfolioSnapshot + TopStrip got one in 15h. The other three surfaces still have none. `/api/freshness` provides the data — frontend integration deferred.
7. **Contradictory timestamps (`paper/state` vs `paper/summary` engine disagreement)**. Documented 15g §7 #4. Not addressed by `/api/freshness` because both endpoints are pre-existing consumers; the freshness endpoint reads `paper_run_log`, which is the canonical write-time. The disagreement is at a different abstraction layer (live decision row vs daily snapshot) and `/api/freshness` cannot resolve it.
8. **Unknown-state UX gaps.** If `/api/freshness` returns `overall: "unknown"` (which it could, per the all-unknown test path in `test_freshness_endpoint.py:159-171`), the UI has no defined rendering for this state. The 15g §6.2 message table covers fresh/degraded/stale; it does not cover unknown. This is the *single most likely-to-occur* state in early production deploys (the API is up but the migration hasn't run, OR the migration has run but no orchestrator writes rows yet). **Frontend-side UX-design gap.**
9. **Frontend integration NOT yet done.** 15h derives client-side; once `/api/freshness` deploys, the 15h surfaces should consume it as the single source of truth (rather than per-surface inference). Until that swap happens, the new endpoint exists but the UI does not benefit. **Net effect:** the truth infrastructure is invisible to users.
10. **Health script not yet wired into anything.** `scripts/check_daily_pipeline_health.py` is a beautifully-correct script that no scheduler currently invokes. 15i §11 #6 already ranked "no alerting destination wired" as a top-10 risk — the new script does not change that.

### Top 5 by trust-impact

1. **Stale data still visually too strong on Today's-read hero (Phase 15h.3 not shipped).** Highest user-facing trust-failure surface; the elite-product perception ceiling cannot move higher until this is addressed.
2. **Recommendations `pick.stale_data` lies at the API layer.** Even if 15h.1 fixes client rendering, the next consumer of the field will inherit the lie. Backend fix needed.
3. **Frontend not yet pointed at `/api/freshness`.** All the new infrastructure is invisible to users until 15h surfaces consume it.
4. **Options has no scheduled writer.** Single largest data-layer freshness gap; `/api/freshness` will perpetually surface options as `stale` or `unknown` until scheduled.
5. **Unknown-state UX undefined.** Most likely state in early production; no design exists.

---

## 7. Readiness for 15i.B (orchestrator)

Verbatim answers to the seven user questions.

### 7.1 Is `/api/freshness` stable enough?

**Conditional yes.** The code is stable, defensive, and read-only. The endpoint will not crash on any realistic database state — every per-channel reader is wrapped in a `_safe_max_ts` that swallows exceptions and returns None. The all-unknown test path (`test_freshness_endpoint.py:69-103`) explicitly verifies graceful degradation. **However:** the endpoint is *not currently live in production* (the API container needs a rebuild — see §1). Stability is provable from code; deployability is unverified until the rebuild. **Recommendation: deploy the rebuild + run migration 065 + observe one full cycle of real traffic before declaring stable.**

### 7.2 Is `pipeline_run` schema sufficient for orchestrator writes?

**Yes, with one structural ambiguity to resolve before first write.** The 18-column schema covers status, timing, retry, errors, watermarks, and metadata adequately for the 12-step pipeline (15i §6.1). Every column the orchestrator needs is present. **Ambiguity:** `idempotency_key` is nullable with a partial unique index — the contract for "what is the canonical key for stage X on date Y" is not declared anywhere. The 15i audit §4.5 proposed `stage || trading_date` by default, but the migration does not enforce a default. Recommendation: a docstring on `PipelineRun` (or a sidecar `apps/api/src/domain/ops/pipeline_run_keys.py`) declaring the canonical key format before any orchestrator code writes.

### 7.3 Which stages should write ledger rows first?

**Recommendation: start with `paper_trading` as 15i.B.1.** Reasons:
- `paper_run_log` already exists with strong UNIQUE(run_date) + idempotent upsert (15i §4.2). Adding a parallel `pipeline_run` row is purely informative — there is no risk of corrupting the paper subsystem if the ledger write fails.
- `scripts/run_paper_daily.py` is invoked from exactly one place (the cron umbrella, via `run_daily_loop.sh:162-167`). One call site = one ledger-write integration point.
- Paper trading is the most user-visible pipeline stage (trades show up in the UI); a working ledger row for paper makes the "did paper trading run today" question instantly answerable from `pipeline_run`.
- The blast radius of getting the ledger write wrong is bounded — a failed `pipeline_run` INSERT does not affect actual paper-trading state because `paper_run_log` is the canonical data store.

**Alternative (lower-risk variant):** start with `ml_shadow_train` — it runs once a night, has no UI consumers, and a failed ledger write would be invisible. But this is so low-risk that it would not exercise the orchestrator integration meaningfully. Paper is the right balance.

### 7.4 Highest-risk scheduler overlaps

The two parallel schedulers (15i §1) overlap in three observable windows:

1. **22:00 ET tickloop `ingest_prices_daily` vs. 03:30 ET cron umbrella stage 0 `run_engine_pipeline.py`** (next morning). The cron umbrella *assumes* ingest already ran; if the tickloop missed (container down, network), the cron's engine pipeline runs on yesterday's bars and produces stale recommendations. Both schedulers think they succeeded; no joined ledger surfaces the gap.

2. **23:30 ET tickloop `run_paper_trading` vs. 03:30 ET cron `scripts/run_paper_daily.py`** (next morning). Both write to `paper_run_log` for the same `run_date`. The 24-hour window hides the race in practice (15i §2.13), but the codepaths are different (`apps/worker/src/jobs/run_paper_trading.py` vs `scripts/run_paper_daily.py`) and could write contradictory rows under unusual timing.

3. **`/tmp/last_daily_loop_success` marker (cron) vs. `daily_run_status` row (orchestrator)** — the same daily intent is recorded in two completely separate locations. The orchestrator does not write the marker; the cron does not write `daily_run_status`. An operator reading either source alone gets a partial truth.

**Highest-risk of the three: #1**, because it can cause silent staleness on otherwise-successful days. The other two are mostly observability gaps, not correctness gaps.

### 7.5 Cadence assumptions still unclear

Per 15i §2.3, the "16:30 ET" cadence cited in 15g was folklore. Other still-unclear cadences:

- **`v2_promotion_snapshot`** runs Mon 00:15 ET (cron: `15 0 * * 1`). What does it depend on? 15i didn't trace.
- **Options chain snapshot ingestion** — entirely unscheduled (15i §2.17). What is the *intended* cadence?
- **Holiday calendar awareness** — `_is_trading_day` is weekday-only with explicit acknowledgement (15i §2.14). On July 4 the system runs but produces "no fresh bar." Is that the desired UX?
- **Market open/close TZ DST handling** — `_is_market_hours` in `freshness.py:106-117` uses zoneinfo with America/New_York. Does the cron container's `TZ=America/New_York` survive DST transitions correctly?
- **What is the expected latency from market close (16:00 ET) to recommendations being available?** 15g implied "by 16:30 ET"; 15i showed "by 03:30 ET next morning." The product UX should declare an explicit SLA on this so users know what to expect.

### 7.6 Should orchestrator work even happen before frontend freshness integration?

**Take a position: YES, orchestrator first.**

**Argument for:** Frontend pointing at `/api/freshness` today shows the SAME data the client-side derivation already shows (15h.1's `isPickFresh()` is computed from `pick.generated_at`, which is the same data `freshness.py` reads via `MAX(generated_at) FROM recommendation`). No UX gain. Meanwhile, deferring frontend integration until after 15i.B writes ledger rows lets `last_run_id` populate (currently always `null` in the response — see `freshness.py:386`). When the frontend eventually consumes it, the field will be useful. Shipping frontend integration now would freeze the contract before `last_run_id` is real.

**Counter-argument considered and rejected:** "Frontend integration is low-risk and immediately visible — it shows the user that something landed." This is true but misses that the *current* UX consequence is misleading: a user looking at "events: unknown" alongside the live events feed creates a worse trust impression than no integration at all. Until 15i.B writes `events_fetch_log` (or equivalent), the frontend should keep deriving locally.

**Position: orchestrator (15i.B) first; frontend integration (15h.6+) after `last_run_id` populates.**

### 7.7 Safest first write-path

**Pick: `paper_trading` stage written from `scripts/run_paper_daily.py`.**

Justification (consolidated from §7.3):
- Single call site.
- Existing strong idempotency in `paper_run_log` provides a backup truth source if ledger write fails.
- High UI visibility for the result, so a working ledger row is observably valuable.
- Failure mode is bounded: the only risk is "ledger row missing" (operationally invisible) or "ledger row wrong" (informational, not corrupting).

**Implementation sketch (PROPOSAL only, NOT in scope for 15i.V):**
```
# At the start of run_paper_daily main():
run_id = uuid.uuid4()
pipeline_run.insert(
    run_id=run_id,
    trading_date=run_date,
    stage="paper_trading",
    status="running",
    started_at=now_utc,
    triggered_by="cron",
    idempotency_key=f"paper_trading|{run_date.isoformat()}",
)

# At the end (success):
pipeline_run.update(...).where(run_id=run_id).values(
    status="success",
    finished_at=now_utc,
    duration_ms=elapsed_ms,
    rows_written=trades_opened + trades_closed,
    output_watermark=now_utc,
)

# At the end (failure path):
pipeline_run.update(...).where(run_id=run_id).values(
    status="failed",
    finished_at=now_utc,
    error_class=type(e).__name__,
    error_message=str(e)[:1000],
)
```

The unique index on `idempotency_key` (`uq_pipeline_run_idempotency`) prevents accidental duplicate rows on retry; the orchestrator should catch the `IntegrityError` and read the existing row instead.

---

## 8. Recommended next move after validation

**Six options were considered.** Verdict below.

The options:
- **A.** Rebuild API container so `/api/freshness` is live, then re-run validation against live endpoint.
- **B.** Apply migration 065 to dev DB via `make db-clean-test`, verify schema lands cleanly, then deploy.
- **C.** Run pytest on Haiku for `test_freshness_endpoint.py` + freshness.py runtime correctness.
- **D.** Fix any defects surfaced in this audit BEFORE deploying anything.
- **E.** Frontend integration: point 15h surfaces at `/api/freshness` (low-risk, immediately visible).
- **F.** 15i.B orchestrator: write ledger rows from one safe stage first.

**Pick: A (Rebuild API container so `/api/freshness` is live, then re-run validation against live endpoint).**

**Rationale:** Every other option is blocked by the same gap. Migration 065 is safe (§4) but until the API container that hosts the freshness reader is rebuilt, the truth-infrastructure loop has no exit. Pytest verifies code correctness (which is already AST-verified) but does not verify runtime against the actual SessionLocal binding. Defect fixes (option D) are appealing but no defect found in this audit is *blocking* — every recommended copy adjustment in §3.5 is a v1.1 polish item, not a v1.0 ship-blocker. Frontend integration (option E) is the wrong sequencing per §7.6. Orchestrator work (option F) needs the freshness endpoint live so the per-stage write paths can be observed end-to-end.

**A is the smallest move that unblocks everything else.** Single command (`docker compose -f infra/compose/docker-compose.yml build api && docker compose -f infra/compose/docker-compose.yml up -d api`), then re-run the empirical evidence gathering (curl /api/freshness, run check_daily_pipeline_health.py with default base URL) and confirm EXIT=0/1/2 paths now resolve. Migration 065 should be applied as part of the same window since the endpoint is harmless without rows but the rebuild is the trigger event for end-to-end observability. With both done, this audit is rerunnable against live data, the ml/options/risk channel predictions in §2 become testable, and 15i.B can start with `paper_trading` per §7.7.

---

*Validation conducted 2026-05-11 from code inspection + the empirical evidence captured immediately prior to this synthesis. No code, schema, container, or migration changes performed during this audit. The freshness endpoint, the migration, the ORM class, the tests, and the health script were each read in full and cross-checked against the 15i operational audit and the 15g UI freshness audit. No live re-probes; the 404 reality of `/api/freshness` and the EXIT=3 reality of the health script were both noted from evidence gathered before this session began.*
