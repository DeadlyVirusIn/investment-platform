"""Wave 1D — Decision Replay Timeline (read-only, zero-migration).

Reconstructs what ArthOS knew, showed, did on paper, and later learned for
ONE pinned recommendation lifecycle, using immutable stored artifacts only.

HINDSIGHT FIREWALL (source- and behavior-pinned by tests):
* stored rows only — no scoring-engine imports, no model inference, no
  provider/market network calls, no current-price lookups, no
  recommendation regeneration, no INSERT/UPDATE/DELETE, no LLM;
* historical language renders under the policy applicable at each event's
  date (reuses the Delta service's ``presentation_for``);
* absence is reported as absence (completeness model), never as success.

IDENTITY RULE: public symbol lookup resolves to the latest recommendation
ONCE, then the entire replay is pinned to that recommendation id + asset id.
A later recommendation on a different asset that reuses the symbol can never
change an existing replay (pg-pinned). The owner route accepts the exact
recommendation id.

LIFECYCLE BOUNDARY (from inspected data): the lifecycle starts at the
pinned row's generation. Later rows for the SAME asset are "updates to the
same open idea" only until the pinned row's outcome resolves
(``barrier_first_touch_at``); with no resolution the window stays open.
Updates are summarized through the Delta service (no separate rules) and
capped to the most significant. Unrelated later ideas are never merged in
by symbol match — everything is asset-and-window scoped, and when nothing
reliable exists the replay stays conservative and says so.

USER ISOLATION: practice-portfolio events are included ONLY for the
authenticated user, resolved via the established ``user:<uid>:...`` book
naming convention plus the stored ``opened_by_recommendation_id`` /
``paper_trade.recommendation_id`` links. Anonymous → no paper events at
all (never another book, never the demo book presented as "your").
Cache keys include the principal, so entries can never cross users.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.domain.recommendations.delta import (
    FAMILY_META,
    presentation_for,
    _parse_families,
)

REPLAY_RULE_SET_VERSION = "replay-1"
MAX_UPDATE_EVENTS = 6
MAX_EVENTS = 40

DetailStatus = Literal["complete", "partial", "unavailable",
                       "not_evaluated", "not_recorded"]

#: deterministic same-timestamp semantic order (pinned by tests)
TYPE_PRIORITY = {
    "idea_generated": 0,
    "preflight": 1,
    "posture": 2,
    "update": 3,
    "paper_action": 4,
    "outcome": 5,
    "thesis": 6,
    "lesson": 7,
}


@dataclass(frozen=True)
class TimelineEvent:
    key: str                      # stable public key (no UUIDs)
    type: str
    occurred_at: str              # ISO
    title: str
    summary: str
    label: str                    # EvidenceBadge vocabulary-ish status
    source: str
    detail_status: DetailStatus
    details: dict[str, Any] = field(default_factory=dict)   # public-safe

    def public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "type": self.type,
            "occurred_at": self.occurred_at, "title": self.title,
            "summary": self.summary, "label": self.label,
            "source": self.source, "detail_status": self.detail_status,
            "details": self.details,
        }


@dataclass
class ReplayInputs:
    """Everything the assembler may consult — loaded once, no lazy I/O."""
    symbol: str
    rec_id: str
    asset_id: str
    generated_at: dt.datetime
    action: str | None
    confidence_label: str | None
    family_scores: dict[str, float]
    stale_data: bool
    engine_version: str | None
    snapshot_hash_present: bool
    price_at: float | None
    outcome: dict[str, Any] | None            # barrier_label/first_touch/dates
    verdict: dict[str, Any] | None            # verdict/limitations/created_at/checks(owner)
    posture: dict[str, Any] | None            # posture/event created_at
    updates: list[dict[str, Any]]             # delta summaries of later rows
    paper: list[dict[str, Any]]               # THIS user's linked activity only
    theses: list[dict[str, Any]]              # asset-level, labeled related
    lessons: list[dict[str, Any]]
    predates_preflight: bool
    predates_posture: bool
    user_scoped: bool                         # an authenticated user was applied
    owner: bool


# ---------------------------------------------------------------------------
# Loading (bounded; every subquery keyed by stored identifiers)
# ---------------------------------------------------------------------------

def _finite(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def resolve_pinned(db: Session, symbol: str) -> tuple[str, str] | None:
    """Public flow step 1: symbol → latest recommendation, ONCE."""
    row = db.execute(text(
        "SELECT r.id, r.asset_id FROM recommendation r "
        "JOIN asset a ON a.id = r.asset_id "
        "WHERE upper(a.symbol) = upper(:s) "
        "ORDER BY r.generated_at DESC, r.id DESC LIMIT 1"
    ), {"s": symbol}).first()
    return (row[0], row[1]) if row else None


def load_inputs(
    db: Session, rec_id: str, *, user_id: str | None = None,
    owner: bool = False,
) -> ReplayInputs | None:
    rec = db.execute(text(
        "SELECT r.id, r.asset_id, r.generated_at, r.action, r.rationale, "
        "r.model_version, r.snapshot_hash, a.symbol "
        "FROM recommendation r JOIN asset a ON a.id = r.asset_id "
        "WHERE r.id = :i"
    ), {"i": rec_id}).first()
    if rec is None:
        return None

    try:
        rationale = json.loads(rec.rationale or "{}",
                               parse_constant=lambda v: float("nan"))
        if not isinstance(rationale, dict):
            rationale = {}
    except (ValueError, TypeError):
        rationale = {}
    scores, _malformed = _parse_families(rationale.get("family_scores"))

    out_row = db.execute(text(
        "SELECT barrier_label, barrier_first_touch_at, "
        "price_at_recommendation, created_at, updated_at "
        "FROM recommendation_outcome WHERE recommendation_id = :r LIMIT 1"
    ), {"r": rec.id}).first()
    outcome = None
    price_at = None
    if out_row:
        price_at = _finite(out_row[2])
        outcome = {
            "barrier": int(out_row[0]) if out_row[0] is not None else None,
            "first_touch_at": out_row[1].isoformat() if out_row[1] else None,
            "recorded_at": out_row[4].isoformat() if out_row[4] else None,
        }
    if price_at is None:
        price_at = _finite(db.execute(text(
            "SELECT close FROM price_bar WHERE asset_id = :a AND "
            "timeframe = '1d' AND ts <= :g ORDER BY ts DESC LIMIT 1"
        ), {"a": rec.asset_id, "g": rec.generated_at}).scalar())

    v_row = db.execute(text(
        "SELECT verdict, limitations_json, checks_json, rule_set_version, "
        "created_at FROM recommendation_preflight "
        "WHERE recommendation_id = :r ORDER BY created_at DESC LIMIT 1"
    ), {"r": rec.id}).first()
    verdict = None
    posture = None
    if v_row:
        try:
            lims = [c.get("beginner_text") for c in
                    json.loads(v_row[1] or "[]")
                    if isinstance(c, dict) and c.get("beginner_text")]
        except (ValueError, TypeError):
            lims = []
        verdict = {
            "verdict": v_row[0], "limitations": lims,
            "rule_set_version": v_row[3],
            "checks_json": v_row[2] if owner else None,
            "created_at": v_row[4],
        }
        p_row = db.execute(text(
            "SELECT posture, created_at FROM system_posture_event "
            "WHERE created_at <= :t "
            "ORDER BY created_at DESC, id DESC LIMIT 1"
        ), {"t": v_row[4]}).first()
        if p_row:
            posture = {"posture": p_row[0],
                       "created_at": p_row[1].isoformat()}

    # lifecycle window end = outcome resolution when it exists
    window_end = None
    if outcome and outcome["first_touch_at"]:
        window_end = outcome["first_touch_at"]

    # updates: later rows for the SAME asset inside the window, summarized
    # through the delta service (no separate rules). Consecutive-pair
    # comparison over a bounded scan.
    from apps.api.src.domain.recommendations.delta import (
        RecFacts, compute as delta_compute,
    )
    later = db.execute(text(
        "SELECT id, generated_at, action, rationale FROM recommendation "
        "WHERE asset_id = :a AND (generated_at, id) > (:g, :i) "
        + ("AND generated_at <= :we " if window_end else "")
        + "ORDER BY generated_at ASC, id ASC LIMIT 40"
    ), {"a": rec.asset_id, "g": rec.generated_at, "i": rec.id,
        **({"we": window_end} if window_end else {})}).all()

    def _facts(row_id, gen, action, rationale_raw) -> RecFacts:
        try:
            rat = json.loads(rationale_raw or "{}",
                             parse_constant=lambda v: float("nan"))
            if not isinstance(rat, dict):
                rat = {}
        except (ValueError, TypeError):
            rat = {}
        s, m = _parse_families(rat.get("family_scores"))
        return RecFacts(
            rec_id=row_id, generated_at=gen, action=action,
            confidence_label=rat.get("confidence_label"),
            family_scores=s, malformed_families=m,
            stale_data=bool(rat.get("stale_data", False)),
            price_at=None, outcome_barrier=None, has_outcome_row=False,
            verdict=None, verdict_limitations=(), posture=None,
        )

    updates: list[dict[str, Any]] = []
    prev = _facts(rec.id, rec.generated_at, rec.action, rec.rationale)
    for row in later:
        cur = _facts(row[0], row[1], row[2], row[3])
        d = delta_compute(rec.symbol, cur, prev)
        if d.changes and d.changes[0].significance in ("meaningful", "large"):
            updates.append({
                "occurred_at": row[1].isoformat(),
                "summary": d.summary,
                "top_kind": d.changes[0].kind,
                "direction": d.changes[0].direction,
            })
        prev = cur
    updates = updates[-MAX_UPDATE_EVENTS:]

    # paper activity — strictly the authenticated user's books
    paper: list[dict[str, Any]] = []
    if user_id:
        rows = db.execute(text(
            "SELECT pp.id, pp.quantity, pp.avg_cost, pp.opened_at, "
            "pp.closed_at, pp.is_open, pp.realized_pnl, "
            "ot.fill_price AS open_fill, ot.execution_cost_json AS open_cost, "
            "ct.fill_price AS close_fill, ct.execution_cost_json AS close_cost "
            "FROM paper_position pp "
            "JOIN paper_portfolio pf ON pf.id = pp.portfolio_id "
            "LEFT JOIN paper_trade ot ON ot.id = pp.opening_trade_id "
            "LEFT JOIN paper_trade ct ON ct.id = pp.closed_by_trade_id "
            "WHERE pp.opened_by_recommendation_id = :r "
            "AND pf.name LIKE :owner_prefix"
        ), {"r": rec.id, "owner_prefix": f"user:{user_id}:%"}).mappings().all()
        for p in rows:
            paper.append({
                "quantity": _finite(p["quantity"]),
                "avg_cost": _finite(p["avg_cost"]),
                "opened_at": p["opened_at"].isoformat() if p["opened_at"] else None,
                "closed_at": p["closed_at"].isoformat() if p["closed_at"] else None,
                "is_open": bool(p["is_open"]),
                "realized_pnl": _finite(p["realized_pnl"]),
                "open_cost_stamp": _cost_stamp(p["open_cost"]),
                "close_cost_stamp": _cost_stamp(p["close_cost"]),
            })

    theses: list[dict[str, Any]] = []
    if settings.THESIS_LEDGER_ENABLED:
        for t_row in db.execute(text(
            "SELECT title, status, status_changed_at, created_at "
            "FROM thesis WHERE asset_id = :a "
            "ORDER BY created_at ASC LIMIT 5"
        ), {"a": rec.asset_id}).all():
            theses.append({
                "title": t_row[0], "status": t_row[1],
                "status_changed_at": t_row[2].isoformat() if t_row[2] else None,
                "created_at": t_row[3].isoformat() if t_row[3] else None,
            })

    lessons: list[dict[str, Any]] = []
    if settings.LEARNING_LOOP_ENABLED:
        for l_row in db.execute(text(
            "SELECT what_happened, review_state, provenance, created_at, "
            "reviewed_at FROM lesson WHERE recommendation_id = :r "
            "ORDER BY created_at ASC LIMIT 5"
        ), {"r": rec.id}).all():
            lessons.append({
                "what_happened": l_row[0], "review_state": l_row[1],
                "provenance": l_row[2],
                "created_at": l_row[3].isoformat() if l_row[3] else None,
                "reviewed_at": l_row[4].isoformat() if l_row[4] else None,
            })

    return ReplayInputs(
        symbol=rec.symbol, rec_id=rec.id, asset_id=rec.asset_id,
        generated_at=rec.generated_at, action=rec.action,
        confidence_label=rationale.get("confidence_label"),
        family_scores=scores,
        stale_data=bool(rationale.get("stale_data", False)),
        engine_version=rec.model_version,
        snapshot_hash_present=bool(rec.snapshot_hash),
        price_at=price_at, outcome=outcome, verdict=verdict, posture=posture,
        updates=updates, paper=paper, theses=theses, lessons=lessons,
        predates_preflight=v_row is None,
        predates_posture=posture is None,
        user_scoped=user_id is not None,
        owner=owner,
    )


def _cost_stamp(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        stamp = raw if isinstance(raw, dict) else json.loads(raw)
        if not isinstance(stamp, dict):
            return None
        return {
            "gross_notional": stamp.get("gross_notional"),
            "commission": stamp.get("commission"),
            "slippage_cost": stamp.get("slippage_cost"),
            "total_cost": stamp.get("total_cost"),
            "net_notional": stamp.get("net_notional"),
            "cost_model_version": stamp.get("cost_model_version")
            or stamp.get("version"),
        }
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Assembly (pure)
# ---------------------------------------------------------------------------

def assemble(i: ReplayInputs) -> dict[str, Any]:
    events: list[TimelineEvent] = []
    unavailable: list[dict[str, str]] = []

    # 1. idea generated
    supportive = sorted(k for k, v in i.family_scores.items() if v > 0)
    cautionary = sorted(k for k, v in i.family_scores.items() if v < 0)
    events.append(TimelineEvent(
        key="generated", type="idea_generated",
        occurred_at=i.generated_at.isoformat(),
        title="Idea generated",
        summary=(
            f"ArthOS recorded a {i.action or 'Hold'} read at "
            f"{presentation_for(i.confidence_label, i.generated_at)}."
        ),
        label="proven", source="recommendation", detail_status="complete",
        details={
            "supporting": [FAMILY_META.get(k, k.replace('_', ' '))
                           for k in supportive],
            "cautionary": [FAMILY_META.get(k, k.replace('_', ' '))
                           for k in cautionary],
            "stored_price": i.price_at,
            "provenance_recorded": i.snapshot_hash_present,
            "data_flagged_stale": i.stale_data,
        },
    ))

    # 2. preflight
    if i.verdict:
        v = i.verdict
        details: dict[str, Any] = {"limitations": v["limitations"]}
        if i.owner:
            details["rule_set_version"] = v["rule_set_version"]
            try:
                details["checks"] = json.loads(v["checks_json"] or "[]")
            except (ValueError, TypeError):
                details["checks"] = []
        events.append(TimelineEvent(
            key="preflight", type="preflight",
            occurred_at=v["created_at"].isoformat(),
            title="Publication check",
            summary={
                "READY": "Published normally after the publication check.",
                "READY_WITH_LIMITATIONS":
                    "Published with honest limitations after the "
                    "publication check.",
                "HOLD": "Held back from publication at this evaluation.",
                "BLOCKED": "Blocked from publication at this evaluation.",
            }.get(v["verdict"], "Publication check recorded."),
            label="proven" if v["verdict"] in ("READY",
                                               "READY_WITH_LIMITATIONS")
            else "degraded",
            source="preflight", detail_status="complete", details=details,
        ))
    else:
        unavailable.append({
            "section": "publication_preflight",
            "reason": "This idea predates publication-preflight recording.",
        })

    # 3. posture
    if i.posture:
        p = i.posture["posture"]
        events.append(TimelineEvent(
            key="posture", type="posture",
            occurred_at=i.posture["created_at"],
            title="System conditions",
            summary={
                "NORMAL": "New ideas were publishing normally at the time.",
                "RESTRICTED": "New ideas were publishing with limitations "
                              "at the time.",
                "SAFE": "New ideas were paused at the time.",
            }.get(p, "System posture recorded."),
            label="proven" if p == "NORMAL" else "degraded",
            source="posture", detail_status="complete",
            details={"posture": p},
        ))
    elif not i.predates_preflight:
        unavailable.append({
            "section": "system_posture",
            "reason": "System posture was not evaluated for this idea.",
        })

    # 4. updates (delta-derived)
    for idx, u in enumerate(i.updates):
        events.append(TimelineEvent(
            key=f"update:{u['occurred_at'][:19]}:{idx}", type="update",
            occurred_at=u["occurred_at"],
            title="Idea updated",
            summary=u["summary"],
            label="preliminary", source="recommendation",
            detail_status="complete",
            details={"direction": u["direction"]},
        ))

    # 5/6. paper activity (+ cost stamps) — authenticated user only
    for idx, p in enumerate(i.paper):
        open_details: dict[str, Any] = {
            "quantity": p["quantity"], "avg_cost": p["avg_cost"],
            "practice_value": (round(p["quantity"] * p["avg_cost"], 2)
                               if p["quantity"] and p["avg_cost"] else None),
        }
        if p["open_cost_stamp"]:
            open_details["execution_costs"] = p["open_cost_stamp"]
            cost_status: DetailStatus = "complete"
        else:
            open_details["execution_costs_note"] = (
                "Execution-cost detail was not recorded for this practice "
                "trade.")
            cost_status = "partial"
        if p["opened_at"]:
            events.append(TimelineEvent(
                key=f"paper_open:{idx}", type="paper_action",
                occurred_at=p["opened_at"],
                title="Added to your practice portfolio",
                summary="You added this idea to your practice portfolio "
                        "(practice money only).",
                label="proven", source="paper",
                detail_status=cost_status, details=open_details,
            ))
        if p["closed_at"]:
            close_details: dict[str, Any] = {
                "realized_practice_pnl": p["realized_pnl"],
            }
            if p["close_cost_stamp"]:
                close_details["execution_costs"] = p["close_cost_stamp"]
            events.append(TimelineEvent(
                key=f"paper_close:{idx}", type="paper_action",
                occurred_at=p["closed_at"],
                title="Practice position closed",
                summary="This practice position was closed.",
                label="proven", source="paper",
                detail_status="complete" if p["close_cost_stamp"]
                else "partial",
                details=close_details,
            ))

    # 7. outcome
    if i.outcome and i.outcome["barrier"] is not None:
        texts = {
            1: ("Target condition reached",
                "The idea reached its target zone (paper tracking)."),
            -1: ("Exit condition reached",
                 "The idea reached its exit condition (paper tracking)."),
            0: ("Time horizon reached",
                "The idea resolved by reaching its time limit "
                "(paper tracking)."),
        }
        title, summary = texts.get(i.outcome["barrier"],
                                   ("Outcome recorded", "Outcome recorded."))
        events.append(TimelineEvent(
            key="outcome", type="outcome",
            occurred_at=i.outcome["first_touch_at"]
            or i.outcome["recorded_at"] or i.generated_at.isoformat(),
            title=title, summary=summary,
            label="proven", source="outcome", detail_status="complete",
            details={},
        ))
        lifecycle_status = {1: "resolved_target", -1: "resolved_exit",
                            0: "resolved_time"}[i.outcome["barrier"]]
    elif i.outcome:
        lifecycle_status = "open"
    else:
        lifecycle_status = "open"
        unavailable.append({
            "section": "outcome",
            "reason": "Outcome tracking has not recorded a row for this "
                      "idea yet.",
        })

    # 8. thesis (asset-level → labeled related, partial)
    for idx, t in enumerate(i.theses):
        events.append(TimelineEvent(
            key=f"thesis:{idx}", type="thesis",
            occurred_at=t["status_changed_at"] or t["created_at"]
            or i.generated_at.isoformat(),
            title="Related asset thesis",
            summary=(
                f"A related thesis for this company is recorded as "
                f"{t['status']}. (Related asset thesis — not necessarily "
                "the exact thesis used for this decision.)"
            ),
            label="preliminary", source="thesis", detail_status="partial",
            details={"status": t["status"]},
        ))

    # 9. lessons (approved public; owner sees drafts/rejected)
    for idx, l in enumerate(i.lessons):
        if l["review_state"] != "approved" and not i.owner:
            continue
        approved = l["review_state"] == "approved"
        events.append(TimelineEvent(
            key=f"lesson:{idx}", type="lesson",
            occurred_at=l["reviewed_at"] or l["created_at"]
            or i.generated_at.isoformat(),
            title="Lesson recorded" if approved
            else f"Lesson {l['review_state']} (owner view)",
            summary=(l["what_happened"] or "A lesson was recorded.")
            if approved or i.owner else "",
            label="proven" if approved else "preliminary",
            source="lesson",
            detail_status="complete" if approved else "partial",
            details={"provenance": l["provenance"]} if i.owner else {},
        ))

    # research reports: no structured link exists — deferred to Wave 2
    unavailable.append({
        "section": "research_reports",
        "reason": "Research reports are not yet linked to individual "
                  "ideas (arrives with entity linking).",
    })

    # ordering: occurred_at → semantic type priority → stable key
    events.sort(key=lambda e: (e.occurred_at,
                               TYPE_PRIORITY.get(e.type, 9), e.key))
    events = events[:MAX_EVENTS]

    present = {e.type for e in events}
    completeness = "complete" if not unavailable else "partial"
    completeness_note = (
        "Every recorded artifact for this idea is shown."
        if not unavailable else
        "; ".join(u["reason"] for u in unavailable[:3])
    )

    return {
        "symbol": i.symbol.upper(),
        "rule_set_version": REPLAY_RULE_SET_VERSION,
        "recommendation_as_of": i.generated_at.isoformat(),
        "lifecycle_status": lifecycle_status,
        "completeness": completeness,
        "completeness_note": completeness_note,
        "events": [e.public_dict() for e in events],
        "unavailable_sections": unavailable,
        "sections_present": sorted(present),
        "user_scoped": i.user_scoped,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Cache — identity + principal keyed (cross-user sharing impossible)
# ---------------------------------------------------------------------------

_CACHE_MAX = 128
_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(i: ReplayInputs, user_id: str | None) -> tuple:
    return (
        REPLAY_RULE_SET_VERSION, i.rec_id, user_id, i.owner,
        (i.verdict or {}).get("verdict"),
        (i.posture or {}).get("created_at"),
        json.dumps(i.outcome, sort_keys=True, default=str),
        len(i.updates), len(i.paper), len(i.theses), len(i.lessons),
        tuple(p.get("closed_at") for p in i.paper),
        tuple(l.get("review_state") for l in i.lessons),
    )


def get_timeline(
    db: Session, *, symbol: str | None = None, rec_id: str | None = None,
    user_id: str | None = None, owner: bool = False,
) -> dict[str, Any] | None:
    if rec_id is None:
        if not symbol:
            return None
        pinned = resolve_pinned(db, symbol)
        if pinned is None:
            return None
        rec_id = pinned[0]
    inputs = load_inputs(db, rec_id, user_id=user_id, owner=owner)
    if inputs is None:
        return None
    key = _cache_key(inputs, user_id)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    result = assemble(inputs)
    with _cache_lock:
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return result


def reset_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
