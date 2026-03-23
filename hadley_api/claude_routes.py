"""Claude CLI extraction routes.

Provides a local Claude extraction endpoint that uses `claude -p` (CLI print mode)
instead of the Anthropic API. This avoids needing an API key — it uses the local
Claude Code OAuth subscription instead.

Uses sync subprocess.run via asyncio.to_thread with shell redirect to temp file
to avoid Windows async PIPE issues (same pattern as japan_train_status.py).

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

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
