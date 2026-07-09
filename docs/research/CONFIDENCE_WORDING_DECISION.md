# Confidence Wording — Owner Decision Record

**Date:** 2026-07-09 · **Decided by:** owner · **Status:** decided, NOT yet implemented in production copy.

## Decision

**Collapse the High and Medium confidence labels into a single "Meets the buy bar" presentation** for published stock ideas.

## Basis

`docs/research/CONFIDENCE_CALIBRATION_REPORT.md` (2026-07-09, research database):
- High-band Buys resolved at 54.4% vs the ~64% the score implies (overconfident, outside the Wilson interval);
- Medium-band Buys outperformed High-band (56.5% vs 54.4%) — the label ordering was inverted;
- discrimination AUC 0.520 — the High/Medium distinction currently conveys no reliable information to a beginner.

## Boundaries (binding until changed)

1. **No production copy changes yet.** Implementation is a separate, approval-gated change (user-facing behavior = HARD STOP).
2. **The 54% figure is a research-database statistic**, not a production statistic — it must never be displayed to users as ArthOS's track record. The calibration report's `preliminary` / `insufficient_data` labels are preserved wherever the study is referenced (Trust Center included).
3. Numeric conviction remains recorded unchanged internally (the engine, outcome labeling, and future calibration re-runs depend on it) — this is a *presentation* decision.
4. Revisit when the fitted-calibrator study activates (live decisions spanning ≥3 embargo-separated quarters, ~2027Q1) or when a promoted model changes the score's discrimination.

## Implementation sketch (for the future approved change)

Frontend label mapping only (`confidence_label` → "Meets the buy bar" for High/Medium) plus glossary entry explaining the bar; engine and API untouched; UX-judge review required before enabling.
