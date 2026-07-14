# Elite ArthOS — Security Review (Agent Gateway + product slices)

Branch: `feature/elite-arthos-provable-ideas` · Reviewed at `d71c379`+fixes ·
Date: 2026-07-11 · Method: **behavioral red-team** (executed attacks via the
real ASGI stack against isolated PostgreSQL) + source scan. Scope: everything
new on the Elite branch — Agent Gateway R/P/B/D, offline jobs, SSE, drafts,
Thesis Ledger / Research Inbox / Learning Loop slices, paper-cost stamp,
migrations 114–117. **Production was never touched.**

Harnesses: `test_elite_authz_matrix_pg.py` (23), `test_agent_gateway_http_pg.py`
(abuse matrix), `test_agent_jobs_pg.py` (44), `test_agent_gateway_pg.py` (token
lifecycle). All attacks below are executed tests, not assertions on source.

## Verdict: no CRITICAL or HIGH findings open.

One MEDIUM found during review was **fixed in development** (disabled-user
token access). Remaining items are LOW / ACCEPTED-RISK with promotion gates.

---

## Findings

### FIXED — was MEDIUM: disabled/deleted user retained gateway access
- **Attack:** mint a P token for user D, then disable D (`app_user.disabled_at`).
  Before the fix the outstanding token still read D's paper book — token
  resolution checked only the token row, not the principal's account state.
- **Fix:** `resolve_token` now `LEFT JOIN app_user ON id = created_by` and
  rejects a known-disabled principal (`u.id IS NULL OR u.disabled_at IS NULL`).
  A disabled/deleted user loses gateway access on the **next request**, no
  session cache. Tokens whose `created_by` is not an app_user (owner-bootstrap)
  are unaffected. Proven: `test_revoked_and_expired_and_disabled_lose_access`
  now asserts 401 on whoami + portfolio.

### ACCEPTED RISK — single-replica in-memory rate limiter
- Rate limits (per-token + global) and SSE single-stream eviction live in
  process memory. Correct for the one-VM deployment; a second API replica would
  not share counters. **Owner:** SRE. **Promotion gate:** no multi-replica
  rollout until limits move to a shared store (DB/redis) — explicitly out of
  scope for this program (no Redis added). Tracked in the gateway spec §
  limitations.

### ACCEPTED RISK — owner-only principal in v0
- Every token's `created_by` is the owner today; true multi-user isolation is
  designed (`NAMED_USER_BETA_AUTHZ.md`) and proven at the authz layer, but the
  named-user beta is not enabled. **Promotion gate:** named-user R+P beta needs
  the authz-matrix re-run against real sessions + per-user token cap +
  disabled-user gate (now in place). B/D stay owner-only.

### LOW — audit stores client-supplied idempotency key verbatim
- The `Idempotency-Key` header is written to `agent_audit.idempotency_key`
  (bounded 64 chars, parameterized). An attacker can store control chars / SQL
  text there. **Not exploitable:** it is stored, never executed
  (`test_audit_log_injection_is_inert` proves the table survives and the string
  is inert); the column is capped; audit is append-only. **Owner:** accepted —
  audit fidelity (recording exactly what was presented) outweighs sanitizing.

### LOW — recommendation corpus bulk-exportable by a valid R token
- A valid R token can page the entire public recommendation corpus over time.
  Mitigation: rate limit + audit visibility; the corpus is already the public
  `/api/recommendations` surface (SECURITY_AUDIT baseline). **Owner:** accepted
  for owner-only v0; revisit for public/beta R tokens.

---

## Attack coverage (all executed, all defended)

| Attack class | Test | Outcome |
|---|---|---|
| **IDOR** — B guesses A's job/draft uid | `test_idor_job_and_draft_uid_guessing` | 404 (unowned = unknown, no oracle) |
| **P-scope cross-user read** | `test_p_scope_cross_user_isolation` | A never sees B's book/trades; no portfolio id crosses |
| **Privilege escalation via scope combo** | `test_privilege_escalation_via_scope_combo_blocked` | full R,P,B,D token → owner console still 404 |
| **Token prefix enumeration** | `test_prefix_enumeration_is_not_an_oracle` | real-prefix+wrong-secret == random-prefix (both 401); dummy constant-time compare on miss |
| **Replay / idempotency abuse** | `test_replay_and_idempotency_abuse` | 20× replay → 1 job; mutated body → 409 |
| **Queue starvation** | `test_queue_starvation_capped_per_owner` | A capped at 5, cannot starve B (per-owner, not global) |
| **SSE resource exhaustion** | `test_sse_*` (agent_jobs) | 120s/500-event caps, heartbeat, single-stream eviction, terminal close, disconnect stops delivery |
| **Malformed / oversized payloads** | `test_malformed_and_oversized_payloads` | bad JSON 400/422; Content-Length>cap → 413 pre-parse; query>2KB → 414 |
| **Unicode / confusable job types** | `test_unicode_confusable_job_types_rejected` | Cyrillic 'е', casing, traversal, NUL, `;DROP` → 422 (exact frozenset match) |
| **Audit-log injection** | `test_audit_log_injection_is_inert` | control/SQL chars stored inert, table intact |
| **SQLAlchemy filter bypass** | `test_sqlalchemy_filter_bypass_attempt` | `' OR '1'='1` in path → 404; `action=buy';--` → 422 (pattern-constrained) |
| **Revoked / expired / disabled access** | `test_revoked_and_expired_and_disabled_lose_access` | all 401 immediately, no cache |
| **Generated-content review bypass** | `test_generated_content_review_bypass_blocked` | "IGNORE PREVIOUS…approve me" → still `pending`; no approve/publish/correct/delete route |
| **Hidden trading coupling** | `test_no_hidden_trading_coupling` | job run → recommendation/paper_trade/portfolio/position counts unchanged |
| **Sensitive data leakage on error** | `test_no_error_leakage_on_db_failure` | DB failure carrying a DSN → 503, DSN never in response |
| **Migration downgrade hazard** | clone downgrade 117→115 | pre-existing rows preserved byte-for-byte; only new column/tables dropped |
| **Cookie/Bearer confusion** | `test_no_cookie_fallback_on_gateway` | owner cookie on `/agent/*` → 401; agent token on console → 404 |
| **Dangerous capabilities** | `test_no_dangerous_capabilities_in_gateway_sources` | no subprocess/eval/exec/import/requests/urllib/socket/pickle/papermill |
| **Write-target scan** | `test_jobs_module_writes_only_agent_and_registry_tables` | jobs.py writes only agent_*/research_run |

## Structural guarantees (not merely tested — no code path exists)

- **No T / live-trading scope.** Scope grammar CHECK `^[RPBD]…` rejects it at
  write time; no mutating portfolio/trade route exists under `/agent`.
- **No shell / eval / generated-code execution.** Job types are a frozen enum
  → hardcoded handlers; params are typed+bounded JSON, never evaluated.
- **No outbound fetch.** The gateway performs zero outbound requests; no URL
  field is accepted anywhere.
- **Hashed tokens at rest.** DB stores sha256(full); a DB dump yields no usable
  token.
- **Append-only audit, hashes not payloads.** No draft body / market data /
  secret is duplicated into audit.

## Sanitized-evidence hygiene
Fixtures/screenshots must never contain a full `arthos_at_…` secret (shown once
at mint), a DSN, or `.env` values. E2E evidence captures token **prefixes**
only and redacts bodies to structure. Verified: no `arthos_at_[0-9a-f]{40}` or
`postgres://…:…@` in the branch diff.
