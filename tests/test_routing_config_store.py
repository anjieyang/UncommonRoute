from __future__ import annotations

from uncommon_route.router.types import RoutingProfile, Tier
from uncommon_route.routing_config_store import InMemoryRoutingConfigStorage, RoutingConfigStore


def test_set_tier_marks_override_and_normalizes_fallback() -> None:
    store = RoutingConfigStore(storage=InMemoryRoutingConfigStorage())

    payload = store.set_tier(
        RoutingProfile.AUTO,
        Tier.SIMPLE,
        primary="openai/gpt-4o-mini",
        fallback=["openai/gpt-4o-mini", "moonshot/kimi-k2.5", "moonshot/kimi-k2.5", ""],
    )

    row = payload["profiles"]["auto"]["tiers"]["SIMPLE"]
    assert row["primary"] == "openai/gpt-4o-mini"
    assert row["fallback"] == ["moonshot/kimi-k2.5"]
    assert row["overridden"] is True
    assert row["hard_pin"] is False
    assert row["selection_mode"] == "adaptive"


def test_set_tier_can_enable_hard_pin() -> None:
    store = RoutingConfigStore(storage=InMemoryRoutingConfigStorage())

    payload = store.set_tier(
        RoutingProfile.AUTO,
        Tier.SIMPLE,
        primary="openai/gpt-4o-mini",
        fallback=["moonshot/kimi-k2.5"],
        hard_pin=True,
    )

    row = payload["profiles"]["auto"]["tiers"]["SIMPLE"]
    assert row["hard_pin"] is True
    assert row["selection_mode"] == "hard-pin"


def test_reset_to_default_clears_override() -> None:
    store = RoutingConfigStore(storage=InMemoryRoutingConfigStorage())

    store.set_tier(
        RoutingProfile.AUTO,
        Tier.SIMPLE,
        primary="openai/gpt-4o-mini",
        fallback=["moonshot/kimi-k2.5"],
    )
    payload = store.reset_tier(RoutingProfile.AUTO, Tier.SIMPLE)

    row = payload["profiles"]["auto"]["tiers"]["SIMPLE"]
    assert row["primary"] == "moonshot/kimi-k2.5"
    assert row["fallback"] == [
        "google/gemini-2.5-flash-lite",
        "nvidia/gpt-oss-120b",
        "deepseek/deepseek-chat",
    ]
    assert row["overridden"] is False


def test_setting_default_values_drops_override() -> None:
    store = RoutingConfigStore(storage=InMemoryRoutingConfigStorage())

    payload = store.set_tier(
        RoutingProfile.ECO,
        Tier.SIMPLE,
        primary="nvidia/gpt-oss-120b",
        fallback=["google/gemini-2.5-flash-lite", "deepseek/deepseek-chat"],
    )

    row = payload["profiles"]["eco"]["tiers"]["SIMPLE"]
    assert row["overridden"] is False
    assert row["selection_mode"] == "adaptive"
