"""Tests for route statistics collection and persistence."""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from uncommon_route.proxy import create_app
from uncommon_route.session import SessionConfig, SessionStore
from uncommon_route.spend_control import InMemorySpendControlStorage, SpendControl
from uncommon_route.stats import (
    InMemoryRouteStatsStorage,
    RouteRecord,
    RouteStats,
)


def _make_record(
    model: str = "moonshot/kimi-k2.5",
    tier: str = "SIMPLE",
    confidence: float = 0.9,
    method: str = "cascade",
    estimated_cost: float = 0.001,
    actual_cost: float | None = None,
    savings: float = 0.95,
    ts: float | None = None,
) -> RouteRecord:
    return RouteRecord(
        timestamp=ts or time.time(),
        model=model,
        tier=tier,
        confidence=confidence,
        method=method,
        estimated_cost=estimated_cost,
        actual_cost=actual_cost,
        savings=savings,
        latency_us=200.0,
    )


class TestRouteStats:
    def test_empty_summary(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        s = rs.summary()
        assert s.total_requests == 0
        assert s.by_tier == {}
        assert s.avg_confidence == 0.0

    def test_record_and_count(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record())
        rs.record(_make_record(tier="COMPLEX", model="google/gemini-3.1-pro"))
        assert rs.count == 2

    def test_summary_by_tier(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record(tier="SIMPLE", confidence=0.9))
        rs.record(_make_record(tier="SIMPLE", confidence=0.8))
        rs.record(_make_record(tier="COMPLEX", confidence=0.7, model="google/gemini-3.1-pro"))
        s = rs.summary()
        assert s.total_requests == 3
        assert s.by_tier["SIMPLE"].count == 2
        assert s.by_tier["COMPLEX"].count == 1
        assert abs(s.by_tier["SIMPLE"].avg_confidence - 0.85) < 0.01

    def test_summary_by_model(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record(model="a/b", estimated_cost=0.01))
        rs.record(_make_record(model="a/b", estimated_cost=0.02))
        rs.record(_make_record(model="c/d", estimated_cost=0.05))
        s = rs.summary()
        assert s.by_model["a/b"].count == 2
        assert s.by_model["c/d"].count == 1
        assert abs(s.by_model["a/b"].total_cost - 0.03) < 1e-9

    def test_summary_by_method(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record(method="cascade"))
        rs.record(_make_record(method="cascade"))
        rs.record(_make_record(method="session-hold"))
        s = rs.summary()
        assert s.by_method["cascade"] == 2
        assert s.by_method["session-hold"] == 1

    def test_actual_cost_preferred(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record(estimated_cost=0.01, actual_cost=0.005))
        s = rs.summary()
        assert abs(s.total_actual_cost - 0.005) < 1e-9
        assert abs(s.total_estimated_cost - 0.01) < 1e-9

    def test_history_reversed(self) -> None:
        now = time.time()
        rs = RouteStats(storage=InMemoryRouteStatsStorage(), now_fn=lambda: now)
        rs.record(_make_record(model="first", ts=now - 100))
        rs.record(_make_record(model="second", ts=now - 50))
        h = rs.history()
        assert h[0].model == "second"
        assert h[1].model == "first"

    def test_history_limit(self) -> None:
        now = time.time()
        rs = RouteStats(storage=InMemoryRouteStatsStorage(), now_fn=lambda: now)
        for i in range(10):
            rs.record(_make_record(ts=now - 10 + i))
        assert len(rs.history(limit=3)) == 3

    def test_reset(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        rs.record(_make_record())
        rs.record(_make_record())
        rs.reset()
        assert rs.count == 0
        assert rs.summary().total_requests == 0

    def test_persistence_roundtrip(self) -> None:
        storage = InMemoryRouteStatsStorage()
        rs1 = RouteStats(storage=storage)
        rs1.record(_make_record(model="test/model", confidence=0.77))
        rs1.record(_make_record(model="test/model2", tier="REASONING"))

        rs2 = RouteStats(storage=storage)
        assert rs2.count == 2
        h = rs2.history()
        assert h[0].model == "test/model2"
        assert h[1].confidence == 0.77

    def test_retention_cleanup(self) -> None:
        t = 1_000_000.0
        rs = RouteStats(
            storage=InMemoryRouteStatsStorage(),
            now_fn=lambda: t,
        )
        rs.record(_make_record(ts=t - 8 * 86_400))  # older than 7 days
        rs.record(_make_record(ts=t - 1_000))  # recent
        assert rs.count == 1

    def test_avg_latency(self) -> None:
        rs = RouteStats(storage=InMemoryRouteStatsStorage())
        r1 = _make_record()
        r1 = RouteRecord(**{**r1.__dict__, "latency_us": 100.0})
        r2 = _make_record()
        r2 = RouteRecord(**{**r2.__dict__, "latency_us": 300.0})
        rs.record(r1)
        rs.record(r2)
        assert abs(rs.summary().avg_latency_us - 200.0) < 0.1


@pytest.fixture
def stats_client() -> TestClient:
    """Test client with in-memory stats."""
    app = create_app(
        upstream="http://127.0.0.1:1/fake",
        session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
        spend_control=SpendControl(storage=InMemorySpendControlStorage()),
        route_stats=RouteStats(storage=InMemoryRouteStatsStorage()),
    )
    return TestClient(app, raise_server_exceptions=False)


class TestStatsEndpoint:
    def test_get_stats_empty(self, stats_client: TestClient) -> None:
        resp = stats_client.get("/v1/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 0
        assert data["by_tier"] == {}

    def test_stats_after_routing(self, stats_client: TestClient) -> None:
        stats_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        resp = stats_client.get("/v1/stats")
        data = resp.json()
        # Upstream is fake (502), but for non-streaming the stats still record
        assert data["total_requests"] == 1
        assert "SIMPLE" in data["by_tier"]
        assert data["by_method"].get("cascade", 0) >= 1
        assert data["avg_confidence"] > 0

    def test_stats_reset(self, stats_client: TestClient) -> None:
        stats_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        resp = stats_client.post("/v1/stats", json={"action": "reset"})
        assert resp.status_code == 200
        assert resp.json()["reset"] is True

        data = stats_client.get("/v1/stats").json()
        assert data["total_requests"] == 0

    def test_stats_invalid_action(self, stats_client: TestClient) -> None:
        resp = stats_client.post("/v1/stats", json={"action": "explode"})
        assert resp.status_code == 400

    def test_health_includes_stats(self, stats_client: TestClient) -> None:
        data = stats_client.get("/health").json()
        assert "stats" in data
        assert data["stats"]["total_requests"] == 0

    def test_debug_not_recorded(self, stats_client: TestClient) -> None:
        """Debug requests should not appear in stats."""
        stats_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "/debug hello"}],
        })
        data = stats_client.get("/v1/stats").json()
        assert data["total_requests"] == 0

    def test_passthrough_not_recorded(self, stats_client: TestClient) -> None:
        """Non-virtual model requests should not appear in stats."""
        stats_client.post("/v1/chat/completions", json={
            "model": "some-other/model",
            "messages": [{"role": "user", "content": "hello"}],
        })
        data = stats_client.get("/v1/stats").json()
        assert data["total_requests"] == 0
