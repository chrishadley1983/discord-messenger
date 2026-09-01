"""Domain chat via the Hadley API /claude/extract CLI path (OAuth, no API key).

Replaces the direct-API ClaudeClient for registry-domain channel chat (news,
api_usage). Those were the last callers of the dead DISCORD_BOT_CLAUDE_KEY —
every other flow already goes through call_claude_via_cli.

/claude/extract is plain prompt-in/text-out, so tool use is preserved with a
JSON handshake instead of the native tool-use protocol: the model either
answers directly or replies with a single {"tool_call": {"name", "args"}}
object; we execute the matching handler and feed the result back, up to
MAX_TOOL_ITERATIONS rounds. Images in the conversation are noted by URL only
(the CLI path is text-only).
"""

import asyncio
import inspect
import json
import re

from config import call_claude_via_cli
from logger import logger

MAX_TOOL_ITERATIONS = 3
MAX_TOOL_RESULT_CHARS = 4000

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _flatten_conversation(conversation: list[dict]) -> str:
    """Render the Discord history (role + content blocks) as a transcript."""
    lines = []
    for msg in conversation:
        role = "User" if msg.get("role") == "user" else "Assistant"
        parts = []
        for block in msg.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "image_url":
                parts.append(f"[image attached: {block.get('url', '')}]")
        text = " ".join(p for p in parts if p).strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _render_tool_catalog(tools: list[dict]) -> str:
    lines = []
    for t in tools:
        schema = json.dumps(t.get("input_schema", {}))
        lines.append(f"- {t['name']}: {t['description']} | args schema: {schema}")
    return "\n".join(lines)


def _parse_tool_call(response: str) -> dict | None:
    """Return {"name", "args"} if the response is a tool call, else None."""
    candidate = response.strip()
    fenced = _JSON_BLOCK.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    if not candidate.startswith("{"):
        return None
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    call = data.get("tool_call")
    if isinstance(call, dict) and isinstance(call.get("name"), str):
        return {"name": call["name"], "args": call.get("args") or {}}
    return None


async def _run_handler(handler, args: dict) -> str:
    result = handler(**args)
    if inspect.isawaitable(result):
        result = await result
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + " …[truncated]"
    return text


async def chat_with_history_via_cli(
    conversation: list[dict],
    system: str,
    tools: list[dict] | None = None,
    tool_handlers: dict | None = None,
    max_tokens: int = 1500,
) -> str | None:
    """Answer the latest channel message, executing domain tools as needed.

    Returns the assistant text, or None if the CLI path is unavailable (the
    caller sends its usual "AI unavailable" message).
    """
    tools = tools or []
    tool_handlers = tool_handlers or {}
    transcript = _flatten_conversation(conversation)

    tool_section = ""
    if tools:
        tool_section = (
            "\n\nYou can call these tools:\n"
            f"{_render_tool_catalog(tools)}\n\n"
            "To call a tool, reply with ONLY this JSON (no other text):\n"
            '{"tool_call": {"name": "<tool name>", "args": {<args>}}}\n'
            "You will receive the result and can then answer (or call another "
            "tool). When you have what you need, reply with the plain-text "
            "answer for Discord — never JSON, never tool syntax."
        )

    prompt = (
        f"{system}{tool_section}\n\n"
        "Conversation so far (most recent last):\n"
        f"{transcript}\n\n"
        "Reply to the latest user message. Keep it under 1800 characters "
        "(Discord limit is 2000)."
    )

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        response = await call_claude_via_cli(prompt, max_tokens=max_tokens)
        if response is None:
            logger.error("cli_chat: /claude/extract returned no result")
            return None

        call = _parse_tool_call(response)
        if call is None:
            return response.strip()

        handler = tool_handlers.get(call["name"])
        if handler is None or iteration == MAX_TOOL_ITERATIONS:
            # Unknown tool, or out of tool budget: force one final plain answer.
            logger.warning(
                f"cli_chat: unresolvable tool call {call['name']!r} "
                f"(iteration {iteration}) — forcing a plain answer"
            )
            prompt += (
                f"\n\n[The tool {call['name']!r} cannot be run. Answer the "
                "user's latest message with plain text using what you already "
                "have — do NOT reply with JSON or tool syntax.]"
            )
            final = await call_claude_via_cli(prompt, max_tokens=max_tokens)
            return final.strip() if final else None

        try:
            result = await _run_handler(handler, call["args"])
            logger.info(f"cli_chat: ran tool {call['name']} args={call['args']}")
        except Exception as e:
            result = f"Tool error: {e}"
            logger.error(f"cli_chat: tool {call['name']} failed: {e}")

        prompt += (
            f"\n\n[Tool result for {call['name']}({json.dumps(call['args'], default=str)}):]\n"
            f"{result}\n\n"
            "Continue: answer the user's latest message with plain text, or "
            "call another tool if genuinely needed."
        )

    return None
