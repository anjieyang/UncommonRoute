"""Feedback-driven online learning for the routing classifier.

Collects implicit (3-strike escalation) and explicit (user) feedback
to incrementally update the Averaged Perceptron weights.

Design: zero user disruption.
  - Implicit: escalation auto-triggers weight update (fully transparent)
  - Explicit: optional POST /v1/feedback with request_id from response header
  - Passive: request_id delivered via x-uncommon-route-request-id header only

Safety rails:
  - Max 100 model updates per hour (prevents abuse / runaway feedback)
  - Context buffer auto-expires after 1 hour
  - Online weights saved to separate file (base model never overwritten)
  - Rollback to base model in one call
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

FeedbackSignal = Literal["weak", "strong", "ok"]

TIER_ORDER = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"]


@dataclass
class RequestContext:
    features: dict[str, float]
    tier: str
    timestamp: float


@dataclass
class FeedbackResult:
    ok: bool
    action: str
    from_tier: str = ""
    to_tier: str = ""
    reason: str = ""


class FeedbackCollector:
    """Orchestrates feedback collection and online model updates.

    Stores compact feature vectors (no raw prompts) for recent requests.
    When feedback arrives, adjusts the Perceptron weights toward the
    corrected tier and periodically persists the updated model.
    """

    def __init__(
        self,
        buffer_ttl_s: int = 3600,
        max_updates_per_hour: int = 100,
        save_every: int = 10,
        now_fn: Any = None,
    ) -> None:
        self._buffer: dict[str, RequestContext] = {}
        self._buffer_ttl_s = buffer_ttl_s
        self._max_hourly = max_updates_per_hour
        self._save_every = save_every
        self._now = now_fn or time.time
        self._update_ts: list[float] = []
        self._total_updates: int = 0
        self._since_save: int = 0

    # ─── Public API ───

    def capture(self, request_id: str, features: dict[str, float], tier: str) -> None:
        """Buffer compact features for a routed request (no raw prompts stored)."""
        self._cleanup_buffer()
        compact = {k: v for k, v in features.items() if not k.startswith("ngram_")}
        self._buffer[request_id] = RequestContext(
            features=compact, tier=tier, timestamp=self._now(),
        )

    def submit(self, request_id: str, signal: FeedbackSignal) -> FeedbackResult:
        """Process explicit user feedback for a previous request."""
        self._cleanup_buffer()
        ctx = self._buffer.pop(request_id, None)
        if ctx is None:
            return FeedbackResult(
                ok=False, action="expired",
                reason="request_id not found or expired",
            )

        target = _adjust_tier(ctx.tier, signal)

        if signal == "ok":
            self._do_update(ctx.features, ctx.tier)
            return FeedbackResult(
                ok=True, action="reinforced",
                from_tier=ctx.tier, to_tier=ctx.tier,
            )

        if target == ctx.tier:
            return FeedbackResult(
                ok=True, action="no_change",
                from_tier=ctx.tier, to_tier=ctx.tier,
                reason="already at tier boundary",
            )

        if not self._rate_ok():
            return FeedbackResult(
                ok=False, action="rate_limited",
                reason=f"max {self._max_hourly} updates/hour",
            )

        self._do_update(ctx.features, target)
        return FeedbackResult(
            ok=True, action="updated",
            from_tier=ctx.tier, to_tier=target,
        )

    def learn_from_escalation(
        self,
        features: dict[str, float],
        original_tier: str,
        escalated_tier: str,
    ) -> bool:
        """Auto-learn from 3-strike escalation. Returns True if updated."""
        if not self._rate_ok():
            return False
        compact = {k: v for k, v in features.items() if not k.startswith("ngram_")}
        self._do_update(compact, escalated_tier)
        return True

    def rollback(self) -> bool:
        """Reset to base model, discard online weights."""
        from uncommon_route.router.classifier import rollback_online_model

        deleted = rollback_online_model()
        self._total_updates = 0
        self._since_save = 0
        self._update_ts.clear()
        return deleted

    # ─── Introspection ───

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    @property
    def total_updates(self) -> int:
        return self._total_updates

    @property
    def online_model_active(self) -> bool:
        from uncommon_route.router.classifier import _get_online_model_path

        return _get_online_model_path().exists()

    def status(self) -> dict[str, Any]:
        now = self._now()
        hourly = sum(1 for t in self._update_ts if now - t < 3600)
        return {
            "pending_contexts": self.pending_count,
            "total_online_updates": self._total_updates,
            "updates_last_hour": hourly,
            "online_model_active": self.online_model_active,
            "buffer_ttl_s": self._buffer_ttl_s,
            "max_updates_per_hour": self._max_hourly,
        }

    # ─── Internals ───

    def _do_update(self, features: dict[str, float], correct_tier: str) -> None:
        from uncommon_route.router.classifier import save_online_model, update_model

        if not update_model(features, correct_tier):
            return
        now = self._now()
        self._total_updates += 1
        self._since_save += 1
        self._update_ts.append(now)
        self._update_ts = [t for t in self._update_ts if now - t < 3600]
        if self._since_save >= self._save_every:
            save_online_model()
            self._since_save = 0

    def _rate_ok(self) -> bool:
        now = self._now()
        hourly = sum(1 for t in self._update_ts if now - t < 3600)
        return hourly < self._max_hourly

    def _cleanup_buffer(self) -> None:
        now = self._now()
        expired = [k for k, v in self._buffer.items() if now - v.timestamp > self._buffer_ttl_s]
        for k in expired:
            del self._buffer[k]


def _adjust_tier(current: str, signal: FeedbackSignal) -> str:
    idx = TIER_ORDER.index(current) if current in TIER_ORDER else 1
    if signal == "weak":
        return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]
    if signal == "strong":
        return TIER_ORDER[max(idx - 1, 0)]
    return current
