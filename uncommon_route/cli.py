"""CLI entry point for UncommonRoute.

Subcommands:
    route    — classify a prompt and print the routing decision
    serve    — start the OpenAI-compatible proxy server
    debug    — show per-dimension scoring breakdown
    openclaw — manage OpenClaw integration (install/uninstall/status)
    spend    — manage spending limits (set/clear/status/history)
    sessions — show active session stats

Global flags:
    --version / -v
    --help    / -h
"""

from __future__ import annotations

import json
import sys
import time

from uncommon_route.router.api import route
from uncommon_route.router.classifier import classify
from uncommon_route.router.structural import extract_structural_features, extract_unicode_block_features
from uncommon_route.router.keywords import extract_keyword_features

VERSION = "0.1.0"


def _print_help() -> None:
    print(f"""uncommon-route v{VERSION} — SOTA LLM Router

Usage:
  uncommon-route route <prompt>         Route a prompt to the best model
  uncommon-route serve                  Start OpenAI-compatible proxy server
  uncommon-route debug <prompt>         Show per-dimension scoring breakdown
  uncommon-route openclaw <sub>         OpenClaw integration (install|uninstall|status)
  uncommon-route spend <sub>            Spending limits (status|set|clear|history)
  uncommon-route provider <sub>          API key management (list|add|remove|models)
  uncommon-route sessions               Show active session stats
  uncommon-route --version              Show version

Route options:
  --system-prompt <text>              System prompt for context
  --max-tokens <n>                    Max output tokens (default: 4096)
  --json                              Output as JSON

Serve options:
  --port <n>                          Port to listen on (default: 8403)
  --host <addr>                       Host to bind (default: 127.0.0.1)
  --upstream <url>                    Upstream API base URL

OpenClaw subcommands:
  openclaw install [--port <n>]       Register as OpenClaw provider
  openclaw uninstall                  Remove from OpenClaw
  openclaw status                     Check registration

Provider subcommands:
  provider list                         Show configured API keys
  provider add <name> <key>             Add key (e.g. deepseek, minimax, openai)
  provider remove <name>                Remove a key
  provider models                       List user-keyed models

Spend subcommands:
  spend status                        Show spending status & limits
  spend set <window> <amount>         Set limit (window: per_request|hourly|daily|session)
  spend clear <window>                Remove a limit
  spend history [--limit <n>]         Show recent spending records

Examples:
  uncommon-route route "what is 2+2"
  uncommon-route serve --port 8403
  uncommon-route openclaw install
  uncommon-route spend set hourly 5.00
  uncommon-route spend status
  uncommon-route provider add deepseek sk-...
  uncommon-route provider add minimax eyJ... --plan coding-plan
""")


def _parse_flags(args: list[str], known_flags: dict[str, bool]) -> tuple[dict[str, str | bool], list[str]]:
    """Parse flags from args. known_flags maps flag name -> has_value."""
    flags: dict[str, str | bool] = {}
    rest: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        clean = arg.lstrip("-")
        if arg.startswith("--") and clean in known_flags:
            if known_flags[clean]:
                if i + 1 < len(args):
                    flags[clean] = args[i + 1]
                    i += 2
                else:
                    print(f"Error: {arg} requires a value", file=sys.stderr)
                    sys.exit(1)
            else:
                flags[clean] = True
                i += 1
        else:
            rest.append(arg)
            i += 1
    return flags, rest


def _cmd_route(args: list[str]) -> None:
    flags, rest = _parse_flags(args, {
        "system-prompt": True,
        "max-tokens": True,
        "json": False,
    })

    prompt = " ".join(rest)
    if not prompt:
        print("Error: no prompt provided", file=sys.stderr)
        sys.exit(1)

    system_prompt = str(flags["system-prompt"]) if "system-prompt" in flags else None
    max_tokens = int(flags.get("max-tokens", 4096))
    output_json = bool(flags.get("json", False))

    start = time.perf_counter_ns()
    decision = route(prompt, system_prompt=system_prompt, max_output_tokens=max_tokens)
    elapsed_us = (time.perf_counter_ns() - start) / 1000

    if output_json:
        print(json.dumps({
            "model": decision.model,
            "tier": decision.tier.value,
            "confidence": round(decision.confidence, 3),
            "cost_estimate": round(decision.cost_estimate, 6),
            "savings": round(decision.savings, 3),
            "reasoning": decision.reasoning,
            "suggested_output_budget": decision.suggested_output_budget,
            "fallback_chain": [
                {"model": fb.model, "cost": round(fb.cost_estimate, 6)}
                for fb in decision.fallback_chain
            ],
            "latency_us": round(elapsed_us, 1),
        }, indent=2))
    else:
        print(f"  Model:      {decision.model}")
        print(f"  Tier:       {decision.tier.value}")
        print(f"  Confidence: {decision.confidence:.2f}")
        print(f"  Cost:       ${decision.cost_estimate:.6f}")
        print(f"  Savings:    {decision.savings:.0%}")
        print(f"  Latency:    {elapsed_us:.0f}µs")
        print(f"  Reasoning:  {decision.reasoning}")
        if decision.fallback_chain:
            print(f"  Fallback:   {' → '.join(fb.model for fb in decision.fallback_chain)}")


def _cmd_debug(args: list[str]) -> None:
    flags, rest = _parse_flags(args, {"system-prompt": True})

    prompt = " ".join(rest)
    if not prompt:
        print("Error: no prompt provided", file=sys.stderr)
        sys.exit(1)

    system_prompt = str(flags["system-prompt"]) if "system-prompt" in flags else None
    full_text = f"{system_prompt or ''} {prompt}".strip()

    result = classify(prompt, system_prompt)

    struct_dims = extract_structural_features(full_text)
    unicode_blocks = extract_unicode_block_features(full_text)
    kw_dims = extract_keyword_features(prompt)

    tier_str = result.tier.value if result.tier else "AMBIGUOUS"
    print(f"  Tier:       {tier_str}")
    print(f"  Confidence: {result.confidence:.3f}")
    print(f"  Signals:    {', '.join(result.signals)}")
    print()

    print("  Structural Features:")
    for d in struct_dims:
        sig = f"  [{d.signal}]" if d.signal else ""
        print(f"    {d.name:<28} {d.score:>7.3f}{sig}")

    print()
    print("  Unicode Blocks:")
    for name, prop in sorted(unicode_blocks.items(), key=lambda x: -x[1]):
        if prop > 0.001:
            print(f"    {name:<28} {prop:>7.3f}")

    print()
    print("  Keyword Features:")
    for d in kw_dims:
        sig = f"  [{d.signal}]" if d.signal else ""
        print(f"    {d.name:<28} {d.score:>7.3f}{sig}")


def _cmd_serve(args: list[str]) -> None:
    flags, _ = _parse_flags(args, {
        "port": True,
        "host": True,
        "upstream": True,
    })

    from uncommon_route.proxy import DEFAULT_PORT, DEFAULT_UPSTREAM, serve

    port = int(flags.get("port", DEFAULT_PORT))
    host = str(flags.get("host", "127.0.0.1"))
    upstream = str(flags.get("upstream", DEFAULT_UPSTREAM))

    serve(port=port, host=host, upstream=upstream)


def _cmd_openclaw(args: list[str]) -> None:
    from uncommon_route.openclaw import cmd_openclaw
    cmd_openclaw(args)


def _cmd_spend(args: list[str]) -> None:
    from uncommon_route.spend_control import SpendControl, format_duration

    sc = SpendControl()

    if not args:
        args = ["status"]

    sub = args[0]

    if sub == "status":
        s = sc.status()
        print("  Spending Limits:")
        if s.limits.per_request is not None:
            print(f"    Per-request:  ${s.limits.per_request:.2f}")
        if s.limits.hourly is not None:
            rem = s.remaining.get("hourly")
            print(f"    Hourly:       ${s.limits.hourly:.2f}  (spent: ${s.spent['hourly']:.4f}, remaining: ${rem:.4f})" if rem is not None else "")
        if s.limits.daily is not None:
            rem = s.remaining.get("daily")
            print(f"    Daily:        ${s.limits.daily:.2f}  (spent: ${s.spent['daily']:.4f}, remaining: ${rem:.4f})" if rem is not None else "")
        if s.limits.session is not None:
            rem = s.remaining.get("session")
            print(f"    Session:      ${s.limits.session:.2f}  (spent: ${s.spent['session']:.4f}, remaining: ${rem:.4f})" if rem is not None else "")
        if all(v is None for v in vars(s.limits).values()):
            print("    (no limits set)")
        print(f"\n  Total calls this session: {s.calls}")

    elif sub == "set":
        if len(args) < 3:
            print("Usage: uncommon-route spend set <window> <amount>", file=sys.stderr)
            print("  Windows: per_request, hourly, daily, session", file=sys.stderr)
            sys.exit(1)
        window = args[1]
        amount = float(args[2])
        sc.set_limit(window, amount)  # type: ignore[arg-type]
        print(f"  Set {window} limit: ${amount:.2f}")

    elif sub == "clear":
        if len(args) < 2:
            print("Usage: uncommon-route spend clear <window>", file=sys.stderr)
            sys.exit(1)
        window = args[1]
        sc.clear_limit(window)  # type: ignore[arg-type]
        print(f"  Cleared {window} limit")

    elif sub == "history":
        flags, _ = _parse_flags(args[1:], {"limit": True})
        limit = int(flags.get("limit", 20))
        records = sc.history(limit=limit)
        if not records:
            print("  No spending records")
            return
        print(f"  Recent spending ({len(records)} records):")
        for r in records:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.timestamp))
            model_str = f"  [{r.model}]" if r.model else ""
            print(f"    {ts}  ${r.amount:.6f}{model_str}")

    else:
        print(f"Unknown spend subcommand: {sub}", file=sys.stderr)
        print("  Available: status, set, clear, history", file=sys.stderr)
        sys.exit(1)


def _cmd_provider(args: list[str]) -> None:
    from uncommon_route.providers import cmd_provider
    cmd_provider(args)


def _cmd_sessions(args: list[str]) -> None:
    from uncommon_route.session import SessionStore
    store = SessionStore()
    stats = store.stats()
    print(f"  Active sessions: {stats['count']}")
    if stats["sessions"]:
        for s in stats["sessions"]:
            print(f"    {s['id']}  model={s['model']}  tier={s['tier']}  requests={s['requests']}  age={s['age_s']}s")
    else:
        print("  (no active sessions — sessions are in-memory, start `serve` first)")


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _print_help()
        sys.exit(0)

    if args[0] in ("--version", "-v"):
        print(VERSION)
        sys.exit(0)

    cmd = args[0]
    sub_args = args[1:]

    commands = {
        "route": _cmd_route,
        "serve": _cmd_serve,
        "debug": _cmd_debug,
        "openclaw": _cmd_openclaw,
        "spend": _cmd_spend,
        "provider": _cmd_provider,
        "sessions": _cmd_sessions,
    }

    handler = commands.get(cmd)
    if handler:
        handler(sub_args)
    else:
        _cmd_route(args)


if __name__ == "__main__":
    main()
