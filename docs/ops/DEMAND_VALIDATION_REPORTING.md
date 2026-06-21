# Demand-Validation Reporting (M5A)

Internal, read-only summary of the `user_feedback_signal` table (M5). Turns raw
demand signals into a concise, **anonymized** report for product validation and
investor updates. Ops script only — not a public API, no dashboard.

## What signals are collected (M5)

Captured by the in-app feedback widgets (PickPage, OptionsSetupDetail) + the
AccountPage beta button. One row per signal in `user_feedback_signal`:

- `trust_useful` / `trust_not_useful` — "Was this explanation useful?"
- `would_use_again` / `would_not_use_again` — "Would you use ArthOS to review another idea?"
- `feedback_text` — optional free text ("What would make this more trustworthy?")
- `beta_interest` — AccountPage "Interested in early beta access?"
- (`confusing`, `investor_interest` reserved for future widgets)

Each row also stores `surface` (pick_detail / options_detail / account / profile / discover),
optional `user_id` (when logged in), and an opaque `session_or_device_id` for
anonymous context. No email, no password, no PII.

## How to run

```sh
make feedback-report          # human-readable summary (all time)
make feedback-report-7d       # last 7 days
make feedback-report-json     # machine-readable JSON (for report automation)
# or directly:
docker exec compose-api-1 sh -lc \
  "cd /app && PYTHONPATH=/app python scripts/report_feedback_signals.py --days 30 --json"
```

`--days N` filters to the last N days; `--json` emits structured output. An empty
table prints `total signals: 0  (no signals yet)` and exits cleanly.

## Metrics that matter for validation

- **useful_ratio** = useful / (useful + not_useful). Does the explanation layer land? Aim high.
- **would_use_again_ratio** = would_use_again / (would_use_again + would_not_use_again). Repeat intent — the core demand signal.
- **beta_interest** count — concrete pull (people opting into beta).
- **authenticated_users** vs **anonymous_contexts** — how much signal comes from real accounts vs drive-by.
- **by_surface** — where users engage (idea detail vs options vs account).
- **trend_7d** — per-day volume; is engagement growing?
- **feedback_text samples** — qualitative "why" (capped, anonymized).

## Privacy / safety

- Output **never** includes email, raw `user_id`, or session tokens — only counts, ratios, and anonymized text samples.
- Free-text samples are **count-capped** (default 5) and **length-capped** (default 160 chars).
- The report is read-only; there is **no public/read API** for feedback, so no cross-user exposure.
- Run it from an internal/ops shell (`make ...`), not from any user-facing surface.

## Example output

```
=== ArthOS — demand-validation report ===
total signals: 5
authenticated users: 1
anonymous contexts:  1
useful: 2  not useful: 1  ratio: 0.6667
would use again: 1  not yet: 0  ratio: 1.0
beta interest: 1
feedback texts: 0
by surface:
  account: 1
  pick_detail: 4
by type:
  beta_interest: 1
  trust_not_useful: 1
  trust_useful: 2
  would_use_again: 1
last 7 days:
  2026-06-21: 5
```

## How to interpret

A high **useful_ratio** says the *trust/explanation* thesis resonates — that's
the product's differentiator. A high **would_use_again_ratio** plus rising
**trend_7d** is the strongest pre-revenue demand evidence. **beta_interest** is
the cleanest opt-in for a waitlist. Treat low N with caution — these are
directional signals for product validation, not statistical proof. Report the
denominators (total signals, distinct users) alongside ratios in investor updates.
