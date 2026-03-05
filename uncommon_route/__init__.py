"""UncommonRoute — SOTA LLM router with cascade classifier, <1ms local routing."""

from uncommon_route.router.api import route
from uncommon_route.router.types import (
    FallbackOption,
    ModelPricing,
    RoutingConfig,
    RoutingDecision,
    ScoringConfig,
    ScoringResult,
    Tier,
    TierConfig,
)
from uncommon_route.router.config import DEFAULT_CONFIG, DEFAULT_MODEL_PRICING
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

__all__ = [
    # Router
    "route",
    "classify",
    "select_model",
    "get_fallback_chain",
    "Tier",
    "RoutingDecision",
    "RoutingConfig",
    "ScoringConfig",
    "ScoringResult",
    "TierConfig",
    "ModelPricing",
    "FallbackOption",
    "DEFAULT_CONFIG",
    "DEFAULT_MODEL_PRICING",
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
