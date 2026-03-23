"""Claude extraction routes.

Provides a local Claude extraction endpoint. Tries the `claude -p` CLI first
(uses OAuth subscription — no API cost), then falls back to the Anthropic API
if the CLI returns empty (common on Windows due to async PIPE issues).

Used by Second Brain seed adapters for summarisation, tagging, and structured
data extraction from emails.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claude", tags=["claude"])

CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class ExtractRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to send to Claude")
    max_tokens: int = Field(default=1500, description="Max tokens for response")
    model: str = Field(default="", description="Model override (empty = default)")


class ExtractResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


@router.post("/extract", response_model=ExtractResponse)
async def claude_extract(req: ExtractRequest):
    """Run a Claude extraction via CLI, with Anthropic API fallback.

    1. Try `claude -p` (free, uses OAuth subscription)
    2. If CLI returns empty, fall back to Anthropic API (uses API credits)
    """
    # Try CLI first
    try:
        result = await _run_claude_cli(req.prompt, req.max_tokens, req.model)
        if result:
            return ExtractResponse(result=result)
        logger.warning("Claude CLI returned empty, trying API fallback")
    except asyncio.TimeoutError:
        logger.warning("Claude CLI timed out, trying API fallback")
    except Exception as e:
        logger.warning(f"Claude CLI failed ({e}), trying API fallback")

    # Fallback to Anthropic API
    if ANTHROPIC_API_KEY:
        try:
            result = await _call_anthropic_api(
                req.prompt, req.max_tokens, req.model or "claude-haiku-4-5-20251001"
            )
            if result:
                return ExtractResponse(result=result)
            return ExtractResponse(error="Anthropic API returned empty")
        except Exception as e:
            return ExtractResponse(error=f"Both CLI and API failed: {e}")

    return ExtractResponse(error="Claude CLI returned no output and no API key configured")


async def _run_claude_cli(prompt: str, max_tokens: int = 1500, model: str = "") -> Optional[str]:
    """Execute claude -p and return the text response."""
    cli = CLAUDE_CLI if os.path.exists(CLAUDE_CLI) else "claude"
    cmd = [cli, "-p", "--output-format", "text", "--max-turns", "1"]
    if model:
        cmd.extend(["--model", model])

    # Build clean env: inherit current env but remove keys that interfere
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDECODE", None)

    # Ensure claude CLI is on PATH
    local_bin = os.path.expanduser("~/.local/bin")
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=60,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore").strip()
        out = stdout.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(
            f"Claude CLI exited {proc.returncode}: "
            f"stderr={err[:300]} stdout={out[:300]}"
        )

    return stdout.decode("utf-8", errors="ignore").strip() or None


async def _call_anthropic_api(
    prompt: str,
    max_tokens: int = 1500,
    model: str = "claude-haiku-4-5-20251001",
) -> Optional[str]:
    """Call the Anthropic Messages API directly as a fallback."""
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if response.status_code == 401:
            raise RuntimeError("Anthropic API key is invalid or expired — regenerate at console.anthropic.com")
        response.raise_for_status()
        data = response.json()

        # Extract text from response content blocks
        content = data.get("content", [])
        texts = [block["text"] for block in content if block.get("type") == "text"]
        return "\n".join(texts).strip() or None
