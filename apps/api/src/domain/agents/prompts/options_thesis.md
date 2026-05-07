Summarize an options strategy candidate.

The endpoint is read-only and never submits orders. Live
options execution remains disabled — every leg insert is
gated on `execution_allowed=false` in the current phase.

Cover:

- The underlying, the rule, and the strategy structure
  (legs, strikes, expiry) using payload values directly.
- The total score and any flags or penalties attached.
- The qualified flag (boolean): a candidate cleared rule
  criteria, NOT that it is a recommendation.
- Any blocking notes — pending_next_bar, missing chain,
  broken liquidity gate, etc.

State explicitly that this is a paper-trading research note.
Do not imply the operator should submit the trade. Do not
invent greeks, IV percentiles, or pricing.
