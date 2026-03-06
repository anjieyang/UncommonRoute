"""Anthropic Messages API ↔ OpenAI Chat Completions format conversion.

Converts between the two API formats so the router can accept Anthropic
Messages requests (``POST /v1/messages``) while forwarding to an
OpenAI-compatible upstream.

Key differences handled:
  - ``system`` as top-level param vs. system message in ``messages``
  - Content blocks (``[{"type":"text","text":"..."}]``) vs. flat strings
  - Tool calling format (``input_schema`` vs. ``function.parameters``)
  - SSE event format (typed events vs. ``data:`` lines)
"""

from __future__ import annotations

import json
import uuid
from typing import Any


# ---------------------------------------------------------------------------
# Finish-reason / stop-reason mapping
# ---------------------------------------------------------------------------

_FINISH_TO_STOP: dict[str, str] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "end_turn",
}

_STATUS_TO_ERROR_TYPE: dict[int, str] = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "api_error",
    503: "overloaded_error",
    504: "api_error",
}


# ---------------------------------------------------------------------------
# Request conversion: Anthropic → OpenAI
# ---------------------------------------------------------------------------

def _flatten_content_blocks(blocks: list[dict[str, Any]]) -> str:
    """Join text blocks into a single string."""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "\n".join(parts) if parts else ""


def anthropic_to_openai_request(body: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic Messages request body to OpenAI Chat Completions."""
    out: dict[str, Any] = {}

    out["model"] = body.get("model", "")
    out["max_tokens"] = body.get("max_tokens", 4096)

    messages: list[dict[str, Any]] = []

    # System prompt → system message
    system = body.get("system")
    if system:
        if isinstance(system, str):
            messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = _flatten_content_blocks(system)
            if text:
                messages.append({"role": "system", "content": text})

    for msg in body.get("messages", []):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            _convert_user_message(content, messages)
        elif role == "assistant":
            _convert_assistant_message(content, messages)

    out["messages"] = messages

    if "stream" in body:
        out["stream"] = body["stream"]
    if "temperature" in body:
        out["temperature"] = body["temperature"]
    if "top_p" in body:
        out["top_p"] = body["top_p"]
    if "stop_sequences" in body:
        out["stop"] = body["stop_sequences"]

    # Tools
    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

    # tool_choice
    tc = body.get("tool_choice")
    if tc is not None:
        out["tool_choice"] = _convert_tool_choice(tc)

    return out


def _convert_user_message(
    content: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> None:
    if isinstance(content, str):
        messages.append({"role": "user", "content": content})
        return

    text_parts: list[str] = []
    tool_results: list[dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_result":
            tool_results.append(block)

    if text_parts:
        messages.append({"role": "user", "content": "\n".join(text_parts)})

    for tr in tool_results:
        tr_content = tr.get("content", "")
        if isinstance(tr_content, list):
            tr_content = _flatten_content_blocks(tr_content)
        messages.append({
            "role": "tool",
            "tool_call_id": tr.get("tool_use_id", ""),
            "content": str(tr_content),
        })


def _convert_assistant_message(
    content: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> None:
    if isinstance(content, str):
        messages.append({"role": "assistant", "content": content})
        return

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })

    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    messages.append(assistant_msg)


def _convert_tool_choice(tc: str | dict[str, Any]) -> str | dict[str, Any]:
    if isinstance(tc, str):
        return {"auto": "auto", "any": "required", "none": "none"}.get(tc, "auto")
    tc_type = tc.get("type", "")
    if tc_type == "auto":
        return "auto"
    if tc_type == "any":
        return "required"
    if tc_type == "tool":
        return {"type": "function", "function": {"name": tc.get("name", "")}}
    return "auto"


# ---------------------------------------------------------------------------
# Response conversion: OpenAI → Anthropic
# ---------------------------------------------------------------------------

def openai_to_anthropic_response(
    data: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    """Convert an OpenAI Chat Completions response to Anthropic Messages."""
    choice = data["choices"][0] if data.get("choices") else {}
    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason", "stop")

    content_blocks: list[dict[str, Any]] = []

    text = message.get("content")
    if text:
        content_blocks.append({"type": "text", "text": text})

    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        try:
            input_data = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            input_data = {}
        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "input": input_data,
        })

    usage = data.get("usage", {})

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": _FINISH_TO_STOP.get(finish_reason, "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# Error conversion
# ---------------------------------------------------------------------------

def anthropic_error_response(status_code: int, message: str) -> dict[str, Any]:
    """Build an Anthropic-format error body."""
    return {
        "type": "error",
        "error": {
            "type": _STATUS_TO_ERROR_TYPE.get(status_code, "api_error"),
            "message": message,
        },
    }


# ---------------------------------------------------------------------------
# Streaming conversion: OpenAI SSE → Anthropic SSE
# ---------------------------------------------------------------------------

class OpenAIToAnthropicStreamConverter:
    """Stateful converter that parses OpenAI SSE chunks and yields Anthropic SSE events.

    Feed raw bytes from the upstream with :meth:`feed`; it returns a list of
    ready-to-send ``bytes`` chunks (each a complete SSE event).  Call
    :meth:`finish` after the upstream closes to flush any pending events.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._message_id = f"msg_{uuid.uuid4().hex[:24]}"
        self._message_started = False
        self._block_index = -1
        self._block_type: str | None = None
        self._output_tokens = 0
        self._buffer = ""
        self._finished = False

    # -- public API ---------------------------------------------------------

    def feed(self, raw: bytes) -> list[bytes]:
        """Process a raw byte chunk from upstream; return Anthropic SSE events."""
        events: list[bytes] = []
        self._buffer += raw.decode("utf-8", errors="replace")

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            if line == "data: [DONE]":
                events.extend(self._finalize())
                continue
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            events.extend(self._on_chunk(data))
        return events

    def finish(self) -> list[bytes]:
        """Flush remaining events (call after upstream stream ends)."""
        if not self._finished:
            return self._finalize()
        return []

    # -- SSE helpers --------------------------------------------------------

    @staticmethod
    def _sse(event_type: str, data: dict[str, Any]) -> bytes:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode()

    # -- event emitters -----------------------------------------------------

    def _emit_message_start(self) -> bytes:
        self._message_started = True
        return self._sse("message_start", {
            "type": "message_start",
            "message": {
                "id": self._message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": self._model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            },
        })

    def _start_block(self, btype: str, **kw: Any) -> bytes:
        self._block_index += 1
        self._block_type = btype
        if btype == "text":
            block: dict[str, Any] = {"type": "text", "text": ""}
        elif btype == "tool_use":
            block = {"type": "tool_use", "id": kw.get("id", ""), "name": kw.get("name", ""), "input": {}}
        else:
            block = {"type": btype}
        return self._sse("content_block_start", {
            "type": "content_block_start",
            "index": self._block_index,
            "content_block": block,
        })

    def _block_delta(self, delta: dict[str, Any]) -> bytes:
        return self._sse("content_block_delta", {
            "type": "content_block_delta",
            "index": self._block_index,
            "delta": delta,
        })

    def _stop_block(self) -> bytes:
        ev = self._sse("content_block_stop", {
            "type": "content_block_stop",
            "index": self._block_index,
        })
        self._block_type = None
        return ev

    # -- chunk processing ---------------------------------------------------

    def _on_chunk(self, data: dict[str, Any]) -> list[bytes]:
        events: list[bytes] = []

        if not self._message_started:
            events.append(self._emit_message_start())
            events.append(self._sse("ping", {"type": "ping"}))

        # Capture usage from stream (some providers include it)
        usage = data.get("usage")
        if usage:
            self._output_tokens = max(
                self._output_tokens,
                usage.get("completion_tokens", 0),
            )

        choices = data.get("choices", [])
        if not choices:
            return events

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason")

        # Text content
        content = delta.get("content")
        if content is not None and content != "":
            if self._block_type != "text":
                if self._block_type is not None:
                    events.append(self._stop_block())
                events.append(self._start_block("text"))
            events.append(self._block_delta({"type": "text_delta", "text": content}))

        # Tool calls
        for tc in delta.get("tool_calls", []):
            tc_id = tc.get("id")
            tc_fn = tc.get("function", {})
            tc_name = tc_fn.get("name")
            tc_args = tc_fn.get("arguments", "")

            if tc_id:
                if self._block_type is not None:
                    events.append(self._stop_block())
                events.append(self._start_block("tool_use", id=tc_id, name=tc_name or ""))

            if tc_args:
                events.append(self._block_delta({
                    "type": "input_json_delta",
                    "partial_json": tc_args,
                }))

        if finish_reason:
            events.extend(self._finalize(finish_reason))

        return events

    def _finalize(self, finish_reason: str | None = None) -> list[bytes]:
        if self._finished:
            return []
        self._finished = True

        events: list[bytes] = []

        if not self._message_started:
            events.append(self._emit_message_start())

        if self._block_type is not None:
            events.append(self._stop_block())

        stop = _FINISH_TO_STOP.get(finish_reason or "stop", "end_turn")
        events.append(self._sse("message_delta", {
            "type": "message_delta",
            "delta": {"stop_reason": stop, "stop_sequence": None},
            "usage": {"output_tokens": self._output_tokens},
        }))
        events.append(self._sse("message_stop", {"type": "message_stop"}))
        return events
