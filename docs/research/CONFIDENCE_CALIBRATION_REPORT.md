# Confidence Calibration Study — Report (Sprint 3)

**Date:** 2026-07-09 · **Data:** local dev DB (read-only) · **Displayed confidence unchanged** — this is a measurement, not a product change.
**Artifacts:** `calibration_metrics.json` (machine-readable, full), `calibration_reliability.svg`, script `scripts/research/confidence_calibration_study.py`.

## 1. What was measured

Whether the stock confidence users see (`recommendation.conviction`, the rule-engine agreement score whose thresholds produce Low/Medium/High) is honest when read as a probability that a **Buy** recommendation *hits* its barrier outcome (`recommendation_outcome.barrier_label = 1` vs `-1`; ±2σ barriers, 63/10/30-bar horizons per signal type, labeled ≥30 days after generation).

## 2. Sample accounting (nothing silently dropped)

| Count | Value |
|---|---|
| Recommendations total (dev DB) | 139,742 |
| Outcome rows | 139,698 |
| Unresolved (barrier_label NULL — includes censored; schema has **no censored flag**, rows retry forever: forensics §6) | 66,364 |
| Neutral (label 0) | 5 (excluded, counted) |
| Missing entry price | 0 |
| **Buy + resolved + scored** | **7,752** → live 2,809 · replay 4,943 |

Cohorts are separated: `live` (`model_version NOT LIKE '%+replay:%'`) vs `replay` (engine re-run over history). Headline claims below use **live only**; replay corroborates.

## 3. Methodology and leakage audit

- **No random splits.** Design: calendar-quarter walk-forward with a 100-day embargo (> the 63-trading-bar max horizon) between any training row's decision time and an evaluation fold's start.
- **Leakage audit result:** identity-mapping metrics are leak-free *by construction* — every prediction (`conviction/100`) was stamped at `generated_at`, strictly before its outcome; no fitting occurs. The in-sample base-rate Brier is reported only as a hindsight floor. Fitted calibrators (Platt, isotonic) were only ever trained on embargo-separated history — and that gate **failed everywhere** (below), so no fitted-calibrator numbers are reported at all rather than reporting leaky ones.
- **Decision timestamps:** `generated_at`; **outcome horizon:** barrier first-touch within `barrier_n_bars`; **as-of inputs:** conviction only (no post-decision features).

## 4. Data-blocked portion (honest negative)

**Calibrator comparison (isotonic vs sigmoid vs baseline) is not scientifically computable today:**
- every **live** resolved Buy sits in a single quarter (2026Q2) — with a 100-day embargo there is no prior training window;
- the **replay** cohort's quarters each have < 500 embargo-clean training rows.

This triggers the program's "historical data cannot support a valid result" rule **for this sub-question only**. Earliest useful re-run: once live Buy decisions span ≥ 3 calendar quarters (~2027Q1 at current cadence). MAPIE: not materially useful until then (nothing valid to wrap).

## 5. Findings — the displayed mapping (live cohort, n = 2,809)

| Metric | Value | Read |
|---|---|---|
| Hit rate | 54.8% | base rate for resolved live Buys |
| Brier (conviction/100) | 0.2540 | **worse than the 0.2477 constant-base-rate floor** |
| ECE / MCE | 6.2% / 8.6% | systematic miscalibration |
| **AUC** | **0.520** | conviction barely ranks hits above misses (replay: 0.492 ≈ none) |
| Conviction range | 50 – 66.67 (mean 61.1) | the score uses a 17-point sliver of 0–100 |

**Product-label bands (live):**

| Band | n | Predicted mean | Observed hit rate | Wilson 95% | Verdict |
|---|---|---|---|---|---|
| Low | 0 | — | — | — | never published for Buys |
| Medium | 531 | 0.500 | **0.565** | [0.522, 0.607] | **underconfident** |
| High | 2,278 | 0.636 | **0.544** | [0.524, 0.565] | **overconfident** (~9 pts) |

**Reliability bins:** 0.50–0.60 → predicted .566 / observed .522; 0.60–0.70 → predicted .667 / observed .581. Both bins overconfident; gap grows with the score.

**The two headline problems:**
1. **Level:** "High confidence" implies ~64% hit odds; reality is ~54% — statistically outside the interval. Users are being told more certainty than the data supports.
2. **Ordering:** Medium Buys *outperformed* High Buys (56.5% vs 54.4%) — at the label level the confidence scale is not even monotone. Combined with AUC 0.52, calibration alone can only flatten everything to ≈55%: the score's problem is **discrimination**, not just scale.

**Stability (live):** by regime — uptrend n=2,529 → 54.4%; sideways n=269 → 59.9%; downtrend n=11 → insufficient. Vol-regime: high n=1,991 → 53.8%, medium n=803 → 57.2%, low n=15 → insufficient. Time stability: not assessable (single quarter). Sector: top-8 sectors reported in JSON; none contradicts the headline within CI. **Replay cohort** (n=4,943): same shape (hit 53.2%, ECE 7.8%, AUC 0.49) — corroborates that this is the score's character, not a 2026Q2 artifact.

## 6. Statistically unsupported areas

Low band (n=0) · downtrend regime (n=11) · low-vol regime (n=15) · any per-quarter live trend (one quarter) · fitted calibrators (embargo gate) — all labeled `insufficient_data`, none used for conclusions.

## 7. Go/no-go and recommendations (no product change made)

**GO — with reframing.** Calibration work should proceed, but the evidence says the first fixes are presentational and upstream, not a calibrator:
1. **Trust Center must label confidence calibration `preliminary / overconfident-at-High`** using these numbers (Sprint 7 feeds directly from `calibration_metrics.json`).
2. **Product wording decision (owner call, later):** while AUC ≈ 0.52, High-vs-Medium granularity is not supported — candidates: collapse to "meets the buy bar" or display the observed band rate ("ideas like this have hit ~54% of the time").
3. **Re-run the fitted-calibrator study** when live decisions span ≥3 embargo-separated quarters; isotonic vs sigmoid comparison per this script (already implements it; it will activate automatically once `MIN_TRAIN` is met).
4. **Discrimination beats calibration:** improving the conviction score's ranking power (or replacing it with a validated model via the Experiment Lab + research_run registry) is worth more than any calibrator; a calibrated coin-flip is still a coin-flip.
5. Dev-DB caveat: results reflect the dev database's outcome history; production has materially fewer resolved outcomes (accuracy gate "0/10 closed"), so **no user-facing claim should cite these numbers as production stats** — they are engine-character evidence.

*Displayed confidence was not modified anywhere in this sprint.*
