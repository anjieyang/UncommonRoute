"""End-to-end tests for all six usage modes.

1. CLI routing        — subprocess: uncommon-route route / debug
2. Python SDK         — import route(), classify(), SpendControl, SessionStore
3. HTTP Proxy         — start ASGI app, hit endpoints with httpx
4. OpenClaw           — install / status / uninstall config patch
5. Session management — sticky routing, escalation via proxy
6. Spend control      — set limits, get blocked at 429, history
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from uncommon_route.proxy import create_app
from uncommon_route.proxy import VERSION as PROXY_VERSION
from uncommon_route.session import SessionConfig, SessionStore
from uncommon_route.spend_control import InMemorySpendControlStorage, SpendControl

PYTHON = sys.executable
CLI_MODULE = [PYTHON, "-m", "uncommon_route.cli"]


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def proxy_client() -> TestClient:
    """Full proxy with session + spend, fake upstream."""
    ss = SessionStore(SessionConfig(enabled=True, timeout_s=300))
    sc = SpendControl(storage=InMemorySpendControlStorage())
    app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolate_openclaw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dir = tmp_path / ".openclaw"
    monkeypatch.setattr("uncommon_route.openclaw._OPENCLAW_DIR", fake_dir)
    monkeypatch.setattr("uncommon_route.openclaw._CONFIG_FILE", fake_dir / "openclaw.json")
    monkeypatch.setattr("uncommon_route.openclaw._PLUGINS_DIR", fake_dir / "plugins")


# ── Mode 1: CLI ──────────────────────────────────────────────────────

class TestCLI:
    def test_version(self) -> None:
        r = subprocess.run([*CLI_MODULE, "--version"], capture_output=True, text=True)
        assert r.returncode == 0
        assert PROXY_VERSION in r.stdout

    def test_help(self) -> None:
        r = subprocess.run([*CLI_MODULE, "--help"], capture_output=True, text=True)
        assert r.returncode == 0
        assert "uncommon-route" in r.stdout
        assert "openclaw" in r.stdout
        assert "spend" in r.stdout

    def test_route_text(self) -> None:
        r = subprocess.run(
            [*CLI_MODULE, "route", "what is 2+2"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "Model:" in r.stdout
        assert "Tier:" in r.stdout
        assert "SIMPLE" in r.stdout

    def test_route_json(self) -> None:
        r = subprocess.run(
            [*CLI_MODULE, "route", "--json", "explain quicksort in detail"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "model" in data
        assert "tier" in data
        assert "confidence" in data
        assert "latency_ms" in data

    def test_route_complex_prompt(self) -> None:
        r = subprocess.run(
            [*CLI_MODULE, "route", "--json",
             "Design a distributed consensus algorithm that handles Byzantine faults "
             "with formal correctness proofs and implement it in Rust"],
            capture_output=True, text=True,
        )
        data = json.loads(r.stdout)
        assert data["tier"] in ("COMPLEX", "REASONING")

    def test_debug(self) -> None:
        r = subprocess.run(
            [*CLI_MODULE, "debug", "prove that sqrt(2) is irrational"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "Structural Features:" in r.stdout
        assert "Keyword Features:" in r.stdout

    def test_route_no_prompt_fails(self) -> None:
        r = subprocess.run([*CLI_MODULE, "route"], capture_output=True, text=True)
        assert r.returncode != 0


# ── Mode 2: Python SDK ───────────────────────────────────────────────

class TestSDK:
    def test_route(self) -> None:
        from uncommon_route import route
        d = route("what is 2+2")
        assert d.model is not None
        assert d.tier.value == "SIMPLE"
        assert 0 <= d.confidence <= 1
        assert d.savings >= 0

    def test_classify(self) -> None:
        from uncommon_route import classify
        r = classify("implement a B-tree in C++ with deletion support")
        assert r.tier is not None
        assert r.tier.value in ("MEDIUM", "COMPLEX")
        assert len(r.signals) > 0

    def test_route_with_system_prompt(self) -> None:
        from uncommon_route import route
        d = route(
            "list 3 colors",
            system_prompt="You are a helpful assistant. Respond in JSON format.",
        )
        # structured output → at least MEDIUM
        assert d.tier.value in ("MEDIUM", "COMPLEX", "REASONING")

    def test_select_model_and_fallback(self) -> None:
        from uncommon_route import route
        d = route("hello")
        assert len(d.fallback_chain) > 0
        assert d.fallback_chain[0].cost_estimate >= 0

    def test_session_store_sdk(self) -> None:
        from uncommon_route import SessionStore, SessionConfig
        store = SessionStore(SessionConfig(enabled=True, timeout_s=60))
        store.set("sdk-test", "model-x", "SIMPLE")
        entry = store.get("sdk-test")
        assert entry is not None
        assert entry.model == "model-x"

    def test_spend_control_sdk(self) -> None:
        from uncommon_route import SpendControl, InMemorySpendControlStorage
        sc = SpendControl(storage=InMemorySpendControlStorage())
        sc.set_limit("per_request", 0.05)
        assert sc.check(0.03).allowed is True
        assert sc.check(0.10).allowed is False

    def test_openclaw_sdk(self) -> None:
        from uncommon_route import openclaw_install, openclaw_status, openclaw_uninstall
        openclaw_install(port=9999)
        s = openclaw_status()
        assert s["registered"] is True
        assert s["base_url"] == "http://127.0.0.1:9999/v1"
        openclaw_uninstall()
        assert openclaw_status()["registered"] is False


# ── Mode 3: HTTP Proxy ───────────────────────────────────────────────

class TestHTTPProxy:
    def test_health(self, proxy_client: TestClient) -> None:
        r = proxy_client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["router"] == "uncommon-route"
        assert "sessions" in d
        assert "spending" in d

    def test_models(self, proxy_client: TestClient) -> None:
        r = proxy_client.get("/v1/models")
        ids = [m["id"] for m in r.json()["data"]]
        assert "uncommon-route/auto" in ids

    def test_chat_debug(self, proxy_client: TestClient) -> None:
        r = proxy_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "/debug explain recursion"}],
        })
        assert r.status_code == 200
        content = r.json()["choices"][0]["message"]["content"]
        assert "Tier:" in content
        assert "Model:" in content

    def test_chat_routes_to_upstream(self, proxy_client: TestClient) -> None:
        """Virtual model routes and forwards (upstream is fake → 502, but routing works)."""
        r = proxy_client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert r.status_code == 502
        assert r.headers["x-uncommon-route-model"] != ""
        assert r.headers["x-uncommon-route-tier"] in ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING")

    def test_passthrough_model(self, proxy_client: TestClient) -> None:
        r = proxy_client.post("/v1/chat/completions", json={
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert r.status_code == 502
        assert "x-uncommon-route-model" not in r.headers


# ── Mode 4: OpenClaw Integration ─────────────────────────────────────

class TestOpenClawIntegration:
    def test_cli_openclaw_status(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI `openclaw status` runs without error."""
        r = subprocess.run(
            [*CLI_MODULE, "openclaw", "status"],
            capture_output=True, text=True,
            env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
        )
        assert r.returncode == 0
        assert "not installed" in r.stdout or "registered" in r.stdout

    def test_install_uninstall_cycle(self) -> None:
        from uncommon_route.openclaw import install, uninstall, status
        install(port=8403)
        s = status()
        assert s["config_patched"] is True
        assert s["model_count"] > 1

        uninstall()
        s = status()
        assert s["config_patched"] is False


# ── Mode 5: Session Management ───────────────────────────────────────

class TestSessionManagement:
    def test_session_sticky_routing(self) -> None:
        """Same session ID → same model across multiple requests."""
        ss = SessionStore(SessionConfig(enabled=True, timeout_s=300))
        sc = SpendControl(storage=InMemorySpendControlStorage())
        app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
        client = TestClient(app, raise_server_exceptions=False)

        headers = {"x-session-id": "test-session-abc"}
        body = {
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        }

        r1 = client.post("/v1/chat/completions", json=body, headers=headers)
        model1 = r1.headers.get("x-uncommon-route-model")
        reasoning1 = r1.headers.get("x-uncommon-route-reasoning", "")

        r2 = client.post("/v1/chat/completions", json=body, headers=headers)
        model2 = r2.headers.get("x-uncommon-route-model")
        reasoning2 = r2.headers.get("x-uncommon-route-reasoning", "")

        assert model1 == model2
        assert "session-hold" in reasoning2

    def test_sessions_endpoint(self) -> None:
        ss = SessionStore(SessionConfig(enabled=True, timeout_s=300))
        sc = SpendControl(storage=InMemorySpendControlStorage())
        app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
        client = TestClient(app, raise_server_exceptions=False)

        # Trigger a session
        client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        }, headers={"x-session-id": "visible-session"})

        r = client.get("/v1/sessions")
        data = r.json()
        assert data["count"] >= 1

    def test_session_escalation_via_proxy(self) -> None:
        """Three identical requests trigger tier escalation."""
        ss = SessionStore(SessionConfig(enabled=True, timeout_s=300))
        sc = SpendControl(storage=InMemorySpendControlStorage())
        app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
        client = TestClient(app, raise_server_exceptions=False)

        headers = {"x-session-id": "escalation-test"}
        body = {
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "same request repeated"}],
        }

        models = []
        for _ in range(4):
            r = client.post("/v1/chat/completions", json=body, headers=headers)
            models.append(r.headers.get("x-uncommon-route-model"))

        # First 3 should be same (sticky), 4th may escalate
        assert models[0] == models[1] == models[2]


# ── Mode 6: Spend Control ────────────────────────────────────────────

class TestSpendControlE2E:
    def test_set_limit_via_api(self, proxy_client: TestClient) -> None:
        proxy_client.post("/v1/spend", json={"action": "set", "window": "hourly", "amount": 10.0})
        data = proxy_client.get("/v1/spend").json()
        assert data["limits"]["hourly"] == 10.0
        assert data["remaining"]["hourly"] == 10.0

    def test_spend_blocks_at_limit(self) -> None:
        ss = SessionStore()
        sc = SpendControl(storage=InMemorySpendControlStorage())
        sc.set_limit("per_request", 0.0001)
        app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
        client = TestClient(app, raise_server_exceptions=False)

        r = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert r.status_code == 429
        err = r.json()["error"]
        assert err["type"] == "spend_limit_exceeded"
        assert "Per-request limit" in err["message"]

    def test_spend_clear_and_retry(self) -> None:
        ss = SessionStore()
        sc = SpendControl(storage=InMemorySpendControlStorage())
        sc.set_limit("per_request", 0.0001)
        app = create_app(upstream="http://127.0.0.1:1/fake", session_store=ss, spend_control=sc)
        client = TestClient(app, raise_server_exceptions=False)

        # Blocked
        r1 = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert r1.status_code == 429

        # Clear limit via API
        client.post("/v1/spend", json={"action": "clear", "window": "per_request"})

        # Now allowed (upstream fake → 502, but not 429)
        r2 = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert r2.status_code != 429

    def test_cli_spend_status(self, tmp_path: Path) -> None:
        r = subprocess.run(
            [*CLI_MODULE, "spend", "status"],
            capture_output=True, text=True,
            env={**dict(__import__("os").environ), "HOME": str(tmp_path)},
        )
        assert r.returncode == 0
        assert "Spending Limits" in r.stdout or "no limits" in r.stdout

    def test_spend_status_in_health(self, proxy_client: TestClient) -> None:
        proxy_client.post("/v1/spend", json={"action": "set", "window": "daily", "amount": 50.0})
        health = proxy_client.get("/health").json()
        assert health["spending"]["limits"]["daily"] == 50.0
