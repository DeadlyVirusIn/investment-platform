# Paper authorization — residuals after two repair loops (ESCALATION)

Branch `security/paper-surface-ownership`, HEAD `43c961d`. Two independent
final reviews (Sol `019f7131`, Claude security-reviewer) returned **BLOCK**.
Per the boss-worker two-repair-loop cap, work STOPPED here and is escalated with
evidence. This documents what is closed, what remains, and the safest next step.

## Closed and verified (do not redo)

Original dual-review findings 1–10 on the enumerated paper surface: **8 CLOSED,
precedence fix verified correct, 1 LOW residual, 1 cosmetic OPEN.** Orchestrator
LIVE-FIRE on a running API (anonymous) confirmed ZERO `user:` names and ZERO
user-book UUIDs from: `paper/portfolios`, `paper/equity`, `performance/paper/
alpha-lab`, `risk-dashboard`, `trade-quality`, `open-positions`, `pending-fills`,
`paper/funnel/saturation`, `paper/live-nav`; `paper/equity` foreign user book →
404, demo book → 200 (56 pts), aggregate → 404; canonical → "Demo book";
`paper.py` CRUD → 404 anon. 89 unit tests pass. Owner elevation is
session-cookie-only across all new helpers (no demo-header owner grant); 404
posture uniform (no existence oracle).

## Residual — confirmed by live-fire (BLOCKS "ready" status)

Same missing-ownership-gate class, in files **outside the mission's enumerated
paper scope** (not paper.py / performance_paper / paper_live / executed):

1. **HIGH — `GET /api/paper/trades` (operator.py:463-588).** Public, ungated;
   returns the 500 most recent `paper_trade` rows across ALL books commingled,
   emitting raw user-book `portfolio_id` + side/qty/price/notional/realized_pnl.
   Live-fire: anon → 200 with a user-book UUID. (Its siblings `/paper/summary`
   and `/paper/equity` were gated; this one was missed.) Fix: owner-gate or JOIN
   `paper_portfolio` + `AND p.name NOT LIKE 'user:%'` for non-owner, drop
   `portfolio_id`.

2. **HIGH — arbitrary-`portfolio_id` IDOR in `performance.py` + `pnl.py`.**
   Live-fire: `GET /api/performance/summary?portfolio_id=<user book>` → 200 data;
   `/api/performance/equity-curve?portfolio_id=<user book>` → 200; `/api/pnl/
   summary?portfolio_id=<user book>` → 200; `/api/pnl/by-symbol?portfolio_id=
   <user book>` → 200 (6.4 KB — the private book's per-symbol PnL). Root: a
   shared, unrestricted portfolio-id resolver in `engine.py` (`session.get`)
   reused by dashboard/briefing/diagnostics/intelligence. Fix once at the
   resolver: for non-owner, reject a `portfolio_id` that is a user book not
   owned by the caller (404), mirroring `operator.paper_equity`.

3. **LOW — risk-dashboard trade counts (performance_paper.py:3445-3464).** The
   repair added a `JOIN paper_portfolio` to `live_trades`/`replay_trades` counts
   but did not append `{user_books_filter}` to their WHERE, so the JOIN is inert
   and the two integer counts still fold user-book trades for non-owner. No
   name/UUID leak (two aggregate ints). Fix: add `{user_books_filter}`.

4. **LOW — SQL `NOT LIKE 'user:%'` is case-sensitive** while the Python helper
   now normalizes case; a non-canonical-cased book name could dodge SQL
   exclusion. Names are machine-generated lowercase, so not currently reachable.

Not reachable in this environment: `reasoning/health`, `reasoning/gaps` → 404
(flag-gated/unmounted); re-check under the flags that expose them.

## Reviewer disagreement (recorded)

Sol classified the broad `performance_paper` core readers (`/summary`,
`/trades`, `/equity`, `/attribution`, `/lifecycle`, `/exit-analytics`) as HIGH.
Orchestrator live-fire found these emit **no** user-book name and **no**
user-book UUID by default (name=none, uuid=none) — they fold user-book figures
into unattributed aggregates, which is the LOW "aggregate totals" class, not an
identity/holdings disclosure. Claude security-reviewer did not flag them as
HIGH. Verdict: treat as LOW (aggregate hygiene), not blocking — but exclude
user books there too when the resolver fix lands, for consistency.

## Safest next step (recommended)

One more bounded backend task (its own dispatch, dual review) closing residuals
1–3: (a) gate `operator.paper_trades`; (b) add the user-book ownership check to
the shared `engine.py` portfolio-id resolver so `performance.py`/`pnl.py`/
dashboard/briefing/intelligence inherit it; (c) fold the risk-dashboard count
filter back in. Then re-run the anonymous live-fire against `/api/paper/trades`,
`/api/performance/*?portfolio_id=`, `/api/pnl/*?portfolio_id=` specifically.
This is small and mechanical (the pattern already exists on this branch); it was
not done here only because the two-repair-loop cap was reached — escalating per
policy rather than looping a third time. The `paper.py` CRUD IDOR (the original
CRITICAL) and the enumerated paper surface are already closed, so this branch is
a large net security improvement even in its current BLOCKED state.
