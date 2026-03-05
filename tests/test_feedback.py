"""Tests for feedback-driven online learning."""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from uncommon_route.feedback import (
    FeedbackCollector,
    _adjust_tier,
)
from uncommon_route.proxy import create_app
from uncommon_route.router.classifier import extract_features
from uncommon_route.session import SessionConfig, SessionStore
from uncommon_route.spend_control import InMemorySpendControlStorage, SpendControl
from uncommon_route.stats import InMemoryRouteStatsStorage, RouteStats


def _dummy_features() -> dict[str, float]:
    return extract_features("explain quicksort in Python")


class TestAdjustTier:
    def test_weak_moves_up(self) -> None:
        assert _adjust_tier("SIMPLE", "weak") == "MEDIUM"
        assert _adjust_tier("MEDIUM", "weak") == "COMPLEX"
        assert _adjust_tier("COMPLEX", "weak") == "REASONING"

    def test_weak_caps_at_reasoning(self) -> None:
        assert _adjust_tier("REASONING", "weak") == "REASONING"

    def test_strong_moves_down(self) -> None:
        assert _adjust_tier("REASONING", "strong") == "COMPLEX"
        assert _adjust_tier("COMPLEX", "strong") == "MEDIUM"
        assert _adjust_tier("MEDIUM", "strong") == "SIMPLE"

    def test_strong_caps_at_simple(self) -> None:
        assert _adjust_tier("SIMPLE", "strong") == "SIMPLE"

    def test_ok_keeps_same(self) -> None:
        assert _adjust_tier("MEDIUM", "ok") == "MEDIUM"


class TestFeedbackCollector:
    def test_capture_and_submit_weak(self) -> None:
        fc = FeedbackCollector()
        feats = _dummy_features()
        fc.capture("req1", feats, "SIMPLE")
        result = fc.submit("req1", "weak")
        assert result.ok
        assert result.action == "updated"
        assert result.from_tier == "SIMPLE"
        assert result.to_tier == "MEDIUM"

    def test_submit_expired(self) -> None:
        fc = FeedbackCollector()
        result = fc.submit("nonexistent", "weak")
        assert not result.ok
        assert result.action == "expired"

    def test_submit_ok_reinforces(self) -> None:
        fc = FeedbackCollector()
        fc.capture("req1", _dummy_features(), "MEDIUM")
        result = fc.submit("req1", "ok")
        assert result.ok
        assert result.action == "reinforced"
        assert result.from_tier == "MEDIUM"

    def test_submit_strong(self) -> None:
        fc = FeedbackCollector()
        fc.capture("req1", _dummy_features(), "COMPLEX")
        result = fc.submit("req1", "strong")
        assert result.ok
        assert result.action == "updated"
        assert result.to_tier == "MEDIUM"

    def test_no_change_at_boundary(self) -> None:
        fc = FeedbackCollector()
        fc.capture("req1", _dummy_features(), "REASONING")
        result = fc.submit("req1", "weak")
        assert result.ok
        assert result.action == "no_change"

    def test_buffer_ttl(self) -> None:
        t = time.time()
        fc = FeedbackCollector(buffer_ttl_s=60, now_fn=lambda: t)
        fc.capture("old", _dummy_features(), "SIMPLE")
        assert fc.pending_count == 1
        fc._now = lambda: t + 120  # advance past TTL
        fc.capture("new", _dummy_features(), "MEDIUM")
        assert fc.pending_count == 1
        assert "old" not in fc._buffer

    def test_rate_limiting(self) -> None:
        t = time.time()
        fc = FeedbackCollector(max_updates_per_hour=2, now_fn=lambda: t)
        feats = _dummy_features()
        fc.capture("a", feats, "SIMPLE")
        fc.submit("a", "weak")
        fc.capture("b", feats, "SIMPLE")
        fc.submit("b", "weak")
        fc.capture("c", feats, "SIMPLE")
        result = fc.submit("c", "weak")
        assert not result.ok
        assert result.action == "rate_limited"

    def test_learn_from_escalation(self) -> None:
        fc = FeedbackCollector()
        feats = _dummy_features()
        updated = fc.learn_from_escalation(feats, "SIMPLE", "MEDIUM")
        assert updated
        assert fc.total_updates == 1

    def test_escalation_rate_limited(self) -> None:
        t = time.time()
        fc = FeedbackCollector(max_updates_per_hour=1, now_fn=lambda: t)
        feats = _dummy_features()
        fc.learn_from_escalation(feats, "SIMPLE", "MEDIUM")
        assert not fc.learn_from_escalation(feats, "SIMPLE", "MEDIUM")

    def test_status(self) -> None:
        fc = FeedbackCollector()
        fc.capture("req1", _dummy_features(), "SIMPLE")
        s = fc.status()
        assert s["pending_contexts"] == 1
        assert s["total_online_updates"] == 0
        assert isinstance(s["online_model_active"], bool)

    def test_ngrams_stripped(self) -> None:
        fc = FeedbackCollector()
        feats = {"s_length": 0.5, "ngram_123": 0.1, "ngram_456": 0.2, "k_code": 0.3}
        fc.capture("req1", feats, "SIMPLE")
        stored = fc._buffer["req1"].features
        assert "ngram_123" not in stored
        assert "ngram_456" not in stored
        assert "s_length" in stored
        assert "k_code" in stored


@pytest.fixture
def fb_client() -> TestClient:
    app = create_app(
        upstream="http://127.0.0.1:1/fake",
        session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
        spend_control=SpendControl(storage=InMemorySpendControlStorage()),
        route_stats=RouteStats(storage=InMemoryRouteStatsStorage()),
        feedback=FeedbackCollector(),
    )
    return TestClient(app, raise_server_exceptions=False)


class TestFeedbackEndpoint:
    def test_get_feedback_status(self, fb_client: TestClient) -> None:
        resp = fb_client.get("/v1/feedback")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_contexts"] == 0

    def test_request_id_in_headers(self, fb_client: TestClient) -> None:
        resp = fb_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert "x-uncommon-route-request-id" in resp.headers
        rid = resp.headers["x-uncommon-route-request-id"]
        assert len(rid) == 12

    def test_feedback_round_trip(self, fb_client: TestClient) -> None:
        resp = fb_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        rid = resp.headers["x-uncommon-route-request-id"]

        pending = fb_client.get("/v1/feedback").json()
        assert pending["pending_contexts"] >= 1

        fb = fb_client.post("/v1/feedback", json={
            "request_id": rid, "signal": "ok",
        })
        assert fb.status_code == 200
        assert fb.json()["action"] == "reinforced"

    def test_feedback_weak_updates(self, fb_client: TestClient) -> None:
        resp = fb_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        rid = resp.headers["x-uncommon-route-request-id"]

        fb = fb_client.post("/v1/feedback", json={
            "request_id": rid, "signal": "weak",
        })
        data = fb.json()
        assert data["ok"]
        assert data["action"] == "updated"
        assert data["total_updates"] >= 1

    def test_feedback_expired_request(self, fb_client: TestClient) -> None:
        fb = fb_client.post("/v1/feedback", json={
            "request_id": "nonexistent", "signal": "weak",
        })
        assert fb.status_code == 404
        assert fb.json()["action"] == "expired"

    def test_feedback_bad_params(self, fb_client: TestClient) -> None:
        fb = fb_client.post("/v1/feedback", json={
            "request_id": "abc", "signal": "invalid",
        })
        assert fb.status_code == 400

    def test_rollback(self, fb_client: TestClient) -> None:
        fb = fb_client.post("/v1/feedback", json={"action": "rollback"})
        assert fb.status_code == 200
        assert "rolled_back" in fb.json()

    def test_passthrough_no_request_id(self, fb_client: TestClient) -> None:
        resp = fb_client.post("/v1/chat/completions", json={
            "model": "some-other/model",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert "x-uncommon-route-request-id" not in resp.headers

    def test_health_includes_feedback(self, fb_client: TestClient) -> None:
        data = fb_client.get("/health").json()
        assert "feedback" in data
        assert data["feedback"]["pending"] == 0
