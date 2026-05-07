# Agent Insights — Operations Runbook

**Status:** dormant by default. Production deployments must remain
disabled until an operator follows the manual enablement procedure
below.

**Last updated:** Phase F5 (2026-05-07). Layer phases F1 → F5 are
all merged on `phase-1/ledger`.

---

## 1. What this layer does

The agent-insights layer wraps the existing read-only diagnostic
endpoints (`/performance/paper/trade-quality`,
`/performance/paper/risk-dashboard`,
`/performance/paper/exit-analytics`,
`/options/evaluation/scores`) with a single Anthropic Messages-API
call that returns a plain-markdown research narrative. The
narrative is rendered in the F3 *Insight Drawer* on Alpha Lab and
the Risk Dashboard, behind a click-only **Explain / Review exits /
Narrative** button.

Phases:

| Phase | Commit  | Scope                                          |
|-------|---------|------------------------------------------------|
| F1    | 2039e79 | Deterministic prompt scaffolding, no LLM       |
| F2    | 1885553 | Anthropic adapter behind hard-off feature flag |
| F3    | 3509763 | Read-only frontend drawer + lazy fetch         |
| F4    | c645b46 | `agent_insight` cache + safety-validated writes|
| F5    | (this)  | Hardening: status endpoint, admin DELETE, docs |

## 2. What this layer does **NOT** do

- Does not place trades.
- Does not modify any execution path, next-bar guard, replay
  recovery manifest, paper-trade table, options-trade table,
  decision log, recommendation table, or any threshold.
- Does not run on a schedule. There is no cron, no background job,
  no auto-fetch on page load. Every request is triggered by an
  operator click.
- Does not affect scoring, signals, exits, or recommendations. The
  drawer is informational only; the rest of the system never reads
  the cache.
- Does not store raw UUIDs, raw API keys, or unsafe LLM responses.
- Does not bundle FinRobot, AutoGen, or LangChain. The adapter is
  a thin direct-SDK wrapper.

## 3. Environment variables

All defaults are safe-off. The layer remains dormant unless every
flag below is explicitly set.

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_INSIGHTS_ENABLED` | `false` | Master gate. Endpoint returns 503 until true. |
| `ANTHROPIC_API_KEY` | `""` | Required *in addition* to the master gate. Empty key keeps the layer disabled even if the flag is true. |
| `AGENT_INSIGHTS_MODEL` | `claude-3-5-haiku-latest` | Anthropic model identifier. |
| `AGENT_INSIGHTS_MAX_TOKENS` | `800` | Hard cap per response. |
| `AGENT_INSIGHTS_TIMEOUT_SECONDS` | `5.0` | Per-call timeout. |
| `AGENT_INSIGHTS_COST_GUARD_USD` | `5.0` | Soft per-process ceiling (surfaced in dashboards; F3 phase does not enforce). |
| `AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED` | `false` | Mounts `DELETE /api/insights/cache`. Requires `RESEARCH_ADMIN_TOKEN` non-empty. |
| `RESEARCH_ADMIN_TOKEN` | `""` | Reused as the `X-Admin-Token` header for the optional cache DELETE. |

## 4. How to enable manually (local / staging only)

**Production should remain disabled** until you have explicit
sign-off. The same procedure works locally for evaluation.

1. Set env vars in your deployment shell (or `.env`):

   ```bash
   export AGENT_INSIGHTS_ENABLED=true
   export ANTHROPIC_API_KEY=sk-ant-...    # real key
   export AGENT_INSIGHTS_MODEL=claude-3-5-haiku-latest
   export AGENT_INSIGHTS_MAX_TOKENS=800
   export AGENT_INSIGHTS_TIMEOUT_SECONDS=5
   ```

2. Restart the API:

   ```bash
   docker compose restart api
   # or, for a local dev process:
   python -m apps.api.src.main
   ```

3. Apply the cache migration if not already applied:

   ```bash
   alembic -c infra/alembic/alembic.ini upgrade head
   ```

4. Hit the status endpoint and confirm `enabled: true`:

   ```bash
   curl http://localhost:8000/api/insights/status
   ```

5. Open Alpha Lab → Trade Quality table → click **Explain** on
   any row. The drawer should open, show the AI banner, and
   render the response. The first click is `cache: "miss"`; an
   identical second click on the same row is `cache: "hit"`.

## 5. How to disable immediately

```bash
export AGENT_INSIGHTS_ENABLED=false
docker compose restart api
```

The endpoint reverts to HTTP 503
`{"error": "agent insights disabled", "cache": "disabled"}`. The
SDK is never touched while the flag is off; there is no draining
or in-flight request to manage.

The `agent_insight` table retains its rows (cache survives the
disablement). Re-enabling later resumes hits on identical
payloads. To wipe explicitly, see §8.

## 6. How to verify disabled mode

```bash
curl -s http://localhost:8000/api/insights/status | jq
# Expect: {"enabled": false, "llm_configured": ..., "cache_rows": N, ...}

curl -i http://localhost:8000/api/insights/trade_quality
# Expect: HTTP/1.1 503  body: {"error":"agent insights disabled","cache":"disabled"}
```

Frontend: open the drawer → it shows
*"Agent insights are disabled. Enable AGENT_INSIGHTS_ENABLED only
when ready."*

## 7. How to verify enabled mode with one safe manual insight

After enabling per §4:

```bash
# 1. confirm enabled
curl -s http://localhost:8000/api/insights/status | jq .enabled
# true

# 2. fire a fixture-payload request (no body required)
curl -s http://localhost:8000/api/insights/trade_quality | jq .cache
# "miss"

# 3. fire the same request again
curl -s http://localhost:8000/api/insights/trade_quality | jq .cache
# "hit"
```

Frontend smoke:

1. Set `AGENT_INSIGHTS_ENABLED=true` and a test API key.
2. Restart API and frontend (`cd apps/web && npm run dev`).
3. Navigate to **Alpha Lab → Trade Quality**.
4. Click **Explain** on any row. Drawer opens. Banner visible.
   Chip reads *"new insight"*.
5. Close drawer. Click **Explain** on the **same row** again.
   Chip reads *"cached insight"*.
6. Set `AGENT_INSIGHTS_ENABLED=false`. Restart. Click **Explain**.
   Drawer shows the disabled message.
7. Verify execution tables untouched:

   ```sql
   SELECT count(*) FROM paper_trade;
   SELECT count(*) FROM paper_position;
   SELECT count(*) FROM paper_equity_snapshot;
   -- These counts should be identical before and after the smoke
   -- test. Only `agent_insight` should change.
   ```

## 8. How to inspect / clear the cache

### Inspect

```sql
-- Rows present
SELECT count(*) FROM agent_insight;

-- Latest 10 entries
SELECT created_at, kind, model, safety_version, payload_hash
FROM agent_insight
ORDER BY created_at DESC
LIMIT 10;

-- Verify banner integrity (every row MUST match exactly)
SELECT count(*) FROM agent_insight
WHERE banner <> 'AI research insight — not execution logic.';
-- Expected: 0
```

The CHECK constraint
`ck_agent_insight_banner` enforces banner integrity at the DB
tier; this query is a sanity check.

### Clear via SQL (safe, always available)

```sql
DELETE FROM agent_insight;
```

This affects only the cache table. It has no foreign keys and no
cascade relationships.

### Clear via admin endpoint (optional, gated)

Requires both:

- `AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED=true`
- `RESEARCH_ADMIN_TOKEN=<non-empty token>`

When mounted:

```bash
curl -X DELETE \
     -H "X-Admin-Token: $RESEARCH_ADMIN_TOKEN" \
     http://localhost:8000/api/insights/cache
# {"deleted_rows": N, "table": "agent_insight"}
```

Without the flag, the route returns 404. With a wrong token, it
returns 403.

## 9. Rollback procedure

| Symptom | Action |
|---------|--------|
| Drawer rendering wrong content | `AGENT_INSIGHTS_ENABLED=false`, restart. The drawer immediately shows the disabled state. |
| Unsafe responses leaking | Endpoint already returns 502; double-check `test_unsafe_response_returns_502_and_caches_nothing` is green in the latest CI run. Disable flag if confidence is shaken. |
| Cost spike | `AGENT_INSIGHTS_ENABLED=false`. Investigate. Re-enable only after `AGENT_INSIGHTS_MAX_TOKENS` / model is reduced. |
| Cache poisoning suspected | Run `DELETE FROM agent_insight;`. Re-enable only after auditing the hash of the suspicious payload + `safety_version`. |
| Need to revert the entire layer | Set `AGENT_INSIGHTS_ENABLED=false` (zero behavior change versus pre-F1 system). For physical rollback, `alembic -c infra/alembic/alembic.ini downgrade 063_opt_strat_outcome` removes `agent_insight`. The frontend drawer remains shipped but unused — no execution side effects. |

## 10. Safety guarantees

These are enforced by code + tests; do not loosen without re-running
the F1–F5 test suites.

1. **Default off.** `AGENT_INSIGHTS_ENABLED=false`. Endpoint returns
   503 with no SDK call and no DB read. Verified by
   `test_disabled_returns_503_and_writes_no_rows`.
2. **No execution coupling.** Source-level scans
   (`test_insights_module_has_no_forbidden_tokens`,
   `test_llm_client_module_has_no_forbidden_tokens`) reject any
   import or string referencing `paper_trading.*`,
   `submit_trade`, `_build_legs_payload`,
   `replay_recovery_manifest`, `BackgroundTasks`, etc.
3. **No DB writes outside `agent_insight`.**
   `test_no_writes_to_execution_tables` snapshots and re-counts
   sample execution tables across a successful insight call.
4. **Banner enforced at DB tier.** CHECK constraint
   `ck_agent_insight_banner` rejects any row whose banner is not
   the canonical disclaimer.
5. **No raw UUIDs in cache.** `validate_cacheable` rejects writes
   whose `payload_redacted` carries an 8-4-4-4-12 hex string;
   `test_cache_row_contains_only_redacted_payload` asserts the
   stored row does not echo the raw input UUID.
6. **No agent framework deps.**
   `pyproject.toml` does not pull `pyautogen`, `langchain`, or
   FinRobot. Source scans block matching imports.
7. **No auto-fetch.** `useInsight` hook has zero `useEffect`;
   every `fetchInsight()` call is wrapped in a button click
   handler. F3 spec compliance grep-confirmed.
8. **No localStorage / sessionStorage** in F3 frontend code.
9. **API key never echoed.** `/api/insights/status` parametrized
   test asserts the secret value is absent from the response body.
10. **GET-only on the public router.** `test_insights_router_only_declares_get`.
    The optional admin DELETE lives on a separate `admin_router`
    that is not mounted unless both gates are set.

## 11. No-go conditions (do not enable if any are true)

- `agent_insight` migration has not been applied
  (`alembic current` does not show `064_agent_insight_cache`).
- `ANTHROPIC_API_KEY` is not provisioned in a real secret store —
  refuse to use a developer key in production.
- The release does not have F1 → F5 tests green in CI.
- Operator cannot reach the rollback shell on ≤ 60s notice.
- Application is mid-migration of next-bar guard, replay manifest,
  or any execution path. Pause enablement until the underlying
  change has shipped.
- Cost monitoring (`AGENT_INSIGHTS_COST_GUARD_USD` dashboard) is
  not visible to the on-call rotation.

## 12. Monitoring / observability

`GET /api/insights/status` now returns a `metrics` block produced
by the in-process counters added in Phase F7. Sample disabled-
state response:

```json
{
  "enabled": false,
  "model": "claude-3-5-haiku-latest",
  "cache_enabled": true,
  "cache_rows": 0,
  "banner": "AI research insight — not execution logic.",
  "execution_linked": false,
  "llm_configured": false,
  "metrics": {
    "requests_total": 0,
    "disabled_total": 0,
    "cache_hit_total": 0,
    "cache_miss_total": 0,
    "llm_calls_total": 0,
    "safety_rejected_total": 0,
    "transport_error_total": 0,
    "estimated_cost_usd_total": 0.0,
    "last_call_at": null,
    "last_error_reason": null
  }
}
```

### What the counters mean

| Field | Increments when |
|-------|----------------|
| `requests_total` | Any reach of `GET /api/insights/{kind}`, regardless of outcome. |
| `disabled_total` | Endpoint short-circuited because `AGENT_INSIGHTS_ENABLED=false` or the API key was empty. |
| `cache_hit_total` | A row matched in `agent_insight`; SDK was NOT invoked. |
| `cache_miss_total` | No row matched; the LLM path was attempted. Increments before the SDK call so failures still count as misses. |
| `llm_calls_total` | A successful Messages-API call returned a non-empty body. Validation might still reject the body afterwards — see `safety_rejected_total`. |
| `safety_rejected_total` | Post-call gate (forbidden phrase, hallucinated number, code fence) refused the body. NOT incremented for transport failures. |
| `transport_error_total` | SDK timeout, connection failure, or empty body. NOT incremented for safety rejections. |
| `cost_guard_blocked_total` | F8 cost-guard gate refused the LLM call before any SDK invocation. Cache hits never increment this counter. |
| `estimated_cost_usd_total` | Sum of per-call cost estimates. Provider `usage` (input/output token counts) is preferred; falls back to char/4 token approximation. |
| `cost_guard_usd` | Effective ceiling read from `AGENT_INSIGHTS_COST_GUARD_USD`. Values `<= 0` mean "unlimited" — guard is disabled. |
| `cost_guard_reached` | Computed: `cost_guard_usd > 0 AND estimated_cost_usd_total >= cost_guard_usd`. |
| `last_call_at` | UTC ISO-8601 timestamp of the most recent successful LLM call. |
| `last_error_reason` | Bounded string (`safety:…`, `transport:…`, or `guard:cost_blocked:…`) describing the most recent failure. |

### Interpretation guidance

* **High `cache_hit_total / requests_total` ratio** → working as
  intended; identical payloads are short-circuiting the LLM.
* **Rising `safety_rejected_total`** → investigate model output.
  If a single rejection reason recurs, consider adjusting the
  narrator prompt or the per-kind allowed-constants list rather
  than disabling the gate.
* **Rising `transport_error_total`** → SDK / network issue. The
  feature flag does NOT need to be disabled; the endpoint already
  returns 502 on these and never caches a partial response.
* **`estimated_cost_usd_total` is an estimate.** It is not billing
  truth. Use it as a leading indicator before reconciling with
  Anthropic's invoice. The `AGENT_INSIGHTS_COST_GUARD_USD`
  setting surfaces the soft ceiling alongside this counter on
  operator dashboards but does not enforce it in F7.

### Cost guard (F8)

Phase F8 enforces `AGENT_INSIGHTS_COST_GUARD_USD` at request time.

Behavior:

* Order of operations: payload → scrub → hash → **cache lookup
  first** → if miss, **then** check guard → if reached, return
  HTTP 429 without invoking the SDK or writing the cache.
* **Cache hits are NEVER blocked by the guard.** A hit costs no
  additional spend, so the operator continues to see narratives
  that are already paid for even after the guard is reached.
* Disabled flag (`AGENT_INSIGHTS_ENABLED=false`) short-circuits
  before guard evaluation. A disabled deployment NEVER touches
  the guard, the SDK, or the cache.
* Unsafe responses (502) and transport errors are unchanged —
  they reach the SDK and ARE counted toward `estimated_cost_usd_total`
  if the SDK returned a body, since the operator was billed for
  those tokens regardless of validation outcome.
* Guard `<= 0` is treated as **unlimited** — `cost_guard_reached`
  always reports False in that mode.

Sample 429 response body when guard is reached on a cache miss:

```json
{
  "error": "agent insights cost guard reached",
  "cache": "disabled",
  "estimated_cost_usd_total": 0.052100,
  "cost_guard_usd": 0.05
}
```

The operator sees the running spend AND the configured ceiling so
they can decide whether to raise the limit, restart, or
investigate.

### How to clear / reset the guard

The estimated total is process-local. To reset:

1. **Restart the API**: `docker compose restart api` — counters
   zero, guard re-evaluates from `$0.00`.
2. **Disable then re-enable** the flag: setting
   `AGENT_INSIGHTS_ENABLED=false` then `true` does NOT clear the
   counter (it persists until process restart). Use this only to
   stop accruing cost, not to reset the gauge.
3. **Raise the ceiling**: change `AGENT_INSIGHTS_COST_GUARD_USD`
   in env and restart.

There is no in-memory reset endpoint — by design, so a misconfigured
client cannot DoS the cost ceiling by spamming a reset call.

### Recommended operator response when guard fires

1. Disable `AGENT_INSIGHTS_ENABLED` to halt new spend immediately.
2. `GET /api/insights/status` and read the metrics block:
   * `estimated_cost_usd_total` — confirm the running total.
   * `cache_hit_total / requests_total` — high ratio means cache
     is working and the new spend is concentrated on novel
     payloads.
   * `safety_rejected_total` — non-zero means tokens were
     spent on rejected bodies; investigate prompt or model.
3. Inspect `agent_insight` for redundant rows / stale safety
   versions: `SELECT count(*), safety_version FROM agent_insight
   GROUP BY safety_version;`.
4. Decide whether to raise `AGENT_INSIGHTS_COST_GUARD_USD` and
   re-enable, or leave disabled until the budget cycle resets.

### Restart semantics

Counters are **process-local**. They reset to zero when the API
process restarts. There is no shared meter, no Prometheus
exporter, and no per-call ledger table — all by design for F7-F8
scope. A future phase may wire a real exporter; until then, treat
the snapshot as a best-effort view of the current process. The
F8 guard ceiling is also re-evaluated against the per-process
counter only — multiple replicas each track their own running
total.

### When to disable AGENT_INSIGHTS_ENABLED based on metrics

Toggle `AGENT_INSIGHTS_ENABLED=false` and restart when any of the
following are observed and unexplained:

* `safety_rejected_total / llm_calls_total` exceeds 10% over a
  sustained window — the model is fighting the guards.
* `estimated_cost_usd_total` crosses
  `AGENT_INSIGHTS_COST_GUARD_USD` for the running process.
* `transport_error_total` is climbing AND the operator dashboard
  shows downstream Anthropic incidents.
* `last_error_reason` shows a payload smuggling pattern that the
  narrator scrub did not catch.

In every case, disabling the flag is non-destructive: the cache
remains, the drawer surfaces the disabled message, and the rest
of the platform is unaffected.

### Other observability surfaces

- `GET /api/health` — overall API health (independent of agents).
- DB query: `SELECT count(*), max(created_at) FROM agent_insight;`
  for cache freshness.

## 13. Escalation

For any issue tied to the agent-insights layer:

1. Disable: `AGENT_INSIGHTS_ENABLED=false` + restart.
2. Verify execution paths unaffected (paper trades still flowing,
   exit cycle still running, options scores still emitted).
3. File a ticket referencing F1–F5 commits and attach
   `/api/insights/status` output + recent `agent_insight` row
   count.
4. Do **not** edit migration `064` in place — write a forward
   migration if the schema needs to change.
