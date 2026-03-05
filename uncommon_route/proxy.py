"""OpenAI-compatible proxy server for UncommonRoute.

Accepts /v1/chat/completions, runs route() for virtual model names
(uncommon-route/auto, eco, premium, free), replaces the model field,
and forwards to a configurable upstream OpenAI-compatible API.

Non-routing model names are passed through unchanged.

Integrations:
  - Session persistence: sticky model per session, three-strike escalation
  - Spend control: per-request / hourly / daily / session limits

Usage:
    from uncommon_route.proxy import create_app, serve
    serve(port=8403, upstream="http://127.0.0.1:11434/v1")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncGenerator

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from uncommon_route.router.api import route
from uncommon_route.router.classifier import classify
from uncommon_route.router.config import DEFAULT_CONFIG, DEFAULT_MODEL_PRICING
from uncommon_route.router.types import Tier
from uncommon_route.session import (
    SessionStore,
    derive_session_id,
    get_session_id,
    hash_request_content,
)
from uncommon_route.spend_control import SpendControl
from uncommon_route.providers import ProvidersConfig, load_providers

VERSION = "0.1.0"
DEFAULT_UPSTREAM = os.environ.get("UNCOMMON_ROUTE_UPSTREAM", "https://openrouter.ai/api/v1")
DEFAULT_PORT = int(os.environ.get("UNCOMMON_ROUTE_PORT", "8403"))
VIRTUAL_MODEL = "uncommon-route/auto"

VIRTUAL_MODELS = [
    {"id": VIRTUAL_MODEL, "object": "model", "owned_by": "uncommon-route"},
]

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
    return _http_client


def _extract_prompt(body: dict) -> tuple[str, str | None, int]:
    """Extract last user message, system prompt, and max_tokens from request body."""
    messages = body.get("messages", [])
    max_tokens: int = body.get("max_tokens", 4096)

    prompt = ""
    system_prompt: str | None = None

    for msg in reversed(messages):
        if msg.get("role") == "user" and not prompt:
            content = msg.get("content", "")
            prompt = content if isinstance(content, str) else str(content)
        if msg.get("role") == "system" and system_prompt is None:
            content = msg.get("content", "")
            system_prompt = content if isinstance(content, str) else str(content)

    return prompt, system_prompt, max_tokens


def _build_debug_response(prompt: str, system_prompt: str | None) -> dict:
    """Build a debug diagnostics response showing routing details."""
    result = classify(prompt, system_prompt)
    decision = route(prompt, system_prompt)

    tier_boundaries = DEFAULT_CONFIG.scoring.tier_boundaries
    lines = [
        "UncommonRoute Debug",
        "",
        f"Tier: {decision.tier.value} | Model: {decision.model}",
        f"Confidence: {decision.confidence:.2f} | Cost: ${decision.cost_estimate:.4f} | Savings: {decision.savings:.0%}",
        f"Reasoning: {decision.reasoning}",
        "",
        f"Scoring (raw: {result.score:.3f})",
        f"  Signals: {', '.join(result.signals)}",
        "",
        f"Tier Boundaries: SIMPLE <{tier_boundaries.simple_medium:.2f}"
        f" | MEDIUM <{tier_boundaries.medium_complex:.2f}"
        f" | COMPLEX <{tier_boundaries.complex_reasoning:.2f}"
        f" | REASONING >={tier_boundaries.complex_reasoning:.2f}",
    ]

    if decision.fallback_chain:
        lines.append("")
        lines.append("Fallback Chain (cost-sorted):")
        for fb in decision.fallback_chain:
            lines.append(f"  {fb.model}: ${fb.cost_estimate:.4f} (budget: {fb.suggested_output_budget})")

    return {
        "id": f"chatcmpl-debug-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "uncommon-route/debug",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "\n".join(lines)},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_upstream(
    upstream_url: str,
    body: dict,
    headers: dict[str, str],
) -> AsyncGenerator[bytes, None]:
    """Stream response from upstream, yielding raw bytes."""
    client = _get_client()
    async with client.stream(
        "POST",
        upstream_url,
        json=body,
        headers=headers,
    ) as resp:
        async for chunk in resp.aiter_bytes():
            yield chunk


def _resolve_session(
    request: Request,
    body: dict,
    session_store: SessionStore,
) -> str | None:
    """Resolve session ID from header or message content."""
    header_name = session_store.config.header_name
    raw_headers = {k: v for k, v in request.headers.items()}
    sid = get_session_id(raw_headers, header_name)
    if sid:
        return sid
    messages = body.get("messages", [])
    return derive_session_id(messages)


def _spend_error(result: Any) -> JSONResponse:
    """Build a 429 error response for spend control violations."""
    body: dict[str, Any] = {
        "error": {
            "message": result.reason or "Spending limit exceeded",
            "type": "spend_limit_exceeded",
            "code": "spend_limit_exceeded",
        }
    }
    if result.reset_in_s is not None:
        body["error"]["reset_in_seconds"] = result.reset_in_s
    return JSONResponse(body, status_code=429)


def create_app(
    upstream: str = DEFAULT_UPSTREAM,
    session_store: SessionStore | None = None,
    spend_control: SpendControl | None = None,
    providers_config: ProvidersConfig | None = None,
) -> Starlette:
    """Create the ASGI application wired to the given upstream base URL.

    Args:
        upstream: Base URL for the upstream OpenAI-compatible API.
        session_store: Optional SessionStore for sticky sessions.
        spend_control: Optional SpendControl for spending limits.
        providers_config: Optional BYOK provider config for user-keyed models.
    """
    _sessions = session_store or SessionStore()
    _spend = spend_control or SpendControl()
    _providers = providers_config or load_providers()

    upstream_chat = f"{upstream.rstrip('/')}/chat/completions"

    tier_configs_dict = {
        tier.value: {"primary": tc.primary, "fallback": tc.fallback}
        for tier, tc in DEFAULT_CONFIG.tiers.items()
    }

    async def handle_health(request: Request) -> JSONResponse:
        spend_status = _spend.status()
        return JSONResponse({
            "status": "ok",
            "router": "uncommon-route",
            "version": VERSION,
            "upstream": upstream,
            "sessions": _sessions.stats(),
            "spending": {
                "limits": {k: v for k, v in vars(spend_status.limits).items() if v is not None},
                "spent": spend_status.spent,
                "remaining": {k: v for k, v in spend_status.remaining.items() if v is not None},
                "calls": spend_status.calls,
            },
            "providers": {
                "count": len(_providers.providers),
                "names": _providers.provider_names(),
                "keyed_models": sorted(_providers.keyed_models()),
            },
        })

    async def handle_models(request: Request) -> JSONResponse:
        return JSONResponse({"object": "list", "data": VIRTUAL_MODELS})

    async def handle_spend(request: Request) -> JSONResponse:
        """GET /v1/spend — current spend status. POST /v1/spend — set limits."""
        if request.method == "GET":
            s = _spend.status()
            return JSONResponse({
                "limits": {k: v for k, v in vars(s.limits).items() if v is not None},
                "spent": s.spent,
                "remaining": {k: v for k, v in s.remaining.items() if v is not None},
                "calls": s.calls,
            })
        body = await request.json()
        action = body.get("action", "set")
        window = body.get("window")
        amount = body.get("amount")
        if action == "set" and window and amount is not None:
            _spend.set_limit(window, float(amount))
            return JSONResponse({"ok": True, "window": window, "amount": amount})
        if action == "clear" and window:
            _spend.clear_limit(window)
            return JSONResponse({"ok": True, "window": window, "cleared": True})
        if action == "reset_session":
            _spend.reset_session()
            return JSONResponse({"ok": True, "session_reset": True})
        return JSONResponse({"error": "Invalid action"}, status_code=400)

    async def handle_sessions(request: Request) -> JSONResponse:
        """GET /v1/sessions — list active sessions."""
        return JSONResponse(_sessions.stats())

    async def handle_chat_completions(request: Request) -> Response:
        body = await request.json()
        model = (body.get("model") or "").strip().lower()
        is_streaming = body.get("stream", False)

        is_virtual = model == VIRTUAL_MODEL

        if is_virtual:
            prompt, system_prompt, max_tokens = _extract_prompt(body)

            if prompt.startswith("/debug"):
                debug_prompt = prompt[len("/debug"):].strip() or "hello"
                debug_body = _build_debug_response(debug_prompt, system_prompt)
                return JSONResponse(debug_body)

            session_id = _resolve_session(request, body, _sessions)
            cached_session = _sessions.get(session_id) if session_id else None

            if cached_session and not cached_session.escalated:
                selected_model = cached_session.model
                tier_value = cached_session.tier
                reasoning = f"session-sticky ({session_id[:8]}...)"

                if session_id:
                    content_hash = hash_request_content(prompt)
                    should_escalate = _sessions.record_request_hash(session_id, content_hash)
                    if should_escalate:
                        result = _sessions.escalate(session_id, tier_configs_dict)
                        if result:
                            selected_model, tier_value = result
                            reasoning = f"escalated ({tier_value})"
            else:
                user_keyed = _providers.keyed_models() or None
                decision = route(prompt, system_prompt, max_tokens, user_keyed_models=user_keyed)
                selected_model = decision.model
                tier_value = decision.tier.value
                reasoning = decision.reasoning

                if session_id:
                    _sessions.set(session_id, selected_model, tier_value)

            check = _spend.check(0.001)
            if not check.allowed:
                return _spend_error(check)

            body["model"] = selected_model
        else:
            selected_model = model
            tier_value = ""
            reasoning = "passthrough"

        # BYOK: if user has a key for this model, route to their provider directly
        provider_entry = _providers.get_for_model(selected_model)
        if provider_entry and provider_entry.base_url:
            target_chat_url = f"{provider_entry.base_url.rstrip('/')}/chat/completions"
        else:
            target_chat_url = upstream_chat

        fwd_headers: dict[str, str] = {}
        for key in ("authorization", "content-type", "accept", "user-agent"):
            val = request.headers.get(key)
            if val:
                fwd_headers[key] = val
        if "content-type" not in fwd_headers:
            fwd_headers["content-type"] = "application/json"
        fwd_headers["user-agent"] = f"uncommon-route/{VERSION}"

        # BYOK: override auth header with user's API key
        if provider_entry:
            fwd_headers["authorization"] = f"Bearer {provider_entry.api_key}"
            # Strip provider prefix for direct API calls (e.g. "deepseek/deepseek-chat" → "deepseek-chat")
            raw_model = selected_model.split("/", 1)[-1] if "/" in selected_model else selected_model
            body["model"] = raw_model

        debug_headers: dict[str, str] = {}
        if is_virtual:
            debug_headers["x-uncommon-route-model"] = selected_model
            debug_headers["x-uncommon-route-tier"] = tier_value
            debug_headers["x-uncommon-route-reasoning"] = reasoning

        try:
            if is_streaming:
                async def sse_passthrough() -> AsyncGenerator[bytes, None]:
                    async for chunk in _stream_upstream(target_chat_url, body, fwd_headers):
                        yield chunk

                return StreamingResponse(
                    sse_passthrough(),
                    media_type="text/event-stream",
                    headers={
                        "cache-control": "no-cache",
                        "connection": "keep-alive",
                        **debug_headers,
                    },
                )

            client = _get_client()
            resp = await client.post(target_chat_url, json=body, headers=fwd_headers)

            if is_virtual:
                _spend.record(0.001, model=selected_model, action="chat")

            resp_headers = {
                "content-type": resp.headers.get("content-type", "application/json"),
                **debug_headers,
            }
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
            )
        except httpx.ConnectError:
            return JSONResponse(
                {"error": {"message": f"Upstream unreachable: {upstream_chat}", "type": "proxy_error"}},
                status_code=502,
                headers=debug_headers,
            )
        except httpx.TimeoutException:
            return JSONResponse(
                {"error": {"message": "Upstream request timed out", "type": "proxy_error"}},
                status_code=504,
                headers=debug_headers,
            )

    return Starlette(
        routes=[
            Route("/health", handle_health, methods=["GET"]),
            Route("/v1/models", handle_models, methods=["GET"]),
            Route("/v1/chat/completions", handle_chat_completions, methods=["POST"]),
            Route("/v1/spend", handle_spend, methods=["GET", "POST"]),
            Route("/v1/sessions", handle_sessions, methods=["GET"]),
        ],
    )


def serve(
    port: int = DEFAULT_PORT,
    host: str = "127.0.0.1",
    upstream: str = DEFAULT_UPSTREAM,
    session_store: SessionStore | None = None,
    spend_control: SpendControl | None = None,
) -> None:
    """Start the proxy server (blocking)."""
    import uvicorn

    app = create_app(
        upstream=upstream,
        session_store=session_store,
        spend_control=spend_control,
    )
    print(f"[UncommonRoute] Proxy listening on http://{host}:{port}")
    print(f"[UncommonRoute] Upstream: {upstream}")
    print(f"[UncommonRoute] Virtual model: {VIRTUAL_MODEL}")
    print(f"[UncommonRoute] Session persistence: enabled")
    print(f"[UncommonRoute] Spend control: enabled")
    uvicorn.run(app, host=host, port=port, log_level="info")
