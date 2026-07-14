# ArthOS Experiment Lab — Wave 3A (lab-1)

Deterministic, reproducible, resource-bounded evaluation of ArthOS
recommendation engines against simple baselines on temporal
out-of-sample windows, recorded in the EXISTING `research_run` registry.
**No migration** (registry verified sufficient: parameters/metrics JSONB,
config_hash, data_hash, parent_run_id, artifact manifest, lifecycle).
The Lab NEVER promotes a model.

- Domain: `apps/api/src/domain/evaluation/lab.py`
- API: `/api/admin/experiments/*` (owner-only, 404 posture)
- UI: `/admin/experiments` (minimal operate/verify surface — NOT the Arena)
- Flags: `EXPERIMENT_LAB_ENABLED` (server) + `VITE_EXPERIMENT_LAB` (web),
  both default OFF. Off = routes absent, no research_run writes from the
  Lab, zero behavior change.

## Phase-0 truth (what was reused vs one-off)

Reused as-is: `apps/ml/lab/splits.py` (purged walk-forward with
`assert_no_leakage` — governs future TRAINED adapters),
`apps/ml/lab/metrics.py` (Brier/ECE/MCE/AUC-with-single-class-None/
precision-recall/drawdown/turnover), `apps/ml/lab/benchmarks.py`
(buy-and-hold, deterministic 12-1 momentum, base-rate Brier),
`apps/ml/lab/registry.py` (RegistryClient: draft→running→completed|
failed|aborted, append-only metrics, NaN-rejecting canonical JSON,
config/data hashing, parent_run_id). `scripts/research/
walk_forward_baseline.py` remains a one-off CLI over `historical_label`
— which is EMPTY on current dev, so the trained-model path is
data-blocked, not code-blocked.

Dev evidence base actually available: 163k stored recommendations,
76k resolved barrier outcomes (40,178 hits / 36,131 misses / 6 neutral;
86,903 open), 4.7M price bars (1,005 assets, 2008–2026).

## Target definition (declared, single)

`resolved_barrier_hit`: among the production engine's STORED decisions
(default action=Buy), did the outcome barrier resolve as a hit
(`barrier_label = 1`) vs a miss (`-1`)? Open/censored outcomes
(`barrier_label IS NULL`) are **counted at dataset level and excluded
from resolved-only metrics with disclosure** — never treated as losses.
Portfolio-like return metrics use the STORED `realized_30d_return`
(missing values counted, never recomputed). Survival analysis is Wave 4.

## Split policy `calendar-eval-1`

The v1 adapter evaluates stored decisions — no training happens, so
train-side purge does not apply (recorded per run:
`leakage_check: not-applicable…`). Folds are calendar evaluation windows
(M/Q/Y) over `generated_at`; a window with fewer than `min_eval_rows`
RESOLVED rows is **skipped and reported**; folds are capped at 16
(oldest dropped, disclosed). Purged folds + embargo
(`apps/ml/lab/splits.py`) become mandatory the moment a trained adapter
lands.

## Experiment identity & reproducibility

- `experiment_hash` = sha256(canonical spec payload) — includes
  evaluator + split-policy versions; any field change changes it.
- `dataset_fingerprint` = sha256(bounded stored-fact aggregates: universe,
  price-bar count/min/max ts, rec count/max generated_at, resolved/
  censored counts, corporate-action count, outcome-label version,
  missing-data policy). Adding in-scope data changes it (pg-pinned);
  unrelated changes don't. No raw data duplicated; no secrets.
- `metric_hash` = sha256(fold+summary numbers rounded to 10 dp) — the
  reproducibility comparator. `POST …/reproduce` re-executes the ORIGINAL
  spec as a NEW run with `parent_run_id`; matching hashes ⇒ verified;
  mismatch ⇒ CRITICAL warning + `REPRODUCIBILITY_FAILED` verdict. The
  original run is never modified (byte-identical, pg-pinned).
- Environment capture: package/python versions ONLY (no env vars, paths,
  secrets — unit-pinned).

## Adapters, benchmarks, costs

Frozen adapter registry (`stored_rules_engine` only in v1) — no
arbitrary code, uploads, generated code, or shell, ever. Benchmarks
(same universe/dates/missing-data rules): `buy_and_hold` (equal-weight
mean of per-asset total returns, missing assets counted), `momentum_12_1`
(deterministic; needs ≥14 months or reports its error), `neutral`.
Cost scenarios: flat round-trip haircuts `zero_cost` 0 / `expected_cost`
10bps / `stressed_cost` 20bps applied to the fold-mean stored 30d
return — simulated assumptions; historical paper-trade stamps are never
recomputed.

## Metrics

Per fold: candidates / resolved / censored / with_confidence, hit rate +
Wilson 95% CI, AUC (None on single-class — pinned), Brier vs TRAIN-free
base-rate Brier, ECE (≥10 confident rows), decile calibration bands with
sample counts, precision/recall + confusion at the publication threshold,
mean stored 30d return (+ missing count). Summary: fold count, skipped
folds, dataset-level censored disclosure, mean/worst/dispersion hit
rate, mean Brier. No annualization anywhere. Weak folds are visible —
never hidden behind an average.

## Dependency decisions

- **statsmodels: NOT added** (absent from the venv). Lightweight Wilson
  intervals via closed form; benchmark-difference tests + Benjamini-
  Hochberg correction are recorded as **Wave 3A.2**, to be added with a
  compatibility check (scipy 1.17.1 / numpy 2.2.6) when multiple-
  configuration sweeps actually exist.
- **Optuna: NOT added.** v1 has no parameter search; explicit reviewable
  configurations only. Any future sweep requires nested validation so
  selection and evaluation never share a holdout (hard stop).

## Promotion readiness `lab-gates-1` (read-only; never approval)

Verdict precedence: `REPRODUCIBILITY_FAILED` (when a reproduction ran
and mismatched) → `INSUFFICIENT_EVIDENCE` (hard gates: ≥300 resolved,
≥4 folds, ≥1 benchmark, multi-fold claim) → `FAILS_BASELINE` (must beat
the base-rate Brier in a majority of measurable folds) →
`PASSES_BASELINE_WITH_LIMITATIONS` (soft gate misses / CRITICAL
warnings) → `ELIGIBLE_FOR_OWNER_REVIEW`. Owner approval remains a
separate manual action (research_run_approval — untouched by the Lab).
Failed runs can never be promoted (status `failed`; registry freezes
them).

## Resource limits

Universe ≤200 symbols (default top-50 by resolved-outcome coverage,
deterministic tie-break), range ≤3660 days, folds ≤16, cost scenarios
≤4, one active run per experiment identity (409), metrics JSON ≤200KB
(calibration bands truncated first, disclosed), spec fields all bounded/
allowlisted; violations are 422 BEFORE any work. Execution is
synchronous by design — measured 0.5s for the 2,553-candidate real run
(no second scheduler; a worker job is future work if runs ever grow).
Dry-run = a tiny explicit universe (used by the pg fixture).

## API

`POST /api/admin/experiments/runs` (bounded structured spec; optional
`research_task_id` records migration-121 provenance in run parameters,
validated) · `GET …/runs` (bounded list) · `GET …/runs/{uid}` (detail;
404 for non-Lab runs) · `POST …/runs/{uid}/reproduce` (completed runs
only; new linked run). Never exposed: SQL, filesystem paths, secrets,
credentials, env vars, stack traces (bounded categorized
`error_summary`: spec_invalid / dataset_empty / internal), hostnames.

## Security findings

No arbitrary code path exists (frozen registries + allowlisted spec);
SQL is parameterized throughout (symbols pass as arrays); resource
exhaustion bounded pre-work; duplicate concurrent identity → 409;
registry rows append-only (overwrite prevented by RegistryClient +
pg-pinned); reproducibility cannot be forged (recomputed hash
comparison); promotion through a failed run impossible; owner 404
posture on every route; agent tokens have no path here (cookie-only
guard). Residual: dataset selection bias (owner chooses universe/window)
is mitigated by the fingerprint + spec being immortalized on the run —
cherry-picking is visible, not prevented.

## Rollback

Flags off (default) → routes/UI absent, zero writes. Code revert removes
the Lab; research_run rows already written are immutable audit history
(harmless, self-describing). No schema to reverse.

## Promotion gates (prod)

Rides the standard promotion plan; before enabling in prod: re-measure
runtime against prod volumes, confirm registry migration 109 present
(it is — prod head), owner smoke of one run + one reproduction.

## Wave 3A.1 (lab-1.1, 2026-07-14)

- `model_versions` spec scoping + CRITICAL replay-pooling warning: dev
  history contains replay variants (same decisions under several
  model_version strings); unscoped multi-version corpora now fail the
  no-critical-warnings gate. Manifest records
  `distinct_model_versions` + the filter.
- **Matched event-horizon benchmark** (comparable accounting): per
  resolved event, stored engine 30d return vs the same asset's
  buy-and-hold over the same horizon from the same stored entry price;
  excess distribution + share-beating with Wilson CI. Return-relative
  promotion claims must use this basis; the calendar-window benchmarks
  remain context only.
- historical_label root cause + rebuild, outcome-gap audit (no backfill
  justified), trained-adapter gate verdict (BLOCKED on temporal depth):
  see `docs/research/HISTORICAL_LABEL_ROOT_CAUSE.md`,
  `OUTCOME_RECONSTRUCTION_AUDIT.md`,
  `EXPERIMENT_LAB_EVIDENCE_UNLOCK_REPORT.md`.

## Known limitations

- Trained-model path (LightGBM meta-labeler) is data-blocked:
  `historical_label` is empty on dev — the purged-fold machinery is
  ready but unexercised in the Lab until that dataset is rebuilt.
- Benchmark returns (buy&hold/momentum) and strategy 30d returns are not
  yet on an identical accounting basis (calendar-window total vs
  fold-mean 30d) — compared side-by-side, not netted; Arena work.
- No statistical significance tests yet (Wave 3A.2, with statsmodels).
- Synchronous execution; no cancellation mid-run (runs are seconds).
- No survival analysis for censored outcomes (Wave 4; counts disclosed).
