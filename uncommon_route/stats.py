"""Route statistics — records every routing decision for analytics.

Tracks tier distribution, model usage, confidence, savings, and latency
across all routed requests. Persistent storage with 7-day rolling window.

Storage: ~/.uncommon-route/stats.json
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RETENTION_S = 7 * 86_400  # 7 days
MAX_RECORDS = 10_000

RouteMethod = Literal["cascade", "session-hold", "session-upgrade", "step-aware", "escalated"]

_DATA_DIR = Path.home() / ".uncommon-route"


@dataclass
class RouteRecord:
    timestamp: float
    model: str
    tier: str
    confidence: float
    method: RouteMethod
    estimated_cost: float
    actual_cost: float | None = None
    savings: float = 0.0
    latency_us: float = 0.0
    session_id: str | None = None
    streaming: bool = False


@dataclass
class TierSummary:
    count: int = 0
    avg_confidence: float = 0.0
    avg_savings: float = 0.0
    total_cost: float = 0.0


@dataclass
class ModelSummary:
    count: int = 0
    total_cost: float = 0.0


@dataclass
class StatsSummary:
    total_requests: int
    time_range_s: float
    by_tier: dict[str, TierSummary]
    by_model: dict[str, ModelSummary]
    by_method: dict[str, int]
    avg_confidence: float
    avg_savings: float
    avg_latency_us: float
    total_estimated_cost: float
    total_actual_cost: float


# ─── Storage abstraction ───


class RouteStatsStorage(ABC):
    @abstractmethod
    def load(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def save(self, records: list[dict[str, Any]]) -> None: ...


class FileRouteStatsStorage(RouteStatsStorage):
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_DATA_DIR / "stats.json")

    def load(self) -> list[dict[str, Any]]:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text())
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def save(self, records: list[dict[str, Any]]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._path.write_text(json.dumps(records, default=str))
            self._path.chmod(0o600)
        except Exception as exc:
            import sys
            print(f"[UncommonRoute] Failed to save stats: {exc}", file=sys.stderr)


class InMemoryRouteStatsStorage(RouteStatsStorage):
    def __init__(self) -> None:
        self._data: list[dict[str, Any]] = []

    def load(self) -> list[dict[str, Any]]:
        return list(self._data)

    def save(self, records: list[dict[str, Any]]) -> None:
        self._data = list(records)


# ─── Collector ───


def _effective_cost(r: RouteRecord) -> float:
    return r.actual_cost if r.actual_cost is not None else r.estimated_cost


class RouteStats:
    """Route-level statistics collector with persistent storage."""

    def __init__(
        self,
        storage: RouteStatsStorage | None = None,
        now_fn: Any = None,
    ) -> None:
        self._storage = storage or FileRouteStatsStorage()
        self._now = now_fn or time.time
        self._records: list[RouteRecord] = []
        self._load()

    def record(self, rec: RouteRecord) -> None:
        self._records.append(rec)
        self._cleanup()
        self._save()

    def history(self, limit: int | None = None) -> list[RouteRecord]:
        records = list(reversed(self._records))
        return records[:limit] if limit else records

    def summary(self) -> StatsSummary:
        if not self._records:
            return StatsSummary(
                total_requests=0, time_range_s=0.0,
                by_tier={}, by_model={}, by_method={},
                avg_confidence=0.0, avg_savings=0.0, avg_latency_us=0.0,
                total_estimated_cost=0.0, total_actual_cost=0.0,
            )

        now = self._now()
        oldest = min(r.timestamp for r in self._records)
        n = len(self._records)

        tier_groups: dict[str, list[RouteRecord]] = {}
        model_groups: dict[str, list[RouteRecord]] = {}
        method_counts: dict[str, int] = {}

        for r in self._records:
            tier_groups.setdefault(r.tier, []).append(r)
            model_groups.setdefault(r.model, []).append(r)
            method_counts[r.method] = method_counts.get(r.method, 0) + 1

        by_tier: dict[str, TierSummary] = {}
        for tier, recs in tier_groups.items():
            cnt = len(recs)
            by_tier[tier] = TierSummary(
                count=cnt,
                avg_confidence=sum(r.confidence for r in recs) / cnt,
                avg_savings=sum(r.savings for r in recs) / cnt,
                total_cost=sum(_effective_cost(r) for r in recs),
            )

        by_model: dict[str, ModelSummary] = {}
        for model, recs in model_groups.items():
            by_model[model] = ModelSummary(
                count=len(recs),
                total_cost=sum(_effective_cost(r) for r in recs),
            )

        total_est = sum(r.estimated_cost for r in self._records)
        total_act = sum(_effective_cost(r) for r in self._records)

        return StatsSummary(
            total_requests=n,
            time_range_s=now - oldest,
            by_tier=by_tier,
            by_model=by_model,
            by_method=method_counts,
            avg_confidence=sum(r.confidence for r in self._records) / n,
            avg_savings=sum(r.savings for r in self._records) / n,
            avg_latency_us=sum(r.latency_us for r in self._records) / n,
            total_estimated_cost=total_est,
            total_actual_cost=total_act,
        )

    def reset(self) -> None:
        self._records.clear()
        self._save()

    @property
    def count(self) -> int:
        return len(self._records)

    def _cleanup(self) -> None:
        cutoff = self._now() - RETENTION_S
        self._records = [r for r in self._records if r.timestamp >= cutoff]
        if len(self._records) > MAX_RECORDS:
            self._records = self._records[-MAX_RECORDS:]

    def _save(self) -> None:
        self._storage.save([
            {
                "timestamp": r.timestamp,
                "model": r.model,
                "tier": r.tier,
                "confidence": r.confidence,
                "method": r.method,
                "estimated_cost": r.estimated_cost,
                "actual_cost": r.actual_cost,
                "savings": r.savings,
                "latency_us": r.latency_us,
                "session_id": r.session_id,
                "streaming": r.streaming,
            }
            for r in self._records
        ])

    def _load(self) -> None:
        for r in self._storage.load():
            if not isinstance(r, dict) or "timestamp" not in r:
                continue
            self._records.append(RouteRecord(
                timestamp=r["timestamp"],
                model=r.get("model", ""),
                tier=r.get("tier", ""),
                confidence=r.get("confidence", 0.0),
                method=r.get("method", "cascade"),
                estimated_cost=r.get("estimated_cost", 0.0),
                actual_cost=r.get("actual_cost"),
                savings=r.get("savings", 0.0),
                latency_us=r.get("latency_us", 0.0),
                session_id=r.get("session_id"),
                streaming=r.get("streaming", False),
            ))
        self._cleanup()
