"""Public API — the route() entry point."""

from __future__ import annotations

from uncommon_route.router.types import (
    RoutingConfig,
    RoutingDecision,
    Tier,
    TierConfig,
)
from uncommon_route.router.classifier import classify
from uncommon_route.router.selector import select_model
from uncommon_route.router.structural import estimate_tokens
from uncommon_route.router.config import DEFAULT_CONFIG


def route(
    prompt: str,
    system_prompt: str | None = None,
    max_output_tokens: int = 4096,
    config: RoutingConfig | None = None,
    user_keyed_models: set[str] | None = None,
) -> RoutingDecision:
    """Route a prompt to the best model.

    This is the main entry point. <1ms, pure local, no external calls.

    Args:
        user_keyed_models: Model IDs backed by user-provided API keys.
            When set, models the user already pays for are prioritized.
    """
    cfg = config or DEFAULT_CONFIG

    full_text = f"{system_prompt or ''} {prompt}".strip()
    estimated_tokens = estimate_tokens(full_text)

    result = classify(prompt, system_prompt, cfg.scoring)

    tier = result.tier if result.tier is not None else cfg.ambiguous_default_tier

    if system_prompt and any(kw in system_prompt.lower() for kw in ("json", "structured", "schema")):
        tier_rank = {Tier.SIMPLE: 0, Tier.MEDIUM: 1, Tier.COMPLEX: 2, Tier.REASONING: 3}
        min_tier = cfg.structured_output_min_tier
        if tier_rank[tier] < tier_rank[min_tier]:
            tier = min_tier

    reasoning = f"score={result.score:.3f} | {', '.join(result.signals)}"

    return select_model(
        tier=tier,
        confidence=result.confidence,
        method="cascade",
        reasoning=reasoning,
        tier_configs=cfg.tiers,
        estimated_input_tokens=estimated_tokens,
        max_output_tokens=max_output_tokens,
        prompt=prompt,
        agentic_score=result.agentic_score,
        user_keyed_models=user_keyed_models,
    )
