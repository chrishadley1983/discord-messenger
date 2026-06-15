"""Claude extraction routes.

Provides a local Claude extraction endpoint for one-shot prompts.

Routing (2026-05 channel migration):
  1. Primary path: POST to extract-channel HTTP on :8106 (persistent Claude Code
     session on Haiku 4.5 — keeps usage on the subscription, not the new
     programmatic credit). See docs/MIGRATE_OFF_CLAUDE_P.md.
  2. Fallback: spawn `claude -p` subprocess (the original behaviour).
     Used only when extract-channel is unreachable.

Used by Second Brain seed adapters for summarisation, tagging, and structured
data extraction from emails.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude", tags=["claude"])

CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")
EXTRACT_CHANNEL_URL = os.environ.get("EXTRACT_CHANNEL_URL", "http://127.0.0.1:8106")
EXTRACT_CHANNEL_TIMEOUT = float(os.environ.get("EXTRACT_CHANNEL_TIMEOUT", "90"))


class ExtractRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to send to Claude")
    max_tokens: int = Field(default=1500, description="Max tokens for response")
    model: str = Field(default="", description="Model override (empty = default)")


class ExtractResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


# Circuit breaker for the extract-channel. When the channel wedges (the
# inject->reply path returns empty after the full timeout — observed 13 Jun
# 2026 returning "" after 100s on every call), waiting EXTRACT_CHANNEL_TIMEOUT
# per request makes EVERYTHING that extracts ~100x slower: school sync hit 17
# min, Second Brain seeding crawled (Spotify import took 4.5h). After
# _BREAKER_THRESHOLD consecutive channel failures we OPEN the breaker and go
# straight to the CLI (~7s) for _BREAKER_COOLDOWN_S, then probe once to
# auto-recover. Trade-off: the CLI fallback is `claude -p`, which from
# 2026-06-15 bills as programmatic spend (NOT the subscription the
# extract-channel runs on — see claude_extract() below and
# docs/MIGRATE_OFF_CLAUDE_P.md). So an open breaker briefly shifts extract
# traffic onto the metered path, bounded by _BREAKER_COOLDOWN_S. This is a
# latency fix with a small, time-boxed metered-cost side effect — recycle the
# wedged extract-channel session to close the breaker (and stop the spend)
# sooner.
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_S = 600.0
_channel_fail_streak = 0
_breaker_open_until = 0.0


def _breaker_is_open() -> bool:
    return time.monotonic() < _breaker_open_until


async def _try_extract_channel(prompt: str) -> Optional[str]:
    """POST to extract-channel; return text on success, None to fall back.

    Skips the channel entirely while the breaker is open. The channel runs
    Haiku 4.5, so model/max_tokens overrides are ignored on this path.
    """
    global _channel_fail_streak, _breaker_open_until

    if _breaker_is_open():
        return None  # breaker open — straight to CLI, no wasted wait

    def _record_fail():
        global _channel_fail_streak, _breaker_open_until
        _channel_fail_streak += 1
        if _channel_fail_streak >= _BREAKER_THRESHOLD:
            _breaker_open_until = time.monotonic() + _BREAKER_COOLDOWN_S
            logger.warning(
                "extract-channel breaker OPEN for %ss after %d failures — "
                "using CLI; recycle the extract-channel session to restore it",
                int(_BREAKER_COOLDOWN_S), _channel_fail_streak)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EXTRACT_CHANNEL_URL}/extract",
                json={"prompt": prompt},
                timeout=EXTRACT_CHANNEL_TIMEOUT,
            )
        if resp.status_code != 200:
            logger.warning(f"extract-channel returned {resp.status_code}; falling back to CLI")
            _record_fail()
            return None
        text = resp.json().get("response", "")
        if not text:
            logger.warning("extract-channel returned empty response; falling back to CLI")
            _record_fail()
            return None
        _channel_fail_streak = 0  # healthy reply resets the breaker
        return text
    except Exception as e:
        logger.warning(f"extract-channel unreachable ({e}); falling back to CLI")
        _record_fail()
        return None


@router.post("/extract", response_model=ExtractResponse)
async def claude_extract(req: ExtractRequest):
    """Run a Claude extraction.

    Primary path: persistent extract-channel session (Haiku 4.5, on subscription).
    Fallback: `claude -p` subprocess (programmatic spend after Jun 15 2026).
    """
    # Channel path first — only fall back if the channel is genuinely down
    channel_result = await _try_extract_channel(req.prompt)
    if channel_result is not None:
        return ExtractResponse(result=channel_result)

    # Fallback: original CLI subprocess
    try:
        result = await asyncio.to_thread(
            _run_claude_cli_sync, req.prompt, req.max_tokens, req.model
        )
        if result is None:
            return ExtractResponse(error="Claude CLI returned no output")
        return ExtractResponse(result=result)
    except subprocess.TimeoutExpired:
        return ExtractResponse(error="Claude CLI timed out (60s)")
    except Exception as e:
        return ExtractResponse(error=str(e))


def _run_claude_cli_sync(
    prompt: str, max_tokens: int = 1500, model: str = ""
) -> Optional[str]:
    """Execute claude -p using sync subprocess with temp file redirect.

    Uses shell redirect to temp file instead of PIPE to avoid
    Windows async subprocess PIPE issues.
    """
    cli = CLAUDE_CLI if os.path.exists(CLAUDE_CLI) else "claude"

    # Build clean env: remove keys that make CLI use API instead of OAuth
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDECODE", None)

    # Ensure claude CLI is on PATH
    local_bin = os.path.expanduser("~/.local/bin")
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")

    # Write prompt to temp file (avoids stdin PIPE issues)
    prompt_file = Path(tempfile.mktemp(suffix=".txt", prefix="claude_prompt_"))
    output_file = Path(tempfile.mktemp(suffix=".txt", prefix="claude_output_"))

    try:
        prompt_file.write_text(prompt, encoding="utf-8")

        # Build command with shell redirect
        cmd_parts = [f'"{cli}"', "-p", "--output-format", "text", "--max-turns", "1"]
        if model:
            cmd_parts.extend(["--model", model])

        # Read from prompt file, write to output file
        cmd = f'{" ".join(cmd_parts)} < "{prompt_file}" > "{output_file}"'

        subprocess.run(
            cmd,
            shell=True,
            timeout=60,
            env=env,
            stderr=subprocess.PIPE,
        )

        if output_file.exists():
            content = output_file.read_text(encoding="utf-8").strip()
            if content:
                return content

        return None

    except subprocess.TimeoutExpired:
        raise
    except Exception as e:
        logger.error(f"Claude CLI error: {e}")
        raise
    finally:
        prompt_file.unlink(missing_ok=True)
        output_file.unlink(missing_ok=True)
