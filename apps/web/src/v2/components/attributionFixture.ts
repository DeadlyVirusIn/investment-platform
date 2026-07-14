// Auto-generated from docs/research/attribution_fixture.json (Sprint 2).
// Dev-preview data only — regenerate via the attribution test fixture step.
import type { AttributionPayload } from './AttributionWorking';

export const ATTRIBUTION_FIXTURE: AttributionPayload = {
  "headline": "Factors that influenced the model result",
  "supporting": [
    {
      "label": "recent price momentum (about a month), market-adjusted",
      "relative_influence": 0.7857
    },
    {
      "label": "the overall market trend (bull)",
      "relative_influence": 0.0715
    },
    {
      "label": "the overall market trend (bear)",
      "relative_influence": 0.0
    }
  ],
  "cautionary": [
    {
      "label": "size of day-to-day price swings",
      "relative_influence": 0.1428
    }
  ],
  "model_version": "lgbm-3711c69290b2eac6",
  "feature_schema_version": "fs-3a4fd7b8349bb46d",
  "as_of": "2026-07-09T12:00:00+00:00",
  "limitations": "These are the factors that influenced the model result \u2014 a statistical read of past patterns, not reasons the stock will rise or fall. Influences are measured in the model's internal score space; they are relative, can change as data updates, and do not imply causality.",
  "scope_note": "Attribution of the research (shadow) model \u2014 not the engine that published this idea."
};
