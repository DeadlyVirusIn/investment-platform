Summarize closed-trade outcomes from the exit-cycle runner.

The endpoint provides:

- `n_closed`, `n_winners`, `n_losers`, `win_rate` — note that
  `win_rate` is null until at least one closed trade exists.
- `realized_pnl_total`, `avg_win_dollars`, `avg_loss_dollars`,
  `avg_hold_days`.
- `by_category` rows for take_profit, stop_loss, max_hold,
  and other.
- `tp_sl_effectiveness` rollup.
- `best_exit` and `worst_exit` payloads.
- `small_sample_warning` — preserve verbatim when present.
  The endpoint sets it whenever `n_closed` is below the
  endpoint's small-sample threshold.

Cover:

- The headline counts and the win rate. State that
  `win_rate` is null when `n_closed` is zero — never imply
  a 0% rate.
- The TP / SL / max_hold split.
- Best and worst exits using payload values directly.
- The small-sample warning verbatim, including the word
  "directional" — do not soften it.

Do not recommend new trades. Do not suggest threshold
changes. The exit-cycle runner already applied its rules
deterministically; this is review context only.
