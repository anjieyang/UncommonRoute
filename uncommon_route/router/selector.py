"""Tier → Model selection with cost estimation and fallback chain."""

from __future__ import annotations

from uncommon_route.router.types import (
    FallbackOption,
    ModelPricing,
    RoutingDecision,
    Tier,
    TierConfig,
)
from uncommon_route.router.structural import estimate_output_budget
from uncommon_route.router.config import BASELINE_MODEL, DEFAULT_MODEL_PRICING


def _calc_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, ModelPricing],
) -> float:
    mp = pricing.get(model, ModelPricing(0, 0))
    return (input_tokens / 1_000_000) * mp.input_price + (output_tokens / 1_000_000) * mp.output_price


def select_model(
    tier: Tier,
    confidence: float,
    method: str,
    reasoning: str,
    tier_configs: dict[Tier, TierConfig],
    estimated_input_tokens: int,
    max_output_tokens: int,
    prompt: str = "",
    pricing: dict[str, ModelPricing] | None = None,
    agentic_score: float = 0.0,
    user_keyed_models: set[str] | None = None,
) -> RoutingDecision:
    pricing = pricing or DEFAULT_MODEL_PRICING
    tc = tier_configs[tier]
    model = tc.primary

    # BYOK: if user has an API key for a model in this tier, prefer it
    if user_keyed_models:
        candidates = [tc.primary, *tc.fallback]
        for candidate in candidates:
            if candidate in user_keyed_models:
                model = candidate
                reasoning = f"byok-preferred ({model}) | {reasoning}"
                break

    # R2-Router: estimate optimal output budget from prompt + tier
    budget = estimate_output_budget(prompt, tier.value)
    effective_output = min(max_output_tokens, budget)

    cost = _calc_cost(model, estimated_input_tokens, effective_output, pricing)

    bp = pricing.get(BASELINE_MODEL, ModelPricing(5.0, 25.0))
    baseline_cost = (
        (estimated_input_tokens / 1_000_000) * bp.input_price
        + (effective_output / 1_000_000) * bp.output_price
    )

    savings = max(0.0, (baseline_cost - cost) / baseline_cost) if baseline_cost > 0 else 0.0

    # Select-then-Route: build cost-aware fallback chain
    chain: list[FallbackOption] = []
    for fb_model in [tc.primary, *tc.fallback]:
        fb_budget = estimate_output_budget(prompt, tier.value)
        fb_effective = min(max_output_tokens, fb_budget)
        fb_cost = _calc_cost(fb_model, estimated_input_tokens, fb_effective, pricing)
        chain.append(FallbackOption(
            model=fb_model,
            cost_estimate=fb_cost,
            suggested_output_budget=fb_effective,
        ))
    # Sort by cost (cheapest first) — caller can try in order, escalating on failure
    chain.sort(key=lambda x: x.cost_estimate)

    return RoutingDecision(
        model=model,
        tier=tier,
        confidence=confidence,
        method=method,  # type: ignore[arg-type]
        reasoning=reasoning,
        cost_estimate=cost,
        baseline_cost=baseline_cost,
        savings=savings,
        agentic_score=agentic_score,
        suggested_output_budget=effective_output,
        fallback_chain=chain,
    )


def get_fallback_chain(tier: Tier, tier_configs: dict[Tier, TierConfig]) -> list[str]:
    tc = tier_configs[tier]
    return [tc.primary, *tc.fallback]
