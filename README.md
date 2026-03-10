<div align="center">

<h1>UncommonRoute</h1>

<p><strong>Don't route by habit. Route by difficulty.</strong></p>

<p>
If your agent sends every prompt to the same frontier model, you are probably overpaying.<br>
UncommonRoute is a local 4-tier LLM router — <strong>92.3% accuracy</strong>, <strong>0.5ms</strong>, <strong>67% cheaper than always-Opus</strong>.
</p>

<p>
<a href="#quick-start"><strong>Quick Start</strong></a> ·
<a href="#benchmarks"><strong>Benchmarks</strong></a> ·
<a href="#usage-modes"><strong>Supported Apps</strong></a> ·
<a href="https://commonstack.ai"><strong>Commonstack</strong></a>
</p>

<a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.11+-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>&nbsp;
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT"></a>&nbsp;
<img src="https://img.shields.io/badge/Tests-169_passing-16a34a?style=for-the-badge&logo=pytest&logoColor=white" alt="169 tests">&nbsp;
<a href="#usage-modes"><img src="https://img.shields.io/badge/Claude_Code-Ready-f97316?style=for-the-badge&logo=anthropic&logoColor=white" alt="Claude Code"></a>&nbsp;
<a href="#usage-modes"><img src="https://img.shields.io/badge/Codex-Ready-412991?style=for-the-badge&logo=openai&logoColor=white" alt="Codex"></a>&nbsp;
<a href="#usage-modes"><img src="https://img.shields.io/badge/Cursor-Compatible-007acc?style=for-the-badge&logo=visual-studio-code&logoColor=white" alt="Cursor"></a>&nbsp;
<a href="https://openclaw.ai"><img src="https://img.shields.io/badge/OpenClaw-Plugin-e11d48?style=for-the-badge" alt="OpenClaw"></a>&nbsp;
<a href="#benchmarks"><img src="https://img.shields.io/badge/Train_Your_Own-Router-8b5cf6?style=for-the-badge&logo=databricks&logoColor=white" alt="Train locally"></a>

<br><br>

<p>
Built by <a href="https://commonstack.ai"><strong>Commonstack</strong></a> — one API key for OpenAI, Anthropic, Google, DeepSeek, xAI, and more.
</p>

</div>

---

## Quick Navigation

[Quick Start](#quick-start) ·
[Supported Apps](#usage-modes) ·
[Benchmarks](#benchmarks) ·
[How It Works](#how-it-works) ·
[Dashboard](#dashboard) ·
[Configuration](#configuration) ·
[Models & Pricing](#models--pricing) ·
[Diagnostics](#diagnostics)

---

## Quick Start

Get from install to routed requests in about 30 seconds.

### 1. Install

```bash
pip install uncommon-route
```

Or use the one-line installer:

```bash
curl -fsSL https://anjieyang.github.io/uncommon-route/install | bash
```

### 2. Point it at your upstream

```bash
export UNCOMMON_ROUTE_UPSTREAM="https://api.commonstack.ai/v1"
export UNCOMMON_ROUTE_API_KEY="csk-..."
```

### 3. Start the router

```bash
uncommon-route serve
```

### 4. Prove it works

```bash
uncommon-route route "write a Python function that validates email addresses"
# Model: moonshot/kimi-k2.5  Tier: MEDIUM  Savings: ...

uncommon-route doctor
# Checks Python, upstream, API key, model discovery, integrations
```

### 5. Connect your client

Pick the client you already use:

| If you use | Do this |
|---|---|
| **CLI / Python SDK** | Already ready — use `uncommon-route route "hello"` |
| **Claude Code** | Run `uncommon-route setup claude-code` |
| **OpenAI Codex** | Run `uncommon-route setup codex` |
| **OpenAI SDK / Cursor** | Run `uncommon-route setup openai` |
| **OpenClaw** | Run `openclaw plugins install @anjieyang/uncommon-route` |

Each `setup` command prints the exact environment variables for your shell.

<details>
<summary>Manual setup reference</summary>

```bash
# 1. Configure upstream (any OpenAI-compatible API)
export UNCOMMON_ROUTE_UPSTREAM="https://api.commonstack.ai/v1"
export UNCOMMON_ROUTE_API_KEY="csk-..."

# 2. Start the proxy
uncommon-route serve

# 3. Check everything works
uncommon-route doctor
```

</details>

---

## Usage Modes

### 1. CLI

```bash
uncommon-route route "what is 2+2"
# Model: moonshot/kimi-k2.5  Tier: SIMPLE  Savings: 97%

uncommon-route route --json "design a distributed database"
# Full JSON with model, tier, confidence, cost, fallback chain

uncommon-route debug "explain quicksort"
# Per-dimension scoring breakdown (structural + keyword + unicode)

uncommon-route doctor
# Check Python version, upstream, API key, model discovery, BYOK keys

uncommon-route serve --daemon     # Run proxy in background
uncommon-route stop               # Stop background proxy
uncommon-route logs --follow      # Tail background proxy log
```

### 2. Python SDK

```python
from uncommon_route import route, classify

decision = route("explain the Byzantine Generals Problem")
print(decision.model)       # google/gemini-3.1-pro
print(decision.tier)        # COMPLEX
print(decision.confidence)  # 0.87
print(decision.savings)     # 0.76

# Classification only (no model selection)
result = classify("hello")
print(result.tier)          # SIMPLE
print(result.signals)       # ['short_prompt', 'greeting_pattern']
```

### 3. HTTP Proxy (OpenAI-compatible)

```bash
uncommon-route serve --port 8403
```

Works with any OpenAI SDK client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8403/v1",
    api_key="your-upstream-key",
)

response = client.chat.completions.create(
    model="uncommon-route/auto",   # smart routing
    messages=[{"role": "user", "content": "hello"}],
)
```

Available virtual routing profiles:

| Model | Strategy |
|---|---|
| `uncommon-route/auto` | Balanced default |
| `uncommon-route/eco` | Cheapest capable model first |
| `uncommon-route/premium` | Quality-first routing |
| `uncommon-route/free` | Free-first, then cheapest capable fallback |
| `uncommon-route/agentic` | Tool-heavy workflow routing |

| Endpoint | Method | Format | Description |
|---|---|---|---|
| `/v1/chat/completions` | POST | OpenAI | Chat with smart routing |
| `/v1/messages` | POST | Anthropic | Chat with smart routing (auto-routes all requests) |
| `/v1/models` | GET | OpenAI | Available models |
| `/v1/models/mapping` | GET | — | Model name mapping (internal → upstream) |
| `/v1/spend` | GET/POST | — | Spend control |
| `/v1/sessions` | GET | — | Active sessions |
| `/v1/stats` | GET/POST | — | Routing analytics |
| `/v1/selector` | GET/POST | — | Selector state + routing preview |
| `/v1/routing-config` | GET/POST | — | Live profile/tier model overrides |
| `/v1/artifacts` | GET | — | Stored large tool outputs |
| `/v1/artifacts/{id}` | GET | — | Retrieve a stored artifact |
| `/v1/feedback` | GET/POST | — | Online learning feedback |
| `/health` | GET | — | Health + status |
| `/dashboard` | GET | — | Web management UI |

### 4. Claude Code

```bash
uncommon-route setup claude-code   # prints env vars for your shell
```

Claude Code connects via the Anthropic Messages API (`/v1/messages`). All requests are automatically smart-routed — the proxy converts between Anthropic and OpenAI formats transparently.

When the selected model is an Anthropic-family model and the upstream is Commonstack or Anthropic directly, UncommonRoute now preserves the request on the native Anthropic `/v1/messages` path so `cache_control` breakpoints and Anthropic cache usage survive end to end.

```bash
# Terminal 1
uncommon-route serve

# Terminal 2
export ANTHROPIC_BASE_URL="http://localhost:8403"
export ANTHROPIC_API_KEY="not-needed"
claude
```

### 5. OpenAI Codex

```bash
uncommon-route setup codex         # prints env vars for your shell
```

Codex connects via the OpenAI Chat Completions API (`/v1/chat/completions`). Use `model="uncommon-route/auto"` for smart routing.

The same Anthropic-native transport is also used behind `/v1/chat/completions` when routing lands on an Anthropic model, so OpenAI-compatible clients still get normal chat-completions JSON/SSE while the upstream request uses Anthropic-native caching semantics.

```bash
# Terminal 1
uncommon-route serve

# Terminal 2
export OPENAI_BASE_URL="http://localhost:8403/v1"
export OPENAI_API_KEY="not-needed"
codex
```

### 6. OpenClaw Plugin

```bash
openclaw plugins install @anjieyang/uncommon-route
```

The plugin auto-installs Python dependencies, starts the proxy, and registers everything. Available commands in OpenClaw:

| Command | Description |
|---|---|
| `/route <prompt>` | Preview routing decision |
| `/spend status` | View spending limits |
| `/spend set hourly 5.00` | Set hourly limit |
| `/sessions` | View active sessions |

---

## Dashboard

UncommonRoute includes a built-in web dashboard for monitoring and management. After starting the proxy, visit:

```
http://127.0.0.1:8403/dashboard/
```

| Tab | What it shows |
|---|---|
| **Overview** | KPI cards (requests, savings, latency, sessions, cost), tier distribution chart, top models, transport/cache usage summary |
| **Routing** | Breakdown by tier, model, routing method, upstream transport, cache mode/family, cache breakpoints |
| **Config** | Edit primary/fallback models for each profile and tier, with live save/reset |
| **Models** | Upstream model discovery status, full internal → resolved mapping table |
| **Sessions** | Active sessions with model, tier, request count, age |
| **Spend** | Current limits, set/clear limits, spending history |

The dashboard handles edge cases gracefully: a loading spinner while connecting, a guided setup card when no requests have been made yet, and clear error states when the proxy is unreachable or the upstream is not configured.

Data auto-refreshes every 5 seconds. Built with React + [Tremor](https://tremor.so) + Tailwind CSS.

`GET /v1/stats` also exposes the same transport/cache observability data programmatically via `by_transport`, `by_cache_mode`, `by_cache_family`, `total_cache_breakpoints`, and the cost delta fields (`total_baseline_cost`, `total_actual_cost`, `total_savings_absolute`, `total_cache_savings`, `total_compaction_savings`). The baseline is fully uncached `anthropic/claude-opus-4.6` list pricing on the full request context.

Routing defaults are now editable at runtime:

```bash
uncommon-route config show
uncommon-route config set-tier auto SIMPLE moonshot/kimi-k2.5 --fallback google/gemini-2.5-flash-lite,deepseek/deepseek-chat
uncommon-route config set-tier premium COMPLEX anthropic/claude-opus-4.6 --fallback anthropic/claude-sonnet-4.6 --mode hard-pin
uncommon-route config reset-tier auto SIMPLE
```

Use `--mode hard-pin` when you want the router to pin a tier to the configured `primary` and only fall back on upstream model errors. `adaptive` keeps the current chooser/bandit behavior across the whole candidate set.

For live updates against a running proxy, use the dashboard Config tab or `POST /v1/routing-config`.

---

## Model Mapping

Different upstream providers use different model IDs for the same model. For example, UncommonRoute internally uses `moonshot/kimi-k2.5`, but Commonstack expects `moonshotai/kimi-k2.5`.

UncommonRoute handles this automatically:

1. **On startup**, the proxy fetches `/v1/models` from the upstream to discover available models
2. **Fuzzy matching** maps internal names to upstream names — handles provider prefix differences (`xai/` ↔ `x-ai/`), version format changes (`4.6` ↔ `4-6`), and suffix additions (`-preview`)
3. **Gateway detection** — gateways (Commonstack) receive the full `provider/model` format; direct provider APIs receive only the model name
4. **Fallback retry** — if the upstream rejects a model, the proxy automatically tries the next model in the fallback chain

Check the mapping status:

```bash
uncommon-route doctor           # Shows model discovery status
curl localhost:8403/v1/models/mapping   # Full mapping table as JSON
```

---

## How It Works

UncommonRoute uses a **cascade classifier** with three levels:

```
Input Prompt
     │
     ▼
┌─────────────────────┐
│ 1. Trivial Override  │  greeting / empty / very long → instant decision
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 2. Learned Model    │  Averaged Perceptron on 39 features
│    (356µs avg)      │  12 structural + 15 unicode + 12 keyword
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 3. Rule Fallback    │  hand-tuned weights when model unavailable
└─────────┬───────────┘
          │
          ▼
    Tier + Model + Cost
```

### Feature Groups (39 total)

**Structural (12):** normalized_length, enumeration_density, sentence_count, code_markers, math_symbols, nesting_depth, vocabulary_diversity, avg_word_length, alphabetic_ratio, functional_intent, unique_concept_density, requirement_phrases

**Unicode (15):** basic_latin, latin_ext, cyrillic, arabic, devanagari, thai, hangul_jamo, cjk_unified, hiragana, katakana, hangul_syllables, punctuation, digits, symbols_math

**Keyword (12):** code_presence, reasoning_markers, technical_terms, creative_markers, simple_indicators, imperative_verbs, constraint_count, output_format, domain_specificity, agentic_task, analytical_verbs, multi_step_patterns

---

## Routing Profiles

Profiles choose *which tier table* to use before model selection:

| Profile | Best For | SIMPLE | MEDIUM | COMPLEX | REASONING |
|---|---|---|---|---|---|
| `auto` | General default | kimi-k2.5 | kimi-k2.5 | gemini-3.1-pro | grok-4.1-fast-reasoning |
| `eco` | Cost minimization | gpt-oss-120b | gemini-2.5-flash-lite | gemini-2.5-flash-lite | grok-4.1-fast-reasoning |
| `premium` | Quality-first routing | gpt-4o | gpt-5.2-codex | claude-opus-4.6 | claude-sonnet-4.6 |
| `free` | Free-first routing | gpt-oss-120b | gpt-oss-120b | gpt-oss-120b | gpt-oss-120b |
| `agentic` | Tool-heavy workflows | kimi-k2.5 | kimi-k2.5 | claude-sonnet-4.6 | claude-sonnet-4.6 |

`free` is best-effort free, not a hard guarantee. If the free model lacks required capabilities (for example tool calling), UncommonRoute falls back to the cheapest capable model instead of forcing an obviously bad choice.

Within each tier, UncommonRoute now uses an adaptive candidate chooser instead of always taking the configured primary model. Each profile applies different weights to:

- curated candidate order
- predicted token cost
- observed latency / throughput
- observed reliability
- explicit user feedback
- cache affinity and effective cached-input cost
- BYOK / free / local biases

That means `eco`, `auto`, `premium`, `free`, and `agentic` can all prefer different models even when they land on the same tier.

On top of those profile weights, UncommonRoute now applies a lightweight bandit scheduler. The current weighted score remains the base policy, then the router adds:

- learned reward from observed success / latency / throughput
- learned reward from real cache-hit efficiency and cached-input savings
- a bounded exploration bonus for under-sampled candidates
- guardrails that disable exploration for low-reliability or overly expensive candidates

Bandit exploration is bucketed by `profile + tier`, so low-risk paths like `SIMPLE` and `MEDIUM` can adapt quickly without destabilizing `REASONING` traffic.

You can inspect the live selector state with `GET /v1/selector`, including current profile weights, bandit config, promoted/demoted models, and recent feedback-driven changes. `POST /v1/selector` accepts either a normal chat-completions-shaped payload or a lightweight `{ "profile": "auto", "prompt": "..." }` body and returns the full candidate score breakdown for that request. The same selector summary is also exposed via `/health` and `/v1/stats`.

## Routing Tiers

The router classifies each prompt and selects the **cheapest model that can handle it**. Default primary models are chosen for cost efficiency — all models (including OpenAI, Claude) are accessible through the upstream provider.

| Tier | When | Default Primary | Fallback Chain | Example |
|---|---|---|---|---|
| **SIMPLE** | Greetings, lookups, translations | moonshot/kimi-k2.5 | gemini-2.5-flash-lite, deepseek-chat | "what is 2+2" |
| **MEDIUM** | Code tasks, explanations, summaries | moonshot/kimi-k2.5 | deepseek-chat, gemini-2.5-flash-lite | "explain quicksort" |
| **COMPLEX** | Multi-requirement system design | google/gemini-3.1-pro | gemini-2.5-pro, gpt-5.2, claude-sonnet-4.6 | "design a distributed DB with 5 requirements..." |
| **REASONING** | Formal proofs, mathematical derivations | xai/grok-4-1-fast-reasoning | deepseek-reasoner, o4-mini, o3 | "prove sqrt(2) is irrational" |

> **Note:** OpenAI and Claude models appear in COMPLEX/REASONING fallback chains. To make them the preferred choice across all tiers, use [BYOK provider configuration](#bring-your-own-key-byok).

---

## Step-Aware Routing

In agentic workflows (OpenClaw, LangChain, etc.), different steps within a single task need different model capabilities. UncommonRoute detects the step type from the request body and routes accordingly:

| Step Type | Detection | Routing Behavior |
|---|---|---|
| **Tool-result followup** | Last message `role: "tool"` | Classifier decides freely — allows cheap model for processing tool output |
| **Tool selection** | `tools` present + last message from user | Normal session logic |
| **General** | No agentic signals | Normal session logic |

**Before (blind session pin):** Agent session pinned to $25/M model for all 200 requests — including "I read this file" steps.

**After (step-aware):** Tool-result steps automatically use $0.40-2.50/M models. Only steps that need reasoning use expensive models.

The step type is visible in the `x-uncommon-route-step` response header.

When a request includes `tools` or image content, UncommonRoute now filters out models that do not advertise the required capability before building the fallback chain. Fallback order follows the selected profile instead of globally sorting everything by cost.

When the upstream returns runtime usage telemetry such as `ttft`, `tps`, `cache_read_input_tokens`, `cache_creation_input_tokens`, or `prompt_tokens_details.cached_tokens` (for example through Commonstack's OpenAI-compatible responses), UncommonRoute feeds those observations back into candidate scoring for future requests. Cached reads are now priced separately when the upstream exposes them, so the selector can learn that some models become much cheaper after the prefix stabilizes.

For `tool-selection` steps, the router now applies a cache-first tier cap before model choice. This keeps the "pick the next tool" turn on a cheaper tool-capable model and leaves the expensive reasoning model for the follow-up step that actually consumes the tool result.

## Composition Pipeline

Large `role: "tool"` payloads are no longer forwarded verbatim by default. UncommonRoute now applies a composition pipeline before forwarding:

- Safe compaction for long text / JSON payloads
- Artifact offload for very large tool results
- Semantic side-channel summaries for large tool outputs
- Checkpoint summaries when the conversation history grows too large
- Explicit artifact rehydration when the user references `artifact://...`

Artifacts are stored locally under `~/.uncommon-route/artifacts/` and exposed via `/v1/artifacts`.

Useful response headers:

- `x-uncommon-route-input-before`
- `x-uncommon-route-input-after`
- `x-uncommon-route-artifacts`
- `x-uncommon-route-semantic-calls`
- `x-uncommon-route-semantic-fallbacks`
- `x-uncommon-route-checkpoints`
- `x-uncommon-route-rehydrated`

The side-channel models are configured independently from routing profiles. By default, tool summaries, checkpoints, and rehydration each have their own primary model, fallback chain, token budget, and quality gate. You can override the full composition policy with:

```bash
export UNCOMMON_ROUTE_COMPOSITION_CONFIG=/path/to/composition.json
# or
export UNCOMMON_ROUTE_COMPOSITION_CONFIG_JSON='{"sidechannel":{"tool_summary":{"primary":"openai/gpt-4o-mini"}}}'

uncommon-route serve --composition-config /path/to/composition.json
```

The active composition policy is visible via `/health` under `composition.policy`.

Checkpointing is now cache-aware for agentic workflows:

- `tool-selection` turns skip checkpointing entirely
- active tool windows delay checkpoint creation
- agentic sessions use a higher checkpoint token threshold and preserve a longer raw tail

That keeps Claude Code / OpenClaw style sessions append-only for longer, which improves prompt-cache hit rates instead of rewriting the middle of the transcript too early.

---

## Session Management

Sessions prevent unnecessary model switching mid-task while allowing cost optimization:

- **Always re-route** — every request gets a fresh classification based on content
- **Only upgrade, never downgrade** — if the classifier says COMPLEX and the session is MEDIUM, upgrade; if it says SIMPLE, hold the session model
- **Lightweight exception** — tool-result steps bypass session hold and use the classifier's recommendation directly
- **30-minute timeout** — sessions auto-expire after inactivity
- **Three-strike escalation** — 3 identical requests → auto-upgrade to next tier (skipped for tool-result steps)

```python
# Sessions work via header
headers = {"X-Session-ID": "my-task-123"}

# OpenClaw's x-openclaw-session-key also supported
# Or auto-derived from first user message
```

---

## Spend Control

Set spending limits to prevent runaway costs:

```bash
uncommon-route spend set per_request 0.10   # max $0.10 per call
uncommon-route spend set hourly 5.00        # max $5/hour
uncommon-route spend set daily 20.00        # max $20/day
uncommon-route spend set session 3.00       # max $3/session
uncommon-route spend status                 # view current spending
uncommon-route spend history                # recent records
```

When a limit is hit, the proxy returns HTTP 429 with `reset_in_seconds`.

Data persists at `~/.uncommon-route/spending.json`.

---

## Diagnostics

### Startup Banner

`uncommon-route serve` shows a structured banner with upstream, proxy URL, and dashboard link. If no upstream is configured, it prints the exact setup commands instead.

### Real-Time Routing Log

Every routed request prints a one-line summary to the proxy terminal:

```
[route] SIMPLE → moonshot/kimi-k2.5  $0.0003  (356µs  cascade  session:a3f2c1b8)
[route] COMPLEX → google/gemini-3.1-pro  $0.0142  (412µs  cascade  stream  [anthropic])
```

### Health Check

```bash
uncommon-route doctor
```

Checks Python version, upstream connectivity, API key validity, model discovery, BYOK provider status, Claude Code integration, and daemon state. Run this first when something isn't working.

### Background Mode

```bash
uncommon-route serve --daemon     # Start in background, logs to ~/.uncommon-route/serve.log
uncommon-route stop               # Stop the background instance
uncommon-route logs               # Show last 50 lines of log
uncommon-route logs --follow      # Stream logs in real-time (Ctrl+C to stop)
uncommon-route logs --limit 100   # Show last 100 lines
```

PID file: `~/.uncommon-route/serve.pid`. Log file: `~/.uncommon-route/serve.log`.

---

## Models & Pricing

The router selects models by tier to minimize cost. Availability depends on your upstream provider — multi-provider gateways (Commonstack) expose all of these; direct provider APIs expose only their own models.

| Model | Input ($/1M) | Output ($/1M) | Role |
|---|---|---|---|
| nvidia/gpt-oss-120b | $0.00 | $0.00 | SIMPLE fallback |
| google/gemini-2.5-flash-lite | $0.10 | $0.40 | SIMPLE/MEDIUM fallback |
| deepseek/deepseek-chat | $0.28 | $0.42 | MEDIUM fallback |
| xai/grok-4-1-fast-reasoning | $0.20 | $0.50 | REASONING primary |
| moonshot/kimi-k2.5 | $0.60 | $3.00 | SIMPLE/MEDIUM primary |
| google/gemini-3.1-pro | $2.00 | $12.00 | COMPLEX primary |
| openai/gpt-5.2 | $1.75 | $14.00 | COMPLEX fallback |
| anthropic/claude-sonnet-4.6 | $3.00 | $15.00 | COMPLEX fallback |

Baseline comparison: anthropic/claude-opus-4.6 at $5.00/$25.00 per 1M tokens.

> **Why these defaults?** The primary models for SIMPLE/MEDIUM tiers (kimi-k2.5, gemini-flash-lite) are 5–37× cheaper than OpenAI/Claude per output token. For most prompts classified as simple or medium, these models produce equivalent results at a fraction of the cost. Complex prompts still route to frontier models (gemini-3.1-pro, with gpt-5.2 and claude-sonnet-4.6 in the fallback chain).

---

## Configuration

### Upstream Provider

UncommonRoute is a **routing layer only** — it does not host models. It forwards requests to an upstream OpenAI-compatible API that you configure.

```bash
# OpenAI direct
export UNCOMMON_ROUTE_UPSTREAM="https://api.openai.com/v1"
export UNCOMMON_ROUTE_API_KEY="sk-..."

# Commonstack (multi-provider gateway)
export UNCOMMON_ROUTE_UPSTREAM="https://api.commonstack.ai/v1"
export UNCOMMON_ROUTE_API_KEY="csk-..."

# Local (Ollama, vLLM, etc.) — no key needed
export UNCOMMON_ROUTE_UPSTREAM="http://127.0.0.1:11434/v1"
```

> **Tip:** Multi-provider gateways like [Commonstack](https://commonstack.ai) work well with UncommonRoute because they expose all models (OpenAI, Claude, Gemini, DeepSeek, etc.) behind a single API key — the router can select across providers without extra configuration.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `UNCOMMON_ROUTE_UPSTREAM` | — | Upstream OpenAI-compatible API URL (required for proxy) |
| `UNCOMMON_ROUTE_API_KEY` | — | API key for the upstream provider |
| `UNCOMMON_ROUTE_PORT` | `8403` | Proxy port |
| `UNCOMMON_ROUTE_DISABLED` | `false` | Disable routing (passthrough) |

### Bring Your Own Key (BYOK)

If you have API keys for specific providers and want the router to **prefer those models**, register them with the BYOK system:

```bash
uncommon-route provider add openai sk-your-openai-key
# Key verified: 47 models available ← auto-validates on add

uncommon-route provider add anthropic sk-ant-your-key
uncommon-route provider list
```

When a BYOK provider is registered, the router will prefer your keyed models whenever they appear in a tier's candidate list. For example, adding an OpenAI key means COMPLEX-tier prompts will prefer `openai/gpt-5.2` over the default `google/gemini-3.1-pro`.

Keys are automatically verified on add. If verification fails, the key is still saved but a warning is shown. Use `uncommon-route doctor` to re-check all provider connections.

Provider config is stored at `~/.uncommon-route/providers.json`.

### OpenClaw Plugin Config

```yaml
plugins:
  entries:
    "@anjieyang/uncommon-route":
      port: 8403
      upstream: "https://api.commonstack.ai/v1"  # or any OpenAI-compatible API
      spendLimits:
        hourly: 5.00
        daily: 20.00
```

---

## Benchmarks

There are two benchmark questions that matter:

1. **Does the router classify prompt complexity correctly on unseen data?**
2. **Does that classification actually reduce spend in a real coding session?**

### Held-Out Routing Benchmark (`router-bench`)

Evaluated on **763 hand-written prompts**, never used for training, across **15 languages** and **35 categories**.

| Metric | UncommonRoute | ClawRouter | NotDiamond (cost) |
|---|---|---|---|
| **Accuracy** | **92.3%** | 52.6% | 46.1% |
| **Weighted F1** | **92.3%** | 47.0% | 38.0% |
| **Latency / request** | **0.5ms** | 0.6ms | 37.6ms |
| **MEDIUM F1** | **88.7%** | 43.6% | 6.2% |
| **REASONING F1** | **97.8%** | 61.7% | 0.0% |

Why this matters: most routers can roughly tell "cheap" from "expensive". The money is won or lost in the middle. UncommonRoute is strong on the **MEDIUM** tier, which is exactly where coding assistants spend most of their time.

### Real Cost Simulation

Simulated on a realistic **131-request agent coding session** and compared against always sending every request to `anthropic/claude-opus-4.6`.

| Metric | Always Opus | UncommonRoute |
|---|---|---|
| **Total cost** | $1.7529 | **$0.5801** |
| **Cost saved** | — | **67%** |
| **Quality retained** | 100% | **93.5%** |
| **Routing accuracy** | — | **90.8%** |

This is the practical pitch in one line: **keep the hard prompts smart, route the easy and medium prompts cheaper, and cut most of the waste.**

### Local Training

The router is not a black box SaaS. You can retrain the local classifier on your own data.

| Metric | Value |
|---|---|
| **Training set used in repo** | 1,904 prompts |
| **Local retraining time** | ~26 seconds |
| **Training accuracy** | 98.6% |
| **Model type** | Averaged Perceptron |
| **Feature family** | 39 features (structural + unicode + keyword) |

Run the benchmark suite yourself:

```bash
cd ../router-bench && python -m router_bench.run
```

Retrain the local classifier yourself:

```bash
python - <<'PY'
from uncommon_route.router.classifier import train_and_save_model
train_and_save_model("bench/data/train.jsonl")
PY
```

---

## Project Structure

```
├── uncommon_route/           # Core package
│   ├── router/               # Cascade classifier + model selection
│   │   ├── classifier.py     # Three-level cascade
│   │   ├── learned.py        # Averaged Perceptron (ScriptAgnosticClassifier)
│   │   ├── structural.py     # 12 structural + 15 unicode features
│   │   ├── keywords.py       # 12 keyword features
│   │   ├── selector.py       # Tier → model + fallback chain
│   │   └── model.json        # Trained weights
│   ├── proxy.py              # ASGI proxy (OpenAI + Anthropic endpoints)
│   ├── anthropic_compat.py   # Anthropic ↔ OpenAI format conversion
│   ├── model_map.py          # Dynamic upstream model discovery + fuzzy matching
│   ├── session.py            # Session persistence + escalation
│   ├── spend_control.py      # Time-windowed spending limits
│   ├── providers.py          # BYOK provider management (with key verification)
│   ├── openclaw.py           # OpenClaw config integration
│   ├── cli.py                # CLI entry point (route/serve/setup/doctor/logs)
│   └── static/               # Built dashboard assets (React + Tremor)
├── frontend/dashboard/       # Dashboard source (Vite + React + TypeScript)
├── openclaw-plugin/          # JS bridge for OpenClaw
├── tests/                    # 169 tests (unit + integration + E2E)
├── bench/                    # Benchmarking suite + datasets
├── scripts/install.sh        # One-line installer
└── pyproject.toml            # PyPI-ready packaging
```

---

## Development

```bash
git clone https://github.com/anjieyang/UncommonRoute.git
cd UncommonRoute
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">
<sub>Built by <a href="https://github.com/anjieyang">Anjie Yang</a></sub>
</div>
