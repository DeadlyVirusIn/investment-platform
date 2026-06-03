# Stage 2A.1 — Width Fidelity Review (design note)

Status: **OPEN — review only, no change made.** Raised during Stage 2B
verification (2026-06-02). Tracks a leg-selection fidelity question in the
Stage 2A materializer; economics (Stage 2B) are unaffected and correct.

## Problem

Stage 2A's credit-spread materializer (`apps/api/src/options/strategy_candidates/legs.py`,
`_credit_legs`) selects the long (protective) leg as the **next strike in
the _priced_ ladder** — `_fetch_ladder` drops rows whose `mid` is null. When
the strictly-adjacent listed strike is **unquoted in that snapshot**, the
long leg jumps to the next *priced* strike, widening the spread beyond the
intended "1-strike-wide" structure.

## Evidence (2026-06-02 forced cycle)

QQQ `SHORT_PUT_CREDIT_SPREAD`, expiry 2026-07-17:
- Persisted legs: short put **700** (`QQQ260717P00700000`, mid 8.445),
  long put **698** (`QQQ260717P00698000`, mid 8.095) → **$2-wide**.
- The 699 strike was absent from that expiry's priced ladder, so 698 became
  "next priced".
- Resulting economics: net credit $35, **max_risk $165** (= (2.00 − 0.35)×100).
  Had it been 1-wide (700/699), max_risk would be ~$65.

All other engine candidates that day were genuinely 1-wide (IWM/SPY IC $1,
GLD $5 = real chain spacing, TLT $0.50 = real spacing). Only the QQQ case
widened due to a missing adjacent quote.

## Impact

- **Economics are faithful to the persisted legs** — the math is correct for
  the structure that was actually stored. No 2B bug.
- **But** the "1-strike-wide defined risk" *intent* is not always met: a
  missing adjacent quote silently produces a wider spread with larger
  max_risk than nominal. A trader reading "$165 max risk" sees the true risk
  of the stored structure, but the structure differs from the engine's
  nominal 1-wide design.

## Options

- **A — strict adjacency:** require the long leg to be the strictly-adjacent
  *listed* strike. If that strike is missing/unquoted → `legs_complete=false`
  → economics null (B.1 null-omit discipline). Pros: never misrepresents the
  intended structure. Cons: more null economics on thin chains.
- **B — keep next-priced, label width:** retain current behavior but surface
  the actual wing width (e.g. "$2-wide") so the widening is explicit, not
  silent. Pros: always computable. Cons: structure still deviates from intent.
- **C — accept as-is:** current behavior; economics are truthful to stored
  legs. Cons: silent intent drift.

## Recommendation

Lean **A** (strict adjacency → null when the 1-wide leg isn't quoted),
because Phase C's whole premise is *truthful, intent-matching* economics, and
a silently-widened spread is a subtle misrepresentation of the engine's
defined-risk design. **B** is an acceptable interim if null-rate is a concern.

## Scope guard

No change made under Stage 2B. This is a Stage 2A leg-selection policy
question. Any change here touches the materializer (`_credit_legs` /
`_fetch_ladder`) and must be a deliberate, separately-approved Stage 2A.1 —
it is **not** a generator/threshold/ranking/wing-width-policy change to the
engine itself; it only governs which already-defined strike is recorded as
the long leg when the adjacent quote is missing.
