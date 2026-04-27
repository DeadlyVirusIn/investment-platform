"""Cognitive Guardrails Layer (Phase 11K).

Read-only interpretation guardrails over Phase 11H scores, 11I
buckets/ranking, and 11J narratives. NEVER changes scoring, ranking,
narrative, or bucket logic. NEVER persists. NEVER calls LLMs.

Output is always a structured set of plain-English clarifications
that emphasise:
  * Scores are deterministic rule-based review values, not forecasts
  * Buckets are review categories, not selections or rejections
  * Rankings reflect ordering rules only — never preference
  * Outputs do NOT mean expected profitability, probability of
    success, suitability, instruction to act, or live signal
"""
