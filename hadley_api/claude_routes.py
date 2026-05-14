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


async def _try_extract_channel(prompt: str) -> Optional[str]:
    """POST to extract-channel; return text on success, None on failure.

    None means caller should fall back to the CLI subprocess. The channel
    runs on Haiku 4.5, so model/max_tokens overrides from the request are
    ignored on this path (callers wanting a specific model should hit the
    CLI directly or pass it via the prompt itself).
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EXTRACT_CHANNEL_URL}/extract",
                json={"prompt": prompt},
                timeout=EXTRACT_CHANNEL_TIMEOUT,
            )
        if resp.status_code != 200:
            logger.warning(f"extract-channel returned {resp.status_code}; falling back to CLI")
            return None
        text = resp.json().get("response", "")
        if not text:
            logger.warning("extract-channel returned empty response; falling back to CLI")
            return None
        return text
    except Exception as e:
        logger.warning(f"extract-channel unreachable ({e}); falling back to CLI")
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
