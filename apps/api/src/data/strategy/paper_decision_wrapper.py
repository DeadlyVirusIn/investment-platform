"""Paper-only decision wrapper.

Orchestrates:
  1. Selector (frozen)
  2. Alpha rule policy evaluation
  3. Paper exploratory gate evaluation

Returns a dataclass the paper pipeline persists via decision_logger. The
real-money path must NOT import this module — it is paper-only by design.

No changes to selector.py. No changes to real execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from apps.api.src.alpha.calibration import load_active_params
from apps.api.src.alpha.context_calibration import match_context_multiplier
from apps.api.src.alpha.exploratory import (
    ExploratoryResult, evaluate_exploratory,
)
from apps.api.src.alpha.rule_policy import (
    RuleAdjustment, RuleMode, evaluate_policy,
)
from apps.api.src.alpha.rule_runtime import load_active_rules
from apps.api.src.alpha.similarity import (
    SimilarityResult, compute_similarity_multiplier,
)
from apps.api.src.ml.shadow.hybrid_policy import (
    HybridConfig, HybridResult, evaluate_hybrid,
)
from apps.api.src.ml.shadow.runtime import load_latest_shadow_signal
from apps.api.src.config import settings
from apps.api.src.data.strategy.selector import SelectorOutput


@dataclass
class PaperDecisionEnriched:
    selector: SelectorOutput
    alpha_rule_adjustment: dict[str, Any] | None
    alpha_rules_applied: list[dict[str, Any]] | None
    alpha_rules_mode: str | None
    alpha_rule_size_multiplier: float | None
    alpha_rule_blocked: bool
    alpha_rule_block_reason: str | None
    # Exploratory
    gate_mode: str
    exploratory_paper: bool
    exploratory_reason: str | None
    gates_passed: int | None
    gates_total:  int | None
    gates_failed: list[str] | None
    strict_would_block: bool
    exploratory_size_multiplier: float | None
    # Context-aware multiplier (SYSTEM-ALPHA-7)
    context_multiplier: float
    context_key: str | None
    # Context-similarity multiplier (SYSTEM-ALPHA-8)
    similarity_multiplier: float
    similarity_matched: bool
    similarity_details: dict[str, Any] | None
    # ML-5 Gated Hybrid Advisor
    ml_shadow_available: bool
    ml_shadow_multiplier: float
    ml_hybrid_action: str
    ml_hybrid_reason: str
    ml_hybrid_snapshot: dict[str, Any] | None
    # Final paper_size_multiplier to apply at fill time (paper only)
    paper_size_multiplier: float

    def to_log_kwargs(self) -> dict[str, Any]:
        """Flatten for decision_from_selector(**kwargs)."""
        return {
            "alpha_rule_adjustment": self.alpha_rule_adjustment,
            "alpha_rules_applied":   self.alpha_rules_applied,
            "alpha_rules_mode":      self.alpha_rules_mode,
            "alpha_rule_size_multiplier":
                self.alpha_rule_size_multiplier,
            "alpha_rule_blocked":       self.alpha_rule_blocked,
            "alpha_rule_block_reason":  self.alpha_rule_block_reason,
        }


def enrich_paper_decision(
    session: Session,
    selector_out: SelectorOutput,
    *,
    symbol: str,
    context_values: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    factor_attribution: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
    execution_quality: dict[str, Any] | None = None,
    portfolio_risk: dict[str, Any] | None = None,
    anomaly_severity: str | None = None,
    risk_level: str | None = None,
    as_of_date: Any = None,
) -> PaperDecisionEnriched:
    """Compute paper-only adjustments. Safe to call on every decision.

    Fail-closed: any exception in rule/exploratory evaluation leaves the
    selector decision unchanged (paper_size_multiplier=1.0 on fire,
    exploratory_paper=False).
    """
    engine_decision = {
        "engine": selector_out.engine,
        "fire":   selector_out.fire,
        "reason": selector_out.reason,
    }

    # --- Alpha rule policy ---
    mode = str(getattr(settings, "ALPHA_RULES_MODE", "advisory"))
    allow_block = bool(getattr(settings, "ALPHA_RULE_ALLOW_BLOCK", False))
    min_size = float(
        getattr(settings, "ALPHA_RULE_MIN_SIZE_MULTIPLIER", 0.5),
    )
    rules_enabled = bool(getattr(settings, "ALPHA_RULES_ENABLED", True))

    adjustment_dict: dict[str, Any] | None = None
    applied_rules: list[dict[str, Any]] | None = None
    adj_blocked = False
    adj_block_reason: str | None = None
    rule_size_mult = 1.0
    try:
        active = load_active_rules(session) if rules_enabled else []
        if active:
            adj: RuleAdjustment = evaluate_policy(
                engine_decision=engine_decision,
                symbol=symbol,
                features=features,
                factor_attribution=factor_attribution,
                catalyst=catalyst,
                data_quality=data_quality,
                execution_quality=execution_quality,
                portfolio_risk=portfolio_risk,
                active_rules=active,
                mode=mode,
                allow_block=allow_block,
                min_size_multiplier=min_size,
            )
            adjustment_dict = adj.to_dict()
            applied_rules = [r.to_dict() for r in adj.applied_rules]
            rule_size_mult = float(adj.size_multiplier)
            if adj.action == "block_paper_trade":
                adj_blocked = True
                adj_block_reason = "; ".join(adj.reason_codes) or "rule block"
    except Exception as e:
        logger.warning(
            "paper_wrapper: alpha rule policy failed: {}", e,
        )

    # --- Exploratory gate mode ---
    gate_mode = str(getattr(settings, "PAPER_GATE_MODE", "strict"))
    exploratory_res: ExploratoryResult | None = None
    try:
        # Preload calibration overrides early so exploratory can use them
        _active = {}
        try:
            _active = load_active_params(session)
        except Exception:
            _active = {}
        data_conf = None
        if isinstance(data_quality, dict):
            v = data_quality.get("confidence")
            if v is not None:
                try:
                    data_conf = float(v)
                except (TypeError, ValueError):
                    data_conf = None
        exploratory_res = evaluate_exploratory(
            strict_fire=bool(selector_out.fire),
            context_values=context_values or {},
            anomaly_severity=anomaly_severity,
            risk_level=risk_level,
            data_confidence=data_conf,
            gate_mode=gate_mode,
            min_gates=int(
                _active.get("paper_exploratory_min_gates",
                              getattr(settings,
                                       "PAPER_EXPLORATORY_MIN_GATES", 2)),
            ),
            size_multiplier=float(
                _active.get("paper_exploratory_size_multiplier",
                              getattr(settings,
                                       "PAPER_EXPLORATORY_SIZE_MULTIPLIER",
                                       0.25)),
            ),
            require_low_risk=bool(
                getattr(settings, "PAPER_EXPLORATORY_REQUIRE_LOW_RISK", True),
            ),
            block_on_anomaly=bool(
                getattr(settings, "PAPER_EXPLORATORY_BLOCK_ON_ANOMALY", True),
            ),
        )
    except Exception as e:
        logger.warning(
            "paper_wrapper: exploratory eval failed: {}", e,
        )

    # --- Active calibration overrides (SYSTEM-ALPHA-6) ---
    # Engine multiplier + exploratory multiplier loaded from
    # alpha_param_active; each clamped to [0,1]. Never increases size.
    active_params: dict[str, Any] = {}
    try:
        active_params = load_active_params(session)
    except Exception as e:
        logger.warning("paper_wrapper: active params read failed: {}", e)
    eng_mult_key = f"engine_size_multiplier_{selector_out.engine}" \
                    if selector_out.engine in ("A", "B") else None
    eng_mult = 1.0
    if eng_mult_key and eng_mult_key in active_params:
        try:
            eng_mult = max(0.0, min(1.0, float(active_params[eng_mult_key])))
        except (TypeError, ValueError):
            eng_mult = 1.0

    # --- Context-aware multiplier (SYSTEM-ALPHA-7) ---
    # Look up per-context multiplier (engine × regime × strict/exploratory)
    # Risk-reducing only — floored at 0.2, capped at 1.0.
    regime_for_ctx = (
        "stress" if (context_values or {}).get("stress_regime")
        else "directional" if (context_values or {}).get("directional_regime")
        else "neutral"
    )
    mode_for_ctx = (
        "exploratory" if (exploratory_res is not None
                            and exploratory_res.allowed)
        else "strict"
    )
    ctx_mult, ctx_key = 1.0, None
    try:
        ctx_mult, ctx_key = match_context_multiplier(
            session,
            engine=selector_out.engine, regime=regime_for_ctx,
            mode=mode_for_ctx,
        )
    except Exception as e:
        logger.warning(
            "paper_wrapper: context multiplier lookup failed: {}", e,
        )

    # --- Context-similarity multiplier (SYSTEM-ALPHA-8) ---
    # K-NN over historical paper outcomes. Never increases; floor 0.5.
    sim_mult = 1.0
    sim_matched = False
    sim_details: dict[str, Any] | None = None
    try:
        sim: SimilarityResult = compute_similarity_multiplier(
            session,
            regime=regime_for_ctx,
            engine=selector_out.engine,
            exploratory=(
                exploratory_res is not None and exploratory_res.allowed
            ),
            gates_passed=(
                exploratory_res.gates_passed if exploratory_res else None
            ),
            context_values=context_values,
            catalyst=catalyst,
            data_quality=data_quality,
        )
        sim_mult = max(0.0, min(1.0, float(sim.multiplier)))
        sim_matched = bool(sim.matched)
        sim_details = sim.to_dict()
    except Exception as e:
        logger.warning(
            "paper_wrapper: similarity lookup failed: {}", e,
        )

    # --- ML-5 — Gated Hybrid Advisor ---
    # Fail-soft: if anything breaks → multiplier 1.0, no effect.
    ml_shadow_available = False
    ml_shadow_mult = 1.0
    ml_action_str = "none"
    ml_reason_str = "not_evaluated"
    ml_snapshot: dict[str, Any] | None = None
    try:
        cfg = HybridConfig.from_settings(settings)
        # Only evaluate when any paper entry is even possible
        will_enter = bool(selector_out.fire) or bool(
            exploratory_res is not None and exploratory_res.allowed,
        )
        if will_enter:
            ml_signal = load_latest_shadow_signal(
                session,
                symbol=symbol,
                as_of_date=as_of_date,
                engine=selector_out.engine,
                decision_context=context_values,
                max_stale_days=int(cfg.max_stale_days),
            )
            ctx_for_policy = {"regime": regime_for_ctx}
            pre_ml_mult = min(
                1.0, rule_size_mult * eng_mult * ctx_mult * sim_mult,
            )
            res: HybridResult = evaluate_hybrid(
                ml_signal=ml_signal,
                cfg=cfg,
                current_paper_mult=pre_ml_mult,
                data_quality=data_quality,
                catalyst=catalyst,
                similarity=(sim_details or None),
                context=ctx_for_policy,
            )
            ml_shadow_available = bool(ml_signal.get("available"))
            ml_shadow_mult = max(0.0, min(1.0, float(res.multiplier)))
            ml_action_str = res.action
            ml_reason_str = res.reason
            ml_snapshot = res.to_dict()
        else:
            ml_reason_str = "no_entry_possible"
    except Exception as e:
        logger.warning("paper_wrapper: ml hybrid eval failed: {}", e)

    # --- Final paper size_multiplier ---
    # If strict fires → rule × engine × context × similarity × ml_shadow
    # Else if exploratory → exploratory × engine × context × sim × ml_shadow
    # Else → 0.0 (no paper entry)
    # ml_shadow_mult defaults to 1.0 in every failure path.
    if selector_out.fire:
        paper_size = min(
            1.0,
            rule_size_mult * eng_mult * ctx_mult * sim_mult * ml_shadow_mult,
        )
    elif exploratory_res is not None and exploratory_res.allowed:
        paper_size = min(
            1.0,
            exploratory_res.size_multiplier * eng_mult
            * ctx_mult * sim_mult * ml_shadow_mult,
        )
    else:
        paper_size = 0.0

    exploratory_paper = bool(
        exploratory_res is not None and exploratory_res.allowed,
    )
    exploratory_reason = (
        exploratory_res.reason if exploratory_res is not None else None
    )

    return PaperDecisionEnriched(
        selector=selector_out,
        alpha_rule_adjustment=adjustment_dict,
        alpha_rules_applied=applied_rules,
        alpha_rules_mode=mode,
        alpha_rule_size_multiplier=(
            rule_size_mult if adjustment_dict is not None else None
        ),
        alpha_rule_blocked=adj_blocked,
        alpha_rule_block_reason=adj_block_reason,
        gate_mode=gate_mode,
        exploratory_paper=exploratory_paper,
        exploratory_reason=exploratory_reason,
        gates_passed=(
            exploratory_res.gates_passed if exploratory_res else None
        ),
        gates_total=(
            exploratory_res.gates_total if exploratory_res else None
        ),
        gates_failed=(
            list(exploratory_res.gates_failed) if exploratory_res else None
        ),
        strict_would_block=bool(
            exploratory_res.strict_would_block if exploratory_res
            else not selector_out.fire
        ),
        exploratory_size_multiplier=(
            exploratory_res.size_multiplier if exploratory_res else None
        ),
        context_multiplier=ctx_mult,
        context_key=ctx_key,
        similarity_multiplier=sim_mult,
        similarity_matched=sim_matched,
        similarity_details=sim_details,
        ml_shadow_available=ml_shadow_available,
        ml_shadow_multiplier=ml_shadow_mult,
        ml_hybrid_action=ml_action_str,
        ml_hybrid_reason=ml_reason_str,
        ml_hybrid_snapshot=ml_snapshot,
        paper_size_multiplier=paper_size,
    )
