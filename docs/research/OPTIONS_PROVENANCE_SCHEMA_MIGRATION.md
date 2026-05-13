# Phase C — denormalized provenance schema (DESIGN; not implemented)

Status: deferred (Phase Opt-B3a Phase B, 2026-05-13)

Phase B (chain-integrity invariants) lives entirely in the
`_read_chains` / `_select_run_batch` selection path. It guarantees
that every shadow_decision row was produced from a single coherent
chain batch. **Provenance lookup, however, still requires a join**
(see `OPTIONS_SHADOW_PROVENANCE_FOLLOWUP.md`).

This document records the design for Phase C — denormalized
provenance columns + an `ingest_batch_id` concept — so it can be
implemented quickly when the operational triggers fire.

## Triggers to revisit

* Chain retention/partitioning starts truncating rows referenced by
  older shadow decisions.
* Audit queries exceed comfortable join cost (50 ms+).
* Cross-provider learning analysis becomes painful.
* Tradier sandbox → production migration; provider audit becomes
  load-bearing.

## Schema migration shape

### Add to `options_chain_snapshot`

```sql
ALTER TABLE options_chain_snapshot
  ADD COLUMN ingest_batch_id UUID;
CREATE INDEX ix_options_chain_snapshot_batch_id
    ON options_chain_snapshot (ingest_batch_id);
```

`ingest_batch_id` is generated once per `ingest_universe()` call (one
UUID stamped onto every row of the same per-cycle ingest). The
existing `(snapshot_at_utc, provider, provider_version)` triple
already serves as a logical batch key; `ingest_batch_id` makes that
explicit and resilient to clock-skew or duplicate timestamps.

### Add to `options_shadow_decision_log`

```sql
ALTER TABLE options_shadow_decision_log
  ADD COLUMN source_snapshot_at_utc      TIMESTAMPTZ,
  ADD COLUMN source_provider             TEXT,
  ADD COLUMN source_provider_version     TEXT,
  ADD COLUMN source_batch_id             UUID,
  ADD COLUMN source_chain_age_seconds    INTEGER,
  ADD COLUMN invariant_version           SMALLINT NOT NULL DEFAULT 1;
CREATE INDEX ix_options_shadow_decision_source_batch
    ON options_shadow_decision_log (source_batch_id);
CREATE INDEX ix_options_shadow_decision_source_provider_version
    ON options_shadow_decision_log (source_provider_version);
```

`invariant_version` increments on each future round of chain-selection
hardening. Allows learning queries to filter by guarantees in force
when the row was persisted.

### Backfill (one-time)

```sql
-- For each shadow decision created post-Phase-B (single-batch runs),
-- the source batch is unambiguous via the join.
UPDATE options_shadow_decision_log sd
   SET source_snapshot_at_utc      = cs.snapshot_at_utc,
       source_provider             = cs.provider,
       source_provider_version     = cs.provider_version,
       source_chain_age_seconds    = cs.quote_age_seconds,
       invariant_version           = 2
  FROM options_chain_snapshot cs
 WHERE sd.option_symbol = cs.option_symbol
   AND DATE(cs.snapshot_at_utc) = sd.run_date
   AND sd.invariant_version = 1
   AND sd.created_at >= '<phase_b_activation_ts>';
```

Pre-Phase-B rows (the 7505 currently in `options_shadow_decision_log`)
remain at `invariant_version=1` and CANNOT be cleanly backfilled
because they reference rows from multiple batches by design. They
stay as historical artifacts and are excluded from learning training
sets via `WHERE invariant_version >= 2`.

## Evaluator changes when Phase C lands

`_persist()` in `shadow_evaluator.py` would write the four `source_*`
columns directly from the picked batch (already known at evaluation
time via `_select_run_batch`). Zero additional joins.

## Phase B is enough until Phase C is needed

Phase B's batch-coherent invariant means every post-Phase-B
`options_shadow_decision_log` row has unambiguous lineage to exactly
one chain batch via the natural join. No data is lost; Phase C only
removes the join.
