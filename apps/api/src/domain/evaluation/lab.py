"""ArthOS Experiment Lab — Wave 3A evidence-generation harness.

Deterministic, reproducible, resource-bounded evaluation of ArthOS
recommendation engines against simple baselines using temporal
out-of-sample windows, recorded in the EXISTING research_run registry
(migration 109 — verified sufficient, NO new schema). Spec:
docs/architecture/EXPERIMENT_LAB.md.

Layer map (one concern per section, top to bottom):
  spec canonicalization + hashing → dataset fingerprint → temporal
  windows → engine adapters → benchmarks → metrics → cost sensitivity →
  promotion-readiness verdict → registry persistence → reproduction.

Hard properties:
  * No arbitrary code: adapters are a FROZEN registry of hardcoded
    callables; the spec is bounded structured data (validated, capped),
    never code, paths, SQL, or shell.
  * Identity: experiment_hash = sha256(canonical spec) and
    dataset_fingerprint = sha256(canonical stored-fact aggregates).
    Same spec + same code + same data ⇒ same identity and (tolerance-
    checked) the same metric hash. Reproduction NEVER edits the original
    run — it creates a new run with parent_run_id set.
  * Evaluation-only v1: the primary adapter evaluates the production
    engine's STORED decisions (recommendation + recommendation_outcome)
    — decisions at time t used only information available at t by
    construction, so training-leakage purge does not apply to it
    (recorded explicitly per run). Purged-fold policy (apps/ml/lab/
    splits) governs any future trained adapter.
  * Censored outcomes are counted and excluded FROM RESOLVED-ONLY
    metrics with disclosure — never silently treated as losses.
  * The Lab never promotes anything: promotion_readiness is a
    deterministic read-only verdict (lab-gates-1); owner approval is a
    separate manual action outside this module.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import platform
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.ml.lab import benchmarks as bench
from apps.ml.lab import metrics as labm
from apps.ml.lab.registry import (
    RegistryClient,
    canonical_json,
    resolve_git_sha,
)

#: lab-1.1 (Wave 3A.1): model_versions scoping + replay-pooling CRITICAL
#: warning + matched event-horizon benchmark (comparable accounting).
#: Original lab-1 runs remain untouched historical evidence.
LAB_EVALUATOR_VERSION = "lab-1.1"
SPLIT_POLICY_VERSION = "calendar-eval-1"   # evaluation windows, no training
GATE_POLICY_VERSION = "lab-gates-1"

# ---------------------------------------------------------------------------
# Resource limits — defaults and hard maxima (constrained shared VM).
# Exceeding a hard max is a 422-shaped SpecError BEFORE any work happens.
# ---------------------------------------------------------------------------
MAX_UNIVERSE = 200
DEFAULT_UNIVERSE = 50
MAX_RANGE_DAYS = 3660           # ~10y
MAX_FOLDS = 16
MAX_COST_SCENARIOS = 4
MAX_CONCURRENT_RUNS = 1         # per experiment identity AND globally
MAX_NAME_LEN = 120
MAX_METRIC_BYTES = 200_000      # metrics JSON size guard
_ERROR_CATEGORIES = frozenset({
    "spec_invalid", "dataset_empty", "insufficient_history",
    "resource_limit", "internal",
})

#: cost scenarios (bps round-trip flat haircut per position period) —
#: zero / expected / stressed, mirroring domain.evaluation.costs tiers.
COST_SCENARIOS_BPS: dict[str, float] = {
    "zero_cost": 0.0,
    "expected_cost": 10.0,
    "stressed_cost": 20.0,
}

VALID_TARGETS = frozenset({"resolved_barrier_hit"})
VALID_ENGINES = frozenset({"stored_rules_engine"})
VALID_BENCHMARKS = frozenset({"buy_and_hold", "momentum_12_1", "neutral"})
VALID_PERIODS = frozenset({"M", "Q", "Y"})


class LabError(Exception):
    """Base."""


class SpecError(LabError):
    """Invalid/out-of-bounds specification — 422-shaped."""


class ConcurrentRunError(LabError):
    """Same experiment identity already has an active run — 409-shaped."""


class DataError(LabError):
    """Dataset empty / insufficient — recorded as a bounded failed run."""


# ---------------------------------------------------------------------------
# 1. Experiment specification — canonical, immutable, hashed
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    engine: str = "stored_rules_engine"
    target: str = "resolved_barrier_hit"
    universe: tuple[str, ...] = ()           # symbols; () = top-N by coverage
    universe_size: int = DEFAULT_UNIVERSE
    start: dt.date = dt.date(2024, 2, 1)
    end: dt.date = dt.date(2026, 7, 1)
    fold_period: str = "Q"
    embargo_days: int = 0                    # evaluation-only: informational
    min_eval_rows: int = 30
    benchmarks: tuple[str, ...] = ("buy_and_hold", "momentum_12_1", "neutral")
    cost_scenarios: tuple[str, ...] = tuple(COST_SCENARIOS_BPS)
    confidence_threshold: float = 60.0       # publication-band boundary
    seed: int = 42
    actions: tuple[str, ...] = ("Buy",)
    #: Wave 3A.1 — model-version scoping. Dev history contains REPLAY
    #: VARIANTS (same window re-generated under several model_version
    #: strings); pooling them duplicates correlated decisions. Empty =
    #: all versions, with a CRITICAL warning when >1 version pools.
    model_versions: tuple[str, ...] = ()


def validate_spec(raw: dict) -> ExperimentSpec:
    """Bounded structured input → frozen spec. Everything checked BEFORE
    any database work; unknown keys rejected (no smuggling)."""
    if not isinstance(raw, dict):
        raise SpecError("spec must be an object")
    allowed = {f.name for f in ExperimentSpec.__dataclass_fields__.values()}
    unknown = set(raw) - allowed
    if unknown:
        raise SpecError(f"unknown spec fields: {sorted(unknown)}")

    name = str(raw.get("name") or "").strip()
    if not name or len(name) > MAX_NAME_LEN:
        raise SpecError(f"name required (1-{MAX_NAME_LEN} chars)")
    engine = raw.get("engine", "stored_rules_engine")
    if engine not in VALID_ENGINES:
        raise SpecError(f"engine must be one of {sorted(VALID_ENGINES)}")
    target = raw.get("target", "resolved_barrier_hit")
    if target not in VALID_TARGETS:
        raise SpecError(f"target must be one of {sorted(VALID_TARGETS)}")

    universe = raw.get("universe") or ()
    if not isinstance(universe, (list, tuple)):
        raise SpecError("universe must be a list of symbols")
    universe = tuple(sorted({str(s).strip().upper() for s in universe
                             if str(s).strip()}))
    if len(universe) > MAX_UNIVERSE:
        raise SpecError(f"universe exceeds {MAX_UNIVERSE} symbols")
    for s in universe:
        if len(s) > 12 or not s.replace(".", "").replace("-", "").isalnum():
            raise SpecError(f"invalid symbol {s!r}")

    usize = int(raw.get("universe_size", DEFAULT_UNIVERSE))
    if not 1 <= usize <= MAX_UNIVERSE:
        raise SpecError(f"universe_size must be in [1,{MAX_UNIVERSE}]")

    def _date(key, default):
        v = raw.get(key, default)
        if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
            return v
        try:
            return dt.date.fromisoformat(str(v))
        except ValueError:
            raise SpecError(f"{key} is not a valid ISO date")

    start = _date("start", "2024-02-01")
    end = _date("end", "2026-07-01")
    if start >= end:
        raise SpecError("start must be before end")
    if (end - start).days > MAX_RANGE_DAYS:
        raise SpecError(f"date range exceeds {MAX_RANGE_DAYS} days")

    period = str(raw.get("fold_period", "Q"))
    if period not in VALID_PERIODS:
        raise SpecError(f"fold_period must be one of {sorted(VALID_PERIODS)}")
    embargo = int(raw.get("embargo_days", 0))
    if not 0 <= embargo <= 60:
        raise SpecError("embargo_days must be in [0,60]")
    min_eval = int(raw.get("min_eval_rows", 30))
    if not 5 <= min_eval <= 10_000:
        raise SpecError("min_eval_rows must be in [5,10000]")

    bms = tuple(raw.get("benchmarks",
                        ("buy_and_hold", "momentum_12_1", "neutral")))
    if not bms or set(bms) - VALID_BENCHMARKS:
        raise SpecError(f"benchmarks must be from {sorted(VALID_BENCHMARKS)}")

    costs = tuple(raw.get("cost_scenarios", tuple(COST_SCENARIOS_BPS)))
    if not costs or set(costs) - set(COST_SCENARIOS_BPS) \
            or len(costs) > MAX_COST_SCENARIOS:
        raise SpecError(
            f"cost_scenarios must be from {sorted(COST_SCENARIOS_BPS)}")

    thr = float(raw.get("confidence_threshold", 60.0))
    if not 0.0 <= thr <= 100.0:
        raise SpecError("confidence_threshold must be in [0,100]")
    seed = int(raw.get("seed", 42))
    if not 0 <= seed <= 2**31 - 1:
        raise SpecError("seed out of range")
    actions = tuple(raw.get("actions", ("Buy",)))
    if not actions or set(actions) - {"Buy", "Sell", "Trim", "Watch", "Hold"}:
        raise SpecError("actions invalid")
    mvs = raw.get("model_versions") or ()
    if not isinstance(mvs, (list, tuple)) or len(mvs) > 8:
        raise SpecError("model_versions must be a list of at most 8")
    model_versions = tuple(sorted({str(v).strip()[:64] for v in mvs
                                   if str(v).strip()}))

    return ExperimentSpec(
        name=name, engine=engine, target=target, universe=universe,
        universe_size=usize, start=start, end=end, fold_period=period,
        embargo_days=embargo, min_eval_rows=min_eval, benchmarks=bms,
        cost_scenarios=costs, confidence_threshold=thr, seed=seed,
        actions=actions, model_versions=model_versions,
    )


def spec_payload(spec: ExperimentSpec) -> dict:
    """Canonical JSON-safe projection — the hashed identity."""
    return {
        "name": spec.name,
        "engine": spec.engine,
        "target": spec.target,
        "universe": list(spec.universe),
        "universe_size": spec.universe_size,
        "start": spec.start.isoformat(),
        "end": spec.end.isoformat(),
        "fold_period": spec.fold_period,
        "embargo_days": spec.embargo_days,
        "min_eval_rows": spec.min_eval_rows,
        "benchmarks": list(spec.benchmarks),
        "cost_scenarios": list(spec.cost_scenarios),
        "confidence_threshold": spec.confidence_threshold,
        "seed": spec.seed,
        "actions": list(spec.actions),
        "model_versions": list(spec.model_versions),
        "evaluator_version": LAB_EVALUATOR_VERSION,
        "split_policy_version": SPLIT_POLICY_VERSION,
    }


def experiment_hash(spec: ExperimentSpec) -> str:
    return hashlib.sha256(
        canonical_json(spec_payload(spec)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# 2. Dataset fingerprint — stored facts, bounded aggregates, never raw data
# ---------------------------------------------------------------------------

def resolve_universe(db: Session, spec: ExperimentSpec) -> list[str]:
    """Explicit universe passes through (existence-checked); empty universe
    = top universe_size symbols by resolved-outcome coverage in the window
    (deterministic: count DESC, symbol ASC)."""
    if spec.universe:
        rows = db.execute(text(
            "SELECT DISTINCT a.symbol FROM asset a "
            "WHERE a.symbol = ANY(:syms)"), {"syms": list(spec.universe)}
        ).scalars().all()
        missing = set(spec.universe) - set(rows)
        if missing:
            raise SpecError(f"unknown symbols: {sorted(missing)[:10]}")
        return sorted(rows)
    rows = db.execute(text(
        """
        SELECT a.symbol, count(*) AS n
        FROM recommendation r
        JOIN asset a ON a.id = r.asset_id
        JOIN recommendation_outcome o ON o.recommendation_id = r.id
        WHERE r.generated_at >= :s AND r.generated_at < :e
          AND r.action = ANY(:acts) AND o.barrier_label IS NOT NULL
        GROUP BY a.symbol ORDER BY n DESC, a.symbol ASC LIMIT :lim
        """),
        {"s": spec.start, "e": spec.end, "acts": list(spec.actions),
         "lim": spec.universe_size},
    ).mappings().all()
    if not rows:
        raise DataError("no resolved outcomes in the requested window")
    return sorted(r["symbol"] for r in rows)


def dataset_fingerprint(db: Session, spec: ExperimentSpec,
                        universe: list[str]) -> tuple[str, dict]:
    """sha256 over bounded stored-fact aggregates. Adding/changing data in
    scope changes the fingerprint; unrelated DB changes do not. Returns
    (fingerprint, manifest) — the manifest is persisted, raw data never."""
    agg = db.execute(text(
        """
        SELECT count(*) AS bars, max(pb.ts) AS max_ts, min(pb.ts) AS min_ts,
               count(DISTINCT pb.asset_id) AS assets
        FROM price_bar pb JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = ANY(:syms) AND pb.ts >= :s AND pb.ts < :e
        """), {"syms": universe, "s": spec.start, "e": spec.end},
    ).mappings().one()
    mv_clause = ""
    rec_params: dict = {"syms": universe, "s": spec.start, "e": spec.end,
                        "acts": list(spec.actions)}
    if spec.model_versions:
        mv_clause = "AND r.model_version = ANY(:mvs)"
        rec_params["mvs"] = list(spec.model_versions)
    recs = db.execute(text(
        f"""
        SELECT count(*) AS n, max(r.generated_at) AS max_gen,
               count(DISTINCT r.model_version) AS n_versions,
               sum(CASE WHEN o.barrier_label IS NOT NULL THEN 1 ELSE 0 END)
                 AS resolved,
               sum(CASE WHEN o.barrier_label IS NULL THEN 1 ELSE 0 END)
                 AS censored
        FROM recommendation r
        JOIN asset a ON a.id = r.asset_id
        LEFT JOIN recommendation_outcome o ON o.recommendation_id = r.id
        WHERE a.symbol = ANY(:syms) AND r.generated_at >= :s
          AND r.generated_at < :e AND r.action = ANY(:acts) {mv_clause}
        """), rec_params,
    ).mappings().one()
    ca = db.execute(text(
        "SELECT count(*) FROM corporate_action c "
        "JOIN asset a ON a.id = c.asset_id WHERE a.symbol = ANY(:syms)"),
        {"syms": universe}).scalar() or 0

    manifest = {
        "universe": universe,
        "n_symbols": len(universe),
        "price_bars": int(agg["bars"] or 0),
        "price_min_ts": str(agg["min_ts"]),
        "price_max_ts": str(agg["max_ts"]),
        "price_assets": int(agg["assets"] or 0),
        "recommendations": int(recs["n"] or 0),
        "rec_max_generated_at": str(recs["max_gen"]),
        "distinct_model_versions": int(recs["n_versions"] or 0),
        "model_version_filter": list(spec.model_versions) or None,
        "resolved_outcomes": int(recs["resolved"] or 0),
        "censored_outcomes": int(recs["censored"] or 0),
        "corporate_actions": int(ca),
        "outcome_label_version": "barrier-v1",   # barrier_label semantics
        "missing_data_policy": "row-dropped-and-counted",
        "source": "dev-postgres",
    }
    fp = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    return fp, manifest


# ---------------------------------------------------------------------------
# 3. Dataset construction (stored decisions + outcomes; bounded)
# ---------------------------------------------------------------------------

def load_decisions(db: Session, spec: ExperimentSpec,
                   universe: list[str]) -> list[dict]:
    """Stored engine decisions joined to outcomes — the evaluation corpus.
    Bounded by universe + window; deterministic order. Optional
    model_versions scoping (Wave 3A.1) — dev history contains replay
    variants; unscoped runs pool them and get a CRITICAL warning."""
    mv_clause = ""
    params: dict = {"syms": universe, "s": spec.start, "e": spec.end,
                    "acts": list(spec.actions)}
    if spec.model_versions:
        mv_clause = "AND r.model_version = ANY(:mvs)"
        params["mvs"] = list(spec.model_versions)
    rows = db.execute(text(
        f"""
        SELECT a.symbol, r.generated_at, r.action, r.conviction,
               r.model_version, r.asset_id,
               o.barrier_label, o.realized_30d_return, o.barrier_n_bars,
               o.price_at_recommendation
        FROM recommendation r
        JOIN asset a ON a.id = r.asset_id
        LEFT JOIN recommendation_outcome o ON o.recommendation_id = r.id
        WHERE a.symbol = ANY(:syms) AND r.generated_at >= :s
          AND r.generated_at < :e AND r.action = ANY(:acts) {mv_clause}
        ORDER BY r.generated_at, a.symbol, r.id
        """), params,
    ).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 4. Temporal windows (evaluation-only folds; deterministic)
# ---------------------------------------------------------------------------

def _period_key(ts: dt.datetime, period: str) -> str:
    if period == "M":
        return f"{ts.year}-{ts.month:02d}"
    if period == "Y":
        return str(ts.year)
    return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"


def build_folds(decisions: list[dict], spec: ExperimentSpec) -> tuple[
        list[dict], list[dict]]:
    """Group decisions into calendar evaluation windows. Returns (folds,
    skipped) — a window below min_eval_rows RESOLVED rows is skipped and
    REPORTED, never silently dropped. Fold count is capped at MAX_FOLDS
    (newest kept, cap disclosed)."""
    by_period: dict[str, list[dict]] = {}
    for d in decisions:
        by_period.setdefault(
            _period_key(d["generated_at"], spec.fold_period), []).append(d)

    folds, skipped = [], []
    for key in sorted(by_period):
        rows = by_period[key]
        resolved = [r for r in rows if r["barrier_label"] in (1, -1)]
        if len(resolved) < spec.min_eval_rows:
            skipped.append({"fold": key, "rows": len(rows),
                            "resolved": len(resolved),
                            "reason": f"resolved < {spec.min_eval_rows}"})
            continue
        folds.append({"fold": key, "rows": rows, "resolved": resolved})
    if len(folds) > MAX_FOLDS:
        dropped = folds[:-MAX_FOLDS]
        skipped.extend({"fold": f["fold"], "rows": len(f["rows"]),
                        "resolved": len(f["resolved"]),
                        "reason": f"fold cap {MAX_FOLDS} (oldest dropped)"}
                       for f in dropped)
        folds = folds[-MAX_FOLDS:]
    return folds, skipped


# ---------------------------------------------------------------------------
# 5. Metrics per fold — target: resolved_barrier_hit
# ---------------------------------------------------------------------------

def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion — lightweight CI,
    no new dependencies (statsmodels deferred to Wave 3A.2)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def evaluate_fold(fold: dict, spec: ExperimentSpec) -> dict:
    """Discrimination + calibration + return metrics for one window.
    Resolved-only for hit metrics (censored counted, disclosed); returns
    use stored realized_30d_return where present (missing counted)."""
    rows = fold["rows"]
    resolved = fold["resolved"]
    y = np.array([1.0 if r["barrier_label"] == 1 else 0.0
                  for r in resolved])
    conf = np.array([float(r["conviction"]) if r["conviction"] is not None
                     else np.nan for r in resolved])
    have_conf = ~np.isnan(conf)
    p = conf[have_conf] / 100.0
    y_c = y[have_conf]

    hits = int(y.sum())
    ci = _wilson_ci(hits, len(y))

    # calibration bands by confidence decile (sample counts included)
    bands = []
    if have_conf.sum() >= 10:
        edges = np.linspace(0.0, 1.0, 11)
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (p >= lo) & (p < hi) if hi < 1.0 else (p >= lo) & (p <= hi)
            if int(m.sum()) == 0:
                continue
            bands.append({
                "band": f"{lo:.1f}-{hi:.1f}",
                "n": int(m.sum()),
                "mean_confidence": float(p[m].mean()),
                "observed_hit_rate": float(y_c[m].mean()),
            })

    # threshold classification at the publication band
    thr = spec.confidence_threshold / 100.0
    if have_conf.sum() > 0:
        y_pred = (p >= thr).astype(float)
        precision, recall = labm.precision_recall(y_c, y_pred)
        tp = int(np.sum((y_pred == 1) & (y_c == 1)))
        fp = int(np.sum((y_pred == 1) & (y_c == 0)))
        fn = int(np.sum((y_pred == 0) & (y_c == 1)))
        tn = int(np.sum((y_pred == 0) & (y_c == 0)))
        confusion = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
    else:
        precision = recall = None
        confusion = None

    rets = [float(r["realized_30d_return"]) for r in resolved
            if r["realized_30d_return"] is not None]
    return {
        "fold": fold["fold"],
        "candidates": len(rows),
        "resolved": len(resolved),
        "censored": len(rows) - len(resolved),
        "with_confidence": int(have_conf.sum()),
        "hit_rate": float(y.mean()) if len(y) else None,
        "hit_rate_ci95": list(ci) if ci else None,
        "auc": labm.auc(y_c, p) if have_conf.sum() > 0 else None,
        "brier": labm.brier(y_c, p) if have_conf.sum() > 0 else None,
        "ece": labm.ece(y_c, p) if have_conf.sum() >= 10 else None,
        "base_rate_brier": bench.base_rate_brier(y_c)
        if have_conf.sum() > 0 else None,
        "precision_at_threshold": precision,
        "recall_at_threshold": recall,
        "confusion": confusion,
        "calibration_bands": bands,
        "mean_realized_30d": (float(np.mean(rets)) if rets else None),
        "n_returns": len(rets),
        "missing_returns": len(resolved) - len(rets),
    }


# ---------------------------------------------------------------------------
# 6. Benchmarks — same universe, window, missing-data rules, costs
# ---------------------------------------------------------------------------

def _monthly_prices(db: Session, universe: list[str],
                    start: dt.date, end: dt.date):
    """Month-end close matrix from stored bars (bounded query)."""
    import pandas as pd
    rows = db.execute(text(
        """
        SELECT a.symbol, date_trunc('month', pb.ts) AS m, max(pb.ts) AS mts
        FROM price_bar pb JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = ANY(:syms) AND pb.ts >= :s AND pb.ts < :e
        GROUP BY a.symbol, date_trunc('month', pb.ts)
        """), {"syms": universe, "s": start, "e": end}).mappings().all()
    if not rows:
        return None
    keys = [(r["symbol"], r["mts"]) for r in rows]
    px = db.execute(text(
        """
        SELECT a.symbol, pb.ts, pb.close
        FROM price_bar pb JOIN asset a ON a.id = pb.asset_id
        WHERE a.symbol = ANY(:syms) AND pb.ts = ANY(:ts)
        """),
        {"syms": universe, "ts": sorted({k[1] for k in keys})},
    ).mappings().all()
    frame: dict[str, dict] = {}
    valid = set(keys)
    for r in px:
        if (r["symbol"], r["ts"]) in valid:
            frame.setdefault(r["symbol"], {})[
                r["ts"].date().replace(day=1)] = float(r["close"])
    df = pd.DataFrame(frame).sort_index()
    return df if not df.empty else None


def run_benchmarks(db: Session, spec: ExperimentSpec,
                   universe: list[str]) -> dict:
    """Benchmark suite over the SAME universe/window. Missing history is
    reported per benchmark, never padded."""
    out: dict[str, dict] = {}
    monthly = _monthly_prices(db, universe, spec.start, spec.end)
    n_months = 0 if monthly is None else len(monthly.index)

    if "neutral" in spec.benchmarks:
        out["neutral"] = {"total_return": 0.0, "note": "no positions"}

    if "buy_and_hold" in spec.benchmarks:
        if monthly is None or n_months < 2:
            out["buy_and_hold"] = {"error": "insufficient price history"}
        else:
            rets = []
            for c in monthly.columns:
                s = monthly[c].dropna()
                if len(s) >= 2 and s.iloc[0] > 0:
                    rets.append(bench.buy_and_hold_return(s))
            out["buy_and_hold"] = {
                "total_return": float(np.mean(rets)) if rets else None,
                "assets_used": len(rets),
                "assets_missing": len(universe) - len(rets),
                "months": n_months,
            }

    if "momentum_12_1" in spec.benchmarks:
        if monthly is None or n_months < 14:
            out["momentum_12_1"] = {
                "error": "needs >= 14 months of history in window"}
        else:
            mrets = bench.momentum_12_1_portfolio_returns(monthly)
            if mrets.empty:
                out["momentum_12_1"] = {"error": "no usable signals"}
            else:
                out["momentum_12_1"] = {
                    "total_return": float(np.prod(1 + mrets.values) - 1),
                    "monthly_mean": float(mrets.mean()),
                    "months": int(len(mrets)),
                    "max_drawdown": labm.max_drawdown(list(mrets.values)),
                }
    return out


MATCHED_HORIZON_DAYS = 30
MATCHED_EXIT_TOLERANCE_DAYS = 7


def matched_event_benchmark(db: Session, decisions: list[dict],
                            universe: list[str]) -> dict:
    """Wave 3A.1 comparable accounting — event-level comparison.

    For every RESOLVED decision with a stored entry price
    (price_at_recommendation) and stored 30d return, compute the SAME
    asset's buy-and-hold return over the SAME event horizon: entry = the
    stored entry price (identical entry convention), exit = last close at
    or before entry+30 calendar days (within a 7-day tolerance; otherwise
    the event is excluded and counted). excess = stored engine 30d return
    − matched asset return. Same missing-data policy (excluded+counted),
    same window, per event — no overlapping-portfolio claims."""
    events = [d for d in decisions
              if d["barrier_label"] in (1, -1)
              and d["realized_30d_return"] is not None
              and d["price_at_recommendation"] is not None]
    if not events:
        return {"error": "no resolved events with entry price + return"}

    asset_ids = sorted({d["asset_id"] for d in events})
    lo = min(d["generated_at"] for d in events)
    hi = max(d["generated_at"] for d in events) + dt.timedelta(
        days=MATCHED_HORIZON_DAYS + MATCHED_EXIT_TOLERANCE_DAYS)
    bars = db.execute(text(
        """
        SELECT asset_id, ts, close FROM price_bar
        WHERE asset_id = ANY(:aids) AND ts >= :lo AND ts < :hi
        ORDER BY asset_id, ts
        """), {"aids": asset_ids, "lo": lo, "hi": hi}).mappings().all()
    by_asset: dict[str, list] = {}
    for b in bars:
        by_asset.setdefault(b["asset_id"], []).append(
            (b["ts"], float(b["close"])))

    import bisect
    excess, engine_r, bench_r = [], [], []
    excluded_no_exit_bar = 0
    for d in events:
        series = by_asset.get(d["asset_id"]) or []
        target = d["generated_at"] + dt.timedelta(days=MATCHED_HORIZON_DAYS)
        idx = bisect.bisect_right([t for t, _ in series], target) - 1
        if idx < 0:
            excluded_no_exit_bar += 1
            continue
        exit_ts, exit_px = series[idx]
        if (target - exit_ts).days > MATCHED_EXIT_TOLERANCE_DAYS \
                or exit_ts <= d["generated_at"]:
            excluded_no_exit_bar += 1
            continue
        entry = float(d["price_at_recommendation"])
        if entry <= 0:
            excluded_no_exit_bar += 1
            continue
        b_ret = exit_px / entry - 1.0
        e_ret = float(d["realized_30d_return"])
        engine_r.append(e_ret)
        bench_r.append(b_ret)
        excess.append(e_ret - b_ret)

    if not excess:
        return {"error": "no events with a matched exit bar",
                "excluded_no_exit_bar": excluded_no_exit_bar}
    ex = np.array(excess)
    pos = int((ex > 0).sum())
    ci = _wilson_ci(pos, len(ex))
    return {
        "basis": (f"per-event {MATCHED_HORIZON_DAYS}d horizon, identical "
                  "entry price, asset buy-and-hold comparator"),
        "events": len(ex),
        "excluded_no_exit_bar": excluded_no_exit_bar,
        "engine_mean_30d": float(np.mean(engine_r)),
        "benchmark_mean_30d": float(np.mean(bench_r)),
        "excess_mean": float(ex.mean()),
        "excess_median": float(np.median(ex)),
        "excess_std": float(ex.std()) if len(ex) > 1 else None,
        "share_events_beating_asset": pos / len(ex),
        "share_beating_ci95": list(ci) if ci else None,
    }


# ---------------------------------------------------------------------------
# 7. Cost sensitivity — flat per-position haircut scenarios
# ---------------------------------------------------------------------------

def cost_sensitivity(fold_metrics: list[dict],
                     spec: ExperimentSpec) -> dict:
    """Apply flat round-trip cost scenarios to the strategy's mean stored
    30d return per fold. Scenarios are SIMULATED assumptions — historical
    paper-trade stamps are never recomputed."""
    per_fold_rets = [f["mean_realized_30d"] for f in fold_metrics
                     if f["mean_realized_30d"] is not None]
    if not per_fold_rets:
        return {"error": "no realized returns available"}
    out = {}
    for name in spec.cost_scenarios:
        bps = COST_SCENARIOS_BPS[name]
        haircut = bps / 1e4
        net = [r - haircut for r in per_fold_rets]
        out[name] = {
            "round_trip_bps": bps,
            "gross_mean_30d": float(np.mean(per_fold_rets)),
            "net_mean_30d": float(np.mean(net)),
            "folds_positive_net": int(sum(1 for r in net if r > 0)),
            "folds": len(net),
        }
    return out


# ---------------------------------------------------------------------------
# 8. Promotion-readiness — deterministic verdict, NEVER an approval
# ---------------------------------------------------------------------------

MIN_RESOLVED_FOR_EVIDENCE = 300
MIN_FOLDS_FOR_EVIDENCE = 4

VERDICTS = ("INSUFFICIENT_EVIDENCE", "REPRODUCIBILITY_FAILED",
            "FAILS_BASELINE", "PASSES_BASELINE_WITH_LIMITATIONS",
            "ELIGIBLE_FOR_OWNER_REVIEW")


def promotion_readiness(summary: dict, fold_metrics: list[dict],
                        benchmarks: dict, costs: dict,
                        warnings: list[str],
                        reproducibility: dict | None = None) -> dict:
    """lab-gates-1. Read-only verdict; owner approval is a separate manual
    action. Never promotes."""
    gates: dict[str, dict] = {}

    def gate(key, ok, detail):
        gates[key] = {"pass": bool(ok), "detail": detail}

    resolved = summary.get("total_resolved", 0)
    gate("min_resolved_sample", resolved >= MIN_RESOLVED_FOR_EVIDENCE,
         f"{resolved} resolved (need {MIN_RESOLVED_FOR_EVIDENCE})")
    n_folds = summary.get("n_folds", 0)
    gate("min_temporal_folds", n_folds >= MIN_FOLDS_FOR_EVIDENCE,
         f"{n_folds} folds (need {MIN_FOLDS_FOR_EVIDENCE})")
    gate("costs_evaluated", "error" not in costs,
         "cost scenarios computed" if "error" not in costs
         else costs["error"])
    has_baseline = any("error" not in v for v in benchmarks.values())
    gate("baseline_compared", has_baseline,
         "at least one benchmark computed")
    cal_folds = [f for f in fold_metrics if f.get("ece") is not None]
    gate("calibration_reported", len(cal_folds) > 0,
         f"{len(cal_folds)} folds with calibration")
    crit = [w for w in warnings if w.startswith("CRITICAL")]
    gate("no_critical_warnings", not crit, crit or "none")
    gate("multi_fold_claim", n_folds >= 2,
         "claims span multiple folds" if n_folds >= 2
         else "single-fold-only")

    # discrimination vs base rate: brier must beat the constant classifier
    # in a majority of folds that could measure it
    beat = [f for f in fold_metrics
            if f.get("brier") is not None
            and f.get("base_rate_brier") is not None
            and f["brier"] < f["base_rate_brier"]]
    measurable = [f for f in fold_metrics if f.get("brier") is not None]
    gate("beats_base_rate_majority",
         len(measurable) > 0 and len(beat) > len(measurable) / 2,
         f"{len(beat)}/{len(measurable)} folds beat the base-rate Brier")

    if reproducibility is not None:
        gate("reproducibility", bool(reproducibility.get("matches")),
             reproducibility)

    hard_missing = [k for k in ("min_resolved_sample", "min_temporal_folds",
                                "baseline_compared", "multi_fold_claim")
                    if not gates[k]["pass"]]
    if reproducibility is not None and not reproducibility.get("matches"):
        verdict = "REPRODUCIBILITY_FAILED"
    elif hard_missing:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif not gates["beats_base_rate_majority"]["pass"]:
        verdict = "FAILS_BASELINE"
    elif not all(g["pass"] for g in gates.values()):
        verdict = "PASSES_BASELINE_WITH_LIMITATIONS"
    else:
        verdict = "ELIGIBLE_FOR_OWNER_REVIEW"
    return {"policy": GATE_POLICY_VERSION, "verdict": verdict,
            "gates": gates}


# ---------------------------------------------------------------------------
# 9. Metric hash + environment capture (no secrets)
# ---------------------------------------------------------------------------

def metric_hash(fold_metrics: list[dict], summary: dict) -> str:
    """Deterministic hash of the reproducibility-relevant numbers, rounded
    to 10 decimal places (float tolerance)."""
    def _round(o):
        if isinstance(o, float):
            return round(o, 10)
        if isinstance(o, dict):
            return {k: _round(v) for k, v in sorted(o.items())}
        if isinstance(o, list):
            return [_round(v) for v in o]
        return o
    payload = _round({"folds": fold_metrics, "summary": summary})
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def environment_capture() -> dict:
    """Package/platform versions only — no env vars, no paths, no secrets."""
    import importlib.metadata as md
    pkgs = {}
    for p in ("numpy", "pandas", "scikit-learn", "scipy", "sqlalchemy"):
        try:
            pkgs[p] = md.version(p)
        except md.PackageNotFoundError:
            pkgs[p] = None
    return {"python": platform.python_version(), "packages": pkgs}


# ---------------------------------------------------------------------------
# 10. Orchestration + registry persistence
# ---------------------------------------------------------------------------

def _active_run_exists(db: Session, cfg_hash: str) -> bool:
    return bool(db.execute(text(
        "SELECT 1 FROM research_run WHERE config_hash = :h "
        "AND status IN ('draft','running') LIMIT 1"), {"h": cfg_hash}
    ).scalar())


def execute_experiment(
    db: Session, raw_spec: dict, *, created_by: str = "owner",
    parent_run_uid: str | None = None,
    research_task_id: str | None = None,
) -> dict:
    """Validate → identity → concurrency guard → evaluate → persist ONE
    research_run row (append-only; failures become bounded failed runs).
    Synchronous by design: caps bound the work to seconds on the dev VM;
    no second scheduler is created. Returns the public run dict."""
    spec = validate_spec(raw_spec)
    exp_hash = experiment_hash(spec)

    params = spec_payload(spec)
    params["experiment_hash"] = exp_hash
    if research_task_id:
        params["research_task_id"] = research_task_id[:36]

    client = RegistryClient(db)
    from apps.ml.lab.registry import config_hash as _cfg_hash
    if _active_run_exists(db, _cfg_hash(params)):
        raise ConcurrentRunError(
            "an active run already exists for this experiment identity")

    parent_id = None
    if parent_run_uid:
        parent = client.get_run(parent_run_uid)
        if parent is None:
            raise SpecError(f"parent run {parent_run_uid!r} does not exist")
        parent_id = parent.id

    run = client.create_run(
        run_type="walk_forward",
        name=f"lab: {spec.name}"[:250],
        params=params,
        seed=spec.seed,
        data_window=(spec.start, spec.end),
        split_method=SPLIT_POLICY_VERSION,
        model_version=spec.engine,
        parent_run_id=parent_id,
        created_by=created_by[:64],
    )
    client.start(run)
    db.commit()

    warnings: list[str] = []
    try:
        universe = resolve_universe(db, spec)
        fp, manifest = dataset_fingerprint(db, spec, universe)
        decisions = load_decisions(db, spec, universe)
        if not decisions:
            raise DataError("zero decisions in scope")
        folds, skipped = build_folds(decisions, spec)
        if not folds:
            raise DataError(
                f"no usable folds ({len(skipped)} skipped below "
                f"min_eval_rows={spec.min_eval_rows})")

        # replay-variant pooling check (Wave 3A.1): multiple model_versions
        # in one corpus = duplicated correlated decisions → CRITICAL.
        versions_seen = sorted({d["model_version"] or "unknown"
                                for d in decisions})
        if len(versions_seen) > 1 and not spec.model_versions:
            warnings.append(
                f"CRITICAL replay pooling: {len(versions_seen)} "
                f"model_versions pooled ({', '.join(versions_seen[:6])}"
                f"{'…' if len(versions_seen) > 6 else ''}) — duplicate "
                "replay variants inflate correlated samples; pin "
                "model_versions in the spec")

        fold_metrics = [evaluate_fold(f, spec) for f in folds]
        benchmarks = run_benchmarks(db, spec, universe)
        benchmarks["matched_event_horizon"] = matched_event_benchmark(
            db, decisions, universe)
        costs = cost_sensitivity(fold_metrics, spec)

        total_resolved = sum(f["resolved"] for f in fold_metrics)
        # censored disclosure is DATASET-level (includes skipped folds) —
        # open outcomes must never vanish behind fold selection
        total_censored = sum(
            1 for d in decisions if d["barrier_label"] not in (1, -1))
        hit_rates = [f["hit_rate"] for f in fold_metrics
                     if f["hit_rate"] is not None]
        briers = [f["brier"] for f in fold_metrics
                  if f["brier"] is not None]
        summary = {
            "n_folds": len(fold_metrics),
            "n_skipped_folds": len(skipped),
            "total_candidates": sum(f["candidates"] for f in fold_metrics),
            "total_resolved": total_resolved,
            "total_censored": total_censored,
            "censored_policy": "counted+excluded from resolved-only metrics",
            "mean_hit_rate": float(np.mean(hit_rates)) if hit_rates else None,
            "worst_fold_hit_rate": (float(min(hit_rates))
                                    if hit_rates else None),
            "hit_rate_dispersion": (float(np.std(hit_rates))
                                    if len(hit_rates) > 1 else None),
            "mean_brier": float(np.mean(briers)) if briers else None,
            "model_versions_seen": versions_seen,
            "leakage_check": ("not-applicable: stored decisions evaluated "
                              "out-of-sample by construction (no training "
                              "in this adapter)"),
        }
        if total_censored > total_resolved:
            warnings.append(
                f"censored outcomes ({total_censored}) exceed resolved "
                f"({total_resolved}) — recent windows are mostly open")
        m_hash = metric_hash(fold_metrics, summary)

        reproducibility = None
        if parent_run_uid:
            parent = client.get_run(parent_run_uid)
            prev = (parent.metrics or {}).get("metric_hash")
            reproducibility = {
                "baseline_run": parent_run_uid,
                "baseline_metric_hash": prev,
                "metric_hash": m_hash,
                "matches": bool(prev) and prev == m_hash,
            }
            if not reproducibility["matches"]:
                warnings.append(
                    "CRITICAL reproducibility: metric hash differs from "
                    f"baseline run {parent_run_uid}")

        readiness = promotion_readiness(
            summary, fold_metrics, benchmarks, costs, warnings,
            reproducibility)

        metrics_doc = {
            "experiment_hash": exp_hash,
            "dataset_fingerprint": fp,
            "dataset_manifest": manifest,
            "summary": summary,
            "folds": fold_metrics,
            "skipped_folds": skipped,
            "benchmarks": benchmarks,
            "cost_sensitivity": costs,
            "warnings": warnings,
            "metric_hash": m_hash,
            "environment": environment_capture(),
            "promotion_readiness": readiness,
        }
        if reproducibility is not None:
            metrics_doc["reproducibility"] = reproducibility
        if len(canonical_json(metrics_doc).encode()) > MAX_METRIC_BYTES:
            # bound the artifact: drop per-fold calibration bands first
            for f in metrics_doc["folds"]:
                f["calibration_bands"] = "truncated (size cap)"
            warnings.append("metrics truncated to stay within size cap")
        client.finish(run, metrics_doc)
        db.commit()
    except (DataError, SpecError) as exc:
        client.fail(run, f"{_categorize(exc)}: {str(exc)[:400]}")
        db.commit()
    except Exception as exc:  # noqa: BLE001 — bounded failure, no stack
        client.fail(run, f"internal: {type(exc).__name__}: {str(exc)[:300]}")
        db.commit()
    return run_public(run)


def _categorize(exc: Exception) -> str:
    if isinstance(exc, SpecError):
        return "spec_invalid"
    if isinstance(exc, DataError):
        return "dataset_empty"
    return "internal"


def run_public(run) -> dict:
    """Owner-safe projection of a research_run row (no stack traces —
    error_summary is already bounded/categorized; no paths beyond the
    artifact manifest the registry keeps)."""
    m = run.metrics or {}
    return {
        "run_uid": run.run_uid,
        "name": run.name,
        "status": run.status,
        "engine": run.model_version,
        "created_by": "owner",
        "data_start": run.data_start.isoformat() if run.data_start else None,
        "data_end": run.data_end.isoformat() if run.data_end else None,
        "seed": run.random_seed,
        "git_sha": run.git_sha,
        "split_method": run.split_method,
        "config_hash": run.config_hash,
        "parent_run_uid": None,   # filled by the route when needed
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": (run.completed_at.isoformat()
                         if run.completed_at else None),
        "error_summary": run.error_summary,
        "metrics": m,
    }
