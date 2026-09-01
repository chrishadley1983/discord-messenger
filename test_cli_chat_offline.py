"""Offline unit tests for cli_chat's JSON tool handshake (no network).

Run: python test_cli_chat_offline.py
"""

import asyncio
import json

import cli_chat


def _conv(text):
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


TOOLS = [{"name": "get_num", "description": "returns a number", "input_schema": {}}]


async def fake_handler(**kwargs):
    return {"value": 42}


def run(scripted_responses, handlers=None):
    """Patch the transport with a scripted sequence and run one chat."""
    calls = {"prompts": []}
    seq = list(scripted_responses)

    async def fake_cli(prompt, max_tokens=1500, timeout=60, model=""):
        calls["prompts"].append(prompt)
        return seq.pop(0) if seq else None

    original = cli_chat.call_claude_via_cli
    cli_chat.call_claude_via_cli = fake_cli
    try:
        result = asyncio.run(
            cli_chat.chat_with_history_via_cli(
                conversation=_conv("hi"),
                system="You are a test bot.",
                tools=TOOLS,
                tool_handlers=handlers or {},
            )
        )
    finally:
        cli_chat.call_claude_via_cli = original
    return result, calls


# 1. Plain answer passes straight through
out, _ = run(["Hello there"])
assert out == "Hello there", out

# 2. Tool call -> handler runs -> result fed back -> final answer
tool_json = json.dumps({"tool_call": {"name": "get_num", "args": {}}})
out, calls = run([tool_json, "The number is 42"], handlers={"get_num": fake_handler})
assert out == "The number is 42", out
assert '"value": 42' in calls["prompts"][1], "tool result not fed back"

# 3. Fenced tool call also parses
out, _ = run([f"```json\n{tool_json}\n```", "Answer"], handlers={"get_num": fake_handler})
assert out == "Answer", out

# 4. Unknown tool -> forced plain answer (no JSON leaked)
bad = json.dumps({"tool_call": {"name": "nope", "args": {}}})
out, _ = run([bad, "Plain fallback answer"])
assert out == "Plain fallback answer", out

# 5. Transport down -> None (caller sends "AI unavailable")
out, _ = run([None])
assert out is None, out

# 6. JSON-looking but non-tool response is returned as text
out, _ = run(['{"not_a_tool": true}'])
assert out == '{"not_a_tool": true}', out

print("ALL 6 OFFLINE TESTS PASS")
