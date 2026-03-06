# @anjieyang/uncommon-route

**OpenClaw plugin for [UncommonRoute](https://github.com/anjieyang/UncommonRoute) — SOTA LLM Router**

98% accuracy, <1ms local routing, OpenAI + Anthropic compatible.

## Install

```bash
openclaw plugins install @anjieyang/uncommon-route
openclaw gateway restart
```

That's it. The plugin auto-installs the Python package, starts the proxy, and registers everything.

## What It Does

Routes every LLM request to the **cheapest model that can handle it** — simple questions go to budget models, complex tasks go to frontier models. Saves 60-97% on API costs with no quality loss.

- **39-feature cascade classifier** — structural, unicode, and keyword analysis
- **Step-aware agentic routing** — different models for different steps in a workflow
- **Session persistence** — sticky model per task, auto-escalation on failure
- **Spend control** — per-request, hourly, daily, session limits
- **Dual protocol** — OpenAI (`/v1/chat/completions`) + Anthropic (`/v1/messages`)

## Commands

| Command | Description |
|---|---|
| `/route <prompt>` | Preview which model would be selected |
| `/spend status` | View current spending and limits |
| `/spend set hourly 5.00` | Set an hourly spending limit |
| `/feedback ok\|weak\|strong` | Rate the last routing decision |
| `/sessions` | View active routing sessions |

## Configuration

```yaml
plugins:
  entries:
    "@anjieyang/uncommon-route":
      port: 8403
      upstream: "https://api.commonstack.ai/v1"
      spendLimits:
        hourly: 5.00
        daily: 20.00
```

## Upstream Providers

Works with any OpenAI-compatible API:

| Provider | URL |
|---|---|
| [Commonstack](https://commonstack.ai) | `https://api.commonstack.ai/v1` |
| [OpenRouter](https://openrouter.ai) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Local (Ollama) | `http://127.0.0.1:11434/v1` |

## Links

- [GitHub](https://github.com/anjieyang/UncommonRoute)
- [PyPI](https://pypi.org/project/uncommon-route/)
- [Full Documentation](https://github.com/anjieyang/UncommonRoute#readme)

## License

MIT
