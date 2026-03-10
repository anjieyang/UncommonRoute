"""UncommonRoute — local LLM router with 4-tier routing and local-first cost control."""

from uncommon_route.router.api import route
from uncommon_route.router.types import (
    BanditConfig,
    CandidateScore,
    FallbackOption,
    ModelCapabilities,
    ModelPricing,
    RequestRequirements,
    RoutingConfig,
    RoutingDecision,
    RoutingProfile,
    ScoringConfig,
    ScoringResult,
    SelectionWeights,
    Tier,
    TierConfig,
)
from uncommon_route.router.config import (
    DEFAULT_CONFIG,
    DEFAULT_MODEL_PRICING,
    VIRTUAL_MODEL_IDS,
    get_bandit_config,
    get_selection_weights,
    get_tier_configs,
)
from uncommon_route.router.classifier import classify
from uncommon_route.router.selector import get_fallback_chain, select_model
from uncommon_route.session import (
    DEFAULT_SESSION_CONFIG,
    SessionConfig,
    SessionEntry,
    SessionStore,
    derive_session_id,
    get_session_id,
    hash_request_content,
)
from uncommon_route.spend_control import (
    CheckResult,
    FileSpendControlStorage,
    InMemorySpendControlStorage,
    SpendControl,
    SpendControlStorage,
    SpendLimits,
    SpendRecord,
    SpendingStatus,
    format_duration,
)
from uncommon_route.openclaw import install as openclaw_install
from uncommon_route.openclaw import uninstall as openclaw_uninstall
from uncommon_route.openclaw import status as openclaw_status
from uncommon_route.providers import (
    ProvidersConfig,
    ProviderEntry,
    add_provider,
    load_providers,
    remove_provider,
    save_providers,
    select_preferred_model,
)
from uncommon_route.feedback import (
    FeedbackCollector,
    FeedbackResult,
    FeedbackSignal,
)
from uncommon_route.artifacts import ArtifactRecord, ArtifactStore
from uncommon_route.composition import (
    CompositionPolicy,
    CompositionResult,
    DEFAULT_COMPOSITION_POLICY,
    compose_messages,
    compose_messages_semantic,
    load_composition_policy,
)
from uncommon_route.semantic import (
    DEFAULT_SIDECHANNEL_CONFIG,
    QualityFallbackPolicy,
    SemanticCallResult,
    SemanticCompressor,
    SideChannelConfig,
    SideChannelTaskConfig,
    score_semantic_quality,
)
from uncommon_route.stats import (
    RouteRecord,
    RouteStats,
    RouteStatsStorage,
    FileRouteStatsStorage,
    InMemoryRouteStatsStorage,
    StatsSummary,
    TierSummary,
    ModelSummary,
)
from uncommon_route.model_experience import (
    CandidateExperience,
    FileModelExperienceStorage,
    InMemoryModelExperienceStorage,
    ModelExperienceRecord,
    ModelExperienceStore,
    ModelExperienceStorage,
)
from uncommon_route.routing_config_store import (
    FileRoutingConfigStorage,
    InMemoryRoutingConfigStorage,
    RoutingConfigStorage,
    RoutingConfigStore,
)

__all__ = [
    # Router
    "route",
    "classify",
    "select_model",
    "get_fallback_chain",
    "Tier",
    "RoutingProfile",
    "RoutingDecision",
    "RoutingConfig",
    "ScoringConfig",
    "ScoringResult",
    "BanditConfig",
    "SelectionWeights",
    "TierConfig",
    "ModelPricing",
    "ModelCapabilities",
    "RequestRequirements",
    "CandidateScore",
    "FallbackOption",
    "DEFAULT_CONFIG",
    "DEFAULT_MODEL_PRICING",
    "VIRTUAL_MODEL_IDS",
    "get_bandit_config",
    "get_selection_weights",
    "get_tier_configs",
    # Session
    "SessionStore",
    "SessionConfig",
    "SessionEntry",
    "DEFAULT_SESSION_CONFIG",
    "get_session_id",
    "derive_session_id",
    "hash_request_content",
    # Spend control
    "SpendControl",
    "SpendLimits",
    "SpendRecord",
    "SpendingStatus",
    "CheckResult",
    "SpendControlStorage",
    "FileSpendControlStorage",
    "InMemorySpendControlStorage",
    "format_duration",
    # OpenClaw
    "openclaw_install",
    "openclaw_uninstall",
    "openclaw_status",
    # Providers (BYOK)
    "ProvidersConfig",
    "ProviderEntry",
    "add_provider",
    "load_providers",
    "remove_provider",
    "save_providers",
    "select_preferred_model",
    # Feedback
    "FeedbackCollector",
    "FeedbackResult",
    "FeedbackSignal",
    # Composition / artifacts
    "ArtifactRecord",
    "ArtifactStore",
    "CompositionPolicy",
    "CompositionResult",
    "DEFAULT_COMPOSITION_POLICY",
    "compose_messages",
    "compose_messages_semantic",
    "load_composition_policy",
    "DEFAULT_SIDECHANNEL_CONFIG",
    "QualityFallbackPolicy",
    "SemanticCallResult",
    "SemanticCompressor",
    "SideChannelConfig",
    "SideChannelTaskConfig",
    "score_semantic_quality",
    # Adaptive model selection memory
    "CandidateExperience",
    "FileModelExperienceStorage",
    "InMemoryModelExperienceStorage",
    "ModelExperienceRecord",
    "ModelExperienceStore",
    "ModelExperienceStorage",
    "RoutingConfigStorage",
    "FileRoutingConfigStorage",
    "InMemoryRoutingConfigStorage",
    "RoutingConfigStore",
    # Stats
    "RouteRecord",
    "RouteStats",
    "RouteStatsStorage",
    "FileRouteStatsStorage",
    "InMemoryRouteStatsStorage",
    "StatsSummary",
    "TierSummary",
    "ModelSummary",
]
