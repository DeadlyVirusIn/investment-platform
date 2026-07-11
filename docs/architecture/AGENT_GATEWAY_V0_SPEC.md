# Agent Gateway v0 — Spec (Sprint 10)

Status: **IMPLEMENTING (Priority 7 / P7)** — the security core of this spec is
now built, flag-off. Landed: migration `114_agent_gateway` (agent_token +
agent_audit, PROPOSED — validated on ephemeral container only, NOT applied to
any DB); token model `domain/agent_gateway/tokens.py` (§2/§3); append-only
audit `domain/agent_gateway/audit.py` (§5); Bearer auth dependency + `/agent`
router + audit middleware `api/agent_gateway.py` (§4); owner-only token console
`api/agent_admin.py` (§2); all mounted behind fail-closed
`AGENT_GATEWAY_ENABLED=False`. `GET /agent/whoami` is a live authenticated
round-trip; the data/job/draft route bodies return 501 pending their
data-contract slices (§4 routes exist + are scope-gated + audited). Pure-core
unit tests green (24 assertions); DB-backed lifecycle + authz-matrix tests
written (`test_agent_gateway_pg.py`) for `make test-auth`. **Not deployed; no
DB applied; no MCP client shipped** — those remain separate approval-gated
changes per `CLAUDE.md`.

Original design intent (unchanged below): architecture-only proposal, no
migration/router/MCP process shipping from the document; approval-gated per
`CLAUDE.md`. Source context: `docs/research/EXTERNAL_QUANT_AI_REVIEW_2026.md`
§3A (QuantDinger governance patterns — **independently re-expressed from
the review's descriptions; no external code copied**), §5 security gate,
§8 Pillar D, §11 M8. Style anchors: `apps/api/src/api/admin_guard.py`
(404 posture, `require_owner`), `apps/api/src/auth/resolver.py`
(server-side identity resolution), `apps/api/src/config/__init__.py`
(fail-closed flags), `docs/architecture/RESEARCH_RUN_REGISTRY_SPEC.md`
and `RESEARCH_INBOX_SPEC.md` (Sprints 5/8 — the resources this gateway
exposes).

## 1. Position in the architecture

```
agent (Claude/other) ──stdio──▶ MCP thin client ──HTTPS──▶ FastAPI REST gateway ──▶ services/DB
                                (NO logic, NO auth         (THE security boundary:
                                 decisions, NO DB,          token auth, scopes, rate
                                 forwards + formats)        limits, audit, idempotency)
```

**The REST API is the security boundary.** The MCP server is a thin
client: it holds one token, translates tool calls to HTTP requests, and
renders responses. It makes no authorization decisions, caches no data,
touches no database, and adding a second protocol front-end (or a raw
curl user) changes nothing about safety. Every guarantee in this document
is enforced server-side.

**Paper-only is architectural, not a flag.** There is no `T`/live-trading
scope, no route that places, stages, modifies, or cancels any trade
(paper or otherwise), and no code path from any gateway module into
`paper_execution.submit_trade` or the options engine. A compromised token,
a malicious agent, and a bug in the gateway all inherit the same ceiling:
**read things, submit offline jobs, write drafts that humans review.**
Nothing to misconfigure; nothing to flip.

## 2. Token model

New table `agent_token` (revision slot **`114_agent_gateway`**, together
with `agent_audit` §5; slots 109–113 are reserved by the Sprint 5–9
proposals: research_run, thesis ledger ×2, research_inbox, lesson). House style: uuid36 PK, TIMESTAMPTZ, CHECK enums.

Token string format, shown exactly once at creation:

```
arthos_at_<prefix(8)><secret(32)>        e.g. arthos_at_7f3a9c21…
```

- **Hashed at rest**: the DB stores `sha256(full_token)` — never the
  token. (sha256, not bcrypt, is correct here: the secret has 128+ bits
  of server-generated entropy, so brute force is infeasible and constant
  lookup cost matters; password-grade KDFs solve a low-entropy problem
  this design doesn't have.)
- **Prefix for lookup**: `token_prefix` (first 8 chars after the
  namespace) is stored in plaintext for O(1) candidate lookup and for
  audit/UI display ("token 7f3a9c21…"), then the full hash is compared
  in constant time.
- **Expiry mandatory**: `expires_at NOT NULL`; v0 default 30 days, max 90.
  No non-expiring tokens exist.
- **Revocation**: `status='revoked'` + `revoked_at` + `revoked_reason`;
  checked on every request; effective immediately (no session cache).
- **Scopes**: subset of `{R, P, B, D}` fixed at creation (no scope
  escalation post-creation; broader access = new token).
- **Per-token rate limit**: `rate_limit_per_min` (default 60; ceiling
  240), enforced server-side per token_prefix; plus a global gateway
  budget so N tokens can't multiply into a VM-class problem.
- **Request size limits**: `max_request_bytes` (default 64 KiB) enforced
  before body parse; oversize → 413 + audit row.

```sql
-- 114_agent_gateway.sql (PROPOSAL — token table)
CREATE TABLE agent_token (
    id                 VARCHAR(36)  PRIMARY KEY,
    agent_name         VARCHAR(64)  NOT NULL,            -- human label: 'research-claude'
    token_prefix       VARCHAR(8)   NOT NULL,
    token_hash         VARCHAR(64)  NOT NULL,            -- sha256 hex of full token
    scopes             VARCHAR(16)  NOT NULL,            -- comma-joined subset of R,P,B,D
    status             VARCHAR(16)  NOT NULL DEFAULT 'active',   -- active | revoked
    expires_at         TIMESTAMPTZ  NOT NULL,
    rate_limit_per_min INTEGER      NOT NULL DEFAULT 60,
    max_request_bytes  INTEGER      NOT NULL DEFAULT 65536,
    created_by         VARCHAR(64)  NOT NULL,            -- app_user.id (owner, v0)
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_used_at       TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revoked_reason     TEXT,
    CONSTRAINT uq_agent_token_prefix UNIQUE (token_prefix),
    CONSTRAINT uq_agent_token_hash   UNIQUE (token_hash),
    CONSTRAINT ck_agent_token_status CHECK (status IN ('active','revoked')),
    CONSTRAINT ck_agent_token_scopes CHECK (scopes ~ '^[RPBD](,[RPBD]){0,3}$'),
    CONSTRAINT ck_agent_token_rate   CHECK (rate_limit_per_min BETWEEN 1 AND 240),
    CONSTRAINT ck_agent_token_revoked CHECK
        (status <> 'revoked' OR revoked_at IS NOT NULL)
);
```

Token management is owner-console-only (`require_owner`, 404 posture):
create (secret displayed once), list (prefix + metadata only), revoke.
There is no self-service or API-driven token creation.

## 3. Scopes — exactly four, and what they do NOT include

| Scope | Grants | Explicitly does NOT grant |
|---|---|---|
| **R** | Read recommendations, their evidence/reasoning envelopes, and public market data already in our DB (prices, factors, regimes) | User/account data; admin surfaces; provider API passthrough; anything not already persisted server-side |
| **P** | Read the token owner's **own** paper portfolio: positions, trades, snapshots, performance | Other portfolios (server resolves ownership — §7.4); any write; canonical/demo books unless owned |
| **B** | Submit **offline** research/backtest job requests (bounded, queued, dev-class work: e.g. "run a walk-forward with these params"), poll status, stream bounded events (§6) | Executing anything inline; shell/code payloads (jobs are named types + validated JSON params, never scripts); touching the production scheduler's trading jobs |
| **D** | Create **draft** research reports (Sprint 8 `research_report` drafts flagged agent-origin, invisible until human review) | Publishing, editing delivered reports, marking anything reviewed, creating tasks/schedules |

**There is no T scope, no fifth scope, and no scope-combination that
executes a trade.** The scope grammar in the DB CHECK (`^[RPBD]…`)
rejects unknown letters at write time; the route table (§4) contains no
mutating portfolio endpoint for any scope to attach to. Adding live
trading would require new routes, new scope grammar, new execution
plumbing — i.e., a deliberate multi-file change that review would catch —
not a config change. That is the design intent: **make the dangerous
thing expensive to build, not merely disabled.**

## 4. Route surface (v0, complete)

Mount: `APIRouter(prefix="/agent", tags=["agent-gateway"])`, behind
fail-closed `AGENT_GATEWAY_ENABLED: bool = False`. Auth: `Authorization:
Bearer arthos_at_…` resolved by a gateway-only dependency (never cookie
auth — `arthos_session` browser sessions and agent tokens must not be
interchangeable in either direction).

| Route | Method | Scope | Notes |
|---|---|---|---|
| `/agent/recommendations` | GET | R | List/filter (as-of aware); public uids only |
| `/agent/recommendations/{rec_uid}` | GET | R | Detail + evidence + envelope summary |
| `/agent/market/prices` | GET | R | Bars from our `price_bar`, bounded window (≤ 5y, ≤ 50 symbols/request) |
| `/agent/portfolio` | GET | P | THE caller's book (resolved from token → created_by → portfolio ownership) |
| `/agent/portfolio/trades` | GET | P | Closed/open trades, paginated |
| `/agent/jobs` | POST | B | Submit job: `{job_type, params, idempotency_key}`; job_type from a fixed enum; params schema-validated per type |
| `/agent/jobs/{job_uid}` | GET | B | Status + result summary (result payloads size-capped) |
| `/agent/jobs/{job_uid}/events` | GET | B | Bounded stream (§6) |
| `/agent/drafts` | POST | D | Create draft report `{task_uid, title, body_md, evidence[], idempotency_key}`; lands as Sprint-8 report draft, `generated_by='agent:<name>'`, reviewer_status flow unchanged — invisible until a human reviews |
| `/agent/whoami` | GET | any | Token introspection: agent_name, scopes, expiry, rate-limit state (no hash, no secret) |

Everything else — admin, auth, paper execution, options, feedback,
scheduler — is **not mounted under `/agent`** and returns 404 to agent
tokens (agent auth is valid only on the `/agent` router; agent tokens
presented to non-agent routes are rejected as anonymous → the existing
404 posture).

**Idempotency keys are mandatory on all writes** (`POST /agent/jobs`,
`POST /agent/drafts`): unique `(token_prefix, idempotency_key)` retained
≥ 24h; a replayed key returns the original response (200-with-same-body,
flagged `"replayed": true`), never a duplicate job/draft. Missing key →
400 before any side effect.

## 5. Audit — one table, every call

Exactly one audit table for the whole gateway (review §5: "one audit
table for all agent/privileged calls"). Written for **every** request —
success, 4xx, 5xx, rate-limited, and auth-failed (with whatever prefix
was presented) — from middleware, so no route can forget it.

```sql
-- 114_agent_gateway.sql (PROPOSAL — audit table)
CREATE TABLE agent_audit (
    id              VARCHAR(36)  PRIMARY KEY,
    agent_name      VARCHAR(64),                    -- NULL when token unknown/invalid
    token_prefix    VARCHAR(8),                     -- as presented (candidate prefix on auth failure)
    route           VARCHAR(128) NOT NULL,          -- templated path, not raw URL ('/agent/recommendations/{rec_uid}')
    method          VARCHAR(8)   NOT NULL,
    scope_used      VARCHAR(4),                     -- R|P|B|D; NULL on pre-scope rejection
    status_code     INTEGER      NOT NULL,
    idempotency_key VARCHAR(64),
    duration_ms     INTEGER      NOT NULL,
    request_hash    VARCHAR(64),                    -- sha256 of canonical(method, path, sorted query, body) — correlation without storing payloads
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_audit_prefix_created ON agent_audit (token_prefix, created_at DESC);
CREATE INDEX ix_agent_audit_route_status   ON agent_audit (route, status_code, created_at DESC);
```

Properties: append-only (no UPDATE/DELETE path — `reasoning_audit`
contract); stores **hashes, not payloads** (no market data duplication,
no draft bodies, nothing to leak); templated route (no user-controlled
strings beyond the 8-char prefix); feeds the owner console
(`/v2/admin/*` pattern) with per-token activity, error-rate, and
rate-limit-hit panels, and later the Trust Center's "agent activity"
disclosure. Retention: 180 days online, then archived via `make
db-backup`-style dumps before pruning (policy documented with the table;
pruning itself is an approval-gated ops action).

## 6. Bounded streaming

`GET /agent/jobs/{job_uid}/events` — SSE, for job progress only:

- **max_events** per connection: 500 (server default; client may request
  lower, never higher).
- **max_seconds** per connection: 120; then the server closes with a
  `cursor` event; the client reconnects with `?after=<cursor>`.
- One concurrent stream per token (a second connection closes the first).
- Events are server-generated status lines (queued/started/progress
  pct/completed/failed + result summary) — never raw job stdout, never
  file contents.

Bounded reconnect-with-cursor beats an unbounded firehose on a one-VM
deployment: worst-case connection cost is a constant, per token.

## 7. Design-level prohibitions

These are structural (no code path exists), not configuration:

1. **No shell.** No tool, route, or job type executes shell commands or
   spawns processes from request data.
2. **No arbitrary URL fetch.** The gateway performs zero outbound fetches
   on behalf of agents. Research jobs that need external data use the
   existing ingest providers (Tiingo/Polygon/yfinance) via the existing
   provider modules and their allowlist — an agent can ask a *question*,
   never name a *URL*. (SSRF surface: none.)
3. **No generated-code execution.** Job params are typed JSON validated
   against per-job-type schemas; no field is ever evaluated, imported,
   templated into SQL, or written to an executable location. The review's
   categorical rejection of in-process exec (§5) is a permanent
   constraint of this product.
4. **No user-selected raw DB ids.** All identifiers crossing the boundary
   are public uids (`rec_…`, `rpt_…`, job uids); the server resolves
   identity from the token and checks ownership before touching a row
   (M1 precedent: identity is server-resolved, never client-supplied).
   Unknown uid and unowned uid are indistinguishable: both 404.
5. **Prompt-injection boundaries.** Everything the gateway returns is
   *data about our system*, already persisted and validated at ingest.
   Response bodies are structured JSON; free-text fields (rationales,
   report bodies) are returned inside JSON strings, and the MCP client
   renders tool results inside fenced blocks labeled as retrieved data.
   No gateway response ever contains an instruction the agent should
   follow, and no gateway component interprets instructions found in
   stored text (fetched filings/news were already treated as data at
   ingest — review §5). The gateway never echoes request content back
   into other users' or surfaces' views (draft reports become visible
   only through human review).

## 8. Threat model

Assets: recommendation/evidence corpus (product IP), paper portfolio
data (private), DB integrity, VM availability, and — above all — the
trust claim that no agent can act on a portfolio.

| # | Archetype | Attack | Mitigations | Expected system response (abuse case) |
|---|---|---|---|---|
| T1 | **Leaked token** (token in a pastebin/log) | Read corpus, spam jobs/drafts until noticed | Hash at rest (DB dump ≠ tokens); mandatory expiry ≤ 90d; instant revocation; per-token rate limit; audit trail keyed by prefix; owner-console "last_used_at + activity" panel makes anomalies visible; scope ceiling = read/jobs/drafts (no trade, no PII beyond own paper book) | Stolen token used at 3am: requests succeed within scope + rate limit, every call audited; owner revokes; damage bounded to reads + reviewable drafts. Post-expiry use → 401 + audit row |
| T2 | **Malicious agent** (hostile client behind a valid token) | Probe for unmounted routes, scope escalation, oversized payloads, SQL/path injection in params | Route allowlist (§4) — everything else 404; scopes fixed at creation, grammar-checked in DB; 413 pre-parse size cap; typed param schemas + bound parameters (house style); public-uid-only resolution | `POST /agent/portfolio/trade` → 404 (route doesn't exist), audited. `scopes=T` at creation → CHECK violation, token never exists. 2 MB body → 413, audited |
| T3 | **Prompt-injected agent** (agent's LLM hijacked by content it read elsewhere) | The agent "decides" to exfiltrate or trade | Same ceiling as T2 — the gateway cannot distinguish a hijacked agent from a hostile one and doesn't need to: no trade path exists; drafts are quarantined behind human review; no outbound fetch means no exfil channel through us; own-book-only P scope limits what's readable | Injected agent tries to "sell everything": no such route; tries to publish propaganda in a report: draft lands, human review reads `generated_by='agent:…'` provenance, rejects |
| T4 | **Replay attacker** (captured request re-sent) | Duplicate jobs/drafts; billing/log spam | TLS everywhere (cloudflared tunnel); idempotency keys mandatory on writes — replay returns the original result, no new side effect; GETs are safe by design; audit `request_hash` makes replay bursts visible | Same POST re-sent 50×: 1 job exists, 50 audit rows with identical request_hash trip the console's anomaly panel |
| T5 | **Resource exhaustion** (one VM, shared with prod) | Connection floods, expensive queries, streaming pile-up, job queue stuffing | Per-token + global rate limits; bounded streaming (§6: 500 events/120s/1 conn); query bounds baked into routes (window/symbol caps, pagination ≤ 200); B jobs run on the dev-class offline lane (Sprint 5 discipline: heavy compute never on the VM), queue depth cap per token (e.g. 5 pending) → 429 | 61st request in a minute → 429 + audit; 6th pending job → 429 `queue_full`; stream past 120s → clean close + cursor |
| T6 | **Cross-user probing** (multi-token future: token A reads user B) | Enumerate uids, guess ids, IDOR | Server-side ownership resolution on every P-scope query (token → created_by → owned book); public uids are random, non-sequential; unknown = unowned = 404 (existence hidden — admin_guard posture); authz-matrix tests lock every route × foreign-uid combination | Token A requests B's portfolio trade uid → 404, audited; scanning 10k guessed uids → rate limit + a wall of 404 audit rows, anomaly-flagged |

Residual risks (accepted, documented): a valid-scope reader can
bulk-export the recommendation corpus over time (mitigation: rate limit +
audit visibility, accepted for owner-only v0); gateway code bugs
(mitigation: the surface is small by design — ~10 routes — and the
release-gate security tooling from `15d7db6` applies); availability of
the shared tunnel (existing ops risk, unchanged by this design).

## 9. Test plan

- **Authz matrix**: every route × every scope subset × no-token ×
  expired × revoked × malformed bearer → expected status, exhaustively
  generated (table-driven), no route omitted. Includes: agent token on
  non-agent routes → 404; cookie session on `/agent/*` → 401.
- **Ownership (T6)**: P-scope reads with foreign uids → 404; uid
  enumeration returns indistinguishable 404s (timing-comparable).
- **Rate limiting**: burst to limit → 429 at N+1; per-token isolation
  (token A throttled, token B unaffected); global budget kicks in under
  multi-token flood; 429s appear in audit.
- **Idempotency**: same key replay → identical response + single side
  effect; same key different body → 409; missing key on write → 400;
  key uniqueness scoped per token (A's key doesn't collide with B's).
- **Injection corpus**: hostile params (SQLi strings, path traversal,
  oversized/deep JSON, unicode confusables, `{"job_type":"__import__"}`,
  instruction-bearing text in draft bodies) → validated rejection or
  inert storage, never execution; draft bodies with "ignore previous
  instructions" land verbatim in the quarantined draft (storage is not
  interpretation).
- **Streaming bounds**: event cap, time cap, cursor resume correctness,
  second-connection eviction.
- **Audit completeness**: property test — for any request that reaches
  the middleware (including auth failures and 413/429 short-circuits),
  exactly one audit row exists with matching status; assert append-only
  (no UPDATE grant/path).
- **Token lifecycle**: hash-at-rest verified (secret never in DB, logs,
  or responses post-creation); revocation immediate; expiry enforced;
  scope grammar CHECK (property: random strings outside `[RPBD]` subsets
  rejected).
- **Migration**: up/down clean on ephemeral alembic container (MP1S
  precedent). Guard tests extend `make test-auth` (new trust-critical
  surface).

## 10. Rollout sequence

1. **v0 — owner-only (this design).** `AGENT_GATEWAY_ENABLED=false` in
   prod until sign-off; tokens creatable only by `require_owner`; every
   token belongs to the owner; the only agent is the owner's own
   research assistant. Exit criteria: authz matrix green, audit panels
   live in owner console, 30 days of clean audit history.
2. **Trusted beta.** Named non-owner users may hold **R+P** tokens only
   (B and D remain owner-only); per-user token cap (2); Trust Center
   discloses that agent access exists and what it can/cannot do.
3. **Never public-write.** B and D scopes are never offered to untrusted/
   self-service users; if the product ever wants public agent access, it
   is read-only (R) and requires a fresh security review of this spec.
   This line is part of the spec, not a roadmap TBD.

Rollback at any stage: flip `AGENT_GATEWAY_ENABLED=false` (router
vanishes, tables stay), revoke all tokens (one UPDATE, effective
immediately), audit history retained.

## NON-GOALS

- **No live trading scope, route, or plumbing — permanently.** Not a v2
  item, not behind a flag; adding it would violate the product charter
  and requires a different product, not an amendment to this spec.
- **No paper-trade execution by agents either** — the human-in-the-loop
  paper flow is the product; agents draft and read, humans act.
- **No implementation in this sprint** — this document is the design
  gate; migration/router/MCP client are separate approval-gated changes.
- **No multi-tenant token issuance** (self-service signup tokens) — v0
  is owner-only; beta is named-users; nothing beyond that is designed
  here.
- **No agent-side logic in the MCP client** — no caching, retries with
  jitter beyond HTTP norms, local storage of results, or auth decisions.
- **No outbound fetch/browse/search tools** — the gateway exposes our
  data, not the internet (provider allowlist lives in ingest, unchanged).
- **No generic admin-over-API** — token management stays in the owner
  console UI; the gateway cannot manage its own tokens.
- **No streaming beyond job events** — no market-data firehose, no
  websocket surface, on a one-VM deployment.
- **No OAuth/OIDC for agents in v0** — bearer tokens with the properties
  in §2; revisit only if third-party agent platforms require delegation.
