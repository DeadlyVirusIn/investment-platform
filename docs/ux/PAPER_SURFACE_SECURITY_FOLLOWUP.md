# Paper-surface authorization — follow-up (escalated, NOT fixed this sprint)

Raised by two independent reviews during the 2026-07 UX sprint (Claude
`security-reviewer`; Codex `gpt-5.6-sol` session `019f6c32`). This sprint gated
the four `/api/paper/executed/*` read endpoints (commit `164415f`, net exposure
**reduction**, Claude reviewer APPROVE-WITH-NOTES). The findings below are
**pre-existing** exposures on the same data that this sprint did **not** change.
They are escalated for an owner decision, not silently shipped. Nothing here is
newly introduced; all of it is already present in frozen production (`7e0af44`).

## Why not fixed in this sprint

The core novice funnel depends on **anonymous** paper activity: a signed-out
visitor can "Add to paper" against a device-scoped book (X-Auth-User-Id header /
`resolve_identity` demo path). Gating the write/list surface without a deliberate
design decision would break that flow — the exact journey the sprint set out to
clarify. This needs an owner call on the anonymous-paper model, not a reflex
patch under a UX sprint. It exceeded the sprint's two-repair-loop budget.

## Findings to triage (severity per reviewers)

1. **`apps/api/src/api/paper.py` legacy router (Sol CRITICAL).** Mounted public.
   Exposes unauthenticated portfolio list/detail/trades, arbitrary portfolio
   **creation**, and **trade submission** with no ownership gate. Because a
   caller can create an arbitrarily-named portfolio, a known victim uid's
   canonical book name `user:<uid>:stock` can in principle be pre-claimed before
   the real user signs up (ownership is a name convention, not a foreign key to
   the account). Decide: keep anonymous paper but namespace device books so a
   name can't collide with a future account's canonical book; and/or require a
   session for create/trade while preserving a distinct anonymous device flow.

2. **`apps/api/src/api/performance_paper.py` (Claude HIGH).** `/api/performance/
   paper/risk-dashboard` (`concentration_by_portfolio`) and siblings scan
   `WHERE p.is_active = TRUE` with no `user:%` exclusion, returning per-user book
   **names** (embedding uids) and holdings to anonymous callers. Fix: reuse the
   existing `engine_tradable_portfolios_stmt` predicate (`name NOT LIKE
   'user:%'`) or gate the router.

3. **`apps/api/src/api/paper_live.py` (Claude HIGH).** `/api/paper/live-nav`
   returns per-portfolio `id` + `name` for active books, same leak class as #2.

4. **Ownership convention brittleness (Sol/Claude LOW).** `is_user_paper_book`
   is a case-sensitive `startswith("user:")`; `user_stock_portfolio_name(uid or
   "")` yields `user::stock` for empty uid. Not currently reachable, but the
   ownership model should be a real relation, not a string prefix.

5. **Owner-check identity source (Claude LOW).** The new executed-endpoint gate
   resolves the owner via `resolve_identity` (honors device header in demo mode)
   while `require_owner` uses the session cookie only. Production-safe (demo mode
   off in prod) but the two owner paths should be aligned.

## Recommended next step

A dedicated **backend paper-authorization** task (its own branch, `security-
reviewer` + `gpt-5.6-sol` dual review, `database-safety-reviewer` if any schema
touch), preceded by an owner decision on the anonymous-paper model. Add items
1–3 to `SECURITY_BACKLOG.md`. This is independent of the frozen production
observation and of Stage-B promotion.
