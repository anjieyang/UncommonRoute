"""Model name mapping between UncommonRoute internal names and upstream providers.

Different upstream APIs use different model IDs for the same underlying model.
For example, UncommonRoute uses ``moonshot/kimi-k2.5`` internally, but
CommonStack expects ``moonshotai/kimi-k2.5``.

Strategy: **dynamic discovery only** — on startup, fetch ``/v1/models`` from the
upstream and build a mapping via fuzzy matching.  No static alias tables to
maintain.

Usage::

    mapper = ModelMapper("https://api.commonstack.ai/v1")
    await mapper.discover(api_key="csk-...")
    upstream_name = mapper.resolve("moonshot/kimi-k2.5")
    # => "moonshotai/kimi-k2.5"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("uncommon-route")

# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

GATEWAY_DOMAINS: dict[str, str] = {
    "commonstack.ai": "commonstack",
    "openrouter.ai": "openrouter",
}

DIRECT_PROVIDER_DOMAINS: dict[str, str] = {
    "api.openai.com": "openai",
    "api.anthropic.com": "anthropic",
    "api.deepseek.com": "deepseek",
    "api.minimax.chat": "minimax",
    "generativelanguage.googleapis.com": "google",
    "api.x.ai": "xai",
    "api.moonshot.cn": "moonshot",
}


def detect_provider(url: str) -> tuple[str, bool]:
    """Return ``(provider_name, is_gateway)`` from an upstream URL."""
    url_lower = url.lower()
    for domain, name in GATEWAY_DOMAINS.items():
        if domain in url_lower:
            return name, True
    for domain, name in DIRECT_PROVIDER_DOMAINS.items():
        if domain in url_lower:
            return name, False
    return "unknown", False


# ---------------------------------------------------------------------------
# Normalization helpers for fuzzy matching
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Normalize a model name for comparison.

    Handles known upstream differences:
      - Date suffixes:  ``claude-sonnet-4-20250514`` → ``claude-sonnet-4``
      - Preview suffix: ``gemini-3.1-pro-preview`` → ``gemini-3.1-pro``
      - Version dots:   ``claude-opus-4.6`` → ``claude-opus-4-6``
        (so it matches ``claude-opus-4-6`` from CommonStack)
    """
    name = name.lower()
    name = re.sub(r"-\d{8}$", "", name)
    name = name.removesuffix("-preview")
    name = re.sub(r"(\d)\.(\d)", r"\1-\2", name)
    return name


def _core(model_id: str) -> str:
    """Model name without provider prefix."""
    return model_id.split("/", 1)[-1] if "/" in model_id else model_id


def _provider_prefix(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else ""


# ---------------------------------------------------------------------------
# ModelMapper
# ---------------------------------------------------------------------------

@dataclass
class ModelMapper:
    """Translates internal model names to upstream-specific IDs via dynamic
    discovery from the upstream ``/v1/models`` endpoint."""

    upstream_url: str
    provider: str = ""
    is_gateway: bool = False
    _upstream_models: set[str] = field(default_factory=set, repr=False)
    _map: dict[str, str] = field(default_factory=dict, repr=False)
    _discovered: bool = False

    def __post_init__(self) -> None:
        self.provider, self.is_gateway = detect_provider(self.upstream_url)

    # ---- discovery --------------------------------------------------------

    async def discover(self, api_key: str | None = None) -> int:
        """Fetch ``/v1/models`` from upstream and build the mapping.

        Returns the number of models discovered (0 on failure).
        """
        if not self.upstream_url:
            return 0

        models_url = f"{self.upstream_url.rstrip('/')}/models"
        headers: dict[str, str] = {"user-agent": "uncommon-route/model-discovery"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0),
            ) as client:
                resp = await client.get(models_url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "Model discovery: HTTP %d from %s", resp.status_code, models_url,
                    )
                    return 0
                data = resp.json()
                raw = data.get("data", [])
                self._upstream_models = {
                    m["id"] for m in raw if isinstance(m, dict) and "id" in m
                }
                self._build_map()
                self._discovered = True
                return len(self._upstream_models)
        except httpx.ConnectError:
            logger.warning("Model discovery: cannot connect to %s", models_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model discovery: %s", exc)
        return 0

    def _build_map(self) -> None:
        """Match every internal model name to the best upstream candidate."""
        from uncommon_route.router.config import DEFAULT_MODEL_PRICING

        self._map.clear()
        for internal in DEFAULT_MODEL_PRICING:
            if internal in self._upstream_models:
                continue
            match = self._fuzzy_match(internal)
            if match:
                self._map[internal] = match

    def _fuzzy_match(self, internal: str) -> str | None:
        """Find the best-matching upstream model for *internal*.

        Scoring heuristic (highest wins, minimum 50 to accept):
          - Exact core name match:           100
          - Normalized core name match:       90
          - Substring containment:            70 * (shorter/longer)
          - Same provider prefix bonus:       +10
          - Similar provider prefix bonus:    +5
        """
        int_core = _core(internal)
        int_norm = _normalize(int_core)
        int_prov = _provider_prefix(internal)

        best_score = 0
        best: str | None = None

        for upstream in self._upstream_models:
            up_core = _core(upstream)
            up_norm = _normalize(up_core)
            up_prov = _provider_prefix(upstream)

            # Core name comparison
            if int_core == up_core:
                score = 100
            elif int_norm == up_norm:
                score = 90
            elif int_norm in up_norm or up_norm in int_norm:
                longer = max(len(int_norm), len(up_norm))
                shorter = min(len(int_norm), len(up_norm))
                score = int(70 * (shorter / longer)) if longer else 0
            else:
                continue

            # Provider prefix similarity
            if int_prov and up_prov:
                if int_prov == up_prov:
                    score += 10
                elif int_prov in up_prov or up_prov in int_prov:
                    score += 5

            if score > best_score:
                best_score = score
                best = upstream

        return best if best_score >= 50 else None

    # ---- resolution -------------------------------------------------------

    def resolve(self, internal_name: str) -> str:
        """Translate an internal model name to what the upstream expects.

        Priority:
          1. Dynamic map (from ``/v1/models`` discovery + fuzzy matching)
          2. Exact match in upstream model set
          3. Gateway → keep full ``provider/model``; direct → strip prefix
        """
        if internal_name in self._map:
            return self._map[internal_name]

        if self._discovered and internal_name in self._upstream_models:
            return internal_name

        # Fallback when discovery hasn't run or model is unknown
        if not self.is_gateway and "/" in internal_name:
            return internal_name.split("/", 1)[-1]

        return internal_name

    # ---- inspection -------------------------------------------------------

    def is_available(self, model_name: str) -> bool | None:
        """``True`` if model resolves to a known upstream ID, ``None`` if unknown."""
        if not self._discovered:
            return None
        resolved = self.resolve(model_name)
        return resolved in self._upstream_models

    def unresolved_models(self) -> list[str]:
        """Internal names that have no confirmed upstream equivalent."""
        if not self._discovered:
            return []
        from uncommon_route.router.config import DEFAULT_MODEL_PRICING

        out: list[str] = []
        for name in DEFAULT_MODEL_PRICING:
            resolved = self.resolve(name)
            if resolved not in self._upstream_models:
                out.append(name)
        return out

    def mapping_table(self) -> list[dict[str, str | bool | None]]:
        """Full mapping table for every internal model — used by the dashboard."""
        from uncommon_route.router.config import DEFAULT_MODEL_PRICING

        rows: list[dict[str, str | bool | None]] = []
        for name in DEFAULT_MODEL_PRICING:
            resolved = self.resolve(name)
            available: bool | None = None
            if self._discovered:
                available = resolved in self._upstream_models
            rows.append({
                "internal": name,
                "resolved": resolved,
                "mapped": name != resolved,
                "available": available,
            })
        return rows

    @property
    def discovered(self) -> bool:
        return self._discovered

    @property
    def upstream_model_count(self) -> int:
        return len(self._upstream_models)
