"""Phase SYSTEM-ALPHA — signal/execution/risk/health analytics.

Single source of truth for all non-ML decision diagnostics. Every function
deterministic, no future outcome access, auditable.
"""

FACTOR_VERSION = "factor-v1.0.0"
FEATURE_SET_VERSION = "alpha-v1.0.0"
FAILURE_VERSION = "failure-v1.0.0"

from apps.api.src.alpha.factor_attribution import (
    FactorAttribution, compute_factor_attribution,
)
from apps.api.src.alpha.signal_analytics import (
    SignalInsights, analyze_signals,
)
from apps.api.src.alpha.execution_quality import (
    EntryQuality, compute_entry_quality, simulate_paper_slippage,
)
from apps.api.src.alpha.exit_research import (
    ExitStrategyResult, simulate_exits,
)
from apps.api.src.alpha.catalyst_analytics import (
    CatalystAnalytics, build_catalyst_analytics,
)
from apps.api.src.alpha.risk_engine import (
    RiskScore, compute_portfolio_risk,
)
from apps.api.src.alpha.data_quality import (
    ProviderReliability, compute_provider_reliability,
    FeatureConfidenceHeatmap, compute_feature_heatmap,
)
from apps.api.src.alpha.failure_classifier import (
    FailureAnalysis, classify_failure,
)
from apps.api.src.alpha.health_score import (
    SystemHealthScore, compute_system_health,
)
from apps.api.src.alpha.feature_registry import (
    FeatureRegistryEntry, DriftReport, detect_drift,
)
from apps.api.src.alpha.rule_analyzer import (
    Finding, analyze_rules,
)
from apps.api.src.alpha.rule_suggestions import (
    Suggestion, generate_suggestions,
)
from apps.api.src.alpha.adaptive_thresholds import (
    ThresholdRecommendation, recommend_thresholds,
)
from apps.api.src.alpha.rule_executor import (
    ALLOWED_AUTO_TYPES, FORBIDDEN_AUTO_TYPES, ApplyResult,
    apply_rule, ignore_suggestion, is_auto_applicable,
    persist_suggestions, rollback_rule,
)

__all__ = [
    "FACTOR_VERSION", "FEATURE_SET_VERSION", "FAILURE_VERSION",
    "FactorAttribution", "compute_factor_attribution",
    "SignalInsights", "analyze_signals",
    "EntryQuality", "compute_entry_quality", "simulate_paper_slippage",
    "ExitStrategyResult", "simulate_exits",
    "CatalystAnalytics", "build_catalyst_analytics",
    "RiskScore", "compute_portfolio_risk",
    "ProviderReliability", "compute_provider_reliability",
    "FeatureConfidenceHeatmap", "compute_feature_heatmap",
    "FailureAnalysis", "classify_failure",
    "SystemHealthScore", "compute_system_health",
    "FeatureRegistryEntry", "DriftReport", "detect_drift",
    "Finding", "analyze_rules",
    "Suggestion", "generate_suggestions",
    "ThresholdRecommendation", "recommend_thresholds",
    "ALLOWED_AUTO_TYPES", "FORBIDDEN_AUTO_TYPES", "ApplyResult",
    "apply_rule", "ignore_suggestion", "is_auto_applicable",
    "persist_suggestions", "rollback_rule",
]
