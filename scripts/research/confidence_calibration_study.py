"""Sprint 3 — offline confidence-calibration study (dev DB, read-only).

Tests whether the displayed stock confidence (recommendation.conviction,
the rule-engine agreement score that drives the Low/Medium/High label) is
HONEST as a probability that the recommendation "hits" its barrier
outcome (recommendation_outcome.barrier_label == 1).

Scientific discipline (hard requirements):
  * NO random splits — calendar-quarter folds by generated_at, evaluated
    strictly forward (walk-forward): calibrators for fold i train only on
    recommendations whose generated_at + EMBARGO_DAYS < fold_i start.
  * EMBARGO_DAYS = 100 calendar days > the longest outcome horizon
    (63 trading bars), so no training label can overlap an eval window.
  * Only RESOLVED outcomes (barrier_label IN (-1, 1)) are scored;
    unresolved/censored and neutral(0) rows are counted and reported,
    never silently dropped.
  * Decision-time inputs only: conviction is stamped at generated_at by
    the producer; nothing later than generated_at enters a prediction.
  * Live vs replay cohorts (model_version LIKE '%+replay:%') are reported
    separately — replay rows were produced against historical data and
    must not silently pad the live story.

Outputs (written under docs/research/):
  calibration_metrics.json        — machine-readable full results
  calibration_reliability.svg     — reliability diagram (no plotting deps)
Read-only against the database; writes only the two artifact files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sqlalchemy import create_engine, text

EMBARGO_DAYS = 100
N_BINS = 10
MIN_TRAIN = 500          # calibrators need this many resolved train rows
MIN_BAND_N = 100         # decile bands below this are "insufficient data"
MIN_LABEL_BAND_N = 30    # product label bands below this are insufficient
OUT_DIR = os.environ.get("STUDY_OUT_DIR", "docs/research")

# Product label thresholds (recommendation_engine._compute_confidence:
# High >= 60, Medium >= 30, else Low — cited in MODEL_AND_DATA_FORENSICS).
LABEL_BANDS = [("Low", 0.0, 30.0), ("Medium", 30.0, 60.0), ("High", 60.0, 100.01)]


@dataclass
class Row:
    generated_at: dt.datetime
    conviction: float           # raw score, expected 0..100
    hit: int                    # 1 / 0
    cohort: str                 # live | replay
    action: str
    trend_regime: str | None
    volatility_regime: str | None
    sector: str | None


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def ece_mce(p: np.ndarray, y: np.ndarray, bins: int = N_BINS) -> tuple[float, float]:
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    mce = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        if mask.sum() == 0:
            continue
        gap = abs(p[mask].mean() - y[mask].mean())
        ece += (mask.sum() / len(p)) * gap
        mce = max(mce, gap)
    return float(ece), float(mce)


def load_rows(engine) -> tuple[list[Row], dict]:
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        counts["recommendations_total"] = conn.execute(
            text("SELECT count(*) FROM recommendation")).scalar()
        counts["outcome_rows_total"] = conn.execute(
            text("SELECT count(*) FROM recommendation_outcome")).scalar()
        counts["unresolved"] = conn.execute(text(
            "SELECT count(*) FROM recommendation_outcome WHERE barrier_label IS NULL"
        )).scalar()
        counts["neutral_label_0"] = conn.execute(text(
            "SELECT count(*) FROM recommendation_outcome WHERE barrier_label = 0"
        )).scalar()
        counts["missing_entry_price"] = conn.execute(text(
            "SELECT count(*) FROM recommendation_outcome "
            "WHERE price_at_recommendation IS NULL"
        )).scalar()
        counts["null_conviction_buy"] = conn.execute(text(
            "SELECT count(*) FROM recommendation r JOIN recommendation_outcome o "
            "ON o.recommendation_id = r.id WHERE r.action = 'Buy' "
            "AND o.barrier_label IN (-1, 1) AND r.conviction IS NULL"
        )).scalar()

        has_sector = conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'asset' AND column_name = 'sector'"
        )).scalar() > 0
        sector_col = "a.sector" if has_sector else "NULL"

        rows = conn.execute(text(f"""
            SELECT r.generated_at, r.conviction, o.barrier_label,
                   CASE WHEN r.model_version LIKE '%+replay:%'
                        THEN 'replay' ELSE 'live' END AS cohort,
                   r.action, o.trend_regime, o.volatility_regime,
                   {sector_col} AS sector
            FROM recommendation r
            JOIN recommendation_outcome o ON o.recommendation_id = r.id
            JOIN asset a ON a.id = r.asset_id
            WHERE r.action = 'Buy'
              AND o.barrier_label IN (-1, 1)
              AND r.conviction IS NOT NULL
            ORDER BY r.generated_at
        """)).all()

    out = [
        Row(
            generated_at=r[0],
            conviction=float(r[1]),
            hit=1 if r[2] == 1 else 0,
            cohort=r[3],
            action=r[4],
            trend_regime=r[5],
            volatility_regime=r[6],
            sector=r[7],
        )
        for r in rows
    ]
    counts["buy_resolved_scored"] = len(out)
    return out, counts


def quarter_of(ts: dt.datetime) -> str:
    return f"{ts.year}Q{(ts.month - 1) // 3 + 1}"


def band_table(rows: list[Row], bands, min_n: int) -> list[dict]:
    table = []
    for name, lo, hi in bands:
        sel = [r for r in rows if lo <= r.conviction < hi]
        n = len(sel)
        k = sum(r.hit for r in sel)
        ci_lo, ci_hi = wilson_ci(k, n)
        pred_mean = float(np.mean([r.conviction for r in sel]) / 100) if n else None
        obs = k / n if n else None
        verdict = "insufficient_data"
        if n >= min_n and pred_mean is not None and obs is not None:
            if pred_mean > ci_hi:
                verdict = "overconfident"
            elif pred_mean < ci_lo:
                verdict = "underconfident"
            else:
                verdict = "consistent"
        table.append({
            "band": name, "n": n, "hits": k,
            "predicted_mean": pred_mean,
            "observed_rate": obs,
            "wilson_95": [ci_lo, ci_hi],
            "verdict": verdict,
        })
    return table


def walk_forward(rows: list[Row]) -> dict:
    """Quarterly walk-forward: eval each quarter with calibrators trained on
    embargoed history. Models: identity (conviction/100), naive (train base
    rate), platt (logistic on score), isotonic."""
    quarters = sorted({quarter_of(r.generated_at) for r in rows})
    per_fold = []
    pooled: dict[str, list] = defaultdict(list)
    pooled_y: list[int] = []

    for q in quarters:
        fold = [r for r in rows if quarter_of(r.generated_at) == q]
        if not fold:
            continue
        fold_start = min(r.generated_at for r in fold)
        cutoff = fold_start - dt.timedelta(days=EMBARGO_DAYS)
        train = [r for r in rows if r.generated_at < cutoff]
        if len(train) < MIN_TRAIN:
            per_fold.append({"fold": q, "n_eval": len(fold),
                             "skipped": f"train<{MIN_TRAIN} after embargo"})
            continue

        Xtr = np.array([r.conviction for r in train]).reshape(-1, 1)
        ytr = np.array([r.hit for r in train])
        Xev = np.array([r.conviction for r in fold]).reshape(-1, 1)
        yev = np.array([r.hit for r in fold])

        preds: dict[str, np.ndarray] = {
            "identity": np.clip(Xev.ravel() / 100.0, 0.0, 1.0),
            "naive_base_rate": np.full(len(fold), ytr.mean()),
        }
        lr = LogisticRegression(C=1e6, max_iter=1000)
        lr.fit(Xtr, ytr)
        preds["platt_sigmoid"] = lr.predict_proba(Xev)[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(Xtr.ravel(), ytr)
        preds["isotonic"] = iso.predict(Xev.ravel())

        fold_metrics = {"fold": q, "n_eval": len(fold),
                        "eval_hit_rate": float(yev.mean()), "models": {}}
        for name, p in preds.items():
            e, m = ece_mce(p, yev)
            fold_metrics["models"][name] = {
                "brier": brier(p, yev), "ece": e, "mce": m,
            }
            pooled[name].append(p)
        pooled_y.append(yev)
        per_fold.append(fold_metrics)

    result: dict = {"per_fold": per_fold, "pooled": {}}
    if pooled_y:
        y_all = np.concatenate(pooled_y)
        result["pooled_n"] = int(len(y_all))
        result["pooled_hit_rate"] = float(y_all.mean())
        for name, chunks in pooled.items():
            p_all = np.concatenate(chunks)
            e, m = ece_mce(p_all, y_all)
            result["pooled"][name] = {
                "brier": brier(p_all, y_all), "ece": e, "mce": m,
            }
        # reliability bins for the identity model (what users see today)
        p_id = np.concatenate(pooled["identity"])
        bins = []
        edges = np.linspace(0, 1, N_BINS + 1)
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (p_id >= lo) & (p_id < hi) if hi < 1 else (p_id >= lo)
            n = int(mask.sum())
            k = int(y_all[mask].sum()) if n else 0
            ci = wilson_ci(k, n)
            bins.append({
                "bin": [float(lo), float(hi)], "n": n,
                "predicted_mean": float(p_id[mask].mean()) if n else None,
                "observed_rate": (k / n) if n else None,
                "wilson_95": list(ci),
            })
        result["identity_reliability_bins"] = bins
    return result


def identity_full_cohort(rows: list[Row]) -> dict:
    """Metrics for the DISPLAYED mapping (conviction/100) over the whole
    cohort. Valid without walk-forward: every prediction was stamped at
    decision time, strictly before its outcome — no fitting, no leakage.
    The in-sample base rate is included only as a reference floor (it IS
    hindsight; a fitted calibrator must beat it out-of-sample to matter).
    """
    p = np.clip(np.array([r.conviction for r in rows]) / 100.0, 0, 1)
    y = np.array([r.hit for r in rows])
    e, m = ece_mce(p, y)
    out = {
        "n": int(len(y)),
        "hit_rate": float(y.mean()),
        "identity": {"brier": brier(p, y), "ece": e, "mce": m},
        "in_sample_base_rate_floor": {
            "brier": brier(np.full(len(y), y.mean()), y),
        },
    }
    try:
        out["identity"]["auc"] = float(roc_auc_score(y, p)) if len(set(y)) > 1 else None
    except ValueError:
        out["identity"]["auc"] = None
    # reliability bins over the observed score range
    bins = []
    edges = np.linspace(0, 1, N_BINS + 1)
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo)
        n = int(mask.sum())
        k = int(y[mask].sum()) if n else 0
        bins.append({
            "bin": [float(lo), float(hi)], "n": n,
            "predicted_mean": float(p[mask].mean()) if n else None,
            "observed_rate": (k / n) if n else None,
            "wilson_95": list(wilson_ci(k, n)),
        })
    out["reliability_bins"] = bins
    return out


def stability(rows: list[Row], key) -> dict:
    groups: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        groups[str(key(r) or "unknown")].append(r)
    out = {}
    for g, sel in sorted(groups.items()):
        n = len(sel)
        k = sum(r.hit for r in sel)
        pred = float(np.mean([r.conviction for r in sel]) / 100) if n else None
        out[g] = {
            "n": n, "observed_rate": (k / n) if n else None,
            "predicted_mean": pred, "wilson_95": list(wilson_ci(k, n)),
            "sufficient": n >= MIN_BAND_N,
        }
    return out


def reliability_svg(bins: list[dict], path: str) -> None:
    W, H, pad = 480, 480, 50
    def sx(v: float) -> float: return pad + v * (W - 2 * pad)
    def sy(v: float) -> float: return H - pad - v * (H - 2 * pad)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="monospace" font-size="11">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(1)}" '
        'stroke="#999" stroke-dasharray="4 3"/>',
        f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(0)}" stroke="#333"/>',
        f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(0)}" y2="{sy(1)}" stroke="#333"/>',
        f'<text x="{W/2}" y="{H-12}" text-anchor="middle">predicted (conviction/100)</text>',
        f'<text x="14" y="{H/2}" transform="rotate(-90 14 {H/2})" '
        'text-anchor="middle">observed hit rate</text>',
        f'<text x="{W/2}" y="20" text-anchor="middle">Reliability — displayed '
        'confidence as probability (walk-forward pooled)</text>',
    ]
    pts = []
    for b in bins:
        if not b["n"] or b["predicted_mean"] is None:
            continue
        x, y = sx(b["predicted_mean"]), sy(b["observed_rate"])
        lo, hi = b["wilson_95"]
        parts.append(f'<line x1="{x}" y1="{sy(lo)}" x2="{x}" y2="{sy(hi)}" '
                     'stroke="#c33" stroke-width="1"/>')
        parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="#c33"/>')
        parts.append(f'<text x="{x}" y="{y-8}" text-anchor="middle" '
                     f'font-size="9">n={b["n"]}</text>')
        pts.append((x, y))
    if len(pts) > 1:
        d = " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts[1:])
        parts.append(f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} {d}" '
                     'fill="none" stroke="#c33" stroke-width="1.5"/>')
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        parts.append(f'<text x="{sx(t)}" y="{sy(0)+16}" text-anchor="middle">{t:g}</text>')
        parts.append(f'<text x="{sx(0)-8}" y="{sy(t)+4}" text-anchor="end">{t:g}</text>')
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def _record_registry_run(
    engine, result: dict, rows: list[Row], artifact_paths: list[tuple[str, str]],
) -> None:
    """Record this study as a completed research_run (--registry only).

    Graceful no-op (with a message) when the target DB has never run
    migration 109 — the study output itself is unaffected either way.
    """
    # Lazy imports: the default (no-flag) path must not gain import side
    # effects or new hard dependencies.
    from sqlalchemy.orm import Session

    from apps.ml.lab.registry import (
        RegistryClient, registry_table_exists, resolve_git_sha,
    )

    if not registry_table_exists(engine):
        print("[registry] research_run table absent on this DB "
              "(migration 109 not applied) — skipping registry record")
        return

    params = {
        "study": result["study"],
        "score_definition": result["score_definition"],
        "outcome_definition": result["outcome_definition"],
        **result["method"],
        "label_bands": [list(b) for b in LABEL_BANDS],
    }
    live = result["cohorts"]["live"]
    idc = live.get("identity_full_cohort", {})
    wf_pooled = live.get("walk_forward", {}).get("pooled", {})
    metrics: dict = {
        **{f"count_{k}": v for k, v in result["counts"].items()},
        "n_live": result["cohorts"]["live"]["n"],
        "n_replay": result["cohorts"]["replay"]["n"],
        "live_identity_brier": idc.get("identity", {}).get("brier"),
        "live_identity_ece": idc.get("identity", {}).get("ece"),
        "live_identity_mce": idc.get("identity", {}).get("mce"),
        "live_identity_auc": idc.get("identity", {}).get("auc"),
        "live_hit_rate": idc.get("hit_rate"),
        "live_wf_pooled_n": live.get("walk_forward", {}).get("pooled_n"),
    }
    for model_name, m in wf_pooled.items():
        for metric_name, val in m.items():
            metrics[f"live_wf_pooled_{model_name}_{metric_name}"] = val

    window = None
    if rows:
        window = (
            min(r.generated_at for r in rows).date(),
            max(r.generated_at for r in rows).date(),
        )

    with Session(engine) as session:
        client = RegistryClient(session)
        run = client.create_run(
            run_type="calibration",
            name=result["study"],
            description="Displayed stock confidence (conviction/100) vs "
                        "resolved barrier outcomes — walk-forward calibration study",
            params=params,
            git_sha=resolve_git_sha(),
            data_window=window,
            split_method="purged_walk_forward",
            created_by="script:confidence_calibration_study",
        )
        client.start(run)
        client.append_metrics(run, metrics)
        for path, kind in artifact_paths:
            client.add_artifact(run, path, kind=kind)
        client.finish(run)
        session.commit()
        print(f"[registry] recorded run {run.run_uid} (completed)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", action="store_true",
        help="record this study as a completed research_run row "
             "(requires a DB with the research_run table; default off)",
    )
    args = parser.parse_args(argv)

    engine = create_engine(os.environ["DATABASE_URL"])
    rows, counts = load_rows(engine)
    live = [r for r in rows if r.cohort == "live"]
    replay = [r for r in rows if r.cohort == "replay"]

    deciles = [(f"{i*10}-{(i+1)*10}", float(i * 10), float((i + 1) * 10) + (0.01 if i == 9 else 0.0))
               for i in range(10)]

    result = {
        "study": "confidence_calibration_v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "score_definition": "recommendation.conviction (rule-engine agreement score, 0-100) interpreted as probability = conviction/100",
        "outcome_definition": "recommendation_outcome.barrier_label == 1 (hit) vs -1 (miss); neutral 0 and unresolved excluded and counted",
        "method": {
            "splits": "calendar-quarter walk-forward, no random splits",
            "embargo_days": EMBARGO_DAYS,
            "min_train": MIN_TRAIN,
            "bins": N_BINS,
        },
        "counts": counts,
        "conviction_distribution": {
            "min": float(min(r.conviction for r in rows)) if rows else None,
            "max": float(max(r.conviction for r in rows)) if rows else None,
            "mean": float(np.mean([r.conviction for r in rows])) if rows else None,
        },
        "cohorts": {
            "live": {"n": len(live)},
            "replay": {"n": len(replay)},
        },
    }

    for name, cohort_rows in (("live", live), ("replay", replay)):
        if not cohort_rows:
            result["cohorts"][name]["skipped"] = "no rows"
            continue
        result["cohorts"][name].update({
            "label_bands": band_table(cohort_rows, LABEL_BANDS, MIN_LABEL_BAND_N),
            "decile_bands": band_table(cohort_rows, deciles, MIN_BAND_N),
            "identity_full_cohort": identity_full_cohort(cohort_rows),
            "walk_forward": walk_forward(cohort_rows),
            "stability_by_year": stability(
                cohort_rows, lambda r: r.generated_at.year),
            "stability_by_trend_regime": stability(
                cohort_rows, lambda r: r.trend_regime),
            "stability_by_vol_regime": stability(
                cohort_rows, lambda r: r.volatility_regime),
            "stability_by_sector_top": dict(sorted(
                stability(cohort_rows, lambda r: r.sector).items(),
                key=lambda kv: -kv[1]["n"])[:8]),
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    json_path = os.path.join(OUT_DIR, "calibration_metrics.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, default=str)
    artifact_paths: list[tuple[str, str]] = [(json_path, "report")]

    bins = (result["cohorts"]["live"].get("walk_forward", {})
            .get("identity_reliability_bins")) or (
        result["cohorts"]["live"].get("identity_full_cohort", {})
        .get("reliability_bins"))
    if bins:
        svg_path = os.path.join(OUT_DIR, "calibration_reliability.svg")
        reliability_svg(bins, svg_path)
        artifact_paths.append((svg_path, "reliability_curve"))

    if args.registry:
        _record_registry_run(engine, result, rows, artifact_paths)

    print(json.dumps({
        "buy_resolved_scored": counts["buy_resolved_scored"],
        "live_n": len(live), "replay_n": len(replay),
        "unresolved": counts["unresolved"],
        "pooled_live": result["cohorts"]["live"].get("walk_forward", {}).get("pooled"),
        "live_label_bands": result["cohorts"]["live"].get("label_bands"),
    }, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
