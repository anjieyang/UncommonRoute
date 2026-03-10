"""Core type definitions for UncommonRoute."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Tier(str, Enum):
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"
    REASONING = "REASONING"


class RoutingProfile(str, Enum):
    FREE = "free"
    ECO = "eco"
    AUTO = "auto"
    PREMIUM = "premium"
    AGENTIC = "agentic"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    tool_calling: bool = False
    vision: bool = False
    reasoning: bool = False
    free: bool = False
    local: bool = False
    responses: bool = False


@dataclass(frozen=True, slots=True)
class RequestRequirements:
    needs_tool_calling: bool = False
    needs_vision: bool = False
    prefers_reasoning: bool = False
    is_agentic: bool = False



@dataclass(frozen=True, slots=True)
class DimensionScore:
    name: str
    score: float  # [-1, 1]
    signal: str | None = None


@dataclass(frozen=True, slots=True)
class ScoringResult:
    score: float
    tier: Tier | None  # None = ambiguous
    confidence: float  # [0, 1]
    signals: list[str]
    dimensions: list[DimensionScore] = field(default_factory=list)
    agentic_score: float = 0.0


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    model: str
    tier: Tier
    profile: RoutingProfile
    confidence: float
    method: Literal["rules", "cascade"]
    reasoning: str
    cost_estimate: float
    baseline_cost: float
    savings: float  # 0-1
    agentic_score: float = 0.0
    suggested_output_budget: int = 4096
    fallback_chain: list[FallbackOption] = field(default_factory=list)
    candidate_scores: list[CandidateScore] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FallbackOption:
    """One option in the cost-aware fallback chain."""
    model: str
    cost_estimate: float
    suggested_output_budget: int


@dataclass(frozen=True, slots=True)
class CandidateScore:
    model: str
    total: float
    predicted_cost: float
    effective_cost_multiplier: float = 1.0
    editorial: float = 0.0
    cost: float = 0.0
    latency: float = 0.0
    reliability: float = 0.0
    feedback: float = 0.0
    cache_affinity: float = 0.0
    byok: float = 0.0
    free_bias: float = 0.0
    local_bias: float = 0.0
    reasoning_bias: float = 0.0
    bandit_mean: float = 0.5
    exploration_bonus: float = 0.0
    samples: int = 0


@dataclass(frozen=True, slots=True)
class TierConfig:
    primary: str
    fallback: list[str] = field(default_factory=list)
    hard_pin: bool = False


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_price: float  # per 1M tokens
    output_price: float  # per 1M tokens
    cached_input_price: float | None = None  # per 1M cached-read tokens
    cache_write_price: float | None = None  # per 1M cache-write / cache-create tokens


@dataclass(frozen=True, slots=True)
class SelectionWeights:
    editorial: float = 0.4
    cost: float = 0.2
    latency: float = 0.1
    reliability: float = 0.1
    feedback: float = 0.1
    cache_affinity: float = 0.05
    byok: float = 0.05
    free_bias: float = 0.0
    local_bias: float = 0.0
    reasoning_bias: float = 0.05


@dataclass(frozen=True, slots=True)
class BanditConfig:
    enabled: bool = True
    reward_weight: float = 0.12
    exploration_weight: float = 0.18
    warmup_pulls: int = 2
    min_samples_for_guardrail: int = 3
    min_reliability: float = 0.25
    max_cost_ratio: float = 3.0
    enabled_tiers: tuple[Tier, ...] = (Tier.SIMPLE, Tier.MEDIUM)


@dataclass
class StructuralWeights:
    """Weights for language-agnostic structural features."""
    normalized_length: float = 0.05
    enumeration_density: float = 0.10
    sentence_count: float = 0.08
    code_markers: float = 0.07
    math_symbols: float = 0.06
    nesting_depth: float = 0.03
    vocabulary_diversity: float = 0.03
    avg_word_length: float = 0.03
    alphabetic_ratio: float = 0.03
    functional_intent: float = 0.06
    unique_concept_density: float = 0.07
    requirement_phrases: float = 0.06


@dataclass
class KeywordWeights:
    """Weights for keyword-based features (language-specific, secondary)."""
    code_presence: float = 0.06
    reasoning_markers: float = 0.06
    technical_terms: float = 0.04
    creative_markers: float = 0.02
    simple_indicators: float = 0.02
    imperative_verbs: float = 0.02
    constraint_count: float = 0.02
    output_format: float = 0.02
    domain_specificity: float = 0.01
    agentic_task: float = 0.02
    analytical_verbs: float = 0.04
    multi_step_patterns: float = 0.04


@dataclass
class TierBoundaries:
    simple_medium: float = -0.02
    medium_complex: float = 0.15
    complex_reasoning: float = 0.25


@dataclass
class ScoringConfig:
    structural_weights: StructuralWeights = field(default_factory=StructuralWeights)
    keyword_weights: KeywordWeights = field(default_factory=KeywordWeights)
    tier_boundaries: TierBoundaries = field(default_factory=TierBoundaries)
    confidence_steepness: float = 18.0
    confidence_threshold: float = 0.55


@dataclass
class RoutingConfig:
    version: str = "3.0"
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    tiers: dict[Tier, TierConfig] = field(default_factory=dict)
    free_tiers: dict[Tier, TierConfig] = field(default_factory=dict)
    eco_tiers: dict[Tier, TierConfig] = field(default_factory=dict)
    premium_tiers: dict[Tier, TierConfig] = field(default_factory=dict)
    agentic_tiers: dict[Tier, TierConfig] = field(default_factory=dict)
    selection_profiles: dict[RoutingProfile, SelectionWeights] = field(default_factory=dict)
    agentic_selection: SelectionWeights | None = None
    bandit_profiles: dict[RoutingProfile, BanditConfig] = field(default_factory=dict)
    agentic_bandit: BanditConfig | None = None
    model_capabilities: dict[str, ModelCapabilities] = field(default_factory=dict)
    free_model: str = "nvidia/gpt-oss-120b"
    max_tokens_force_complex: int = 100_000
    structured_output_min_tier: Tier = Tier.MEDIUM
    ambiguous_default_tier: Tier = Tier.MEDIUM
