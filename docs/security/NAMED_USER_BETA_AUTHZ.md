# Agent Gateway — Named-User Beta Authorization (design, dev-only, default-off)

Status: **DESIGN + TEST HARNESS ONLY.** No multi-tenant production support is
built. v0 remains owner-only (`created_by` = owner for every token). This
document specifies the authorization model a future named-user beta (spec §10.2)
must satisfy, and is backed by an executable authorization-matrix harness
(`apps/api/tests/integration/test_elite_authz_matrix_pg.py`).

## Principal model

A gateway token has exactly one owning principal — `agent_token.created_by`,
an `app_user.id`, set at creation and **never mutable** (no route updates
`created_by`; a broader/different principal = a new token). The token secret
is shown once; identity on every request is resolved server-side from the
token hash, never from client input.

```
token ──(sha256 lookup by prefix, constant-time compare)──▶ agent_token row
      ──▶ created_by = app_user.id  ──▶ THE principal for this request
```

## Scope semantics under named users

| Scope | Named-user rule | Enforcement point |
|---|---|---|
| **R** | Any valid token reads the **published recommendation corpus** — global engine content, no per-user data. Equal for all principals. | Route reads `recommendation`/`asset` only; no user/portfolio join exists. |
| **P** | A token reads **only** `user:<created_by>:stock` — the principal's own paper book. No portfolio id crosses the boundary in either direction. | `_own_book_id(s, ident)` derives the book name from `ident["created_by"]`; a client cannot name another book. |
| **B** | Jobs are **owned** by `created_by`; `get_job`/`cancel`/events return 404 for any other principal (existence hidden). Queue cap counted per `created_by`. | `get_job` filters `created_by`; SSE re-checks ownership before streaming. |
| **D** | Drafts are attributed `generated_by='agent:<name>'` and land in the shared inbox as `pending`; the **owner console** reviews. A user's draft is visible to the owner (administrative visibility) but the gateway exposes no read-back of another principal's drafts. | `create_report` sets `generated_by` server-side; gateway has no draft-read route. |

## Required invariants (all covered by the matrix harness)

1. **P isolation** — token(A) never reads B's book; token(B) never reads A's.
   Unknown/unowned = 404, timing-comparable (no existence oracle).
2. **R equality** — A and B both read the same published corpus; neither sees
   user data (no `model_version`, portfolio, or PII in R payloads).
3. **B/D isolation** — A cannot GET/cancel/stream B's job; A's draft carries
   `agent:<A-name>` and B cannot read it back through the gateway.
4. **Owner visibility without impersonation** — the owner reviews any user's
   drafts through the existing owner console (`require_owner`), but there is
   **no** gateway route by which one principal acts *as* another. The owner
   never holds a user's token; the owner console reads rows, it does not mint
   or borrow user tokens.
5. **Revoked/deleted user loses access immediately** — a revoked token (status
   or expiry) resolves to None on the very next request (no session cache); a
   disabled `app_user` (`disabled_at`) fails the session path, and P reads of a
   disabled user's book return empty/denied.
6. **No principal mutation** — no route changes `created_by`; the CHECK/write
   surface offers no path to escalate a token's principal or scope after
   creation.
7. **No prefix collision across users** — `token_prefix` is `UNIQUE`; two
   tokens (any principals) can never share a prefix, so a forged token can
   never resolve against another user's row. Token transfer is meaningless:
   presenting A's secret authenticates as A regardless of who holds it, and
   the secret is hashed at rest so a DB reader cannot recover it.

## Beta rollout constraints (unchanged from spec §10.2)

- Named users may hold **R+P only**; B and D remain owner-only until a separate
  review. (The harness proves the isolation model for all four scopes so B/D
  can be opened later without redesign.)
- Per-user token cap enforced at mint time (owner console).
- `AGENT_GATEWAY_ENABLED` and named-user behavior stay **default-off**;
  production promotion requires the single-replica rate-limit blocker resolved
  (shared store) and a fresh security review.

## What is NOT designed here

Multi-tenant billing, self-service token issuance, cross-org sharing, and any
production multi-replica coordination. Those are out of scope for the beta and
for this program.
