"""Tier → Model selection with cost estimation and fallback chain."""

from __future__ import annotations

import math

from uncommon_route.router.types import (
    BanditConfig,
    CandidateScore,
    FallbackOption,
    ModelCapabilities,
    ModelPricing,
    RequestRequirements,
    RoutingDecision,
    RoutingProfile,
    SelectionWeights,
    Tier,
    TierConfig,
)
from uncommon_route.router.structural import estimate_output_budget
from uncommon_route.router.config import BASELINE_MODEL, DEFAULT_MODEL_PRICING
from uncommon_route.model_experience import CandidateExperience


def _calc_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, ModelPricing],
    *,
    input_cost_multiplier: float = 1.0,
) -> float:
    mp = pricing.get(model, ModelPricing(0, 0))
    effective_multiplier = max(0.1, min(2.0, input_cost_multiplier))
    return (
        (input_tokens / 1_000_000) * mp.input_price * effective_multiplier
        + (output_tokens / 1_000_000) * mp.output_price
    )


def _supports_requirements(
    model: str,
    requirements: RequestRequirements,
    capabilities: dict[str, ModelCapabilities],
) -> tuple[bool, list[str]]:
    cap = capabilities.get(model, ModelCapabilities())
    missing: list[str] = []
    if requirements.needs_tool_calling and not cap.tool_calling:
        missing.append("tool_calling")
    if requirements.needs_vision and not cap.vision:
        missing.append("vision")
    if requirements.prefers_reasoning and not cap.reasoning:
        missing.append("reasoning")
    return (not missing), missing


def _filter_candidates(
    candidates: list[str],
    requirements: RequestRequirements,
    capabilities: dict[str, ModelCapabilities],
) -> tuple[list[str], dict[str, list[str]]]:
    filtered: list[str] = []
    excluded: dict[str, list[str]] = {}
    for candidate in candidates:
        ok, missing = _supports_requirements(candidate, requirements, capabilities)
        if ok:
            filtered.append(candidate)
        else:
            excluded[candidate] = missing
    return filtered, excluded


def select_model(
    tier: Tier,
    profile: RoutingProfile,
    confidence: float,
    method: str,
    reasoning: str,
    tier_configs: dict[Tier, TierConfig],
    estimated_input_tokens: int,
    max_output_tokens: int,
    prompt: str = "",
    pricing: dict[str, ModelPricing] | None = None,
    model_capabilities: dict[str, ModelCapabilities] | None = None,
    request_requirements: RequestRequirements | None = None,
    agentic_score: float = 0.0,
    user_keyed_models: set[str] | None = None,
    selection_weights: SelectionWeights | None = None,
    bandit_config: BanditConfig | None = None,
    model_experience: object | None = None,
) -> RoutingDecision:
    pricing = pricing or DEFAULT_MODEL_PRICING
    capabilities = model_capabilities or {}
    requirements = request_requirements or RequestRequirements()
    weights = selection_weights or SelectionWeights()
    tc = tier_configs[tier]
    configured_candidates = [tc.primary, *tc.fallback]
    filtered_candidates, excluded = _filter_candidates(configured_candidates, requirements, capabilities)
    candidates = filtered_candidates or configured_candidates

    capability_notes: list[str] = []
    if filtered_candidates:
        capability_notes.extend(
            sorted({miss for missing in excluded.values() for miss in missing}),
        )
    elif excluded:
        capability_notes.append("capability-relaxed")
    if capability_notes:
        kept = len(filtered_candidates) if filtered_candidates else len(configured_candidates)
        reasoning = f"{reasoning} | caps={','.join(capability_notes)} ({kept}/{len(configured_candidates)})"

    if tc.hard_pin and tc.primary in candidates:
        scoring_candidates = [tc.primary]
        reasoning = f"{reasoning} | chooser=hard-pin"
    elif tc.hard_pin:
        scoring_candidates = candidates
        reasoning = f"{reasoning} | chooser=hard-pin-relaxed"
    else:
        scoring_candidates = candidates

    # R2-Router: estimate optimal output budget from prompt + tier
    budget = estimate_output_budget(prompt, tier.value)
    effective_output = min(max_output_tokens, budget)

    candidate_scores = _score_candidates(
        scoring_candidates,
        profile=profile,
        tier=tier,
        effective_output=effective_output,
        estimated_input_tokens=estimated_input_tokens,
        pricing=pricing,
        capabilities=capabilities,
        requirements=requirements,
        weights=weights,
        user_keyed_models=user_keyed_models,
        bandit_config=bandit_config or BanditConfig(),
        model_experience=model_experience,
    )
    candidate_scores.sort(key=lambda item: item.total, reverse=True)
    if user_keyed_models:
        keyed_scores = [item for item in candidate_scores if item.model in user_keyed_models]
        if keyed_scores:
            unkeyed_scores = [item for item in candidate_scores if item.model not in user_keyed_models]
            candidate_scores = keyed_scores + unkeyed_scores
    model = candidate_scores[0].model
    cost = candidate_scores[0].predicted_cost
    if user_keyed_models and model in user_keyed_models:
        reasoning = f"byok-preferred ({model}) | {reasoning}"
    if "chooser=hard-pin" not in reasoning:
        reasoning = f"{reasoning} | chooser=adaptive"

    bp = pricing.get(BASELINE_MODEL, ModelPricing(5.0, 25.0))
    baseline_cost = (
        (estimated_input_tokens / 1_000_000) * bp.input_price
        + (effective_output / 1_000_000) * bp.output_price
    )

    savings = max(0.0, (baseline_cost - cost) / baseline_cost) if baseline_cost > 0 else 0.0

    # Build fallback chain in configured profile order. Costs are attached for visibility.
    chain: list[FallbackOption] = []
    if tc.hard_pin:
        fallback_models = candidates
    else:
        fallback_models = [scored.model for scored in candidate_scores]
    for fb_model in fallback_models:
        exp = _experience_snapshot(model_experience, fb_model, profile, tier)
        fb_cost = _calc_cost(
            fb_model,
            estimated_input_tokens,
            effective_output,
            pricing,
            input_cost_multiplier=exp.input_cost_multiplier,
        )
        chain.append(FallbackOption(
            model=fb_model,
            cost_estimate=fb_cost,
            suggested_output_budget=effective_output,
        ))

    return RoutingDecision(
        model=model,
        tier=tier,
        profile=profile,
        confidence=confidence,
        method=method,  # type: ignore[arg-type]
        reasoning=reasoning,
        cost_estimate=cost,
        baseline_cost=baseline_cost,
        savings=savings,
        agentic_score=agentic_score,
        suggested_output_budget=effective_output,
        fallback_chain=chain,
        candidate_scores=candidate_scores,
    )


def get_fallback_chain(tier: Tier, tier_configs: dict[Tier, TierConfig]) -> list[str]:
    tc = tier_configs[tier]
    return [tc.primary, *tc.fallback]


def _score_candidates(
    candidates: list[str],
    *,
    profile: RoutingProfile,
    tier: Tier,
    effective_output: int,
    estimated_input_tokens: int,
    pricing: dict[str, ModelPricing],
    capabilities: dict[str, ModelCapabilities],
    requirements: RequestRequirements,
    weights: SelectionWeights,
    user_keyed_models: set[str] | None,
    bandit_config: BanditConfig,
    model_experience: object | None,
) -> list[CandidateScore]:
    experience = {
        model: _experience_snapshot(model_experience, model, profile, tier)
        for model in candidates
    }
    costs = {
        model: _calc_cost(
            model,
            estimated_input_tokens,
            effective_output,
            pricing,
            input_cost_multiplier=experience[model].input_cost_multiplier,
        )
        for model in candidates
    }
    cost_scores = _normalize_inverse(costs)
    ranked: list[CandidateScore] = []
    candidate_count = len(candidates)
    cheapest_cost = min(costs.values()) if costs else 0.0
    bucket_pulls = _bucket_pulls(model_experience, profile, tier)
    bandit_active = bandit_config.enabled and tier in bandit_config.enabled_tiers

    for index, model in enumerate(candidates):
        cap = capabilities.get(model, ModelCapabilities())
        exp = experience[model]
        editorial = 1.0 / (index + 1)
        reasoning_bias = 1.0 if requirements.prefers_reasoning and cap.reasoning else 0.0
        byok = 1.0 if user_keyed_models and model in user_keyed_models else 0.0
        free_bias = 1.0 if cap.free else 0.0
        local_bias = 1.0 if cap.local else 0.0
        exploration_bonus = _bandit_bonus(
            enabled=bandit_active,
            bandit_config=bandit_config,
            candidate_cost=costs[model],
            cheapest_cost=cheapest_cost,
            reliability=exp.reliability,
            samples=exp.samples,
            bucket_pulls=bucket_pulls,
        )
        bandit_mean = exp.reward_mean
        total = (
            weights.editorial * editorial
            + weights.cost * cost_scores[model]
            + weights.latency * exp.latency
            + weights.reliability * exp.reliability
            + weights.feedback * exp.feedback
            + weights.cache_affinity * exp.cache_affinity
            + weights.byok * byok
            + weights.free_bias * free_bias
            + weights.local_bias * local_bias
            + weights.reasoning_bias * reasoning_bias
        )
        if bandit_active:
            total += bandit_config.reward_weight * (bandit_mean - 0.5)
            total += exploration_bonus
        # Break ties slightly in favor of earlier curated candidates.
        total += 0.002 * (candidate_count - index)
        ranked.append(CandidateScore(
            model=model,
            total=total,
            predicted_cost=costs[model],
            effective_cost_multiplier=exp.input_cost_multiplier,
            editorial=editorial,
            cost=cost_scores[model],
            latency=exp.latency,
            reliability=exp.reliability,
            feedback=exp.feedback,
            cache_affinity=exp.cache_affinity,
            byok=byok,
            free_bias=free_bias,
            local_bias=local_bias,
            reasoning_bias=reasoning_bias,
            bandit_mean=bandit_mean,
            exploration_bonus=exploration_bonus,
            samples=exp.samples,
        ))
    return ranked


def _normalize_inverse(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    minimum = min(values.values())
    maximum = max(values.values())
    if maximum <= minimum:
        return {key: 0.5 for key in values}
    return {
        key: 1.0 - ((value - minimum) / (maximum - minimum))
        for key, value in values.items()
    }


def _experience_snapshot(
    store: object | None,
    model: str,
    profile: RoutingProfile,
    tier: Tier,
) -> CandidateExperience:
    if store is None or not hasattr(store, "snapshot"):
        return CandidateExperience()
    snapshot = store.snapshot(model, profile, tier)
    if isinstance(snapshot, CandidateExperience):
        return snapshot
    return CandidateExperience()


def _bucket_pulls(
    store: object | None,
    profile: RoutingProfile,
    tier: Tier,
) -> int:
    if store is None or not hasattr(store, "bucket_pulls"):
        return 0
    try:
        pulls = int(store.bucket_pulls(profile, tier))
    except Exception:
        return 0
    return max(0, pulls)


def _bandit_bonus(
    *,
    enabled: bool,
    bandit_config: BanditConfig,
    candidate_cost: float,
    cheapest_cost: float,
    reliability: float,
    samples: int,
    bucket_pulls: int,
) -> float:
    if not enabled:
        return 0.0
    if cheapest_cost > 0 and candidate_cost > (cheapest_cost * bandit_config.max_cost_ratio):
        return 0.0
    if samples >= bandit_config.min_samples_for_guardrail and reliability < bandit_config.min_reliability:
        return 0.0
    if samples < bandit_config.warmup_pulls:
        return bandit_config.exploration_weight
    return bandit_config.exploration_weight * math.sqrt(
        math.log(max(2, bucket_pulls + 1)) / (samples + 1),
    )
