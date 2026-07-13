"""Wave 1C — "What changed?" recommendation delta (read-only, zero-migration).

Compares the latest stored recommendation for a symbol with its
deterministically-selected prior and explains meaningful changes in
beginner-safe, server-owned language.

Authoritative prior-selection rule (documented in
RECOMMENDATION_DELTA_CONTRACT.md):
    prior = the recommendation for the SAME asset_id that is strictly
    earlier by the tuple (generated_at, id) — i.e.
    generated_at < cur.generated_at OR
    (generated_at = cur.generated_at AND id < cur.id)
    ordered by (generated_at DESC, id DESC), LIMIT 1.
Rationale: dev history contains real same-timestamp sibling rows (the
historical dual-scheduler era), so calendar-day or timestamp-only selection
is ambiguous; the (generated_at, id) tuple is total, stable under pagination
and concurrent inserts, and can never select a newer sibling or the row
itself. The symbol's canonical asset is the asset of the LATEST
recommendation among assets sharing the symbol (same tuple ordering).

Integrity rules enforced here:
* no writes, no LLM, no network, no live market data — stored rows only;
* never recompute with present-day engine code: family scores, actions,
  labels, prices (outcome.price_at_recommendation, else the newest stored
  bar at-or-before each row's generated_at) are read as stored;
* preflight verdicts / posture events are consumed ONLY as already-persisted
  facts (never triggering an evaluation); absent → "not evaluated";
* historical confidence wording renders under the policy in force AT THAT
  ROW'S generated_at (WORDING_CUTOVER) — history is never rewritten with
  today's copy;
* all beginner_text comes from server-owned templates (stored
  thesis/evidence narrative is never echoed);
* malformed / NaN / Infinity family values yield an explicit unavailable
  state, never a fabricated direction.
"""

from __future__ import annotations

import datetime as dt
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

DELTA_RULE_SET_VERSION = "delta-1"

# ---- materiality policy (versioned; changing these bumps the version) -----
SCORE_EPS = 0.05          # |delta| below this → unchanged
SCORE_SMALL = 0.15        # < → small
SCORE_MEANINGFUL = 0.35   # < → meaningful; >= → large
PRICE_EPS_PCT = 0.3       # |move| below → unchanged
PRICE_SMALL_PCT = 1.5
PRICE_MEANINGFUL_PCT = 4.0
MAX_CHANGES = 8

#: When the approved "Meets the buy bar" presentation became the default.
WORDING_CUTOVER = dt.datetime(2026, 7, 11, tzinfo=dt.timezone.utc)

Direction = Literal["positive", "negative", "cautious", "neutral",
                    "informational"]
Significance = Literal["small", "meaningful", "large"]
Source = Literal["recommendation", "evidence", "plan", "freshness",
                 "posture", "thesis", "outcome"]

#: Server-owned vocabulary for the families the engine actually stores
#: (verified against dev data: exactly these three). Unknown families get
#: the generic phrasing. Sign convention (uniform, from the engine): score
#: > 0 supports the idea, < 0 is cautionary.
FAMILY_META: dict[str, str] = {
    "trend_momentum": "the price trend",
    "volatility_risk": "price-swing risk",
    "exposure": "market exposure",
}


@dataclass(frozen=True)
class RecFacts:
    """Stored facts for one recommendation row (identity kept internal)."""
    rec_id: str
    generated_at: dt.datetime
    action: str | None
    confidence_label: str | None
    family_scores: dict[str, float]        # finite values only
    malformed_families: tuple[str, ...]    # names whose values were unusable
    stale_data: bool
    price_at: float | None                 # stored fact (outcome else bar)
    outcome_barrier: int | None            # 1 target · -1 exit · 0 time · None open
    has_outcome_row: bool
    verdict: str | None                    # persisted preflight verdict
    verdict_limitations: tuple[str, ...]   # beginner texts, already public-safe
    posture: str | None                    # persisted posture at verdict time


@dataclass(frozen=True)
class Change:
    id: str
    kind: str
    direction: Direction
    significance: Significance
    beginner_text: str
    source: Source
    priority: int                           # internal ordering only


@dataclass
class DeltaResult:
    symbol: str
    current_as_of: str
    prior_as_of: str | None
    first_seen: bool
    summary: str
    changes: list[Change] = field(default_factory=list)
    evidence_balance: str = "not_evaluated"
    price_context: str | None = None
    freshness_context: str | None = None
    limitations: list[str] = field(default_factory=list)
    thesis_revision: None = None            # no reliable stored link — omitted

    def public_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rule_set_version": DELTA_RULE_SET_VERSION,
            "current_as_of": self.current_as_of,
            "prior_as_of": self.prior_as_of,
            "first_seen": self.first_seen,
            "summary": self.summary,
            "changes": [{
                "id": c.id, "kind": c.kind, "direction": c.direction,
                "significance": c.significance,
                "beginner_text": c.beginner_text, "source": c.source,
            } for c in self.changes],
            "evidence_balance": self.evidence_balance,
            "price_context": self.price_context,
            "freshness_context": self.freshness_context,
            "limitations": self.limitations,
            "thesis_revision": self.thesis_revision,
        }


# ---------------------------------------------------------------------------
# Loading (bounded query set; no writes)
# ---------------------------------------------------------------------------

def _finite(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _parse_families(raw: Any) -> tuple[dict[str, float], tuple[str, ...]]:
    scores: dict[str, float] = {}
    malformed: list[str] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            if v is None:            # explicitly absent value — treat as missing
                malformed.append(str(k))
                continue
            f = _finite(v)
            if f is None:
                malformed.append(str(k))
            else:
                scores[str(k)] = f
    return scores, tuple(sorted(malformed))


def _load_row_facts(db: Session, row: Any) -> RecFacts:
    import json as _json
    try:
        rationale = _json.loads(row.rationale or "{}",
                                parse_constant=lambda v: float("nan"))
        if not isinstance(rationale, dict):
            rationale = {}
    except (ValueError, TypeError):
        rationale = {}
    scores, malformed = _parse_families(rationale.get("family_scores"))

    out = db.execute(text(
        "SELECT barrier_label, price_at_recommendation "
        "FROM recommendation_outcome WHERE recommendation_id = :r LIMIT 1"
    ), {"r": row.id}).first()
    price_at = _finite(out[1]) if out else None
    if price_at is None:
        bar = db.execute(text(
            "SELECT close FROM price_bar WHERE asset_id = :a "
            "AND timeframe = '1d' AND ts <= :g "
            "ORDER BY ts DESC LIMIT 1"
        ), {"a": row.asset_id, "g": row.generated_at}).scalar()
        price_at = _finite(bar)

    verdict_row = db.execute(text(
        "SELECT verdict, limitations_json, created_at "
        "FROM recommendation_preflight WHERE recommendation_id = :r "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"r": row.id}).first()
    verdict = verdict_row[0] if verdict_row else None
    limitations: tuple[str, ...] = ()
    posture: str | None = None
    if verdict_row:
        try:
            lims = _json.loads(verdict_row[1] or "[]")
            limitations = tuple(
                c["beginner_text"] for c in lims
                if isinstance(c, dict) and c.get("beginner_text")
            )
        except (ValueError, TypeError):
            limitations = ()
        posture = db.execute(text(
            "SELECT posture FROM system_posture_event "
            "WHERE created_at <= :t ORDER BY created_at DESC, id DESC LIMIT 1"
        ), {"t": verdict_row[2]}).scalar()

    return RecFacts(
        rec_id=row.id,
        generated_at=row.generated_at,
        action=row.action,
        confidence_label=rationale.get("confidence_label"),
        family_scores=scores,
        malformed_families=malformed,
        stale_data=bool(rationale.get("stale_data", False)),
        price_at=price_at,
        outcome_barrier=int(out[0]) if out and out[0] is not None else None,
        has_outcome_row=bool(out),
        verdict=verdict,
        verdict_limitations=limitations,
        posture=posture,
    )


def load_pair(db: Session, symbol: str) -> tuple[RecFacts, RecFacts | None] | None:
    """Resolve the canonical latest recommendation for a symbol and its
    prior per the documented rule. Returns None when the symbol has no
    recommendations at all."""
    cur = db.execute(text(
        "SELECT r.id, r.asset_id, r.generated_at, r.action, r.rationale "
        "FROM recommendation r JOIN asset a ON a.id = r.asset_id "
        "WHERE upper(a.symbol) = upper(:s) "
        "ORDER BY r.generated_at DESC, r.id DESC LIMIT 1"
    ), {"s": symbol}).first()
    if cur is None:
        return None
    prior = db.execute(text(
        "SELECT r.id, r.asset_id, r.generated_at, r.action, r.rationale "
        "FROM recommendation r "
        "WHERE r.asset_id = :a AND (r.generated_at, r.id) < (:g, :i) "
        "ORDER BY r.generated_at DESC, r.id DESC LIMIT 1"
    ), {"a": cur.asset_id, "g": cur.generated_at, "i": cur.id}).first()
    cur_facts = _load_row_facts(db, cur)
    prior_facts = _load_row_facts(db, prior) if prior is not None else None
    return cur_facts, prior_facts


# ---------------------------------------------------------------------------
# Pure comparison
# ---------------------------------------------------------------------------

def _score_sig(delta: float) -> Significance | None:
    a = abs(delta)
    if a < SCORE_EPS:
        return None
    if a < SCORE_SMALL:
        return "small"
    if a < SCORE_MEANINGFUL:
        return "meaningful"
    return "large"


def _price_sig(pct: float) -> Significance | None:
    a = abs(pct)
    if a < PRICE_EPS_PCT:
        return None
    if a < PRICE_SMALL_PCT:
        return "small"
    if a < PRICE_MEANINGFUL_PCT:
        return "meaningful"
    return "large"


def _family_name(key: str) -> str:
    return FAMILY_META.get(key, key.replace("_", " "))


def presentation_for(label: str | None, at: dt.datetime) -> str:
    """Historically-correct confidence presentation. History is rendered
    under the wording policy in force at that row's generated_at."""
    l = label or "Medium"
    if at >= WORDING_CUTOVER and l in ("High", "Medium"):
        return "meets the buy bar"
    return f"{l.lower()} confidence"


_ACTION_RANK = {"Buy": 3, "Hold": 2, "Trim": 1, "Sell": 0}


def compute(symbol: str, cur: RecFacts, prior: RecFacts | None) -> DeltaResult:
    res = DeltaResult(
        symbol=symbol.upper(),
        current_as_of=cur.generated_at.isoformat(),
        prior_as_of=prior.generated_at.isoformat() if prior else None,
        first_seen=prior is None,
        summary="",
    )
    res.limitations = list(cur.verdict_limitations)

    if prior is None:
        res.summary = "This is a new idea from ArthOS."
        res.evidence_balance = "not_evaluated"
        return res

    changes: list[Change] = []

    # -- 2. action change (priority 1) --------------------------------------
    if (cur.action or "") != (prior.action or ""):
        more_cautious = _ACTION_RANK.get(cur.action or "", 2) < \
            _ACTION_RANK.get(prior.action or "", 2)
        changes.append(Change(
            id="action_change", kind="action_change",
            direction="cautious" if more_cautious else "positive",
            significance="large",
            beginner_text=(
                f"ArthOS moved from {prior.action} to {cur.action}. "
                + ("The recommended action became more cautious."
                   if more_cautious
                   else "The recommended action became more constructive.")
            ),
            source="recommendation", priority=1,
        ))

    # -- 9. outcome status (target/exit crossings — priority 2) -------------
    if cur.outcome_barrier is not None and prior.outcome_barrier is None:
        texts = {
            1: ("reached its target zone", "positive"),
            -1: ("reached its exit condition", "cautious"),
            0: ("resolved by reaching its time limit", "neutral"),
        }
        t, d = texts.get(cur.outcome_barrier, ("resolved", "neutral"))
        changes.append(Change(
            id="outcome_status", kind="outcome_status",
            direction=d,  # type: ignore[arg-type]
            significance="large",
            beginner_text=f"Since the previous update this idea {t}.",
            source="outcome", priority=2,
        ))

    # -- 4. evidence-family changes ------------------------------------------
    pos_moves = 0
    neg_moves = 0
    fam_changes: list[Change] = []
    all_keys = sorted(set(cur.family_scores) | set(prior.family_scores)
                      | set(cur.malformed_families)
                      | set(prior.malformed_families))
    for k in all_keys:
        name = _family_name(k)
        if k in cur.malformed_families or k in prior.malformed_families:
            fam_changes.append(Change(
                id=f"family_unavailable:{k}", kind="family_unavailable",
                direction="informational", significance="small",
                beginner_text=f"The reading for {name} is unavailable in "
                              "this comparison.",
                source="evidence", priority=6,
            ))
            continue
        in_cur, in_prior = k in cur.family_scores, k in prior.family_scores
        if in_cur and not in_prior:
            supportive = cur.family_scores[k] > 0
            fam_changes.append(Change(
                id=f"family_added:{k}", kind="family_added",
                direction="positive" if supportive else "cautious",
                significance="meaningful",
                beginner_text=(
                    f"New {'supporting' if supportive else 'cautionary'} "
                    f"evidence appeared around {name}."
                ),
                source="evidence", priority=5,
            ))
            pos_moves += int(supportive)
            neg_moves += int(not supportive)
            continue
        if in_prior and not in_cur:
            fam_changes.append(Change(
                id=f"family_removed:{k}", kind="family_removed",
                direction="informational", significance="meaningful",
                beginner_text=f"A previous signal around {name} is no "
                              "longer part of the case.",
                source="evidence", priority=5,
            ))
            continue
        delta = cur.family_scores[k] - prior.family_scores[k]
        sig = _score_sig(delta)
        if sig is None:
            continue
        supportive_move = delta > 0
        pos_moves += int(supportive_move)
        neg_moves += int(not supportive_move)
        strength = {"small": "slightly", "meaningful": "noticeably",
                    "large": "sharply"}[sig]
        fam_changes.append(Change(
            id=f"family_change:{k}", kind="family_change",
            direction="positive" if supportive_move else "cautious",
            significance=sig,
            beginner_text=(
                f"The reading for {name} moved {strength} "
                f"{'in the idea’s favor' if supportive_move else 'toward caution'}."
            ),
            source="evidence", priority=6,
        ))
    changes.extend(fam_changes)

    # -- 5. evidence balance (priority 3) ------------------------------------
    if pos_moves and neg_moves:
        res.evidence_balance = "mixed"
        changes.append(Change(
            id="evidence_balance", kind="evidence_balance",
            direction="neutral", significance="meaningful",
            beginner_text="The evidence moved in both directions — mixed "
                          "signals increased.",
            source="evidence", priority=3,
        ))
    elif pos_moves:
        res.evidence_balance = "more_supportive"
        changes.append(Change(
            id="evidence_balance", kind="evidence_balance",
            direction="positive", significance="meaningful",
            beginner_text="The balance of evidence became more supportive.",
            source="evidence", priority=3,
        ))
    elif neg_moves:
        res.evidence_balance = "more_cautious"
        changes.append(Change(
            id="evidence_balance", kind="evidence_balance",
            direction="cautious", significance="meaningful",
            beginner_text="The balance of evidence became more cautious.",
            source="evidence", priority=3,
        ))
    else:
        res.evidence_balance = "unchanged"

    # -- 6. price relative to the two stored reads (priority 2 when large) --
    # Plan corridors (entry/target/exit) are derived client-side and not
    # persisted, so plan-zone comparisons are honestly UNAVAILABLE in this
    # slice (documented limitation). What IS stored: each row's own price
    # (outcome.price_at_recommendation, else the newest bar at generation).
    if cur.price_at is not None and prior.price_at is not None \
            and prior.price_at > 0:
        pct = (cur.price_at - prior.price_at) / prior.price_at * 100.0
        sig = _price_sig(pct)
        if sig is not None:
            up = pct > 0
            res.price_context = (
                f"The stored price moved {'up' if up else 'down'} about "
                f"{abs(pct):.1f}% between the two reads."
            )
            changes.append(Change(
                id="price_move", kind="price_move",
                direction="informational",
                significance=sig,
                beginner_text=res.price_context,
                source="plan",
                priority=2 if sig == "large" else 6,
            ))
        else:
            res.price_context = "The stored price is little changed between reads."
    else:
        res.price_context = None

    # -- 7. freshness / system-state changes ---------------------------------
    if cur.stale_data != prior.stale_data:
        fresher = prior.stale_data and not cur.stale_data
        res.freshness_context = (
            "The data is fresher than in the previous update." if fresher
            else "This update carries a data-staleness flag the previous "
                 "one did not."
        )
        changes.append(Change(
            id="freshness_change", kind="freshness_change",
            direction="positive" if fresher else "cautious",
            significance="meaningful",
            beginner_text=res.freshness_context,
            source="freshness", priority=4,
        ))

    if cur.verdict is not None or prior.verdict is not None:
        cur_l, prior_l = set(cur.verdict_limitations), set(prior.verdict_limitations)
        if cur_l - prior_l:
            changes.append(Change(
                id="limitation_added", kind="preflight_limitation",
                direction="cautious", significance="meaningful",
                beginner_text="ArthOS is now publishing with an additional "
                              "data limitation.",
                source="freshness", priority=4,
            ))
        elif prior_l - cur_l:
            changes.append(Change(
                id="limitation_removed", kind="preflight_limitation",
                direction="positive", significance="small",
                beginner_text="A previous data limitation no longer applies.",
                source="freshness", priority=4,
            ))

    if cur.posture and prior.posture and cur.posture != prior.posture:
        worse = {"NORMAL": 0, "RESTRICTED": 1, "SAFE": 2}
        degraded = worse.get(cur.posture, 1) > worse.get(prior.posture, 1)
        txt = ("New ideas are currently paused by Safe Mode."
               if cur.posture == "SAFE"
               else "System publishing conditions "
                    + ("tightened" if degraded else "improved")
                    + " since the previous update.")
        changes.append(Change(
            id="posture_change", kind="posture_change",
            direction="cautious" if degraded else "positive",
            significance="meaningful",
            beginner_text=txt,
            source="posture", priority=4,
        ))

    # -- 3. confidence presentation change (priority 5) ----------------------
    cur_p = presentation_for(cur.confidence_label, cur.generated_at)
    prior_p = presentation_for(prior.confidence_label, prior.generated_at)
    if cur_p != prior_p:
        changes.append(Change(
            id="confidence_presentation", kind="confidence_presentation",
            direction="informational", significance="meaningful",
            beginner_text=f"ArthOS's confidence presentation moved from "
                          f"“{prior_p}” to “{cur_p}”.",
            source="recommendation", priority=5,
        ))

    # -- ordering, cap, summary ----------------------------------------------
    order_sig = {"large": 0, "meaningful": 1, "small": 2}
    changes.sort(key=lambda c: (c.priority, order_sig[c.significance], c.id))
    res.changes = changes[:MAX_CHANGES]

    if not changes:
        res.summary = "The evidence is broadly unchanged since the previous update."
    else:
        top = res.changes[0]
        if top.kind == "action_change":
            res.summary = ("ArthOS became more cautious since the previous update."
                           if top.direction == "cautious"
                           else "ArthOS became more constructive since the previous update.")
        elif top.kind == "outcome_status":
            res.summary = top.beginner_text
        elif top.kind == "evidence_balance":
            res.summary = ("The main action is unchanged, but the evidence "
                           + {"more_supportive": "strengthened.",
                              "more_cautious": "turned more cautious.",
                              "mixed": "sent mixed signals."}[res.evidence_balance])
        elif top.kind in ("posture_change", "freshness_change",
                          "preflight_limitation"):
            res.summary = top.beginner_text
        elif top.kind == "price_move":
            res.summary = top.beginner_text
        else:
            res.summary = "There are minor changes since the previous update."
    return res


# ---------------------------------------------------------------------------
# Bounded identity-keyed cache (new rec / new verdict / new posture event
# produce a new key, so staleness is impossible by construction)
# ---------------------------------------------------------------------------

_CACHE_MAX = 256
_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(cur: RecFacts, prior: RecFacts | None) -> tuple:
    return (
        DELTA_RULE_SET_VERSION,
        cur.rec_id, cur.verdict, tuple(cur.verdict_limitations), cur.posture,
        cur.outcome_barrier,
        prior.rec_id if prior else None,
        prior.outcome_barrier if prior else None,
    )


def get_delta(db: Session, symbol: str) -> dict[str, Any] | None:
    pair = load_pair(db, symbol)
    if pair is None:
        return None
    cur, prior = pair
    key = _cache_key(cur, prior)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    result = compute(symbol, cur, prior).public_dict()
    with _cache_lock:
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return result


def reset_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()
