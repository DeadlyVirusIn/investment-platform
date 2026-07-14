# Experiment Lab Validation Report — Wave 3A (2026-07-14)

Real runs against the dev database (read-only over data; writes = the
immutable `research_run` rows themselves, retained as audit evidence:
`rr_20260714_c8528c85`, `rr_20260714_53bf9c07`, `rr_20260714_0e3e0fb2`).

## Run 1 — real data, top-30 universe by resolved-outcome coverage

Spec: stored_rules_engine · Buy · 2024-02-01→2026-07-01 · Q folds ·
min_eval_rows 30 · seed 42. Runtime **0.5s**; dataset fingerprint
`2aeb9eecc8e1edce…`; metric hash `59a7308662f2faf0…`.

Coverage: 2,553 candidates · **2,217 resolved · 336 censored**
(disclosed) · 3 usable folds · 2 skipped (2024-Q2, 2025-Q1 — resolved
< 30; the dev outcome corpus has a 2024-H2/2025 gap).

| Fold | Resolved | Censored | Hit | AUC | Brier | Base Brier | ECE | 30d ret |
|---|---|---|---|---|---|---|---|---|
| 2024-Q1 | 76 | 0 | 63.2% | 0.446 | 0.247 | 0.233 | 0.114 | +1.5% |
| 2026-Q1 | 504 | 0 | 54.4% | 0.409 | 0.261 | 0.248 | 0.118 | −0.9% |
| 2026-Q2 | 1,637 | 336 | 56.1% | 0.501 | 0.250 | 0.246 | 0.039 | +8.2% |

Benchmarks (same universe/window): buy&hold +111.9%, momentum 12-1
+111.8%, neutral 0%. Cost sensitivity (fold-mean 30d): gross +2.9% →
expected(10bps) +2.8% → stressed(20bps) +2.7%; 2/3 folds positive net.

**Honest findings:** hit rate ≈ 57.9% is real but the CONVICTION SIGNAL
carries no discrimination — AUC ≈ 0.41–0.50 (at or below chance) and the
constant base-rate classifier beats the engine's Brier in **0/3 folds**.
Calibration is poor in 2 of 3 folds (ECE 0.11+, overconfident). The
strategy's fold-mean 30d return is positive after costs but is dwarfed
by the same-window buy-and-hold benchmark (a strong bull window).

**Verdict: `INSUFFICIENT_EVIDENCE`** (3 folds < 4 required;
`beats_base_rate_majority` also FAILS — with a 4th fold this would be
`FAILS_BASELINE`). This is the Lab working as designed: the current
engine's conviction labels do not yet constitute promotable evidence.

## Run 2 — reproducibility re-run (parent = Run 1)

Runtime 0.2s. Metric hash **exactly matches** the baseline
(`59a7308662f2faf0…` == baseline). `reproducibility.matches = true`;
gate `reproducibility: PASS`; original run verified byte-identical after
the reproduction (pg-pinned in tests as well).

## Run 3 — explicit 5-asset universe (NVDA/AAPL/MSFT/AMZN/META)

152 resolved · 16 censored · 3 folds (1 skipped). Worst fold 2025-Q1:
15 resolved, **hit rate 0.0%**, single-class ⇒ AUC honestly absent.
Mean hit 32.7%; net 30d NEGATIVE at every cost tier (−6.0%…−6.2%);
momentum benchmark −2.6%, buy&hold +5.1%. Verdict
`INSUFFICIENT_EVIDENCE` (sample + folds + baseline gates all fail).
Weak folds are fully visible — nothing hidden behind the average.

## Fixture + edge coverage (test suite)

Deterministic 3-asset fixture (pg): full lifecycle, fingerprint
determinism + change-detection, censored-tail disclosure, concurrent-
duplicate 409, failed-run boundedness (`dataset_empty:` category, no
traceback), reproduce-creates-new-linked-run with original byte-identity,
task provenance, redaction. Unit: single-class folds, censored counting,
missing confidence/returns, Wilson CI bounds, fold cap disclosure,
metric-hash tolerance (10dp), gate matrix incl. REPRODUCIBILITY_FAILED
dominance.

## Resource usage

Largest real run: 0.5s wall, 5 bounded SQL queries, metrics JSON ~15KB
(cap 200KB). Reproduction 0.2s. Well inside the one-VM budget;
synchronous execution justified.

## Conclusion

The harness produces evidence, not vindication: the current stored
engine FAILS its baseline on conviction discrimination and lacks the
fold depth for any promotion claim. That is the honest, useful answer
Wave 3A was built to give. Next evidence unlock: rebuild
`historical_label` so the trained meta-labeler path (purged folds) can
run, and extend the outcome corpus to close the 2024-H2/2025 fold gap.
