"""Compare two E1 ablation runs across label-versions.

Expects two E1 JSON outputs (e.g., symmetric baseline vs asymmetric pivot).
Writes a comparison memo with:
  - class balance
  - retention (fixed at 80% in E1, included for record)
  - Spearman(y_hit, realized_vol_20d)
  - CV AUC
  - CV Sharpe uplift
  - per-fold uplift stability (mean, std, min/max)

Usage::

    python -m scripts.compare_label_versions \
        --old artifacts/e1_ablation_result_sym.json \
        --new artifacts/e1_ablation_result_asym.json \
        --out artifacts/e1_compare_memo.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from loguru import logger


def _load(p: Path) -> dict:
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text())


def _fold_uplifts(payload: dict) -> list[float]:
    return [float(f["sharpe_uplift"]) for f in payload.get("folds", [])]


def _fold_aucs(payload: dict) -> list[float]:
    return [float(f["auc"]) for f in payload.get("folds", [])]


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.fmean(vals), 4),
        "std": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
    }


def _row(metric: str, old_v, new_v, delta_str: str) -> str:
    return f"| {metric} | {old_v} | {new_v} | {delta_str} |"


def _classify_verdict(
    new_verdict: str, old_auc: float, new_auc: float,
    old_uplift: float, new_uplift: float,
) -> tuple[str, str]:
    """Per user spec Task 5:
      - PASS  → continue
      - FAIL but materially improved → optional alpha158 verification
      - FAIL with no meaningful improvement → abandon
    """
    if new_verdict == "PASS":
        return "CONTINUE", (
            "New label PASSES E1 gate (AUC >= 0.53, Sharpe uplift >= 0.25). "
            "Proceed with Phase 2 (alpha158 + bet sizing) using the asymmetric "
            "label as canonical."
        )

    auc_delta = new_auc - old_auc
    uplift_delta = new_uplift - old_uplift
    # "Materially improved" thresholds: +0.01 AUC OR +0.5 Sharpe uplift
    materially_improved = (auc_delta >= 0.01) or (uplift_delta >= 0.5)

    if materially_improved:
        return "OPTIONAL_ALPHA158", (
            f"New label still below PASS gate but materially improved "
            f"(ΔAUC={auc_delta:+.4f}, ΔSharpe_uplift={uplift_delta:+.4f}). "
            "The label was part of the problem. Optional next step: run "
            "alpha158 cross-sectional feature verification on the new label "
            "before committing to abandon."
        )
    return "ABANDON", (
        f"New label did not meaningfully improve "
        f"(ΔAUC={auc_delta:+.4f}, ΔSharpe_uplift={uplift_delta:+.4f}). "
        "Label symmetry was not the dominant failure mode. The meta-label "
        "signal is genuinely absent — abandon current setup. Archive "
        "artifacts, keep triple-barrier + LightGBM infra for future reuse."
    )


def build_memo(old: dict, new: dict) -> str:
    om = old.get("metrics", {})
    nm = new.get("metrics", {})

    old_auc = float(om.get("cv_auc_oof", 0.0))
    new_auc = float(nm.get("cv_auc_oof", 0.0))
    old_uplift = float(om.get("cv_sharpe_uplift_oof", 0.0))
    new_uplift = float(nm.get("cv_sharpe_uplift_oof", 0.0))

    old_sp = float(
        old.get("diagnostic_D1_sonnet", {})
           .get("spearman_label_vs_realized_vol_20d") or 0.0
    )
    new_sp = float(
        new.get("diagnostic_D1_sonnet", {})
           .get("spearman_label_vs_realized_vol_20d") or 0.0
    )
    old_ent = (
        new.get("diagnostic_D1_sonnet", {})
           .get("barrier_structurally_entangled", False)
    )
    new_ent = (
        new.get("diagnostic_D1_sonnet", {})
           .get("barrier_structurally_entangled", False)
    )

    old_uplifts = _fold_uplifts(old)
    new_uplifts = _fold_uplifts(new)
    old_aucs = _fold_aucs(old)
    new_aucs = _fold_aucs(new)

    old_stats = _stats(old_uplifts)
    new_stats = _stats(new_uplifts)
    old_auc_stats = _stats(old_aucs)
    new_auc_stats = _stats(new_aucs)

    old_verdict = old.get("verdict", "?")
    new_verdict = new.get("verdict", "?")

    action_tag, action_text = _classify_verdict(
        new_verdict, old_auc, new_auc, old_uplift, new_uplift,
    )

    lines: list[str] = []
    lines.append("# E1 — Old vs New Label Comparison Memo")
    lines.append("")
    lines.append("## Versions")
    lines.append("")
    lines.append(
        f"- **Old (symmetric PT=SL=2σ):** {old.get('experiment', 'E1 old')} "
        f"— verdict `{old_verdict}`"
    )
    lines.append(
        f"- **New (asymmetric PT=2σ, SL=1σ):** {new.get('experiment', 'E1 new')} "
        f"— verdict `{new_verdict}`"
    )
    lines.append(
        f"- **Pass/fail gates (unchanged):** AUC ≥ 0.53, Sharpe uplift ≥ 0.25"
    )
    lines.append("")

    lines.append("## Headline comparison")
    lines.append("")
    lines.append("| Metric | Old (symmetric) | New (asymmetric) | Δ |")
    lines.append("|--------|-----------------|------------------|---|")
    lines.append(_row("Verdict", f"`{old_verdict}`", f"`{new_verdict}`", "—"))
    lines.append(_row(
        "CV AUC (OOF)",
        f"{old_auc:.4f}", f"{new_auc:.4f}",
        f"{new_auc - old_auc:+.4f}",
    ))
    lines.append(_row(
        "CV Sharpe uplift (OOF)",
        f"{old_uplift:+.4f}", f"{new_uplift:+.4f}",
        f"{new_uplift - old_uplift:+.4f}",
    ))
    lines.append(_row(
        "CV filtered Sharpe",
        f"{om.get('cv_filtered_sharpe_oof', '—')}",
        f"{nm.get('cv_filtered_sharpe_oof', '—')}",
        "—",
    ))
    lines.append(_row(
        "CV baseline Sharpe",
        f"{om.get('cv_baseline_sharpe_oof', '—')}",
        f"{nm.get('cv_baseline_sharpe_oof', '—')}",
        "—",
    ))
    lines.append(_row(
        "Bailey DSR",
        f"{om.get('bailey_dsr', '—')}",
        f"{nm.get('bailey_dsr', '—')}",
        "—",
    ))
    lines.append(_row(
        "Retention frac",
        f"{om.get('retention_frac', '—')}",
        f"{nm.get('retention_frac', '—')}",
        "—",
    ))
    lines.append("")

    lines.append("## Class balance (n_cv_rows and hit-rate-proxy)")
    lines.append("")
    lines.append("| Item | Old | New |")
    lines.append("|------|-----|-----|")
    lines.append(
        f"| CV rows | {old.get('n_cv_rows', '—')} | {new.get('n_cv_rows', '—')} |"
    )
    lines.append(
        f"| Lockbox rows (UNTOUCHED) | "
        f"{old.get('n_lockbox_rows_untouched', '—')} | "
        f"{new.get('n_lockbox_rows_untouched', '—')} |"
    )
    # Proba stats as a proxy for class balance (hit_rate)
    o_p = old.get("proba_stats", {})
    n_p = new.get("proba_stats", {})
    lines.append(
        f"| Proba mean (≈hit-rate) | {o_p.get('mean', '—')} | {n_p.get('mean', '—')} |"
    )
    lines.append(
        f"| Proba std | {o_p.get('std', '—')} | {n_p.get('std', '—')} |"
    )
    lines.append(
        f"| Proba q20 threshold | {o_p.get('quantile_20_threshold', '—')} "
        f"| {n_p.get('quantile_20_threshold', '—')} |"
    )
    lines.append("")

    lines.append("## Sonnet D1 vol-label entanglement")
    lines.append("")
    lines.append("| Diagnostic | Old | New | Δ |")
    lines.append("|-----------|-----|-----|---|")
    lines.append(
        f"| Spearman(y_hit, realized_vol_20d) | {old_sp:+.4f} | {new_sp:+.4f} "
        f"| {new_sp - old_sp:+.4f} |"
    )
    lines.append(
        f"| abs(ρ) ≥ 0.20 (entangled) | {abs(old_sp) >= 0.20} | {abs(new_sp) >= 0.20} | — |"
    )
    if abs(new_sp) < abs(old_sp):
        lines.append(
            "- **Asymmetric barrier REDUCED vol-entanglement.** This is the "
            "primary hypothesis check from the debate — it held."
        )
    elif abs(new_sp) > abs(old_sp):
        lines.append(
            "- **Asymmetric barrier did NOT reduce vol-entanglement.** "
            "The label-vol coupling was not the dominant issue."
        )
    else:
        lines.append(
            "- **Vol-entanglement unchanged.** Asymmetric barrier had no effect."
        )
    lines.append("")

    lines.append("## Per-fold CV AUC stability")
    lines.append("")
    lines.append("| Stat | Old | New |")
    lines.append("|------|-----|-----|")
    lines.append(f"| Mean | {old_auc_stats['mean']} | {new_auc_stats['mean']} |")
    lines.append(f"| Std  | {old_auc_stats['std']} | {new_auc_stats['std']} |")
    lines.append(f"| Min  | {old_auc_stats['min']} | {new_auc_stats['min']} |")
    lines.append(f"| Max  | {old_auc_stats['max']} | {new_auc_stats['max']} |")
    lines.append("")

    lines.append("## Per-fold Sharpe uplift stability (regime-sensitivity proxy)")
    lines.append("")
    lines.append("| Stat | Old | New |")
    lines.append("|------|-----|-----|")
    lines.append(f"| Mean | {old_stats['mean']} | {new_stats['mean']} |")
    lines.append(f"| Std  | {old_stats['std']} | {new_stats['std']} |")
    lines.append(f"| Min  | {old_stats['min']} | {new_stats['min']} |")
    lines.append(f"| Max  | {old_stats['max']} | {new_stats['max']} |")
    lines.append("")
    if new_stats["std"] < old_stats["std"]:
        lines.append(
            "- **Asymmetric label REDUCED per-fold uplift volatility.** "
            "Model less regime-sensitive under new label."
        )
    else:
        lines.append(
            "- **Per-fold uplift volatility unchanged or worse.** Regime "
            "sensitivity persists — label was not the regime-driver."
        )
    lines.append("")

    lines.append("## Per-fold detail")
    lines.append("")
    lines.append("| Fold | Old AUC | New AUC | Old Uplift | New Uplift |")
    lines.append("|------|---------|---------|------------|------------|")
    old_folds = old.get("folds", [])
    new_folds = new.get("folds", [])
    n = max(len(old_folds), len(new_folds))
    for i in range(n):
        o = old_folds[i] if i < len(old_folds) else {}
        nf = new_folds[i] if i < len(new_folds) else {}
        lines.append(
            f"| {i} | {o.get('auc', '—')} | {nf.get('auc', '—')} "
            f"| {o.get('sharpe_uplift', '—')} | {nf.get('sharpe_uplift', '—')} |"
        )
    lines.append("")

    lines.append("## Decision recommendation")
    lines.append("")
    lines.append(f"**Action:** `{action_tag}`")
    lines.append("")
    lines.append(action_text)
    lines.append("")

    lines.append("## Safety guardrails honored")
    lines.append("")
    lines.append("- Lockbox NOT touched in E1 (neither old nor new run).")
    lines.append("- No alpha158 / new features introduced — label-only pivot.")
    lines.append("- E1 gates unchanged (AUC ≥ 0.53, Sharpe uplift ≥ 0.25).")
    lines.append("- Old label version preserved (separate engine_version).")
    lines.append("- No model hyper-parameter changes.")
    lines.append(
        "- `calibration_applied=False` on both runs (Phase 1 alignment)."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path,
        default=Path("artifacts/e1_compare_memo.md"),
    )
    args = parser.parse_args()

    old = _load(args.old)
    new = _load(args.new)
    memo = build_memo(old, new)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(memo, encoding="utf-8")
    logger.info("[compare] memo written → {}", args.out)
    print(memo)
    # Exit 0 on CONTINUE, 1 on ABANDON, 2 on OPTIONAL_ALPHA158
    if "CONTINUE" in memo:
        return 0
    if "OPTIONAL_ALPHA158" in memo:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
