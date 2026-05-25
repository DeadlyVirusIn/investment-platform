"""Phase L reasoning audit recorder.

Persists envelope + render-time metadata to `reasoning_audit`. Idempotent
on envelope_hash — re-rendering an identical envelope updates nothing.

Append-only contract: no UPDATE path exposed.
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.reasoning.envelope import ReasoningEnvelope


def record_envelope(
    session: Session,
    envelope: ReasoningEnvelope,
    *,
    paper_trade_id: Optional[str] = None,
) -> str:
    """Persist envelope; returns envelope_hash.

    Idempotent: if a row with the same envelope_hash already exists,
    leaves it intact and returns the existing hash.
    """
    h = envelope.envelope_hash()
    payload = {
        "envelope_hash": h,
        "skeleton_id": envelope.skeleton_id.value,
        "slot_fills_json": json.dumps(envelope.slot_fills),
        "invalidation_json": json.dumps(
            {
                "condition_vocab": envelope.invalidation.condition_vocab,
                "threshold": envelope.invalidation.threshold,
            }
        ),
        "thesis_json": json.dumps(
            {
                "horizon": envelope.thesis.horizon.value,
                "expected_signal": envelope.thesis.expected_signal.value,
            }
        ),
        "uncertainty_markers": json.dumps(
            [m.value for m in envelope.uncertainty_markers]
        ),
        "source": envelope.source.value,
        "envelope_generated_at": envelope.generated_at,
        "paper_trade_id": paper_trade_id,
    }
    session.execute(
        text(
            "INSERT INTO reasoning_audit "
            "  (envelope_hash, skeleton_id, slot_fills_json, "
            "   invalidation_json, thesis_json, uncertainty_markers, "
            "   source, envelope_generated_at, paper_trade_id) "
            "VALUES "
            "  (:envelope_hash, :skeleton_id, :slot_fills_json, "
            "   :invalidation_json, :thesis_json, :uncertainty_markers, "
            "   :source, :envelope_generated_at, :paper_trade_id) "
            "ON CONFLICT ON CONSTRAINT uq_reasoning_audit_envelope_hash_trade "
            "DO NOTHING"
        ),
        payload,
    )
    return h
