"""Integration tests for the proxy server with session + spend control."""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from uncommon_route.artifacts import ArtifactStore
from uncommon_route.composition import CompositionPolicy
from uncommon_route.model_experience import InMemoryModelExperienceStorage, ModelExperienceStore
from uncommon_route.proxy import _extract_prompt, create_app
from uncommon_route.router.config import routing_profile_from_model
from uncommon_route.routing_config_store import InMemoryRoutingConfigStorage, RoutingConfigStore
from uncommon_route.session import SessionConfig, SessionStore
from uncommon_route.semantic import SemanticCallResult, SideChannelConfig, SideChannelTaskConfig
from uncommon_route.spend_control import InMemorySpendControlStorage, SpendControl
from uncommon_route.router.types import RoutingProfile


class FakeSemanticCompressor:
    async def summarize_tool_result(self, content: str, *, tool_name: str, latest_user_prompt: str, request: object) -> SemanticCallResult | None:
        return SemanticCallResult(text=f"semantic summary for {tool_name}", model="deepseek/deepseek-chat", estimated_cost=0.001)

    async def summarize_history(self, transcript: str, *, latest_user_prompt: str, session_id: str, request: object) -> SemanticCallResult | None:
        return SemanticCallResult(text=f"checkpoint summary for {session_id}", model="deepseek/deepseek-chat", estimated_cost=0.002)

    async def rehydrate_artifact(self, query: str, *, artifact_id: str, content: str, summary: str, request: object) -> SemanticCallResult | None:
        return SemanticCallResult(text=f"rehydrated excerpt for {artifact_id}", model="deepseek/deepseek-chat", estimated_cost=0.001)


class QualityFallbackSemanticCompressor(FakeSemanticCompressor):
    async def summarize_tool_result(self, content: str, *, tool_name: str, latest_user_prompt: str, request: object) -> SemanticCallResult | None:
        return SemanticCallResult(
            text=f"semantic summary for {tool_name}",
            model="google/gemini-2.5-flash-lite",
            estimated_cost=0.001,
            quality_fallbacks=3,
        )


class TestPromptExtraction:
    def test_extract_prompt_ignores_claude_code_wrapper_blocks(self) -> None:
        prompt, system_prompt, max_tokens = _extract_prompt({
            "max_tokens": 128,
            "messages": [
                {"role": "system", "content": "top-level system"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "<system-reminder>\nThe following skills are available for use with the Skill tool.\n</system-reminder>",
                        },
                        {
                            "type": "text",
                            "text": "<system-reminder>\nAs you answer the user's questions, you can use the following context.\n# claudeMd\n</system-reminder>",
                        },
                        {
                            "type": "text",
                            "text": "List the top-level directories in the current repository.",
                        },
                    ],
                },
            ],
        })

        assert prompt == "List the top-level directories in the current repository."
        assert system_prompt == "top-level system"
        assert max_tokens == 128

    def test_extract_prompt_strips_wrapper_prefix_from_string_message(self) -> None:
        prompt, _system_prompt, _max_tokens = _extract_prompt({
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "<system-reminder>\n"
                        "The following skills are available for use with the Skill tool.\n"
                        "</system-reminder>\n"
                        "Find routing_profile_from_model in this repository."
                    ),
                },
            ],
        })

        assert prompt == "Find routing_profile_from_model in this repository."


@pytest.fixture
def client() -> TestClient:
    """Test client with in-memory session + spend control (no real upstream)."""
    session_store = SessionStore(SessionConfig(enabled=True, timeout_s=300))
    spend_control = SpendControl(storage=InMemorySpendControlStorage())
    app = create_app(
        upstream="http://127.0.0.1:1/fake",
        session_store=session_store,
        spend_control=spend_control,
    )
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["router"] == "uncommon-route"

    def test_health_includes_sessions(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "sessions" in data
        assert data["sessions"]["count"] == 0

    def test_health_includes_spending(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "spending" in data
        assert "calls" in data["spending"]

    def test_health_exposes_custom_composition_policy(self, tmp_path) -> None:
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
            spend_control=SpendControl(storage=InMemorySpendControlStorage()),
            artifact_store=ArtifactStore(root=tmp_path / "artifacts"),
            composition_policy=CompositionPolicy(
                tool_offload_threshold_tokens=1234,
                sidechannel=SideChannelConfig(
                    tool_summary=SideChannelTaskConfig(
                        primary="openai/gpt-4o-mini",
                        fallback=("anthropic/claude-haiku-4.5",),
                    ),
                    checkpoint=SideChannelTaskConfig(primary="moonshot/kimi-k2.5"),
                    rehydrate=SideChannelTaskConfig(primary="deepseek/deepseek-chat"),
                ),
            ),
        )
        client = TestClient(app, raise_server_exceptions=False)

        data = client.get("/health").json()

        assert data["composition"]["policy"]["tool_offload_threshold_tokens"] == 1234
        assert data["composition"]["policy"]["sidechannel"]["tool_summary"]["primary"] == "openai/gpt-4o-mini"
        assert data["composition"]["sidechannel_models"]["tool_summary"] == [
            "openai/gpt-4o-mini",
            "anthropic/claude-haiku-4.5",
        ]


class TestModelsEndpoint:
    def test_models_list(self, client: TestClient) -> None:
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        model_ids = [m["id"] for m in data["data"]]
        assert "uncommon-route/auto" in model_ids
        assert "uncommon-route/eco" in model_ids
        assert "uncommon-route/premium" in model_ids
        assert "uncommon-route/free" in model_ids
        assert "uncommon-route/agentic" in model_ids


class TestVirtualModelAliases:
    def test_routing_profile_from_bare_alias(self) -> None:
        assert routing_profile_from_model("auto") is RoutingProfile.AUTO
        assert routing_profile_from_model("premium") is RoutingProfile.PREMIUM

    def test_chat_accepts_bare_virtual_alias(self, client: TestClient) -> None:
        resp = client.post("/v1/chat/completions", json={
            "model": "auto",
            "messages": [{"role": "user", "content": "hello"}],
        })

        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-profile"] == "auto"


class TestSelectorEndpoint:
    def test_get_selector_state(self, client: TestClient) -> None:
        resp = client.get("/v1/selector")
        assert resp.status_code == 200
        data = resp.json()
        assert "selection_profiles" in data
        assert "bandit_profiles" in data
        assert "experience" in data

    def test_get_selector_bucket_summary(self) -> None:
        store = ModelExperienceStore(storage=InMemoryModelExperienceStorage())
        store.record_feedback("google/gemini-2.5-flash-lite", "auto", "SIMPLE", "ok")
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
            spend_control=SpendControl(storage=InMemorySpendControlStorage()),
            model_experience=store,
        )
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/v1/selector?profile=auto&tier=SIMPLE")

        assert resp.status_code == 200
        data = resp.json()
        assert data["bucket"]["profile"] == "auto"
        assert data["bucket"]["tier"] == "SIMPLE"
        assert data["bucket"]["models"][0]["model"] == "google/gemini-2.5-flash-lite"

    def test_selector_preview_accepts_prompt_shape(self, client: TestClient) -> None:
        resp = client.post("/v1/selector", json={
            "profile": "auto",
            "prompt": "hello",
            "max_tokens": 128,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["virtual"] is True
        assert data["profile"] == "auto"
        assert data["candidate_scores"]
        assert data["candidate_scores"][0]["model"] == data["decision_model"]

    def test_selector_preview_reflects_session_hold(self, client: TestClient) -> None:
        headers = {"x-session-id": "selector-hold"}
        client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "design a distributed database with failure proofs"}],
        }, headers=headers)

        resp = client.post("/v1/selector", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        }, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["method"] == "session-hold"
        assert data["session"]["applied"] is True
        assert data["served_model"] != data["decision_model"] or data["served_tier"] != data["decision_tier"]

    def test_selector_preview_caps_tool_selection_to_medium(self, client: TestClient) -> None:
        resp = client.post("/v1/selector", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "list the files changed in this repo and pick the best tool"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run shell commands",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["step_type"] == "tool-selection"
        assert data["decision_tier"] == "MEDIUM"


class TestRoutingConfigEndpoint:
    def test_get_routing_config_returns_profiles(self, client: TestClient) -> None:
        resp = client.get("/v1/routing-config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["editable"] is True
        assert "auto" in data["profiles"]
        assert data["profiles"]["auto"]["tiers"]["SIMPLE"]["primary"]
        assert data["profiles"]["auto"]["tiers"]["SIMPLE"]["selection_mode"] == "adaptive"

    def test_post_set_tier_updates_selector_preview(self, client: TestClient) -> None:
        resp = client.post("/v1/routing-config", json={
            "action": "set-tier",
            "profile": "auto",
            "tier": "MEDIUM",
            "primary": "openai/gpt-4o-mini",
            "fallback": [],
        })

        assert resp.status_code == 200
        updated = resp.json()
        assert updated["profiles"]["auto"]["tiers"]["MEDIUM"]["primary"] == "openai/gpt-4o-mini"
        assert updated["profiles"]["auto"]["tiers"]["MEDIUM"]["overridden"] is True

        preview = client.post("/v1/selector", json={
            "profile": "auto",
            "prompt": "Return valid JSON with keys a and b.",
            "max_tokens": 128,
        })

        assert preview.status_code == 200
        data = preview.json()
        assert data["decision_tier"] == "MEDIUM"
        assert data["decision_model"] == "openai/gpt-4o-mini"
        assert data["active_tier_configs"]["MEDIUM"]["primary"] == "openai/gpt-4o-mini"
        assert data["active_tier_configs"]["MEDIUM"]["selection_mode"] == "adaptive"

    def test_hard_pin_forces_primary_over_adaptive_cheaper_candidate(self, client: TestClient) -> None:
        adaptive = client.post("/v1/routing-config", json={
            "action": "set-tier",
            "profile": "eco",
            "tier": "SIMPLE",
            "primary": "openai/gpt-4o",
            "fallback": ["nvidia/gpt-oss-120b"],
            "selection_mode": "adaptive",
        })
        assert adaptive.status_code == 200

        adaptive_preview = client.post("/v1/selector", json={
            "profile": "eco",
            "prompt": "hello",
            "max_tokens": 64,
        })
        assert adaptive_preview.status_code == 200
        adaptive_model = adaptive_preview.json()["decision_model"]

        pinned = client.post("/v1/routing-config", json={
            "action": "set-tier",
            "profile": "eco",
            "tier": "SIMPLE",
            "primary": "openai/gpt-4o",
            "fallback": ["nvidia/gpt-oss-120b"],
            "selection_mode": "hard-pin",
        })
        assert pinned.status_code == 200

        pinned_preview = client.post("/v1/selector", json={
            "profile": "eco",
            "prompt": "hello",
            "max_tokens": 64,
        })

        assert pinned_preview.status_code == 200
        pinned_data = pinned_preview.json()
        assert pinned_data["decision_tier"] == "SIMPLE"
        assert pinned_data["decision_model"] == "openai/gpt-4o"
        assert pinned_data["active_tier_configs"]["SIMPLE"]["selection_mode"] == "hard-pin"
        assert adaptive_model != pinned_data["decision_model"]

    def test_hard_pin_overrides_session_hold(self, client: TestClient) -> None:
        headers = {"x-session-id": "pinned-session"}
        client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "design a distributed system with formal guarantees"}],
        }, headers=headers)

        pinned = client.post("/v1/routing-config", json={
            "action": "set-tier",
            "profile": "auto",
            "tier": "SIMPLE",
            "primary": "openai/gpt-4o-mini",
            "fallback": [],
            "selection_mode": "hard-pin",
        })
        assert pinned.status_code == 200

        preview = client.post("/v1/selector", json={
            "profile": "auto",
            "prompt": "hello",
            "max_tokens": 64,
        }, headers=headers)

        assert preview.status_code == 200
        data = preview.json()
        assert data["method"] == "hard-pin"
        assert data["served_model"] == "openai/gpt-4o-mini"

    def test_post_reset_tier_restores_default(self) -> None:
        store = RoutingConfigStore(storage=InMemoryRoutingConfigStorage())
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
            spend_control=SpendControl(storage=InMemorySpendControlStorage()),
            routing_config_store=store,
        )
        client = TestClient(app, raise_server_exceptions=False)

        set_resp = client.post("/v1/routing-config", json={
            "action": "set-tier",
            "profile": "auto",
            "tier": "SIMPLE",
            "primary": "openai/gpt-4o-mini",
            "fallback": ["moonshot/kimi-k2.5"],
        })
        assert set_resp.status_code == 200

        reset_resp = client.post("/v1/routing-config", json={
            "action": "reset-tier",
            "profile": "auto",
            "tier": "SIMPLE",
        })

        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()
        assert reset_data["profiles"]["auto"]["tiers"]["SIMPLE"]["primary"] == "moonshot/kimi-k2.5"
        assert reset_data["profiles"]["auto"]["tiers"]["SIMPLE"]["overridden"] is False
        assert reset_data["profiles"]["auto"]["tiers"]["SIMPLE"]["selection_mode"] == "adaptive"


class TestChatCompletions:
    def test_virtual_model_routes(self, client: TestClient) -> None:
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "/debug what is 2+2"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "uncommon-route/debug"
        assert "UncommonRoute Debug" in data["choices"][0]["message"]["content"]

    def test_routing_headers_present(self, client: TestClient) -> None:
        """Non-debug requests forward to upstream; headers are set even if upstream fails."""
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        # Upstream is fake so we get 502, but routing headers should still be present
        assert resp.status_code == 502
        assert "x-uncommon-route-model" in resp.headers
        assert "x-uncommon-route-tier" in resp.headers
        assert resp.headers["x-uncommon-route-profile"] == "auto"
        assert "x-uncommon-route-transport" in resp.headers
        assert "x-uncommon-route-cache-mode" in resp.headers

    def test_openai_cache_key_is_emitted_for_sessioned_openai_routing(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "uncommon-route/premium",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"x-session-id": "premium-cache"},
        )

        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-transport"] == "openai-chat"
        assert resp.headers["x-uncommon-route-cache-family"] == "openai"
        assert resp.headers["x-uncommon-route-cache-mode"] == "prompt_cache_key"
        assert resp.headers["x-uncommon-route-cache-key"].startswith("ur:")

    def test_free_profile_tool_request_avoids_non_tool_model(self, client: TestClient) -> None:
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/free",
            "messages": [{"role": "user", "content": "list files in this repo"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a shell command",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        })
        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-profile"] == "free"
        assert resp.headers["x-uncommon-route-model"] != "nvidia/gpt-oss-120b"

    def test_premium_profile_routes(self, client: TestClient) -> None:
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/premium",
            "messages": [{"role": "user", "content": "design a distributed database with five constraints"}],
        })
        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-profile"] == "premium"

    def test_anthropic_messages_accept_explicit_provider_model(self, client: TestClient) -> None:
        resp = client.post("/v1/messages", json={
            "model": "anthropic/claude-sonnet-4.6",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "hello"}],
        })

        assert resp.status_code == 502
        assert "x-uncommon-route-profile" not in resp.headers

    def test_large_tool_result_creates_artifact(self, tmp_path) -> None:
        session_store = SessionStore(SessionConfig(enabled=True, timeout_s=300))
        spend_control = SpendControl(storage=InMemorySpendControlStorage())
        artifact_store = ArtifactStore(root=tmp_path / "artifacts")
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=session_store,
            spend_control=spend_control,
            artifact_store=artifact_store,
        )
        client = TestClient(app, raise_server_exceptions=False)

        large_text = "\n".join(f"line {i} with repeated tool output" for i in range(3000))
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [
                {"role": "user", "content": "analyze this output"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": large_text},
            ],
        })

        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-artifacts"] == "1"
        assert int(resp.headers["x-uncommon-route-input-after"]) < int(resp.headers["x-uncommon-route-input-before"])

        artifacts = client.get("/v1/artifacts").json()
        assert artifacts["count"] == 1
        artifact_id = artifacts["items"][0]["id"]
        artifact = client.get(f"/v1/artifacts/{artifact_id}").json()
        assert artifact["tool_name"] == "bash"
        assert "line 0 with repeated tool output" in artifact["content"]

    def test_semantic_headers_present_when_compressor_runs(self, tmp_path) -> None:
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
            spend_control=SpendControl(storage=InMemorySpendControlStorage()),
            artifact_store=ArtifactStore(root=tmp_path / "artifacts"),
            semantic_compressor=FakeSemanticCompressor(),
        )
        client = TestClient(app, raise_server_exceptions=False)
        large_text = "\n".join(f"tool output {i}" for i in range(2500))
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [
                {"role": "user", "content": "analyze and keep using artifact:// references later"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": large_text},
            ],
        })
        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-semantic-calls"] == "1"
        assert resp.headers["x-uncommon-route-artifacts"] == "1"

    def test_semantic_quality_fallback_header_present(self, tmp_path) -> None:
        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=SessionStore(SessionConfig(enabled=True, timeout_s=300)),
            spend_control=SpendControl(storage=InMemorySpendControlStorage()),
            artifact_store=ArtifactStore(root=tmp_path / "artifacts"),
            semantic_compressor=QualityFallbackSemanticCompressor(),
        )
        client = TestClient(app, raise_server_exceptions=False)
        large_text = "\n".join(f"tool output {i}" for i in range(2500))
        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [
                {"role": "user", "content": "extract the critical error"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": large_text},
            ],
        })

        assert resp.status_code == 502
        assert resp.headers["x-uncommon-route-semantic-fallbacks"] == "3"

    def test_passthrough_no_routing_headers(self, client: TestClient) -> None:
        resp = client.post("/v1/chat/completions", json={
            "model": "some-other/model",
            "messages": [{"role": "user", "content": "hello"}],
        })
        # Upstream is fake, expect 502
        assert resp.status_code == 502
        assert "x-uncommon-route-model" not in resp.headers


class TestSpendEndpoint:
    def test_get_spend_status(self, client: TestClient) -> None:
        resp = client.get("/v1/spend")
        assert resp.status_code == 200
        data = resp.json()
        assert "limits" in data
        assert "calls" in data

    def test_set_and_get_limit(self, client: TestClient) -> None:
        resp = client.post("/v1/spend", json={
            "action": "set", "window": "hourly", "amount": 5.00,
        })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        data = client.get("/v1/spend").json()
        assert data["limits"]["hourly"] == 5.00

    def test_clear_limit(self, client: TestClient) -> None:
        client.post("/v1/spend", json={"action": "set", "window": "daily", "amount": 10})
        client.post("/v1/spend", json={"action": "clear", "window": "daily"})
        data = client.get("/v1/spend").json()
        assert "daily" not in data["limits"]

    def test_reset_session(self, client: TestClient) -> None:
        resp = client.post("/v1/spend", json={"action": "reset_session"})
        assert resp.status_code == 200
        assert resp.json()["session_reset"] is True

    def test_invalid_action(self, client: TestClient) -> None:
        resp = client.post("/v1/spend", json={"action": "explode"})
        assert resp.status_code == 400


class TestSessionsEndpoint:
    def test_sessions_empty(self, client: TestClient) -> None:
        resp = client.get("/v1/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestSpendControlIntegration:
    def test_spend_limit_blocks_request(self) -> None:
        """When spend limit is exhausted, chat completions returns 429."""
        session_store = SessionStore()
        sc = SpendControl(storage=InMemorySpendControlStorage())
        sc.set_limit("per_request", 0.0001)

        app = create_app(
            upstream="http://127.0.0.1:1/fake",
            session_store=session_store,
            spend_control=sc,
        )
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/v1/chat/completions", json={
            "model": "uncommon-route/auto",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 429
        assert "spend_limit_exceeded" in resp.json()["error"]["type"]
