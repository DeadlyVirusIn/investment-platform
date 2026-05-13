# Deferred — denormalized provenance on `options_shadow_decision_log`

Status: deferred (Phase Opt-B3a Step 6a, 2026-05-13)

## Decision

Step 6a chose **join-based provenance** (shadow_decision_log
× options_chain_snapshot on (run_date / option_symbol)) over schema
augmentation. Provider, provider_version, quote_age_seconds, and the
liquidity profile that admitted each chain row remain on the chain
snapshot side. Shadow rows are pure-decision artifacts.

## Rationale for the deferral

* Ships Step 6a faster — no migration, no backfill.
* Joins work cleanly for the first 30-day audit window.
* Avoids freezing schema choices before learning queries are designed.

## Triggers to revisit

Augment the `options_shadow_decision_log` schema if any of these hit:

* Cross-provider learning analysis becomes painful via repeated joins.
* `options_chain_snapshot` retention/partitioning starts truncating
  rows that shadow rows still reference.
* Audit queries (regulatory or post-incident) need self-contained
  shadow rows independent of chain retention.
* Tradier sandbox / production swap occurs — provider audit becomes
  more critical.

## Migration shape (when triggered)

Add four columns:

| Column | Type | Source |
|---|---|---|
| `provider` | `TEXT` | join from options_chain_snapshot |
| `provider_version` | `TEXT` | join from options_chain_snapshot |
| `liquidity_profile_name` | `TEXT` | from chain ingest log; needs to be persisted at ingest time too |
| `underlying_quote_age_seconds` | `INTEGER` | join from options_chain_snapshot |

Backfill:
```sql
UPDATE options_shadow_decision_log sd
   SET provider = cs.provider,
       provider_version = cs.provider_version,
       underlying_quote_age_seconds = cs.quote_age_seconds
  FROM options_chain_snapshot cs
 WHERE sd.option_symbol = cs.option_symbol
   AND DATE(cs.snapshot_at_utc) = sd.run_date;
```

`liquidity_profile_name` requires an additional schema change to
`options_chain_snapshot` (or equivalent ingest log) to persist the
profile that admitted each row. Currently the profile name lives
only in the per-cycle ingest log line, not on the chain row itself.

## Until then

Provenance lookup pattern for any shadow row:

```sql
SELECT sd.run_date, sd.option_symbol, sd.would_trade, sd.reason,
       cs.provider, cs.provider_version, cs.quote_age_seconds,
       cs.snapshot_at_utc
  FROM options_shadow_decision_log sd
  JOIN options_chain_snapshot cs USING (option_symbol)
 WHERE sd.run_date = '2026-05-13'
   AND DATE(cs.snapshot_at_utc) = sd.run_date
 ORDER BY sd.created_at DESC
 LIMIT 50;
```
