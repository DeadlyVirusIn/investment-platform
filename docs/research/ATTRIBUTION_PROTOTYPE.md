# Attribution Prototype — Reconciliation Report & Limitations (Sprint 2)

**Date:** 2026-07-09 · **Branch:** `feature/elite-arthos-provable-ideas` · Dev-only, flag-off, nothing deployed.

## Method

`apps/ml/attribution.py` uses LightGBM's native `pred_contrib=True` (TreeSHAP) on the **actual shadow meta-labeler architecture** (binary objective, the `apps/ml/dataset.py` feature set). Contributions are additive in raw-score (log-odds) space with the expected value in the trailing column.

## Reconciliation result — VERIFIED

`base_value + Σ feature_contributions == raw_score` holds to **≤ 2.3e-15** on controlled predictions (committed fixture `docs/research/attribution_fixture.json`), and is enforced at runtime: `compute_attributions` raises `AttributionError` if any row deviates beyond 1e-6, if outputs contain NaN/Inf, if the contribution matrix has the wrong shape, or if any feature lacks beginner language.

**Raw → displayed conversion:** binary objective ⇒ `probability = sigmoid(raw_score)`. Contributions do **not** decompose the probability linearly (log-odds space); the beginner payload therefore shows only *relative influence shares*, never per-factor probability points.

## Test coverage (9 tests, `apps/api/tests/unit/test_ml_attribution.py`)

positive drivers · negative drivers · NaN feature values (native missing-value path still reconciles; value surfaced as `null`, never imputed for display) · one-hot encoded features mapped to beginner language · unknown-feature rejection · two distinct model artifacts (distinct `model_version` content hashes, both reconcile) · NaN/Infinity output protection · provenance completeness (model_version, feature_schema_version, inference timestamp, method, raw score, base value) · beginner-payload wording contract.

## Scope honesty (forensics-driven)

Per `MODEL_AND_DATA_FORENSICS.md`: user-facing **stock** ideas are produced by the rule-based engine; the LightGBM meta-labeler is shadow-only (`ML_CAN_AFFECT_TRADES=False`, dead inference seam, no persisted artifact). Therefore:
- this attribution belongs to **research/Experiment-Lab surfaces** and any *future promoted* model;
- the idea page's existing factor narrative (from `recommendation_evidence` / family scores) remains the truthful "why" for published ideas;
- every payload carries `scope_note: "Attribution of the research (shadow) model — not the engine that published this idea."`;
- the dev UI prototype (`AttributionWorking.tsx`) renders behind `VITE_DEV_ATTRIBUTION`, absent by default, and does not replace the narrative explanation.

## Wording contract

Headline fixed to **"Factors that influenced the model result"**; limitations statement embedded in every record; no causal market claims anywhere outside the disclaimer (test-enforced).

## Limitations

1. Attribution explains the **model's score**, not the market: influence ≠ causality.
2. Log-odds additivity means magnitudes aren't probability points; we display relative shares only.
3. `model_version` is a content hash of the booster string — necessary because **no artifact registry exists yet** (forensics §10); the research_run registry (Sprint 5 spec) is the durable home.
4. Feature-schema hash covers names+ordering; the underlying one-hot ordering is data-dependent upstream (flagged in forensics) and must be frozen when the model is ever promoted.
5. Shadow-model attribution on real candidates requires the dead inference seam (`predict_proba_for_candidates`) to be exercised — deliberately out of scope until a promotion decision exists.
