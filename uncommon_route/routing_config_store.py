"""Persistent routing-config overrides for profile/tier model priorities."""

from __future__ import annotations

import copy
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from uncommon_route.paths import data_dir
from uncommon_route.router.config import DEFAULT_CONFIG
from uncommon_route.router.types import RoutingConfig, RoutingProfile, Tier, TierConfig

_DATA_DIR = data_dir()


class RoutingConfigStorage(ABC):
    @abstractmethod
    def load(self) -> dict[str, Any]: ...

    @abstractmethod
    def save(self, data: dict[str, Any]) -> None: ...


class FileRoutingConfigStorage(RoutingConfigStorage):
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_DATA_DIR / "routing_config.json")

    def load(self) -> dict[str, Any]:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save(self, data: dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._path.write_text(json.dumps(data, indent=2, sort_keys=True))
            self._path.chmod(0o600)
        except Exception:
            pass


class InMemoryRoutingConfigStorage(RoutingConfigStorage):
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def save(self, data: dict[str, Any]) -> None:
        self._data = copy.deepcopy(data)


def _profile_table(config: RoutingConfig, profile: RoutingProfile) -> dict[Tier, TierConfig]:
    if profile is RoutingProfile.AUTO:
        return config.tiers
    if profile is RoutingProfile.FREE:
        return config.free_tiers
    if profile is RoutingProfile.ECO:
        return config.eco_tiers
    if profile is RoutingProfile.PREMIUM:
        return config.premium_tiers
    return config.agentic_tiers


def _normalize_fallback(primary: str, fallback: list[str]) -> list[str]:
    normalized: list[str] = []
    seen = {primary}
    for raw in fallback:
        model = str(raw).strip()
        if not model or model in seen:
            continue
        normalized.append(model)
        seen.add(model)
    return normalized


def _sanitize_overrides(raw: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict):
        return result

    for profile_name, tier_map in profiles.items():
        try:
            profile = RoutingProfile(str(profile_name))
        except ValueError:
            continue
        if not isinstance(tier_map, dict):
            continue
        clean_tiers: dict[str, dict[str, Any]] = {}
        for tier_name, payload in tier_map.items():
            try:
                tier = Tier(str(tier_name))
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            primary = str(payload.get("primary", "")).strip()
            selection_mode = str(payload.get("selection_mode", "")).strip().lower()
            hard_pin = bool(payload.get("hard_pin", False))
            if selection_mode:
                hard_pin = selection_mode in {"hard-pin", "hard_pin", "pinned"}
            fallback_raw = payload.get("fallback", [])
            if isinstance(fallback_raw, str):
                fallback = [part.strip() for part in fallback_raw.split(",")]
            elif isinstance(fallback_raw, list):
                fallback = [str(item).strip() for item in fallback_raw]
            else:
                fallback = []
            if not primary:
                continue
            clean_tiers[tier.value] = {
                "primary": primary,
                "fallback": _normalize_fallback(primary, fallback),
                "hard_pin": hard_pin,
            }
        if clean_tiers:
            result[profile.value] = clean_tiers
    return result


class RoutingConfigStore:
    def __init__(
        self,
        storage: RoutingConfigStorage | None = None,
        base_config: RoutingConfig | None = None,
    ) -> None:
        self._storage = storage or FileRoutingConfigStorage()
        self._base_config = copy.deepcopy(base_config or DEFAULT_CONFIG)
        self._overrides = _sanitize_overrides(self._storage.load())

    def config(self) -> RoutingConfig:
        cfg: RoutingConfig = copy.deepcopy(self._base_config)
        for profile_name, tier_map in self._overrides.items():
            profile = RoutingProfile(profile_name)
            table = _profile_table(cfg, profile)
            for tier_name, payload in tier_map.items():
                tier = Tier(tier_name)
                table[tier] = TierConfig(
                    primary=str(payload["primary"]),
                    fallback=list(payload.get("fallback", [])),
                    hard_pin=bool(payload.get("hard_pin", False)),
                )
        return cfg

    def export(self) -> dict[str, Any]:
        cfg = self.config()
        profiles: dict[str, dict[str, Any]] = {}
        for profile in RoutingProfile:
            active = _profile_table(cfg, profile)
            overridden_tiers = self._overrides.get(profile.value, {})
            tier_rows: dict[str, Any] = {}
            for tier in Tier:
                tc = active[tier]
                tier_rows[tier.value] = {
                    "primary": tc.primary,
                    "fallback": list(tc.fallback),
                    "overridden": tier.value in overridden_tiers,
                    "hard_pin": tc.hard_pin,
                    "selection_mode": "hard-pin" if tc.hard_pin else "adaptive",
                }
            profiles[profile.value] = {"tiers": tier_rows}
        return {
            "source": "local-file",
            "editable": True,
            "profiles": profiles,
        }

    def set_tier(
        self,
        profile: RoutingProfile,
        tier: Tier,
        *,
        primary: str,
        fallback: list[str],
        hard_pin: bool = False,
    ) -> dict[str, Any]:
        normalized_primary = str(primary).strip()
        if not normalized_primary:
            raise ValueError("primary model is required")
        normalized_fallback = _normalize_fallback(normalized_primary, fallback)

        default_tc = _profile_table(self._base_config, profile)[tier]
        profile_overrides = self._overrides.setdefault(profile.value, {})
        if (
            normalized_primary == default_tc.primary
            and normalized_fallback == list(default_tc.fallback)
            and bool(hard_pin) is bool(default_tc.hard_pin)
        ):
            profile_overrides.pop(tier.value, None)
        else:
            profile_overrides[tier.value] = {
                "primary": normalized_primary,
                "fallback": normalized_fallback,
                "hard_pin": bool(hard_pin),
            }

        if not profile_overrides:
            self._overrides.pop(profile.value, None)
        self._persist()
        return self.export()

    def reset_tier(self, profile: RoutingProfile, tier: Tier) -> dict[str, Any]:
        profile_overrides = self._overrides.get(profile.value)
        if profile_overrides is not None:
            profile_overrides.pop(tier.value, None)
            if not profile_overrides:
                self._overrides.pop(profile.value, None)
            self._persist()
        return self.export()

    def reset(self) -> dict[str, Any]:
        self._overrides = {}
        self._persist()
        return self.export()

    def _persist(self) -> None:
        self._storage.save({"profiles": self._overrides})
