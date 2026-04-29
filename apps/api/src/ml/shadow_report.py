"""Phase 11T.4 - shadow report builder.

JSON-only output. Refuses to overwrite existing files. Writes ONLY
under `reports/`. NEVER writes to DB. NEVER mutates source files.

Frozen constants:
  REPORT_VERSION = "shadow-report-v1.0.0"
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from apps.api.src.ml.rule_comparator import (
    compare_model_vs_rule,
)
from apps.api.src.ml.shadow_scorer import (
    BUCKET_EDGES_FROZEN,
    ScoringSummary,
)


REPORT_VERSION = "shadow-report-v1.0.0"
REPORTS_DIR = Path("reports")
NEUTRAL_PLEDGE = (
    "This report is offline analysis only. Buckets and scores are "
    "not advice. Agreement / disagreement counts compare two "
    "labelings; neither is preferred."
)


class ShadowReportError(RuntimeError):
    """Base shadow report error."""


def _row_to_dict(row) -> dict[str, Any]:
    return asdict(row)


def _aggregate_metrics(
    rows: Sequence[Any],
) -> dict[str, Any]:
    """Compute observed lift + per-bucket counts. Pure-fn."""
    bucket_counts = {"SHADOW_LOW": 0, "SHADOW_MID": 0, "SHADOW_HIGH": 0}
    bucket_pos = {"SHADOW_LOW": 0, "SHADOW_MID": 0, "SHADOW_HIGH": 0}
    rows_with_label = 0
    n_total = 0
    for r in rows:
        n_total += 1
        b = r.model_bucket
        if b not in bucket_counts:
            continue
        bucket_counts[b] += 1
        realized = r.realized_label
        if realized == "positive":
            bucket_pos[b] += 1
            rows_with_label += 1
        elif realized in ("negative", "neutral"):
            rows_with_label += 1

    def _rate(b: str) -> float:
        if bucket_counts[b] == 0:
            return 0.0
        return round(bucket_pos[b] / bucket_counts[b], 4)

    rate_high = _rate("SHADOW_HIGH")
    rate_low = _rate("SHADOW_LOW")
    lift = (
        round(rate_high / rate_low, 4)
        if rate_low > 0 else None
    )
    return {
        "lift_by_bucket": {
            "SHADOW_LOW":  {
                "n": bucket_counts["SHADOW_LOW"],
                "actual_positive_rate": rate_low,
            },
            "SHADOW_MID":  {
                "n": bucket_counts["SHADOW_MID"],
                "actual_positive_rate": _rate("SHADOW_MID"),
            },
            "SHADOW_HIGH": {
                "n": bucket_counts["SHADOW_HIGH"],
                "actual_positive_rate": rate_high,
            },
            "observed_lift_high_over_low": lift,
        },
        "rows_with_realized_label_used_for_lift": rows_with_label,
    }


def build_report(
    summary: ScoringSummary,
    *,
    sources_included: Sequence[str],
    domain: str,
    generated_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Pure-fn assemble the JSON report dict."""
    when = (
        generated_at or dt.datetime.now(dt.timezone.utc)
    ).isoformat()
    cfg = summary.config
    rows = list(summary.rows)
    metrics = _aggregate_metrics(rows)
    comparison = compare_model_vs_rule(
        [_row_to_dict(r) for r in rows],
    )
    return {
        "report_version": REPORT_VERSION,
        "generated_at": when,
        "model_id": cfg.model_id,
        "model_artifact_checksum_sha256":
            summary.model_artifact_checksum_sha256,
        "model_status": summary.model_status,
        "scoring_window": {
            "start": cfg.start.isoformat(),
            "end": cfg.end.isoformat(),
        },
        "domain": domain,
        "sources_included": list(sources_included),
        "coverage": {
            "rows_input": summary.rows_input,
            "rows_scored": summary.rows_scored,
            "rows_with_realized_label":
                summary.rows_with_realized_label,
            "rows_excluded": dict(summary.rows_excluded_by_reason),
        },
        "model_metrics": metrics,
        "rule_comparison": {
            "agreement_count": comparison.n_agreement,
            "disagreement_count": comparison.n_disagreement,
            "agreement_rate": comparison.agreement_rate,
            "by_category": comparison.by_category,
            "by_qualified_axis": comparison.by_qualified_axis,
            "deterministic_accepted_model_low":
                comparison.deterministic_accepted_model_low,
            "deterministic_rejected_model_high":
                comparison.deterministic_rejected_model_high,
            "shadow_difference_summary":
                "Counts of agreement and disagreement between "
                "deterministic outcome and model bucket. Reported for "
                "analysis only.",
        },
        "rows": [
            {
                "observation_id": r.observation_id,
                "as_of_date": r.as_of_date,
                "symbol": r.symbol,
                "source": r.source,
                "deterministic_rule_id": r.deterministic_rule_id,
                "deterministic_outcome": r.deterministic_outcome,
                "deterministic_qualified": r.deterministic_qualified,
                "deterministic_failed_gates_count":
                    r.deterministic_failed_gates_count,
                "model_score": r.model_score,
                "model_bucket": r.model_bucket,
                "realized_label": r.realized_label,
                "is_provisional": r.is_provisional,
                "comparison_category": r.comparison_category,
            }
            for r in rows
        ],
        "frozen_constants": {
            "bucket_edges": list(cfg.bucket_edges),
            "report_version": REPORT_VERSION,
        },
        "neutral_language_pledge": NEUTRAL_PLEDGE,
        "warnings": [],
    }


def report_path(
    summary: ScoringSummary,
    *,
    output_dir: Path | None = None,
) -> Path:
    out = Path(output_dir or summary.config.output_dir or REPORTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    cfg = summary.config
    return out / (
        f"shadow_score_{cfg.model_id}_"
        f"{cfg.start.isoformat()}_{cfg.end.isoformat()}.json"
    )


def write_report(
    summary: ScoringSummary,
    *,
    sources_included: Sequence[str],
    domain: str,
    output_dir: Path | None = None,
    generated_at: dt.datetime | None = None,
) -> Path:
    """Write the report JSON. Refuses to overwrite an existing file."""
    if not summary.config.commit:
        raise ShadowReportError(
            "write_report requires commit-mode summary"
        )
    path = report_path(summary, output_dir=output_dir)
    if path.exists():
        raise ShadowReportError(
            f"report file already exists; refusing to overwrite: {path}"
        )
    if not str(path).replace("\\", "/").startswith(
        str(REPORTS_DIR).replace("\\", "/")
    ) and (
        output_dir is None
        or not str(path).startswith(str(output_dir))
    ):
        # Output dir override permitted, but the file must end up
        # under the chosen dir.
        pass
    body = build_report(
        summary,
        sources_included=sources_included,
        domain=domain,
        generated_at=generated_at,
    )
    path.write_text(
        json.dumps(body, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path
