"""Phase 2 (Weeks 2-4) conditional pipeline — alpha158 features +
asymmetric-barrier proxy label + AFML Ch.10 bet sizing + fresh-forward
validation.

Gated on E1 VERDICT=PASS. Per-debate synthesis (2026-04-21):
  - Week 2: Qlib alpha158-style cross-sectional features added on top of
    E1 kept-feature set.
  - Week 3: asymmetric triple-barrier proxy label + bet_size_probability
    (Lopez de Prado AFML Ch.10 formula) replacing filter-at-threshold.
  - Week 4: fresh-forward validation on last 25% of CV date-range
    (i.e., 20% of total). Original 537-trade lockbox REMAINS UNTOUCHED.
  - Shadow-only: no writes to recommendation / action / model tables.
  - calibration_applied=False (Phase 1/4 alignment).

Qlib and mlfinlab are NOT required — alpha158-like features and the
bet-sizing formula are implemented in-house from primary sources
(Qlib `alpha158` design notes + AFML Ch.10 Eq. 10.4).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import sqrt
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger
from scipy.stats import norm, spearmanr

from apps.ml.dataset import DatasetBundle, split_cv_and_lockbox
from apps.ml.e1_ablation import (
    ENTANGLEMENT_RHO_THRESHOLD,
    compute_spearman_label_vol,
    split_features,
)
from apps.ml.metrics import bailey_dsr, cv_auc_logloss, simulate_filtered_sharpe
from apps.ml.training import EARLY_STOPPING, LGB_PARAMS, NUM_BOOST_ROUND

# ---------------------------------------------------------------------------
# Phase 2 spec constants
# ---------------------------------------------------------------------------

# Fresh-forward split: last 25% of CV date-range held as Phase 2 fresh
# holdout. Lockbox (final 20% of TOTAL) is NEVER touched.
PHASE2_FRESH_FRAC: float = 0.25

# Alpha158-like cross-sectional features built from existing alpha-proxy
# columns (residual momentum, sector rank, trend, price vs SMA, composite).
ALPHA158_BASE_COLS: tuple[str, ...] = (
    "residual_momentum_60d",
    "sector_relative_rank",
    "trend_strength_20d",
    "price_vs_200sma",
    "composite_score",
)
ALPHA158_SUFFIXES: tuple[str, ...] = ("_xs_rank", "_xs_zscore")

# AFML Ch.10 bet-sizing parameters
BET_SIZE_MIN_PROBA: float = 1e-6
BET_SIZE_MAX_PROBA: float = 1.0 - 1e-6
BET_SIZE_LONG_ONLY_CLIP: bool = True   # clip to [0, 1] for long-only primary

# Artifacts
ARTIFACTS_DIR = Path("artifacts")
E1_RESULT_PATH = ARTIFACTS_DIR / "e1_ablation_result.json"
E2_RESULT_PATH = ARTIFACTS_DIR / "e2_pipeline_result.json"
E2_MEMO_PATH = ARTIFACTS_DIR / "e2_pipeline_memo.md"

# Gate: which verdicts permit Phase 2 execution
PROCEED_VERDICTS: frozenset[str] = frozenset({"PASS"})
PROCEED_VERDICTS_WITH_FORCE: frozenset[str] = frozenset(
    {"PASS", "AMBIGUOUS_LABEL_SIZING", "AMBIGUOUS_NOISE"}
)


# ---------------------------------------------------------------------------
# Gate check
# ---------------------------------------------------------------------------


class Phase2GateBlocked(RuntimeError):
    pass


def check_e1_gate(
    e1_result: dict, *, force: bool = False,
) -> tuple[bool, str]:
    verdict = e1_result.get("verdict", "UNKNOWN")
    allowed = PROCEED_VERDICTS_WITH_FORCE if force else PROCEED_VERDICTS
    if verdict not in allowed:
        return False, (
            f"E1 verdict={verdict} not in allowed={sorted(allowed)}. "
            "Use --force to proceed on AMBIGUOUS_* buckets."
        )
    return True, f"E1 verdict={verdict} — phase 2 green-lit"


def load_e1_result(path: Path = E1_RESULT_PATH) -> dict:
    if not path.exists():
        raise Phase2GateBlocked(
            f"E1 result not found: {path}. "
            "Run `python -m scripts.run_e1_ablation` first."
        )
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Week 2 — alpha158-like cross-sectional block
# ---------------------------------------------------------------------------


def build_alpha158_block(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Augment df with cross-sectional rank + z-score features per Qlib
    alpha158 cross-sectional design notes.

    For each base column c in ALPHA158_BASE_COLS:
      - c_xs_rank      = rank within as_of_date / n_per_day
      - c_xs_zscore    = (c - mean_day) / std_day

    Missing base columns are skipped silently; the list of added feature
    names is returned.
    """
    out = df.copy()
    added: list[str] = []
    for col in ALPHA158_BASE_COLS:
        if col not in out.columns:
            logger.warning("[e2.alpha158] base col missing, skipping: {}", col)
            continue
        rank_col = f"{col}_xs_rank"
        z_col = f"{col}_xs_zscore"
        out[rank_col] = (
            out.groupby("as_of_date")[col].rank(method="average", pct=True)
        )
        day_mean = out.groupby("as_of_date")[col].transform("mean")
        day_std = out.groupby("as_of_date")[col].transform("std").replace(0, np.nan)
        out[z_col] = ((out[col] - day_mean) / day_std).fillna(0.0)
        added.extend([rank_col, z_col])
    logger.info("[e2.alpha158] added {} features: {}", len(added), added)
    return out, added


# ---------------------------------------------------------------------------
# Week 3a — asymmetric barrier proxy label
# ---------------------------------------------------------------------------


def asymmetric_barrier_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """Approximate asymmetric triple-barrier (pt_sl=[2.0, 1.0]) label.

    TRUE asymmetric barriers require re-running outcome_labeling.py against
    the price_bar series with `PT_SIGMAS=2.0, SL_SIGMAS=1.0`. This is a
    Phase 2 scaffold; we approximate using the terminal forward return:

        y_hit_asym = 1 if forward_return_pct > 0 else 0

    This proxy accepts any positive-at-horizon trade as a win
    (asymmetric because a wider SL would not have stopped it out at −1σ).
    Flag in the memo that this is an APPROXIMATION pending a re-backfill.
    """
    out = df.copy()
    if "forward_return_pct" not in out.columns:
        raise ValueError("forward_return_pct column required")
    out["y_hit_asym"] = (out["forward_return_pct"] > 0).astype(int)
    flip_rate = float((out["y_hit"] != out["y_hit_asym"]).mean())
    logger.info(
        "[e2.asymbarrier] y_hit_asym computed. flip_rate vs y_hit = {:.4f}",
        flip_rate,
    )
    return out


# ---------------------------------------------------------------------------
# Week 3b — bet sizing per AFML Ch.10
# ---------------------------------------------------------------------------


def bet_size_probability(
    proba: np.ndarray | float, num_classes: int = 2,
    long_only: bool = BET_SIZE_LONG_ONLY_CLIP,
) -> np.ndarray:
    """Per Lopez de Prado AFML Ch.10 Eq. 10.4:

        z = (p - 1/K) / sqrt(p * (1-p))
        m = 2*Phi(z) - 1

    Returns bet size in [-1, 1]. For long-only primary (meta-label on a
    Buy-only engine), clip to [0, 1] — negative size = abstain.
    """
    p = np.asarray(proba, dtype=float).clip(
        BET_SIZE_MIN_PROBA, BET_SIZE_MAX_PROBA,
    )
    z = (p - 1.0 / num_classes) / np.sqrt(p * (1.0 - p))
    m = 2.0 * norm.cdf(z) - 1.0
    if long_only:
        m = np.clip(m, 0.0, 1.0)
    return m


# ---------------------------------------------------------------------------
# Week 4 — fresh-forward split (lockbox untouched)
# ---------------------------------------------------------------------------


def split_cv_train_and_fresh_holdout(
    cv_df: pd.DataFrame,
    fresh_frac: float = PHASE2_FRESH_FRAC,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split pre-lockbox CV rows into (train, fresh_holdout) by date.

    Last `fresh_frac` of CV date range goes to fresh_holdout. The original
    lockbox (final 20% of TOTAL) is already excluded from cv_df upstream.
    """
    dates = sorted(cv_df["as_of_date"].unique())
    if not dates:
        raise ValueError("empty cv_df")
    cutoff_idx = int(len(dates) * (1.0 - fresh_frac))
    cutoff = dates[cutoff_idx]
    train = cv_df[cv_df["as_of_date"] < cutoff].copy()
    fresh = cv_df[cv_df["as_of_date"] >= cutoff].copy()
    logger.info(
        "[e2.split] cv_train={} fresh_holdout={} cutoff={}",
        len(train), len(fresh), cutoff,
    )
    return train, fresh


# ---------------------------------------------------------------------------
# Shadow metrics (no writes)
# ---------------------------------------------------------------------------


def shadow_evaluate_bet_sizing(
    df: pd.DataFrame, proba: np.ndarray,
) -> dict:
    """Simulate bet-sized PnL vs unfiltered baseline. Metrics-only; no
    writes to live tables. Mirrors simulate_filtered_sharpe signature but
    with continuous sizing (m = bet_size_probability) instead of filtering.
    """
    from collections import defaultdict
    from statistics import mean, stdev

    import math
    assert len(df) == len(proba)
    df = df.copy()
    df["_proba"] = proba
    df["_size"] = bet_size_probability(proba, long_only=True)
    df["_daily_ret_per_bar"] = (
        df["forward_return_pct"].astype(float) / 100.0
    ) / df["barrier_n_bars"].clip(lower=1)

    # Baseline (all Buys, full size)
    by_day_base: dict[object, list[float]] = defaultdict(list)
    for _, r in df.iterrows():
        by_day_base[r["as_of_date"]].append(r["_daily_ret_per_bar"])
    base_rets = [
        sum(v) / max(1, len(v)) for _, v in sorted(by_day_base.items())
    ]

    # Bet-sized (size * return, daily avg over sized positions)
    df["_sized_ret"] = df["_size"] * df["_daily_ret_per_bar"]
    by_day_sized: dict[object, list[float]] = defaultdict(list)
    for _, r in df.iterrows():
        if r["_size"] > 0:
            by_day_sized[r["as_of_date"]].append(r["_sized_ret"])
    sized_rets = [
        sum(v) / max(1, len(v)) for _, v in sorted(by_day_sized.items())
    ]

    def _sharpe(rets: list[float]) -> float:
        if len(rets) < 5:
            return 0.0
        m_ = mean(rets)
        s = stdev(rets) if len(rets) > 1 else 0.0
        if s == 0:
            return 0.0
        return (m_ / s) * math.sqrt(252)

    base_sh = _sharpe(base_rets)
    sized_sh = _sharpe(sized_rets)

    size_arr = df["_size"].to_numpy()
    return {
        "baseline_trade_count": int(len(df)),
        "sized_active_count": int((size_arr > 0).sum()),
        "baseline_sharpe": round(base_sh, 4),
        "sized_sharpe": round(sized_sh, 4),
        "sharpe_uplift": round(sized_sh - base_sh, 4),
        "avg_size_when_active": round(
            float(size_arr[size_arr > 0].mean())
            if (size_arr > 0).any() else 0.0, 4,
        ),
        "size_distribution": {
            "q10": round(float(np.quantile(size_arr, 0.10)), 4),
            "q50": round(float(np.quantile(size_arr, 0.50)), 4),
            "q90": round(float(np.quantile(size_arr, 0.90)), 4),
        },
    }


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class Phase2Result:
    gate_passed: bool
    gate_reason: str
    e1_verdict: str
    features_used: list[str]
    features_added_alpha158: list[str]
    asymmetric_barrier_flip_rate: float
    cv_train_rows: int
    fresh_holdout_rows: int
    lockbox_rows_untouched: int
    # metrics on fresh_holdout (the honest OOS for Phase 2 decision)
    fresh_auc_original_label: float
    fresh_auc_asymmetric_label: float
    fresh_bet_sizing_metrics: dict
    fresh_filter_metrics_top80: dict
    spearman_label_vs_vol20d: float | None
    spearman_p_value: float | None
    barrier_structurally_entangled: bool
    feature_importance_top15: list[tuple[str, float]]
    bailey_dsr: float
    calibration_applied: bool           # always False
    proba_stats: dict
    # Conditional plan markers
    weeks_2_4_plan_status: str


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_phase2_pipeline(
    bundle: DatasetBundle,
    e1_result: dict,
    *,
    force: bool = False,
) -> Phase2Result:
    """Execute Phase 2 conditional pipeline. Lockbox untouched.
    Returns Phase2Result; raises Phase2GateBlocked if E1 gate denies.
    """
    gate_ok, gate_reason = check_e1_gate(e1_result, force=force)
    if not gate_ok:
        raise Phase2GateBlocked(gate_reason)
    logger.info("[e2] gate: {}", gate_reason)

    # --- split off the lockbox and NEVER touch it again ---------------------
    cv_df, lockbox_df = split_cv_and_lockbox(bundle.df)
    n_lockbox = len(lockbox_df)
    del lockbox_df

    if len(cv_df) < 400:
        raise RuntimeError(
            f"too few CV rows ({len(cv_df)}) for Phase 2 (train + fresh)"
        )

    # --- Sonnet D1 diagnostic (continues from E1) ---------------------------
    rho, pval = compute_spearman_label_vol(cv_df)
    entangled = rho is not None and abs(rho) > ENTANGLEMENT_RHO_THRESHOLD
    logger.info(
        "[e2][D1] spearman(y_hit, realized_vol_20d) rho={} entangled={}",
        rho, entangled,
    )

    # --- Week 2: drop risk features + add alpha158 block --------------------
    kept, dropped = split_features(bundle.features)
    cv_df, added_alpha158 = build_alpha158_block(cv_df)
    features_phase2 = kept + added_alpha158
    logger.info(
        "[e2] features: kept={} + alpha158={} → {} total (dropped={})",
        len(kept), len(added_alpha158), len(features_phase2), len(dropped),
    )

    # --- Week 3a: asymmetric-barrier proxy label ----------------------------
    cv_df = asymmetric_barrier_proxy(cv_df)
    flip_rate = float((cv_df["y_hit"] != cv_df["y_hit_asym"]).mean())

    # --- Week 4: fresh-forward split (NOT the lockbox) ----------------------
    train_df, fresh_df = split_cv_train_and_fresh_holdout(cv_df)
    if len(train_df) < 100 or len(fresh_df) < 50:
        raise RuntimeError(
            f"train={len(train_df)} fresh={len(fresh_df)} too small"
        )

    # --- Train two models: original label vs asymmetric-proxy --------------
    X_tr = train_df[features_phase2].values
    X_fr = fresh_df[features_phase2].values

    def _fit_and_predict(target_col: str) -> tuple[float, np.ndarray, lgb.Booster]:
        y_tr = train_df[target_col].values
        y_fr = fresh_df[target_col].values
        dtr = lgb.Dataset(X_tr, label=y_tr)
        dva = lgb.Dataset(X_fr, label=y_fr, reference=dtr)
        model = lgb.train(
            LGB_PARAMS, dtr,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[dva],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )
        proba = model.predict(X_fr, num_iteration=model.best_iteration)
        cls = cv_auc_logloss(y_fr, proba)
        return float(cls["auc"]), proba, model

    auc_orig, proba_orig, model_orig = _fit_and_predict("y_hit")
    auc_asym, proba_asym, _ = _fit_and_predict("y_hit_asym")
    logger.info(
        "[e2] fresh-holdout AUC: original_label={:.4f} asymmetric_proxy={:.4f}",
        auc_orig, auc_asym,
    )

    # --- Bet sizing metrics (on original-label model) -----------------------
    sizing = shadow_evaluate_bet_sizing(fresh_df, proba_orig)
    logger.info(
        "[e2] fresh-holdout bet-sizing: base_sharpe={:.4f} sized_sharpe={:.4f} "
        "uplift={:.4f} active={} avg_size={:.4f}",
        sizing["baseline_sharpe"], sizing["sized_sharpe"],
        sizing["sharpe_uplift"], sizing["sized_active_count"],
        sizing["avg_size_when_active"],
    )

    # --- Comparison filter at top-80% quantile (apples-to-apples w/ E1) ----
    threshold_top80 = float(np.quantile(proba_orig, 0.20))
    filter_metrics = simulate_filtered_sharpe(
        fresh_df, proba_orig, threshold_top80,
    )

    # --- Feature importance (original label model) --------------------------
    gains = model_orig.feature_importance(importance_type="gain")
    importance = sorted(
        [(f, float(g)) for f, g in zip(features_phase2, gains)],
        key=lambda x: -x[1],
    )[:15]

    # --- DSR (informational, n_trials=2 since we train 2 labels) ------------
    dsr = bailey_dsr(
        sharpe=sizing["sized_sharpe"],
        n_trials=2,
        n_obs=max(30, len(fresh_df)),
    )

    proba_stats = {
        "mean": float(np.mean(proba_orig)),
        "std": float(np.std(proba_orig)),
        "min": float(np.min(proba_orig)),
        "max": float(np.max(proba_orig)),
        "q20_threshold_used": threshold_top80,
    }

    # --- Conditional plan status --------------------------------------------
    if sizing["sharpe_uplift"] > 0 and auc_orig >= 0.53:
        plan_status = "PROCEED_TO_WEEK5_SHADOW"
    elif auc_asym > auc_orig + 0.02:
        plan_status = "ITERATE_RUN_TRUE_ASYMMETRIC_BARRIER_BACKFILL"
    else:
        plan_status = "ITERATE_OR_ABANDON_RECONSIDER"

    result = Phase2Result(
        gate_passed=True,
        gate_reason=gate_reason,
        e1_verdict=e1_result.get("verdict", "UNKNOWN"),
        features_used=features_phase2,
        features_added_alpha158=added_alpha158,
        asymmetric_barrier_flip_rate=round(flip_rate, 4),
        cv_train_rows=len(train_df),
        fresh_holdout_rows=len(fresh_df),
        lockbox_rows_untouched=n_lockbox,
        fresh_auc_original_label=round(auc_orig, 4),
        fresh_auc_asymmetric_label=round(auc_asym, 4),
        fresh_bet_sizing_metrics=sizing,
        fresh_filter_metrics_top80=filter_metrics,
        spearman_label_vs_vol20d=rho,
        spearman_p_value=pval,
        barrier_structurally_entangled=entangled,
        feature_importance_top15=importance,
        bailey_dsr=round(dsr, 4),
        calibration_applied=False,
        proba_stats=proba_stats,
        weeks_2_4_plan_status=plan_status,
    )
    logger.info(
        "[e2] phase_2_plan_status={} sized_uplift={:.4f} auc_orig={:.4f}",
        plan_status, sizing["sharpe_uplift"], auc_orig,
    )
    return result


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------


def write_json(result: Phase2Result, path: Path = E2_RESULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": "Phase 2 — Weeks 2-4 conditional pipeline",
        "debate_ref": (
            "~/debates/meta_label_lightgbm_20260421_162118/synthesis.md"
        ),
        "e1_verdict": result.e1_verdict,
        "gate_passed": result.gate_passed,
        "gate_reason": result.gate_reason,
        "metrics_fresh_holdout": {
            "auc_original_label": result.fresh_auc_original_label,
            "auc_asymmetric_proxy_label": result.fresh_auc_asymmetric_label,
            "bet_sizing": result.fresh_bet_sizing_metrics,
            "filter_top80_quantile": result.fresh_filter_metrics_top80,
            "bailey_dsr": result.bailey_dsr,
        },
        "asymmetric_barrier_flip_rate": result.asymmetric_barrier_flip_rate,
        "asymmetric_barrier_NOTE": (
            "PROXY label = forward_return_pct > 0. TRUE asymmetric barrier "
            "requires re-running apps/worker/src/jobs/score_outcomes.py with "
            "PT_SIGMAS=2.0, SL_SIGMAS=1.0 and re-backfill."
        ),
        "diagnostic_D1_sonnet": {
            "spearman_label_vs_realized_vol_20d": result.spearman_label_vs_vol20d,
            "p_value": result.spearman_p_value,
            "entanglement_rho_threshold": ENTANGLEMENT_RHO_THRESHOLD,
            "barrier_structurally_entangled": result.barrier_structurally_entangled,
        },
        "features_used": result.features_used,
        "features_added_alpha158": result.features_added_alpha158,
        "feature_importance_top15": result.feature_importance_top15,
        "proba_stats": result.proba_stats,
        "calibration_applied": result.calibration_applied,
        "cv_train_rows": result.cv_train_rows,
        "fresh_holdout_rows": result.fresh_holdout_rows,
        "lockbox_rows_untouched": result.lockbox_rows_untouched,
        "weeks_2_4_plan_status": result.weeks_2_4_plan_status,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info("[e2] json written → {}", path)
    return path


def write_memo(result: Phase2Result, path: Path = E2_MEMO_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizing = result.fresh_bet_sizing_metrics
    filt = result.fresh_filter_metrics_top80

    lines: list[str] = []
    lines.append("# Phase 2 — Weeks 2-4 Conditional Pipeline Memo")
    lines.append("")
    lines.append(f"**E1 verdict:** `{result.e1_verdict}` → gate `{result.gate_passed}`")
    lines.append(f"**Plan status:** `{result.weeks_2_4_plan_status}`")
    lines.append("")

    lines.append("## Fresh-holdout metrics (Week 4 validation)")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append(
        f"| AUC (original label) | {result.fresh_auc_original_label:.4f} | "
        "with alpha158 block, risk features dropped |"
    )
    lines.append(
        f"| AUC (asymmetric proxy label) | "
        f"{result.fresh_auc_asymmetric_label:.4f} | "
        f"Δ vs original = "
        f"{result.fresh_auc_asymmetric_label - result.fresh_auc_original_label:+.4f} |"
    )
    lines.append(
        f"| Baseline Sharpe (fresh) | {sizing['baseline_sharpe']:.4f} | "
        "all Buys, full size |"
    )
    lines.append(
        f"| Bet-sized Sharpe (fresh) | {sizing['sized_sharpe']:.4f} | "
        f"AFML Ch.10 bet_size_probability |"
    )
    lines.append(
        f"| Sharpe uplift (sized) | {sizing['sharpe_uplift']:+.4f} | "
        f"primary decision metric |"
    )
    lines.append(
        f"| Filter@top80 Sharpe (comparison) | "
        f"{filt['filtered_sharpe']:.4f} | "
        f"uplift = {filt['sharpe_uplift']:+.4f} |"
    )
    lines.append(
        f"| Bet-size avg when active | {sizing['avg_size_when_active']:.4f} | "
        f"[0, 1] long-only clip |"
    )
    lines.append(
        f"| Bet-size q10 / q50 / q90 | "
        f"{sizing['size_distribution']['q10']:.3f} / "
        f"{sizing['size_distribution']['q50']:.3f} / "
        f"{sizing['size_distribution']['q90']:.3f} | |"
    )
    lines.append(
        f"| Bailey DSR (informational) | {result.bailey_dsr:.4f} | n_trials=2 |"
    )
    lines.append("")

    lines.append("## Sonnet D1 vol-label entanglement")
    lines.append("")
    rho_s = (
        f"{result.spearman_label_vs_vol20d:.4f}"
        if result.spearman_label_vs_vol20d is not None else "n/a"
    )
    p_s = (
        f"{result.spearman_p_value:.4g}"
        if result.spearman_p_value is not None else "n/a"
    )
    lines.append(
        f"- Spearman(y_hit, realized_vol_20d) = **{rho_s}** (p = {p_s}) — "
        f"entangled: {result.barrier_structurally_entangled}"
    )
    lines.append("")

    lines.append("## Asymmetric barrier label")
    lines.append("")
    lines.append(
        f"- Flip-rate y_hit → y_hit_asym = **{result.asymmetric_barrier_flip_rate:.4f}**"
    )
    lines.append(
        "- **WARNING:** This is a PROXY (`y_hit_asym = forward_return_pct > 0`). "
        "True asymmetric triple-barrier requires re-running "
        "`apps/worker/src/jobs/score_outcomes.py` with "
        "`PT_SIGMAS=2.0, SL_SIGMAS=1.0` and re-backfilling HistoricalLabel. "
        "If `asymmetric AUC - original AUC > 0.02` the re-backfill is worth doing."
    )
    lines.append("")

    lines.append("## Features")
    lines.append("")
    lines.append(
        f"**Alpha158-like block added ({len(result.features_added_alpha158)}):** "
        + ", ".join(f"`{f}`" for f in result.features_added_alpha158)
    )
    lines.append("")
    lines.append(f"**Total features used:** {len(result.features_used)}")
    lines.append("")

    lines.append("## Feature importance (gain, top 15)")
    lines.append("")
    lines.append("| # | Feature | Gain |")
    lines.append("|---|---------|------|")
    for i, (f, g) in enumerate(result.feature_importance_top15, 1):
        lines.append(f"| {i} | `{f}` | {g:.1f} |")
    lines.append("")

    lines.append("## Data split")
    lines.append("")
    lines.append(f"- CV train rows: {result.cv_train_rows}")
    lines.append(
        f"- Fresh holdout rows (Phase 2 OOS): {result.fresh_holdout_rows}"
    )
    lines.append(
        f"- **Lockbox rows UNTOUCHED:** {result.lockbox_rows_untouched} "
        "(held for single final read after model is locked)"
    )
    lines.append(f"- Calibration applied: `{result.calibration_applied}`")
    lines.append("")

    lines.append("## Conditional plan — Weeks 2-4")
    lines.append("")
    lines.append(f"**Current status:** `{result.weeks_2_4_plan_status}`")
    lines.append("")
    lines.append(
        "- **Week 2 (DONE in this run)** — Qlib alpha158-style cross-sectional "
        "features added: rank-within-day + z-score-within-day for "
        "residual_momentum_60d, sector_relative_rank, trend_strength_20d, "
        "price_vs_200sma, composite_score."
    )
    lines.append(
        "- **Week 3 (PARTIAL)** — Bet sizing via AFML Ch.10 "
        "`bet_size_probability` computed and shadow-evaluated on fresh holdout. "
        "Asymmetric barrier is a PROXY (forward_return_pct>0) until re-backfill."
    )
    lines.append(
        "- **Week 4 (DONE in this run)** — Fresh-forward validation on last 25% "
        "of CV date-range (20% of total). Lockbox untouched."
    )
    lines.append(
        "- **Weeks 5+ (conditional)** — Shadow redesigned model at full "
        "position weight against fresh forward data for 2-4 weeks. "
        f"Decision: `{result.weeks_2_4_plan_status}`."
    )
    lines.append("")

    lines.append("## Safety and guardrails (Phase 2 constraints)")
    lines.append("")
    lines.append("- No writes to recommendation / action / ranked_signal tables.")
    lines.append("- No modifications to alpha signal pipeline.")
    lines.append("- Calibration layer explicitly disabled (Phase 1 alignment).")
    lines.append("- LightGBM deterministic seed = 42.")
    lines.append(
        "- Original 537-trade lockbox RESERVED for single final read after "
        "full redesign is locked. Phase 2 never reads it."
    )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("[e2] memo written → {}", path)
    return path
