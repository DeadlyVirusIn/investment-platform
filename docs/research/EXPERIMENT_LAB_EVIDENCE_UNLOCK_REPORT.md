# Experiment Lab Evidence Unlock Report — Wave 3A.1 (2026-07-14)

Investigation-first mission. Companion docs:
`HISTORICAL_LABEL_ROOT_CAUSE.md`, `OUTCOME_RECONSTRUCTION_AUDIT.md`.
Original Wave 3A runs (`rr_20260714_c8528c85`, `_53bf9c07`, `_0e3e0fb2`)
are untouched immutable evidence.

## Phase-0 frozen manifest

Baseline `dcf6934` (local=origin) · dev head `121_research_exec_provenance`
· prod verified 109 (Wave 2C read-only check; unchanged since) · backup
`.backups/devdb_full_20260714_pre3a1.dump` (425 MB, pg_restore-listable,
1045 entries) · counts: historical_label 0 → recommendations 163,262 ·
outcomes 163,218 (resolved 76,315: +1 40,178 / −1 36,131 / 0 6; open
86,903) · price_bar 4,707,935 · corporate_action 0 · assets 1,008.

## What was reconstructed (and what deliberately was not)

- `historical_label`: rebuilt via the ORIGINAL pipeline for the full
  snapshot-covered window → **1,601 rows / 36 trading days / balanced
  classes** (details + rollback in the root-cause doc).
- `recommendation_outcome`: **zero rows inserted** — the "gap" is
  recommendation-generation coverage (replay eras), not outcome
  processing; reconstructable scope was 49 immaterial rows (audit doc).
- Existing outcomes byte-untouched; all mutations dev-only, after backup.

## Lab changes (evaluator lab-1 → lab-1.1)

1. `model_versions` spec scoping (hashed identity) + **CRITICAL replay
   pooling warning** when a corpus mixes versions unscoped + manifest
   fields. Fixes the discovered Wave 3A defect (duplicate replay variants
   pooled as independent samples).
2. **Matched event-horizon benchmark** — the comparable-accounting fix:
   per resolved event, engine stored 30d return vs the SAME asset's
   buy-and-hold over the SAME horizon from the SAME stored entry price
   (exit = last close ≤ entry+30d, 7-day tolerance, exclusions counted);
   reports excess mean/median/std, share-of-events-beating-asset with
   Wilson CI. No overlapping-portfolio claims. The old
   incomparable pair (fold-mean 30d vs calendar-window buy&hold) remains
   displayed as context, never as promotion evidence.

## Re-run results (all runs retained; 4 new runs)

| Run | Scope | Folds | Resolved | Matched excess (mean / median) | Share beating asset (CI95) | Verdict |
|---|---|---|---|---|---|---|
| `rr_20260714_f74e6d5e` original spec under lab-1.1 | 8 versions POOLED | 3 | 2,217 | +0.18% / ~0.00% | 52.0% (49.7–54.3%) | INSUFFICIENT_EVIDENCE + **CRITICAL pooling warning** |
| `rr_20260714_1b2d6c25` live engine only (`0.1.0`) | clean | 1 | 549 | +0.82% / +1.28% | 66.1% (56.8–74.3%) | INSUFFICIENT_EVIDENCE (1 fold) |
| `rr_20260714_442e993c` reproduce live-only | clean | 1 | 549 | identical | identical | metric hash **EXACT match** |
| `rr_20260714_5ee77547` 2024+2025 replay eras | clean | 1 | 76 | **−0.60% / −0.33%** | 30.6% | INSUFFICIENT_EVIDENCE |

Honest reading:

- On a comparable basis the pooled engine's per-event edge over simply
  holding the same asset is **statistically indistinguishable from zero**
  (CI straddles 50%; median excess ≈ 0). The old "2.9% strategy vs 111.9%
  buy&hold" contrast was an accounting artifact in BOTH directions.
- The live engine (2026-Q2 only) shows a *suggestive* +0.82% mean excess
  with 66% share (CI 57–74%) — but one fold, 109 matched events, AUC
  0.498. Suggestive ≠ evidence; verdict stays INSUFFICIENT.
- The 2024/2025 replay eras show NEGATIVE excess — the engine underperformed
  its own assets in those windows.
- Fold depth did NOT improve (3 max): the gap is generation coverage, and
  Wave 3A's 3-fold ceiling stands until either a new replay campaign or
  live accumulation adds windows.

## Trained-adapter (LightGBM) gate verdict: **BLOCKED**

Point-in-time feature integrity PASSES within 2026-04-22→06-17, but 36
trading days ⇒ ≤2 monthly folds (<4 required) and 294 Buy labels. No
adapter built; no tuning performed; Optuna not added; statsmodels not
added (descriptive evidence + Wilson CIs only — no multi-configuration
comparison happened, so no correction machinery is owed). Unlock ≈ late
2026-08 via daily snapshot accumulation (+ optional weekly label job,
separate approval).

## Security/integrity review outcomes

Backfill overwrite risk: eliminated (zero outcome writes; label upsert
idempotent into an empty table). Lookahead: label pipeline entries start
at as_of+1; matched benchmark uses stored entry price and forward closes
only; same-bar ambiguity policy recorded as binding for any future
outcome campaign. Survivorship: matched benchmark uses each event's own
asset (no index survivorship); missing exit bars excluded AND counted.
Cherry-picking: model_versions filter is part of the hashed identity —
scope choices are immortalized on the run. No secrets/paths in any new
payload (existing redaction tests still green).

## Gates

Backend: lab 42 (unit 26 + pg 16) green; combined board/provenance/splits
selection 134 green; earlier full W1+2+3 selection 371 green pre-change and
lab suite fully re-verified post-change. Web: tsc/eslint/lint:portfolio/
build green; Vitest 287. Runtime: heaviest re-run 0.5s.

## Remaining limitations

- 3-fold ceiling until new windows exist (replay campaign = separate
  approval; live accumulation = time).
- Matched benchmark horizon fixed at 30d (matches the stored return
  fact); other horizons need stored facts first.
- Trained adapter blocked (above). Arena (3B) still premature: one
  adapter, INSUFFICIENT verdicts.
