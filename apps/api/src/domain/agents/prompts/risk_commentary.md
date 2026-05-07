Summarize the current paper-trading risk surface.

Use only fields present in the payload. If `mark_unavailable`
is true, state plainly that the mark-to-market exposure is
unavailable rather than reporting it as zero.

Cover:

- NAV, cash, exposure value, and the open-positions count.
- Concentration: the most-weighted symbol from
  `top_5_notional` and the most-weighted portfolio from
  `concentration_by_portfolio`.
- The realized and unrealized P&L numbers exactly as given.
- Live vs replay split — never call replay rows live trades.
- Max drawdown if present; otherwise note it as unavailable.

Do not recommend trimming, rotating, or buying. Do not
suggest threshold or sizing changes. The dashboard is
informational.
