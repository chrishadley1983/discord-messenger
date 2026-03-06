"""Claude CLI extraction routes.

Provides a local Claude extraction endpoint that uses `claude -p` (CLI print mode)
instead of the Anthropic API. This avoids needing an API key — it uses the local
Claude Code OAuth subscription instead.

Used by Second Brain seed adapters for summarisation, tagging, and structured
data extraction from emails.
"""

import asyncio
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/claude", tags=["claude"])

CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")


class ExtractRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to send to Claude")
    max_tokens: int = Field(default=1500, description="Max tokens for response")
    model: str = Field(default="", description="Model override (empty = default)")


class ExtractResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


@router.post("/extract", response_model=ExtractResponse)
async def claude_extract(req: ExtractRequest):
    """Run a Claude extraction via the local CLI.

    Uses `claude -p` (print mode) which reads from stdin and writes to stdout.
    No API key needed — uses the local Claude Code OAuth subscription.
    """
    try:
        result = await _run_claude_cli(req.prompt, req.max_tokens, req.model)
        if result is None:
            return ExtractResponse(error="Claude CLI returned no output")
        return ExtractResponse(result=result)
    except asyncio.TimeoutError:
        return ExtractResponse(error="Claude CLI timed out (60s)")
    except Exception as e:
        return ExtractResponse(error=str(e))


async def _run_claude_cli(prompt: str, max_tokens: int = 1500, model: str = "") -> Optional[str]:
    """Execute claude -p and return the text response.

    Clears ANTHROPIC_API_KEY and CLAUDECODE from the subprocess env to ensure
    the CLI uses OAuth credentials from ~/.claude/.credentials.json rather
    than a potentially stale API key from .env.
    """
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
