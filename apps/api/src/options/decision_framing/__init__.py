"""Assisted Decision Framing (Phase 11J).

Read-only, deterministic, template-based narrative + comparison +
review checklist surfaces over Phase 11I review queue rows.

NEVER uses LLM. NEVER uses ML. NEVER generates advice. NEVER imports
V2 / equity / governance / paper.engine mutation modules. NEVER
writes to any DB table.

Output forms:
  * narrative_templates  — frozen-template render of "why it appears"
  * comparison           — neutral factual A vs B deltas
  * checklist            — frozen human-review checklist (no action verbs)
  * framing_service      — orchestrator consuming 11I outputs
"""
