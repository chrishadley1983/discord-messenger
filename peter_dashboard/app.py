"""Peter Dashboard - Web UI for monitoring the Peterbot system.

Provides real-time visibility into:
- Process status (API, Bot, tmux sessions)
- Log viewing
- Key file viewing/editing
- Context messages being sent
- Service control (restart)
- Background task monitoring
"""

import asyncio
import subprocess
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="Peter Dashboard", version="1.0.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
CONFIG = {
    "hadley_api_url": "http://localhost:8100",
    "claude_mem_url": "http://localhost:37777",
    "wsl_peterbot_path": "/home/chris_hadley/peterbot",
    "windows_project_path": r"C:\Users\Chris Hadley\Discord-Messenger",
}

# Key files to monitor
KEY_FILES = {
    "CLAUDE.md": "domains/peterbot/wsl_config/CLAUDE.md",
    "PETERBOT_SOUL.md": "domains/peterbot/wsl_config/PETERBOT_SOUL.md",
    "SCHEDULE.md": "domains/peterbot/wsl_config/SCHEDULE.md",
    "HEARTBEAT.md": "domains/peterbot/wsl_config/HEARTBEAT.md",
    "USER.md": "domains/peterbot/wsl_config/USER.md",
    "Bot Config": "domains/peterbot/config.py",
    "Router": "domains/peterbot/router.py",
    "Parser": "domains/peterbot/parser.py",
}

# WSL key files
WSL_FILES = {
    "context.md": "/home/chris_hadley/peterbot/context.md",
    "raw_capture.log": "/home/chris_hadley/peterbot/raw_capture.log",
    "HEARTBEAT.md": "/home/chris_hadley/peterbot/HEARTBEAT.md",
    "SCHEDULE.md": "/home/chris_hadley/peterbot/SCHEDULE.md",
}


def run_wsl_command(cmd: str, timeout: int = 10) -> tuple[str, str, int]:
    """Run a command in WSL and return stdout, stderr, returncode."""
    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            timeout=timeout
        )
        # Decode with explicit UTF-8 and error handling
        stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
        stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""
        return stdout, stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1


def check_process_running(process_name: str) -> bool:
    """Check if a Windows process is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True,
            text=True
        )
        return process_name.lower() in result.stdout.lower()
    except Exception:
        return False


def get_tmux_sessions() -> list[dict]:
    """Get list of tmux sessions from WSL."""
    stdout, stderr, code = run_wsl_command("tmux list-sessions -F '#{session_name}:#{session_windows}:#{session_attached}' 2>/dev/null || echo ''")

    sessions = []
    for line in stdout.strip().split('\n'):
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 3:
                sessions.append({
                    "name": parts[0],
                    "windows": parts[1],
                    "attached": parts[2] == "1"
                })
    return sessions


async def check_http_service(url: str, timeout: float = 2.0) -> dict:
    """Check if an HTTP service is responding."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            start = datetime.now()
            response = await client.get(url)
            latency = (datetime.now() - start).total_seconds() * 1000
            return {
                "status": "up",
                "code": response.status_code,
                "latency_ms": round(latency, 2)
            }
    except httpx.ConnectError:
        return {"status": "down", "error": "Connection refused"}
    except httpx.TimeoutException:
        return {"status": "down", "error": "Timeout"}
    except Exception as e:
        return {"status": "down", "error": str(e)}


def read_file_content(filepath: str, tail_lines: int = 100) -> dict:
    """Read file content, optionally tailing."""
    try:
        full_path = os.path.join(CONFIG["windows_project_path"], filepath)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # If tail_lines specified and file is large, only return last N lines
            lines = content.split('\n')
            if tail_lines and len(lines) > tail_lines:
                content = '\n'.join(lines[-tail_lines:])

            return {
                "exists": True,
                "content": content,
                "size": os.path.getsize(full_path),
                "modified": datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat()
            }
        return {"exists": False, "error": "File not found"}
    except Exception as e:
        return {"exists": False, "error": str(e)}


def read_wsl_file(wsl_path: str, tail_lines: int = 100) -> dict:
    """Read file content from WSL."""
    try:
        if tail_lines:
            cmd = f"tail -n {tail_lines} '{wsl_path}' 2>/dev/null || cat '{wsl_path}' 2>/dev/null || echo 'File not found'"
        else:
            cmd = f"cat '{wsl_path}' 2>/dev/null || echo 'File not found'"

        stdout, stderr, code = run_wsl_command(cmd)

        if code == 0 and stdout != 'File not found\n':
            # Get file stats
            stat_cmd = f"stat -c '%s %Y' '{wsl_path}' 2>/dev/null || echo '0 0'"
            stat_out, _, _ = run_wsl_command(stat_cmd)
            parts = stat_out.strip().split()
            size = int(parts[0]) if parts else 0
            mtime = int(parts[1]) if len(parts) > 1 else 0

            return {
                "exists": True,
                "content": stdout,
                "size": size,
                "modified": datetime.fromtimestamp(mtime).isoformat() if mtime else None
            }
        return {"exists": False, "error": "File not found"}
    except Exception as e:
        return {"exists": False, "error": str(e)}


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def dashboard():
    """Serve the dashboard HTML."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/health")
async def health_check():
    """Health check for the dashboard itself."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
async def get_system_status():
    """Get overall system status."""
    # Check services in parallel
    hadley_task = check_http_service(f"{CONFIG['hadley_api_url']}/health")
    mem_task = check_http_service(f"{CONFIG['claude_mem_url']}/health")

    hadley_status, mem_status = await asyncio.gather(hadley_task, mem_task)

    # Check tmux sessions
    sessions = get_tmux_sessions()
    peterbot_session = next((s for s in sessions if s["name"] == "claude-peterbot"), None)

    # Check Discord bot process (Python running bot.py)
    bot_running = False
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=5
        )
        bot_running = "bot.py" in result.stdout
    except Exception:
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "services": {
            "hadley_api": hadley_status,
            "claude_mem": mem_status,
            "discord_bot": {"status": "up" if bot_running else "down"},
            "peterbot_session": {
                "status": "up" if peterbot_session else "down",
                "attached": peterbot_session["attached"] if peterbot_session else False
            }
        },
        "tmux_sessions": sessions
    }


@app.get("/api/files")
async def list_files():
    """List available files to view."""
    files = []

    # Windows files
    for name, path in KEY_FILES.items():
        full_path = os.path.join(CONFIG["windows_project_path"], path)
        exists = os.path.exists(full_path)
        files.append({
            "name": name,
            "path": path,
            "type": "windows",
            "exists": exists,
            "modified": datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat() if exists else None
        })

    # WSL files
    for name, path in WSL_FILES.items():
        stat_cmd = f"stat -c '%Y' '{path}' 2>/dev/null || echo '0'"
        stdout, _, code = run_wsl_command(stat_cmd)
        mtime = int(stdout.strip()) if stdout.strip() != '0' else 0
        files.append({
            "name": name,
            "path": path,
            "type": "wsl",
            "exists": mtime > 0,
            "modified": datetime.fromtimestamp(mtime).isoformat() if mtime else None
        })

    return {"files": files}


@app.get("/api/file/{file_type}/{file_name}")
async def get_file(file_type: str, file_name: str, tail: int = 0):
    """Get file content."""
    if file_type == "windows":
        if file_name not in KEY_FILES:
            raise HTTPException(404, "File not found")
        return read_file_content(KEY_FILES[file_name], tail_lines=tail if tail > 0 else None)
    elif file_type == "wsl":
        if file_name not in WSL_FILES:
            raise HTTPException(404, "File not found")
        return read_wsl_file(WSL_FILES[file_name], tail_lines=tail if tail > 0 else 100)
    else:
        raise HTTPException(400, "Invalid file type")


@app.get("/api/context")
async def get_current_context():
    """Get the current context.md being sent to Claude Code."""
    return read_wsl_file(WSL_FILES["context.md"], tail_lines=0)


@app.get("/api/captures")
async def get_recent_captures():
    """Get recent raw screen captures for debugging."""
    return read_wsl_file(WSL_FILES["raw_capture.log"], tail_lines=200)


@app.get("/api/logs/bot")
async def get_bot_logs():
    """Get recent Discord bot logs."""
    # Try to read from Windows logs directory
    log_path = os.path.join(CONFIG["windows_project_path"], "logs", "bot.log")
    if os.path.exists(log_path):
        return read_file_content(os.path.join("logs", "bot.log"), tail_lines=200)
    return {"exists": False, "error": "Log file not found"}


@app.get("/api/screen/{session}")
async def get_tmux_screen(session: str, lines: int = 60):
    """Capture current tmux screen content."""
    cmd = f"tmux capture-pane -t {session} -p -S -{lines} 2>/dev/null || echo 'Session not found'"
    stdout, stderr, code = run_wsl_command(cmd)

    if code == 0 and stdout != 'Session not found\n':
        return {"content": stdout, "lines": lines}
    return {"error": "Session not found or not accessible"}


@app.post("/api/restart/{service}")
async def restart_service(service: str):
    """Restart a service."""
    if service == "hadley_api":
        # Kill existing and restart
        try:
            # Find and kill existing uvicorn process
            subprocess.run(
                ["taskkill", "/F", "/IM", "uvicorn.exe"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

        # Start new instance from project root so domains module is importable
        subprocess.Popen(
            ["python", "-m", "uvicorn", "hadley_api.main:app", "--host", "0.0.0.0", "--port", "8100"],
            cwd=CONFIG["windows_project_path"],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        return {"status": "restarting", "message": "Hadley API restart initiated"}

    elif service == "discord_bot":
        # Kill existing bot
        try:
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe' and commandline like '%bot.py%'", "call", "terminate"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass

        # Start new instance
        subprocess.Popen(
            ["python", "bot.py"],
            cwd=CONFIG["windows_project_path"],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        return {"status": "restarting", "message": "Discord Bot restart initiated"}

    elif service == "peterbot_session":
        # Kill and recreate tmux session
        run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
        run_wsl_command(f"tmux new-session -d -s claude-peterbot -c {CONFIG['wsl_peterbot_path']}")
        # Source profile for proper environment, use current CLI flag
        run_wsl_command("tmux send-keys -t claude-peterbot 'source ~/.profile && claude --permission-mode bypassPermissions' Enter")
        return {"status": "restarting", "message": "Peterbot session recreated"}

    else:
        raise HTTPException(400, f"Unknown service: {service}")


@app.post("/api/restart-all")
async def restart_all_services():
    """Restart all Peter-related services (headless - no console windows)."""
    results = {}

    # Windows flags for headless execution
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    # 1. Restart Hadley API
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "uvicorn.exe"],
            capture_output=True, timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass
    # Start from project root so domains module is importable
    subprocess.Popen(
        ["python", "-m", "uvicorn", "hadley_api.main:app", "--host", "0.0.0.0", "--port", "8100"],
        cwd=CONFIG["windows_project_path"],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    results["hadley_api"] = "restarting"

    # 2. Restart Discord Bot
    try:
        subprocess.run(
            ["wmic", "process", "where", "name='python.exe' and commandline like '%bot.py%'", "call", "terminate"],
            capture_output=True, timeout=5,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass
    subprocess.Popen(
        ["python", "bot.py"],
        cwd=CONFIG["windows_project_path"],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    results["discord_bot"] = "restarting"

    # 3. Restart Peterbot tmux session
    run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
    run_wsl_command(f"tmux new-session -d -s claude-peterbot -c {CONFIG['wsl_peterbot_path']}")
    run_wsl_command("tmux send-keys -t claude-peterbot 'source ~/.profile && claude --permission-mode bypassPermissions' Enter")
    results["peterbot_session"] = "restarting"

    return {
        "status": "restarting",
        "message": "All services restart initiated",
        "services": results
    }


@app.post("/api/send/{session}")
async def send_to_session(session: str, text: str):
    """Send text to a tmux session."""
    # Escape special characters
    escaped = text.replace("'", "'\\''")
    cmd = f"tmux send-keys -t {session} -l '{escaped}' && tmux send-keys -t {session} Enter"
    stdout, stderr, code = run_wsl_command(cmd)

    if code == 0:
        return {"status": "sent", "text": text}
    return {"status": "error", "error": stderr}


def parse_memory_response(data):
    """Parse MCP-style memory response into observations."""
    import re
    if data.get("content") and len(data["content"]) > 0:
        text = data["content"][0].get("text", "")

        # Parse observations from the markdown table format
        observations = []
        # Match rows like: | #548 | 3:26 PM | 📝 | Title here | ~156 |
        pattern = r'\| #(\d+) \| ([^|]+) \| [^|]+ \| ([^|]+) \| [^|]+ \|'
        matches = re.findall(pattern, text)

        for match in matches:
            obs_id, time_str, title = match
            observations.append({
                "id": int(obs_id),
                "time": time_str.strip(),
                "title": title.strip(),
                "obs_type": "observation"
            })

        return {
            "observations": observations,
            "raw_text": text,
            "count": len(observations)
        }
    return {"observations": [], "error": "No content returned"}


@app.get("/api/memory/peter")
async def get_peter_memories():
    """Get recent memory observations from peter-mem (peterbot project)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{CONFIG['claude_mem_url']}/api/timeline",
                params={"project": "peterbot", "query": "recent"}
            )
            if response.status_code == 200:
                return parse_memory_response(response.json())
            return {"error": f"Status {response.status_code}", "observations": []}
    except Exception as e:
        return {"error": str(e), "observations": []}


@app.get("/api/memory/claude")
async def get_claude_memories():
    """Get recent memory observations from claude-mem (all projects)."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search without project filter to get all recent observations
            response = await client.get(
                f"{CONFIG['claude_mem_url']}/api/search",
                params={"query": "recent", "limit": "30"}
            )
            if response.status_code == 200:
                return parse_memory_response(response.json())
            return {"error": f"Status {response.status_code}", "observations": []}
    except Exception as e:
        return {"error": str(e), "observations": []}


@app.get("/api/memory/recent")
async def get_recent_memories():
    """Get recent memory observations from claude-mem (peterbot project)."""
    return await get_peter_memories()


@app.get("/api/hadley/endpoints")
async def get_hadley_endpoints():
    """Get list of Hadley API endpoints."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CONFIG['hadley_api_url']}/openapi.json")
            if response.status_code == 200:
                openapi = response.json()
                paths = []
                for path, methods in openapi.get("paths", {}).items():
                    for method, details in methods.items():
                        if method in ("get", "post", "put", "delete"):
                            paths.append({
                                "path": path,
                                "method": method.upper(),
                                "summary": details.get("summary", "")
                            })
                return {"endpoints": sorted(paths, key=lambda x: x["path"])}
            return {"error": f"Status {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/heartbeat/status")
async def get_heartbeat_status():
    """Get heartbeat system status including SCHEDULE.md and HEARTBEAT.md."""
    import re
    from datetime import datetime, timedelta

    schedule = read_wsl_file("/home/chris_hadley/peterbot/SCHEDULE.md", tail_lines=0)
    heartbeat = read_wsl_file("/home/chris_hadley/peterbot/HEARTBEAT.md", tail_lines=0)

    # Check for heartbeat tracking file
    heartbeat_state = read_wsl_file("/home/chris_hadley/peterbot/.heartbeat_last_run", tail_lines=0)

    # Parse to-do items from HEARTBEAT.md with timestamps
    todos = []
    last_run = None

    if heartbeat.get("exists") and heartbeat.get("content"):
        content = heartbeat["content"]

        # Try to find last run timestamp (look for patterns like "Last run: 2026-02-01 10:00" or similar)
        last_run_match = re.search(r'[Ll]ast\s*[Rr]un[:\s]+(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(?::\d{2})?)', content)
        if last_run_match:
            last_run = last_run_match.group(1)

        # Check tracking file for accurate last run
        if not last_run and heartbeat_state.get("exists") and heartbeat_state.get("content"):
            last_run = heartbeat_state["content"].strip()

        # Fallback to file modification time (less accurate)
        if not last_run and heartbeat.get("modified"):
            last_run = heartbeat.get("modified") + " (file modified)"

        for line in content.split("\n"):
            if "- [ ]" in line or "- [x]" in line.lower():
                done = "- [x]" in line.lower()
                text = line.replace("- [ ]", "").replace("- [x]", "").replace("- [X]", "").strip()

                # Try to extract timestamp from the line (e.g., "[10:30]" or "(2026-02-01)")
                timestamp = None
                time_match = re.search(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)\]', text)
                date_match = re.search(r'\((\d{4}-\d{2}-\d{2})\)', text)

                if time_match:
                    timestamp = time_match.group(1)
                    text = re.sub(r'\[\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?\]\s*', '', text)
                elif date_match:
                    timestamp = date_match.group(1)
                    text = re.sub(r'\(\d{4}-\d{2}-\d{2}\)\s*', '', text)

                todos.append({
                    "text": text.strip(),
                    "done": done,
                    "timestamp": timestamp
                })

    # Parse next scheduled from SCHEDULE.md and calculate next due time
    next_scheduled = None
    interval_minutes = None

    if schedule.get("exists") and schedule.get("content"):
        lines = schedule["content"].split("\n")
        for line in lines:
            if "heartbeat" in line.lower():
                # Look for interval patterns like "30m" or "60m"
                interval_match = re.search(r'(\d+)m', line)
                if interval_match:
                    interval_minutes = int(interval_match.group(1))
                    break

    # Calculate next due time
    if interval_minutes and last_run:
        try:
            # Parse last run time
            last_run_clean = last_run.replace(" (file modified)", "")
            if "T" in last_run_clean:
                last_dt = datetime.fromisoformat(last_run_clean.replace("Z", ""))
            else:
                last_dt = datetime.strptime(last_run_clean, "%Y-%m-%d %H:%M:%S")

            # Calculate next due
            next_dt = last_dt + timedelta(minutes=interval_minutes)
            now = datetime.now()

            # If next due is in the past, calculate next future occurrence
            while next_dt < now:
                next_dt += timedelta(minutes=interval_minutes)

            time_until = next_dt - now
            minutes_until = int(time_until.total_seconds() / 60)

            if minutes_until < 1:
                next_scheduled = "Due now!"
            elif minutes_until < 60:
                next_scheduled = f"In {minutes_until} min ({next_dt.strftime('%H:%M')})"
            else:
                hours = minutes_until // 60
                mins = minutes_until % 60
                next_scheduled = f"In {hours}h {mins}m ({next_dt.strftime('%H:%M')})"
        except Exception as e:
            next_scheduled = f"Every {interval_minutes} min (calc error)"
    elif interval_minutes:
        next_scheduled = f"Every {interval_minutes} minutes"

    return {
        "schedule": schedule,
        "heartbeat": heartbeat,
        "todos": todos,
        "pending_count": len([t for t in todos if not t["done"]]),
        "completed_count": len([t for t in todos if t["done"]]),
        "last_run": last_run,
        "next_scheduled": next_scheduled
    }


@app.post("/api/heartbeat/ran")
async def record_heartbeat_run():
    """Record that heartbeat just ran (call this from heartbeat skill)."""
    from datetime import datetime
    timestamp = datetime.now().isoformat()
    cmd = f"echo '{timestamp}' > /home/chris_hadley/peterbot/.heartbeat_last_run"
    stdout, stderr, code = run_wsl_command(cmd)
    if code == 0:
        return {"status": "recorded", "timestamp": timestamp}
    return {"status": "error", "error": stderr}


@app.get("/api/skills")
async def list_skills():
    """List available Peterbot skills."""
    skills_path = "/home/chris_hadley/peterbot/.claude/skills"
    cmd = f"find {skills_path} -maxdepth 2 -name 'SKILL.md' 2>/dev/null"
    stdout, stderr, code = run_wsl_command(cmd)

    skills = []
    if stdout.strip():
        for path in stdout.strip().split('\n'):
            if path:
                # Extract skill name from path
                parts = path.split('/')
                name = parts[-2] if len(parts) > 1 else 'unknown'
                skills.append({
                    "name": name,
                    "path": path
                })

    return {"skills": skills, "count": len(skills)}


@app.get("/api/skill/{name}")
async def get_skill(name: str):
    """Get skill content by name."""
    path = f"/home/chris_hadley/peterbot/.claude/skills/{name}/SKILL.md"
    return read_wsl_file(path, tail_lines=0)


@app.post("/api/file/append/{file_type}/{file_name}")
async def append_to_file(file_type: str, file_name: str, content: str):
    """Append content to an .md file."""
    if file_type == "windows":
        if file_name not in KEY_FILES:
            raise HTTPException(404, "File not found in KEY_FILES")
        full_path = os.path.join(CONFIG["windows_project_path"], KEY_FILES[file_name])
        try:
            with open(full_path, 'a', encoding='utf-8') as f:
                f.write("\n" + content)
            return {"status": "success", "message": f"Appended to {file_name}"}
        except Exception as e:
            raise HTTPException(500, str(e))
    elif file_type == "wsl":
        if file_name not in WSL_FILES:
            raise HTTPException(404, "File not found in WSL_FILES")
        wsl_path = WSL_FILES[file_name]
        # Escape content for shell
        escaped = content.replace("'", "'\\''")
        cmd = f"echo '\n{escaped}' >> '{wsl_path}'"
        stdout, stderr, code = run_wsl_command(cmd)
        if code == 0:
            return {"status": "success", "message": f"Appended to {file_name}"}
        raise HTTPException(500, stderr or "Failed to append")
    else:
        raise HTTPException(400, "Invalid file type")


@app.put("/api/file/write/{file_type}/{file_name}")
async def write_file(file_type: str, file_name: str, content: str):
    """Write/replace content of an .md file."""
    if file_type == "windows":
        if file_name not in KEY_FILES:
            raise HTTPException(404, "File not found in KEY_FILES")
        full_path = os.path.join(CONFIG["windows_project_path"], KEY_FILES[file_name])
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"status": "success", "message": f"Wrote to {file_name}"}
        except Exception as e:
            raise HTTPException(500, str(e))
    elif file_type == "wsl":
        if file_name not in WSL_FILES:
            raise HTTPException(404, "File not found in WSL_FILES")
        wsl_path = WSL_FILES[file_name]
        # Use printf for multi-line content
        escaped = content.replace("'", "'\\''").replace("\n", "\\n")
        cmd = f"printf '%b' '{escaped}' > '{wsl_path}'"
        stdout, stderr, code = run_wsl_command(cmd, timeout=15)
        if code == 0:
            return {"status": "success", "message": f"Wrote to {file_name}"}
        raise HTTPException(500, stderr or "Failed to write")
    else:
        raise HTTPException(400, "Invalid file type")


# ============================================================================
# Peter State and Fun Features
# ============================================================================

import random

INSPIRATIONAL_QUOTES = [
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Innovation distinguishes between a leader and a follower. - Steve Jobs",
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    "It does not matter how slowly you go as long as you do not stop. - Confucius",
    "Everything you've ever wanted is on the other side of fear. - George Addair",
    "Success is not final, failure is not fatal: it is the courage to continue that counts. - Churchill",
    "The only impossible journey is the one you never begin. - Tony Robbins",
    "In the middle of difficulty lies opportunity. - Albert Einstein",
]

PETER_SONGS = [
    "🎵 I'm a little teapot, short and stout, here is my API, here is my route! 🎵",
    "🎶 We're no strangers to code... You know the rules, and so do I! 🎶",
    "🎵 Hello from the other side... of localhost:8100! 🎵",
    "🎶 Never gonna give you up, never gonna let the server down! 🎶",
    "🎵 I got the bytes, I got the bits, I got the APIs for days! 🎵",
    "🎶 Don't stop believing... in good error handling! 🎶",
    "🎵 We will, we will, COMPILE YOU! 🎵",
    "🎶 Every request you make, every call you break, I'll be watching you... (in the logs) 🎶",
    "🎵 Let it flow, let it flow, can't hold the data back anymore! 🎵",
    "🎶 Async all night long! 🎶",
]

PETER_FACTS = [
    "Fun fact: I process about 1,000 requests per cup of virtual coffee ☕",
    "Did you know? My favorite color is #e94560 (that's my accent color!)",
    "Peter's tip: Always test your APIs before production. Trust me.",
    "Random thought: Is a WebSocket just a very chatty HTTP request? 🤔",
    "Fun fact: I've been running for {uptime} without a single existential crisis!",
    "Peter says: CORS issues are just servers playing hard to get 💕",
    "Quick tip: When in doubt, console.log it out!",
    "Did you know? I dream in JSON format 💤",
]


@app.get("/api/peter/state")
async def get_peter_state():
    """Get Peter's current activity state for the animated logo."""
    try:
        # Check tmux session activity
        cmd = "tmux capture-pane -t claude-peterbot -p | tail -5"
        stdout, stderr, code = run_wsl_command(cmd)

        state = "idle"
        message = "Standing by"
        mood = "content"

        if code != 0 or not stdout.strip():
            state = "sleeping"
            message = "Session not active"
            mood = "sleepy"
        else:
            content = stdout.lower()
            if "thinking" in content or "pondering" in content or "considering" in content:
                state = "thinking"
                message = "Deep in thought..."
                mood = "curious"
            elif "searching" in content or "looking" in content or "finding" in content:
                state = "searching"
                message = "Hunting for answers"
                mood = "focused"
            elif "writing" in content or "creating" in content or "generating" in content:
                state = "working"
                message = "Making magic happen"
                mood = "happy"
            elif "error" in content or "failed" in content or "exception" in content:
                state = "error"
                message = "Hit a snag!"
                mood = "concerned"
            elif "success" in content or "complete" in content or "done" in content:
                state = "success"
                message = "Mission accomplished!"
                mood = "proud"
            elif "waiting" in content or ">" in content or "❯" in content:
                state = "ready"
                message = "Ready for action"
                mood = "eager"
            else:
                state = "active"
                message = "Busy at work"
                mood = "determined"

        return {
            "state": state,
            "message": message,
            "mood": mood,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "state": "unknown",
            "message": "Can't reach Peter",
            "mood": "confused",
            "timestamp": datetime.now().isoformat()
        }


@app.get("/api/peter/quote")
async def get_peter_quote():
    """Get a random quote, song, or fun fact from Peter."""
    category = random.choice(["quote", "song", "fact"])

    if category == "quote":
        text = random.choice(INSPIRATIONAL_QUOTES)
        emoji = "💡"
    elif category == "song":
        text = random.choice(PETER_SONGS)
        emoji = "🎤"
    else:
        # For uptime fact, calculate actual uptime
        text = random.choice(PETER_FACTS)
        if "{uptime}" in text:
            text = text.replace("{uptime}", "a while now")
        emoji = "🤓"

    return {
        "category": category,
        "text": text,
        "emoji": emoji,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# WebSocket for real-time updates
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send status updates every 5 seconds
            status = await get_system_status()
            await websocket.send_json({"type": "status", "data": status})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================================
# Dashboard HTML
# ============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Peter Dashboard</title>
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --accent: #e94560;
            --success: #4ade80;
            --warning: #fbbf24;
            --error: #ef4444;
            --border: #333;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        .header {
            background: var(--bg-secondary);
            padding: 1rem 2rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 {
            font-size: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .header h1 .icon {
            font-size: 1.8rem;
        }

        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }

        .status-up { background: var(--success); }
        .status-down { background: var(--error); }
        .status-unknown { background: var(--warning); }

        .main {
            display: grid;
            grid-template-columns: 280px 1fr;
            min-height: calc(100vh - 60px);
        }

        .sidebar {
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            padding: 1rem;
        }

        .sidebar-section {
            margin-bottom: 1.5rem;
        }

        .sidebar-section h3 {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            letter-spacing: 0.05em;
        }

        .nav-item {
            display: flex;
            align-items: center;
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            cursor: pointer;
            margin-bottom: 0.25rem;
            transition: background 0.2s;
        }

        .nav-item:hover {
            background: var(--bg-card);
        }

        .nav-item.active {
            background: var(--accent);
        }

        .content {
            padding: 1.5rem;
            overflow-y: auto;
        }

        .grid {
            display: grid;
            gap: 1rem;
        }

        .grid-2 { grid-template-columns: repeat(2, 1fr); }
        .grid-3 { grid-template-columns: repeat(3, 1fr); }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }

        @media (max-width: 1200px) {
            .grid-4 { grid-template-columns: repeat(2, 1fr); }
            .grid-3 { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 768px) {
            .main { grid-template-columns: 1fr; }
            .sidebar { display: none; }
            .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr; }
        }

        .card {
            background: var(--bg-card);
            border-radius: 8px;
            padding: 1.25rem;
            border: 1px solid var(--border);
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .card-title {
            font-size: 0.9rem;
            font-weight: 600;
        }

        .card-value {
            font-size: 1.5rem;
            font-weight: 700;
        }

        .btn {
            padding: 0.5rem 1rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: opacity 0.2s;
        }

        .btn:hover { opacity: 0.9; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .btn-primary { background: var(--accent); color: white; }
        .btn-secondary { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border); }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.75rem; }

        .service-card {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .service-info {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .service-icon {
            width: 40px;
            height: 40px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
        }

        .service-details h4 {
            font-size: 0.9rem;
            margin-bottom: 0.25rem;
        }

        .service-details span {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .code-viewer {
            background: #0d1117;
            border-radius: 6px;
            overflow: hidden;
        }

        .code-header {
            background: #161b22;
            padding: 0.75rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
        }

        .code-content {
            padding: 1rem;
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
        }

        .code-content pre {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.8rem;
            line-height: 1.5;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .tabs {
            display: flex;
            gap: 0.25rem;
            margin-bottom: 1rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 0.5rem;
        }

        .tab {
            padding: 0.5rem 1rem;
            cursor: pointer;
            border-radius: 6px 6px 0 0;
            transition: background 0.2s;
        }

        .tab:hover { background: var(--bg-card); }
        .tab.active { background: var(--accent); }

        .endpoint-list {
            max-height: 400px;
            overflow-y: auto;
        }

        .endpoint-item {
            display: flex;
            align-items: center;
            padding: 0.5rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
        }

        .endpoint-method {
            padding: 0.15rem 0.4rem;
            border-radius: 3px;
            font-size: 0.7rem;
            font-weight: 600;
            margin-right: 0.75rem;
            min-width: 50px;
            text-align: center;
        }

        .method-get { background: #22c55e; color: white; }
        .method-post { background: #3b82f6; color: white; }
        .method-put { background: #f59e0b; color: white; }
        .method-delete { background: #ef4444; color: white; }

        .endpoint-path {
            font-family: monospace;
            flex: 1;
        }

        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s;
            z-index: 1000;
        }

        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }

        .toast.success { border-color: var(--success); }
        .toast.error { border-color: var(--error); }

        /* Restart Confirmation Modal */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 2000;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s;
        }

        .modal-overlay.show {
            opacity: 1;
            visibility: visible;
        }

        .modal {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 2rem;
            min-width: 400px;
            max-width: 500px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
            transform: scale(0.9);
            transition: transform 0.3s;
        }

        .modal-overlay.show .modal {
            transform: scale(1);
        }

        .modal-header {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }

        .modal-icon {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
        }

        .modal-icon.loading {
            background: var(--accent);
            width: 50px;
            height: 50px;
            border: none;
            animation: none;
        }

        .modal-icon.loading::after {
            content: '';
            width: 30px;
            height: 30px;
            border: 3px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        .modal-icon.success { background: var(--success); }
        .modal-icon.error { background: var(--error); }

        .modal-title {
            font-size: 1.2rem;
            font-weight: 600;
        }

        .modal-body {
            margin-bottom: 1.5rem;
        }

        .service-status-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem;
            background: var(--bg-secondary);
            border-radius: 6px;
            margin-bottom: 0.5rem;
        }

        .service-status-item .status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse-dot 1s ease-in-out infinite;
        }

        .status-dot.pending { background: var(--warning); }
        .status-dot.success { background: var(--success); animation: none; }
        .status-dot.error { background: var(--error); animation: none; }

        @keyframes pulse-dot {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 0.5rem;
        }

        /* Memory Tabs */
        .memory-tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            border-bottom: 2px solid var(--border);
            padding-bottom: 0.5rem;
        }

        .memory-tab {
            padding: 0.5rem 1rem;
            cursor: pointer;
            border-radius: 6px 6px 0 0;
            transition: all 0.2s;
            border: 1px solid transparent;
            border-bottom: none;
        }

        .memory-tab:hover {
            background: var(--bg-card);
        }

        .memory-tab.active {
            background: var(--accent);
            border-color: var(--accent);
        }

        .memory-tab .tab-icon {
            margin-right: 0.5rem;
        }

        .loading {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid var(--text-secondary);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .memory-item {
            padding: 0.75rem;
            border-bottom: 1px solid var(--border);
        }

        .memory-item:last-child { border-bottom: none; }

        .memory-type {
            font-size: 0.7rem;
            padding: 0.1rem 0.4rem;
            border-radius: 3px;
            background: var(--accent);
            margin-right: 0.5rem;
        }

        .memory-time {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .memory-content {
            margin-top: 0.5rem;
            font-size: 0.85rem;
            line-height: 1.4;
        }

        .session-card {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem;
            background: var(--bg-secondary);
            border-radius: 6px;
            margin-bottom: 0.5rem;
        }

        .session-name {
            font-family: monospace;
            font-weight: 600;
        }

        .session-meta {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        #last-update {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        /* Peter Animated Logo Styles */
        .peter-logo-container {
            display: flex;
            align-items: center;
            gap: 1rem;
            cursor: pointer;
            transition: transform 0.3s;
        }

        .peter-logo-container:hover {
            transform: scale(1.05);
        }

        .peter-logo {
            width: 50px;
            height: 55px;
            border-radius: 8px;
            background: linear-gradient(180deg, #3a3a4a 0%, #2a2a3a 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            animation: float 3s ease-in-out infinite;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.1);
            transition: all 0.5s ease;
            border: 2px solid #4a4a5a;
        }

        .peter-logo::before {
            content: '';
            position: absolute;
            top: -8px;
            left: 50%;
            transform: translateX(-50%);
            width: 4px;
            height: 8px;
            background: #666;
            border-radius: 2px 2px 0 0;
        }

        .peter-logo::after {
            content: '';
            position: absolute;
            top: -12px;
            left: 50%;
            transform: translateX(-50%);
            width: 8px;
            height: 8px;
            background: var(--accent);
            border-radius: 50%;
            animation: antenna-blink 2s ease-in-out infinite;
            box-shadow: 0 0 10px var(--accent);
        }

        @keyframes antenna-blink {
            0%, 100% { opacity: 1; box-shadow: 0 0 10px var(--accent); }
            50% { opacity: 0.4; box-shadow: 0 0 5px var(--accent); }
        }

        .peter-face {
            position: relative;
            width: 100%;
            height: 100%;
        }

        .peter-visor {
            position: absolute;
            top: 8px;
            left: 50%;
            transform: translateX(-50%);
            width: 40px;
            height: 18px;
            background: linear-gradient(180deg, #1a1a2e 0%, #0a0a1e 100%);
            border-radius: 4px;
            border: 1px solid #5a5a6a;
            overflow: hidden;
        }

        .peter-eyes {
            display: flex;
            justify-content: center;
            gap: 8px;
            padding-top: 4px;
        }

        .peter-eye {
            width: 10px;
            height: 10px;
            background: #00ff88;
            border-radius: 2px;
            position: relative;
            animation: led-glow 2s ease-in-out infinite;
            box-shadow: 0 0 8px #00ff88;
        }

        @keyframes led-glow {
            0%, 100% { box-shadow: 0 0 8px #00ff88; }
            50% { box-shadow: 0 0 15px #00ff88, 0 0 20px #00ff88; }
        }

        .peter-eye.scanning {
            animation: led-scan 0.5s ease-in-out infinite;
        }

        @keyframes led-scan {
            0%, 100% { background: #00ff88; }
            50% { background: #00ffff; }
        }

        .peter-mouth {
            position: absolute;
            bottom: 8px;
            left: 50%;
            transform: translateX(-50%);
            width: 24px;
            height: 4px;
            background: #333;
            border-radius: 2px;
            overflow: hidden;
        }

        .peter-mouth::after {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 30%;
            background: var(--accent);
            animation: voice-bar 0.3s ease-in-out infinite;
        }

        @keyframes voice-bar {
            0%, 100% { width: 30%; }
            50% { width: 80%; }
        }

        .peter-ear {
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            width: 4px;
            height: 12px;
            background: #5a5a6a;
            border-radius: 2px;
        }

        .peter-ear.left { left: -3px; }
        .peter-ear.right { right: -3px; }

        /* Peter Robot States */
        .peter-logo.idle, .peter-logo.ready {
            border-color: #4ade80;
        }
        .peter-logo.idle::after, .peter-logo.ready::after {
            background: #4ade80;
            box-shadow: 0 0 10px #4ade80;
        }
        .peter-logo.idle .peter-eye, .peter-logo.ready .peter-eye {
            background: #4ade80;
            box-shadow: 0 0 8px #4ade80;
        }

        .peter-logo.thinking {
            border-color: #fbbf24;
            animation: float 3s ease-in-out infinite, robot-think 1s ease-in-out infinite;
        }
        .peter-logo.thinking::after {
            background: #fbbf24;
            box-shadow: 0 0 10px #fbbf24;
            animation: antenna-blink 0.5s ease-in-out infinite;
        }
        .peter-logo.thinking .peter-eye {
            background: #fbbf24;
            box-shadow: 0 0 8px #fbbf24;
            animation: led-scan 0.3s ease-in-out infinite;
        }

        @keyframes robot-think {
            0%, 100% { box-shadow: 0 4px 15px rgba(251, 191, 36, 0.3); }
            50% { box-shadow: 0 4px 25px rgba(251, 191, 36, 0.6); }
        }

        .peter-logo.working {
            border-color: #3b82f6;
            animation: float 3s ease-in-out infinite;
        }
        .peter-logo.working::after {
            background: #3b82f6;
            box-shadow: 0 0 10px #3b82f6;
            animation: antenna-blink 0.3s ease-in-out infinite;
        }
        .peter-logo.working .peter-eye {
            background: #3b82f6;
            box-shadow: 0 0 8px #3b82f6;
        }
        .peter-logo.working .peter-mouth::after {
            animation: voice-bar 0.15s ease-in-out infinite;
        }

        .peter-logo.searching {
            border-color: #8b5cf6;
            animation: float 3s ease-in-out infinite, wobble 0.5s ease-in-out infinite;
        }
        .peter-logo.searching::after {
            background: #8b5cf6;
            box-shadow: 0 0 10px #8b5cf6;
        }
        .peter-logo.searching .peter-eye {
            background: #8b5cf6;
            box-shadow: 0 0 8px #8b5cf6;
            animation: led-scan 0.2s ease-in-out infinite;
        }

        .peter-logo.error {
            border-color: #ef4444;
            animation: shake 0.5s ease-in-out infinite;
        }
        .peter-logo.error::after {
            background: #ef4444;
            box-shadow: 0 0 10px #ef4444;
            animation: none;
        }
        .peter-logo.error .peter-eye {
            background: #ef4444;
            box-shadow: 0 0 8px #ef4444;
            animation: error-flash 0.3s ease-in-out infinite;
        }

        @keyframes error-flash {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        .peter-logo.success {
            border-color: #10b981;
            animation: float 3s ease-in-out infinite, bounce-happy 0.5s ease-in-out;
        }
        .peter-logo.success::after {
            background: #10b981;
            box-shadow: 0 0 15px #10b981;
        }
        .peter-logo.success .peter-eye {
            background: #10b981;
            box-shadow: 0 0 12px #10b981;
        }

        .peter-logo.sleeping {
            border-color: #6b7280;
            animation: float 6s ease-in-out infinite;
        }
        .peter-logo.sleeping::after {
            background: #6b7280;
            box-shadow: 0 0 5px #6b7280;
            animation: none;
            opacity: 0.5;
        }
        .peter-logo.sleeping .peter-eye {
            background: #6b7280;
            box-shadow: 0 0 3px #6b7280;
            height: 3px;
            animation: none;
        }

        .peter-logo.singing {
            border-color: #ec4899;
            animation: float 3s ease-in-out infinite, dance 0.3s ease-in-out infinite;
        }
        .peter-logo.singing::after {
            background: #ec4899;
            box-shadow: 0 0 15px #ec4899;
            animation: antenna-blink 0.2s ease-in-out infinite;
        }
        .peter-logo.singing .peter-eye {
            background: #ec4899;
            box-shadow: 0 0 10px #ec4899;
            animation: led-scan 0.15s ease-in-out infinite;
        }
        .peter-logo.singing .peter-mouth::after {
            animation: voice-bar 0.1s ease-in-out infinite;
            background: #ec4899;
        }

        /* Animations */
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-5px); }
        }

        @keyframes pulse {
            0%, 100% { box-shadow: 0 4px 15px rgba(251, 191, 36, 0.4); }
            50% { box-shadow: 0 4px 25px rgba(251, 191, 36, 0.8); }
        }

        @keyframes blink {
            0%, 45%, 55%, 100% { transform: scaleY(1); }
            50% { transform: scaleY(0.1); }
        }

        @keyframes look-around {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(2px); }
            75% { transform: translateX(-2px); }
        }

        @keyframes look-up {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-2px); }
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-3px); }
            75% { transform: translateX(3px); }
        }

        @keyframes wobble {
            0%, 100% { transform: rotate(0deg); }
            25% { transform: rotate(-5deg); }
            75% { transform: rotate(5deg); }
        }

        @keyframes spin-subtle {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        @keyframes bounce-happy {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.15); }
        }

        @keyframes dance {
            0%, 100% { transform: translateX(0) rotate(0deg); }
            25% { transform: translateX(-3px) rotate(-5deg); }
            75% { transform: translateX(3px) rotate(5deg); }
        }

        @keyframes sing {
            0%, 100% { height: 10px; }
            50% { height: 6px; }
        }

        .peter-status h1 {
            font-size: 1.5rem;
            margin: 0;
        }

        .peter-message {
            font-size: 0.75rem;
            color: var(--text-secondary);
            display: block;
        }

        .header-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 0.5rem;
        }

        /* Quote Bubble */
        .quote-bubble {
            max-width: 300px;
            background: var(--bg-card);
            border: 1px solid var(--accent);
            border-radius: 12px;
            padding: 1rem;
            position: relative;
            animation: fadeInUp 0.3s ease-out;
            box-shadow: 0 4px 15px rgba(233, 69, 96, 0.2);
        }

        .quote-bubble::before {
            content: '';
            position: absolute;
            right: 20px;
            top: -8px;
            border-left: 8px solid transparent;
            border-right: 8px solid transparent;
            border-bottom: 8px solid var(--accent);
        }

        .quote-bubble.hidden {
            display: none;
        }

        .quote-text {
            font-size: 0.85rem;
            line-height: 1.4;
            color: var(--text-primary);
        }

        .quote-emoji {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
            display: block;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="peter-logo-container" onclick="showPeterQuote()">
            <div class="peter-logo" id="peter-logo">
                <div class="peter-ear left"></div>
                <div class="peter-ear right"></div>
                <div class="peter-face">
                    <div class="peter-visor">
                        <div class="peter-eyes">
                            <div class="peter-eye left"></div>
                            <div class="peter-eye right"></div>
                        </div>
                    </div>
                    <div class="peter-mouth"></div>
                </div>
            </div>
            <div class="peter-status">
                <h1>Peter Dashboard</h1>
                <span id="peter-message" class="peter-message">Initializing systems...</span>
            </div>
        </div>
        <div class="header-right">
            <span id="last-update">Last update: --</span>
            <div id="quote-bubble" class="quote-bubble hidden"></div>
        </div>
    </div>

    <div class="main">
        <div class="sidebar">
            <div class="sidebar-section">
                <h3>Overview</h3>
                <div class="nav-item active" data-view="dashboard">
                    📊 Dashboard
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Monitoring</h3>
                <div class="nav-item" data-view="context">
                    📝 Context Viewer
                </div>
                <div class="nav-item" data-view="captures">
                    🖥️ Screen Captures
                </div>
                <div class="nav-item" data-view="memory">
                    🧠 Memory
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Configuration</h3>
                <div class="nav-item" data-view="files">
                    📁 Key Files
                </div>
                <div class="nav-item" data-view="endpoints">
                    🔌 API Endpoints
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Sessions</h3>
                <div class="nav-item" data-view="sessions">
                    💻 Tmux Sessions
                </div>
            </div>

            <div class="sidebar-section">
                <h3>Proactive</h3>
                <div class="nav-item" data-view="heartbeat">
                    💓 Heartbeat
                </div>
                <div class="nav-item" data-view="schedule">
                    📅 Schedule
                </div>
                <div class="nav-item" data-view="skills">
                    🛠️ Skills
                </div>
            </div>
        </div>

        <div class="content" id="content">
            <!-- Content loaded dynamically -->
        </div>
    </div>

    <div class="toast" id="toast"></div>

    <!-- Restart Confirmation Modal -->
    <div class="modal-overlay" id="restart-modal">
        <div class="modal">
            <div class="modal-header">
                <div class="modal-icon loading" id="modal-icon"></div>
                <div>
                    <div class="modal-title" id="modal-title">Restarting Services</div>
                </div>
            </div>
            <div class="modal-body" id="modal-body">
                <div class="service-status-item">
                    <span>Hadley API</span>
                    <div class="status">
                        <div class="status-dot pending" id="status-hadley"></div>
                        <span id="status-hadley-text">Pending...</span>
                    </div>
                </div>
                <div class="service-status-item">
                    <span>Discord Bot</span>
                    <div class="status">
                        <div class="status-dot pending" id="status-discord"></div>
                        <span id="status-discord-text">Pending...</span>
                    </div>
                </div>
                <div class="service-status-item">
                    <span>Peterbot Session</span>
                    <div class="status">
                        <div class="status-dot pending" id="status-peterbot"></div>
                        <span id="status-peterbot-text">Pending...</span>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" id="modal-close" onclick="closeRestartModal()" style="display: none;">Close</button>
            </div>
        </div>
    </div>

    <script>
        // State
        let currentView = 'dashboard';
        let statusData = null;
        let ws = null;
        let peterState = 'idle';
        let quoteTimeout = null;

        // Peter State Updates
        async function updatePeterState() {
            try {
                const data = await api('/peter/state');
                if (data && data.state) {
                    peterState = data.state;
                    const logo = document.getElementById('peter-logo');
                    const message = document.getElementById('peter-message');

                    // Update logo class
                    logo.className = 'peter-logo ' + data.state;
                    message.textContent = data.message;

                    // Occasionally trigger singing mode for fun
                    if (Math.random() < 0.02) { // 2% chance each poll
                        triggerSinging();
                    }
                }
            } catch (e) {
                console.log('Peter state update failed:', e);
            }
        }

        function triggerSinging() {
            const logo = document.getElementById('peter-logo');
            const message = document.getElementById('peter-message');
            const originalState = peterState;
            const originalMessage = message.textContent;

            logo.className = 'peter-logo singing';
            showPeterQuote('song');

            setTimeout(() => {
                logo.className = 'peter-logo ' + originalState;
                message.textContent = originalMessage;
            }, 5000);
        }

        async function showPeterQuote(category = null) {
            try {
                const url = category ? `/peter/quote?type=${category}` : '/peter/quote';
                const data = await api('/peter/quote');
                if (data && data.text) {
                    const bubble = document.getElementById('quote-bubble');
                    bubble.innerHTML = `
                        <span class="quote-emoji">${data.emoji}</span>
                        <span class="quote-text">${escapeHtml(data.text)}</span>
                    `;
                    bubble.classList.remove('hidden');

                    // Auto-hide after 8 seconds
                    if (quoteTimeout) clearTimeout(quoteTimeout);
                    quoteTimeout = setTimeout(() => {
                        bubble.classList.add('hidden');
                    }, 8000);

                    // If it's a song, trigger singing animation
                    if (data.category === 'song') {
                        const logo = document.getElementById('peter-logo');
                        const message = document.getElementById('peter-message');
                        logo.className = 'peter-logo singing';
                        message.textContent = '🎤 Singing...';

                        setTimeout(() => {
                            updatePeterState(); // Reset to actual state
                        }, 5000);
                    }
                }
            } catch (e) {
                console.log('Quote fetch failed:', e);
            }
        }

        // Random quote timer (every 2-5 minutes)
        function scheduleRandomQuote() {
            const delay = (120 + Math.random() * 180) * 1000; // 2-5 minutes
            setTimeout(() => {
                if (Math.random() < 0.5) { // 50% chance to show quote
                    showPeterQuote();
                }
                scheduleRandomQuote(); // Schedule next one
            }, delay);
        }

        // Toast notifications
        function showToast(message, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast show ' + type;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        // API calls
        async function api(endpoint, options = {}) {
            try {
                const response = await fetch('/api' + endpoint, options);
                return await response.json();
            } catch (e) {
                console.error('API error:', e);
                showToast('API error: ' + e.message, 'error');
                return null;
            }
        }

        // Restart service
        async function restartService(service) {
            if (!confirm(`Restart ${service}?`)) return;

            const btn = event.target;
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span>';

            const result = await api(`/restart/${service}`, { method: 'POST' });
            if (result && result.status === 'restarting') {
                showToast(result.message, 'success');
            } else {
                showToast('Restart failed', 'error');
            }

            btn.disabled = false;
            btn.textContent = 'Restart';

            // Refresh status after a delay
            setTimeout(refreshStatus, 3000);
        }

        // Restart all services with modal
        async function restartAll() {
            if (!confirm('Restart ALL services? This will restart Hadley API, Discord Bot, and Peterbot session.')) return;

            // Show modal
            showRestartModal('all');

            const result = await api('/restart-all', { method: 'POST' });

            if (result && result.status === 'restarting') {
                // Start checking services
                await checkServicesAfterRestart();
            } else {
                updateModalError('Restart failed: ' + (result?.error || 'Unknown error'));
            }
        }

        function showRestartModal(type) {
            const modal = document.getElementById('restart-modal');
            const title = document.getElementById('modal-title');
            const icon = document.getElementById('modal-icon');
            const closeBtn = document.getElementById('modal-close');

            title.textContent = type === 'all' ? 'Restarting All Services' : 'Restarting Service';
            icon.className = 'modal-icon loading';
            icon.innerHTML = '';
            closeBtn.style.display = 'none';

            // Reset all status dots
            ['hadley', 'discord', 'peterbot'].forEach(s => {
                document.getElementById('status-' + s).className = 'status-dot pending';
                document.getElementById('status-' + s + '-text').textContent = 'Restarting...';
            });

            modal.classList.add('show');
        }

        function closeRestartModal() {
            document.getElementById('restart-modal').classList.remove('show');
        }

        async function checkServicesAfterRestart() {
            // Wait a bit for services to start shutting down
            await new Promise(r => setTimeout(r, 2000));

            let attempts = 0;
            const maxAttempts = 15;
            let allSuccess = false;

            while (attempts < maxAttempts && !allSuccess) {
                attempts++;
                await new Promise(r => setTimeout(r, 2000));

                try {
                    const status = await api('/status');
                    if (status && status.services) {
                        const services = status.services;

                        // Update Hadley API
                        if (services.hadley_api?.status === 'up') {
                            document.getElementById('status-hadley').className = 'status-dot success';
                            document.getElementById('status-hadley-text').textContent = 'Running (' + services.hadley_api.latency_ms + 'ms)';
                        }

                        // Update Discord Bot
                        if (services.discord_bot?.status === 'up') {
                            document.getElementById('status-discord').className = 'status-dot success';
                            document.getElementById('status-discord-text').textContent = 'Running';
                        }

                        // Update Peterbot Session
                        if (services.peterbot_session?.status === 'up') {
                            document.getElementById('status-peterbot').className = 'status-dot success';
                            document.getElementById('status-peterbot-text').textContent = 'Running';
                        }

                        // Check if all are up
                        allSuccess = services.hadley_api?.status === 'up' &&
                                    services.discord_bot?.status === 'up' &&
                                    services.peterbot_session?.status === 'up';
                    }
                } catch (e) {
                    console.log('Status check attempt ' + attempts + ' failed');
                }
            }

            // Update modal to show completion
            const icon = document.getElementById('modal-icon');
            const title = document.getElementById('modal-title');
            const closeBtn = document.getElementById('modal-close');

            if (allSuccess) {
                icon.className = 'modal-icon success';
                icon.innerHTML = '✓';
                title.textContent = 'All Services Running';
            } else {
                icon.className = 'modal-icon error';
                icon.innerHTML = '!';
                title.textContent = 'Some Services May Need Attention';
            }

            closeBtn.style.display = 'block';
            refreshStatus();
        }

        function updateModalError(message) {
            const icon = document.getElementById('modal-icon');
            const title = document.getElementById('modal-title');
            const closeBtn = document.getElementById('modal-close');

            icon.className = 'modal-icon error';
            icon.innerHTML = '✗';
            title.textContent = message;
            closeBtn.style.display = 'block';
        }

        // Refresh status
        async function refreshStatus() {
            statusData = await api('/status');
            if (statusData) {
                document.getElementById('last-update').textContent =
                    'Last update: ' + new Date().toLocaleTimeString();
                if (currentView === 'dashboard') renderDashboard();
            }
        }

        // Render functions
        function getStatusClass(status) {
            if (status === 'up') return 'status-up';
            if (status === 'down') return 'status-down';
            return 'status-unknown';
        }

        function renderDashboard() {
            if (!statusData) return;

            const services = statusData.services;
            const content = document.getElementById('content');

            content.innerHTML = `
                <h2 style="margin-bottom: 1.5rem;">System Status</h2>

                <div class="grid grid-4" style="margin-bottom: 1.5rem;">
                    <div class="card service-card">
                        <div class="service-info">
                            <div class="service-icon" style="background: ${services.hadley_api.status === 'up' ? 'var(--success)' : 'var(--error)'}">
                                🌐
                            </div>
                            <div class="service-details">
                                <h4>Hadley API</h4>
                                <span>${services.hadley_api.status === 'up' ? services.hadley_api.latency_ms + 'ms' : services.hadley_api.error || 'Down'}</span>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="restartService('hadley_api')">Restart</button>
                    </div>

                    <div class="card service-card">
                        <div class="service-info">
                            <div class="service-icon" style="background: ${services.discord_bot.status === 'up' ? 'var(--success)' : 'var(--error)'}">
                                🤖
                            </div>
                            <div class="service-details">
                                <h4>Discord Bot</h4>
                                <span>${services.discord_bot.status === 'up' ? 'Running' : 'Stopped'}</span>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="restartService('discord_bot')">Restart</button>
                    </div>

                    <div class="card service-card">
                        <div class="service-info">
                            <div class="service-icon" style="background: ${services.peterbot_session.status === 'up' ? 'var(--success)' : 'var(--error)'}">
                                💻
                            </div>
                            <div class="service-details">
                                <h4>Peterbot Session</h4>
                                <span>${services.peterbot_session.status === 'up' ? (services.peterbot_session.attached ? 'Attached' : 'Running') : 'Stopped'}</span>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="restartService('peterbot_session')">Restart</button>
                    </div>

                    <div class="card service-card">
                        <div class="service-info">
                            <div class="service-icon" style="background: ${services.claude_mem.status === 'up' ? 'var(--success)' : 'var(--error)'}">
                                🧠
                            </div>
                            <div class="service-details">
                                <h4>Claude-Mem</h4>
                                <span>${services.claude_mem.status === 'up' ? services.claude_mem.latency_ms + 'ms' : services.claude_mem.error || 'Down'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-2">
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Tmux Sessions</span>
                        </div>
                        <div id="sessions-list">
                            ${statusData.tmux_sessions.length === 0 ? '<p style="color: var(--text-secondary)">No sessions</p>' :
                              statusData.tmux_sessions.map(s => `
                                <div class="session-card">
                                    <div>
                                        <div class="session-name">${s.name}</div>
                                        <div class="session-meta">${s.windows} window(s), ${s.attached ? 'attached' : 'detached'}</div>
                                    </div>
                                    <button class="btn btn-sm btn-secondary" onclick="viewSession('${s.name}')">View</button>
                                </div>
                              `).join('')}
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Quick Actions</span>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <button class="btn btn-primary" onclick="switchView('context')">View Current Context</button>
                            <button class="btn btn-secondary" onclick="switchView('captures')">View Screen Captures</button>
                            <button class="btn btn-secondary" onclick="switchView('files')">Edit Key Files</button>
                            <button class="btn btn-secondary" onclick="switchView('endpoints')">Browse API Endpoints</button>
                            <button class="btn btn-secondary" style="margin-top: 0.5rem; background: var(--error); color: white;" onclick="restartAll()">Restart All Services</button>
                        </div>
                    </div>
                </div>
            `;
        }

        async function renderContext() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading context...</h2>';

            const data = await api('/context');

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Current Context</h2>
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    This is the context.md file being sent to Claude Code with each message.
                </p>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>context.md</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">
                            ${data.exists ? `${data.size} bytes, modified ${new Date(data.modified).toLocaleString()}` : 'File not found'}
                        </span>
                    </div>
                    <div class="code-content">
                        <pre>${data.exists ? escapeHtml(data.content) : 'Context file not found or empty'}</pre>
                    </div>
                </div>
                <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="renderContext()">Refresh</button>
            `;
        }

        async function renderCaptures() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading captures...</h2>';

            const data = await api('/captures');

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Recent Screen Captures</h2>
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    Raw screen captures for debugging response extraction.
                </p>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>raw_capture.log</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">
                            ${data.exists ? 'Last 200 lines' : 'File not found'}
                        </span>
                    </div>
                    <div class="code-content" style="max-height: 600px;">
                        <pre>${data.exists ? escapeHtml(data.content) : 'No captures found'}</pre>
                    </div>
                </div>
                <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="renderCaptures()">Refresh</button>
            `;
        }

        let currentMemoryTab = 'peter';

        async function renderMemory() {
            const content = document.getElementById('content');
            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Memory Systems</h2>
                <div class="memory-tabs">
                    <div class="memory-tab ${currentMemoryTab === 'peter' ? 'active' : ''}" onclick="switchMemoryTab('peter')">
                        <span class="tab-icon">🤖</span>Peter-Mem
                    </div>
                    <div class="memory-tab ${currentMemoryTab === 'claude' ? 'active' : ''}" onclick="switchMemoryTab('claude')">
                        <span class="tab-icon">🧠</span>Claude-Mem
                    </div>
                </div>
                <div id="memory-content">
                    <div class="card"><p style="color: var(--text-secondary);">Loading...</p></div>
                </div>
            `;

            await loadMemoryTab(currentMemoryTab);
        }

        async function switchMemoryTab(tab) {
            currentMemoryTab = tab;

            // Update tab styles
            document.querySelectorAll('.memory-tab').forEach(t => {
                t.classList.remove('active');
                if (t.textContent.toLowerCase().includes(tab)) {
                    t.classList.add('active');
                }
            });

            await loadMemoryTab(tab);
        }

        async function loadMemoryTab(tab) {
            const memoryContent = document.getElementById('memory-content');
            memoryContent.innerHTML = '<div class="card"><p style="color: var(--text-secondary);">Loading...</p></div>';

            const endpoint = tab === 'peter' ? '/memory/peter' : '/memory/claude';
            const data = await api(endpoint);

            let memoryHtml = '';
            if (data.error) {
                memoryHtml = `<p style="color: var(--error);">Error: ${data.error}</p>`;
            } else if (data.observations && data.observations.length > 0) {
                memoryHtml = data.observations.map(obs => `
                    <div class="memory-item">
                        <span class="memory-type">#${obs.id}</span>
                        <span class="memory-time">${obs.time || 'Unknown time'}</span>
                        <div class="memory-content">${escapeHtml(obs.title || 'No title')}</div>
                    </div>
                `).join('');
            } else {
                memoryHtml = '<p style="color: var(--text-secondary);">No recent memories found</p>';
            }

            const description = tab === 'peter'
                ? "Observations from Peter's personal interactions and context (peterbot project)."
                : "General observations from all Claude Code sessions.";

            memoryContent.innerHTML = `
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    ${description} (${data.count || 0} found)
                </p>
                <div class="card" style="max-height: 500px; overflow-y: auto;">
                    ${memoryHtml}
                </div>
                <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="loadMemoryTab('${tab}')">Refresh</button>
            `;
        }

        async function renderFiles() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading files...</h2>';

            const data = await api('/files');

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Key Files</h2>
                <div class="grid grid-2">
                    ${data.files.map(f => `
                        <div class="card" style="cursor: pointer;" onclick="viewFile('${f.type}', '${f.name}')">
                            <div class="card-header">
                                <span class="card-title">${f.name}</span>
                                <span class="status-indicator ${f.exists ? 'status-up' : 'status-down'}"></span>
                            </div>
                            <p style="font-size: 0.8rem; color: var(--text-secondary); font-family: monospace;">
                                ${f.path}
                            </p>
                            <p style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">
                                ${f.modified ? 'Modified: ' + new Date(f.modified).toLocaleString() : 'Not found'}
                            </p>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        async function viewFile(type, name) {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading file...</h2>';

            const data = await api(`/file/${type}/${encodeURIComponent(name)}`);

            // Check if file is editable (.md files)
            const isEditable = name.endsWith('.md');

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>${name}</h2>
                    <div style="display: flex; gap: 0.5rem;">
                        ${isEditable ? `<button class="btn btn-primary" onclick="editFile('${type}', '${name}')">Edit</button>` : ''}
                        <button class="btn btn-secondary" onclick="renderFiles()">Back to Files</button>
                    </div>
                </div>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>${name}</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">
                            ${data.exists ? `${data.size} bytes` : 'File not found'}
                        </span>
                    </div>
                    <div class="code-content" style="max-height: 600px;">
                        <pre>${data.exists ? escapeHtml(data.content) : 'File not found'}</pre>
                    </div>
                </div>
            `;
        }

        async function renderEndpoints() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading endpoints...</h2>';

            const data = await api('/hadley/endpoints');

            let endpointsHtml = '';
            if (data.error) {
                endpointsHtml = `<p style="color: var(--error);">Error loading endpoints: ${data.error}</p>`;
            } else if (data.endpoints) {
                endpointsHtml = `
                    <div class="endpoint-list">
                        ${data.endpoints.map(e => `
                            <div class="endpoint-item">
                                <span class="endpoint-method method-${e.method.toLowerCase()}">${e.method}</span>
                                <span class="endpoint-path">${e.path}</span>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Hadley API Endpoints</h2>
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    ${data.endpoints ? data.endpoints.length + ' endpoints available' : 'Unable to load endpoints'}
                </p>
                <div class="card">
                    ${endpointsHtml}
                </div>
            `;
        }

        async function renderSessions() {
            if (!statusData) await refreshStatus();

            const content = document.getElementById('content');
            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">Tmux Sessions</h2>
                <div class="grid grid-2">
                    ${statusData.tmux_sessions.map(s => `
                        <div class="card">
                            <div class="card-header">
                                <span class="card-title">${s.name}</span>
                                <span class="status-indicator ${s.attached ? 'status-up' : 'status-unknown'}"></span>
                            </div>
                            <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                                ${s.windows} window(s), ${s.attached ? 'attached' : 'detached'}
                            </p>
                            <button class="btn btn-primary btn-sm" onclick="viewSession('${s.name}')">View Screen</button>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        async function viewSession(name) {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading session screen...</h2>';

            const data = await api(`/screen/${name}?lines=80`);

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>Session: ${name}</h2>
                    <div>
                        <button class="btn btn-secondary" onclick="viewSession('${name}')">Refresh</button>
                        <button class="btn btn-secondary" onclick="renderSessions()">Back</button>
                    </div>
                </div>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>tmux capture-pane</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">
                            Last 80 lines
                        </span>
                    </div>
                    <div class="code-content" style="max-height: 600px; background: #000; color: #0f0;">
                        <pre>${data.content ? escapeHtml(data.content) : data.error || 'No content'}</pre>
                    </div>
                </div>
            `;
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function renderHeartbeat() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading heartbeat...</h2>';

            const data = await api('/heartbeat/status');

            let todosHtml = '<p style="color: var(--text-secondary);">No to-do items found</p>';
            if (data.todos && data.todos.length > 0) {
                todosHtml = data.todos.map(item => `
                    <div style="padding: 0.75rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.2rem;">${item.done ? '✅' : '⬜'}</span>
                        <div style="flex: 1;">
                            <span style="color: ${item.done ? 'var(--text-secondary)' : 'var(--text-primary)'}; ${item.done ? 'text-decoration: line-through;' : ''}">
                                ${escapeHtml(item.text)}
                            </span>
                            ${item.timestamp ? `<span style="margin-left: 0.5rem; font-size: 0.75rem; color: var(--text-secondary); background: var(--bg-secondary); padding: 0.1rem 0.4rem; border-radius: 3px;">⏰ ${escapeHtml(item.timestamp)}</span>` : ''}
                        </div>
                    </div>
                `).join('');
            }

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">💓 Heartbeat System</h2>

                <div class="grid grid-3" style="margin-bottom: 1.5rem;">
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Status</span>
                        </div>
                        <div style="display: flex; gap: 2rem;">
                            <div>
                                <div style="font-size: 2rem; font-weight: bold; color: var(--warning);">${data.pending_count || 0}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Pending</div>
                            </div>
                            <div>
                                <div style="font-size: 2rem; font-weight: bold; color: var(--success);">${data.completed_count || 0}</div>
                                <div style="font-size: 0.8rem; color: var(--text-secondary);">Completed</div>
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Timing</span>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Last Run</div>
                                <div style="font-size: 0.9rem; color: var(--text-primary);">${data.last_run ? escapeHtml(data.last_run) : 'Unknown'}</div>
                            </div>
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.25rem;">Next Scheduled</div>
                                <div style="font-size: 0.9rem; color: var(--accent);">${data.next_scheduled ? escapeHtml(data.next_scheduled) : 'Not scheduled'}</div>
                            </div>
                        </div>
                    </div>
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Quick Actions</span>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <button class="btn btn-secondary" onclick="editFile('wsl', 'HEARTBEAT.md')">Edit HEARTBEAT.md</button>
                            <button class="btn btn-secondary" onclick="switchView('schedule')">View Schedule</button>
                            <button class="btn btn-secondary" onclick="renderHeartbeat()">Refresh</button>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span class="card-title">To-Do List</span>
                    </div>
                    ${todosHtml}
                </div>
            `;
        }

        async function renderSchedule() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading schedule...</h2>';

            const data = await api('/file/wsl/SCHEDULE.md');

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">📅 Schedule</h2>
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    Peterbot's scheduled jobs configuration.
                </p>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>SCHEDULE.md</span>
                        <span style="font-size: 0.75rem; color: var(--text-secondary);">
                            ${data.exists ? `${data.size} bytes` : 'File not found'}
                        </span>
                    </div>
                    <div class="code-content">
                        <pre>${data.exists ? escapeHtml(data.content) : 'Schedule file not found'}</pre>
                    </div>
                </div>
                <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                    <button class="btn btn-secondary" onclick="renderSchedule()">Refresh</button>
                    <button class="btn btn-primary" onclick="editFile('wsl', 'SCHEDULE.md')">Edit Schedule</button>
                </div>
            `;
        }

        async function renderSkills() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading skills...</h2>';

            const data = await api('/skills');

            let skillsHtml = '<p style="color: var(--text-secondary);">No skills found</p>';
            if (data.skills && data.skills.length > 0) {
                skillsHtml = `
                    <div class="grid grid-3">
                        ${data.skills.map(skill => `
                            <div class="card" style="cursor: pointer;" onclick="viewSkill('${skill.name}')">
                                <div class="card-header">
                                    <span class="card-title">🛠️ ${skill.name}</span>
                                </div>
                                <p style="font-size: 0.75rem; color: var(--text-secondary); font-family: monospace;">
                                    ${skill.path}
                                </p>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            content.innerHTML = `
                <h2 style="margin-bottom: 1rem;">🛠️ Skills</h2>
                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    ${data.count || 0} skill(s) available. Click to view details.
                </p>
                ${skillsHtml}
            `;
        }

        async function viewSkill(name) {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading skill...</h2>';

            const data = await api(`/skill/${name}`);

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>🛠️ ${name}</h2>
                    <button class="btn btn-secondary" onclick="renderSkills()">Back to Skills</button>
                </div>
                <div class="code-viewer">
                    <div class="code-header">
                        <span>SKILL.md</span>
                    </div>
                    <div class="code-content" style="max-height: 600px;">
                        <pre>${data.exists ? escapeHtml(data.content) : 'Skill not found'}</pre>
                    </div>
                </div>
            `;
        }

        async function editFile(type, name) {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading file for editing...</h2>';

            const data = await api(`/file/${type}/${encodeURIComponent(name)}`);

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>Edit: ${name}</h2>
                    <button class="btn btn-secondary" onclick="renderFiles()">Cancel</button>
                </div>
                <div class="card">
                    <textarea id="file-editor" style="width: 100%; height: 400px; background: #0d1117; color: var(--text-primary); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; font-family: 'Consolas', monospace; font-size: 0.85rem; resize: vertical;">${data.exists ? escapeHtml(data.content) : ''}</textarea>
                    <div style="margin-top: 1rem; display: flex; gap: 0.5rem;">
                        <button class="btn btn-primary" onclick="saveFile('${type}', '${name}')">Save Changes</button>
                        <button class="btn btn-secondary" onclick="appendToFile('${type}', '${name}')">Append Text</button>
                    </div>
                </div>

                <div class="card" style="margin-top: 1rem;">
                    <div class="card-header">
                        <span class="card-title">Quick Append</span>
                    </div>
                    <textarea id="append-text" style="width: 100%; height: 100px; background: #0d1117; color: var(--text-primary); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; font-family: 'Consolas', monospace; font-size: 0.85rem;" placeholder="Enter text to append..."></textarea>
                    <button class="btn btn-secondary" style="margin-top: 0.5rem;" onclick="quickAppend('${type}', '${name}')">Append This Text</button>
                </div>
            `;
        }

        async function saveFile(type, name) {
            const content = document.getElementById('file-editor').value;
            const result = await fetch(`/api/file/write/${type}/${encodeURIComponent(name)}?content=${encodeURIComponent(content)}`, {
                method: 'PUT'
            });
            const data = await result.json();
            if (data.status === 'success') {
                showToast('File saved successfully', 'success');
            } else {
                showToast('Failed to save file: ' + (data.detail || 'Unknown error'), 'error');
            }
        }

        async function quickAppend(type, name) {
            const text = document.getElementById('append-text').value;
            if (!text.trim()) {
                showToast('Please enter text to append', 'error');
                return;
            }
            const result = await fetch(`/api/file/append/${type}/${encodeURIComponent(name)}?content=${encodeURIComponent(text)}`, {
                method: 'POST'
            });
            const data = await result.json();
            if (data.status === 'success') {
                showToast('Text appended successfully', 'success');
                document.getElementById('append-text').value = '';
                // Refresh the editor content
                editFile(type, name);
            } else {
                showToast('Failed to append: ' + (data.detail || 'Unknown error'), 'error');
            }
        }

        function switchView(view) {
            currentView = view;

            // Update nav
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.remove('active');
                if (item.dataset.view === view) item.classList.add('active');
            });

            // Render view
            switch(view) {
                case 'dashboard': renderDashboard(); break;
                case 'context': renderContext(); break;
                case 'captures': renderCaptures(); break;
                case 'memory': renderMemory(); break;
                case 'files': renderFiles(); break;
                case 'endpoints': renderEndpoints(); break;
                case 'sessions': renderSessions(); break;
                // Proactive views
                case 'heartbeat': renderHeartbeat(); break;
                case 'schedule': renderSchedule(); break;
                case 'skills': renderSkills(); break;
            }
        }

        // Initialize
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => switchView(item.dataset.view));
        });

        // Initial load
        refreshStatus().then(() => renderDashboard());

        // Auto-refresh every 30 seconds
        setInterval(refreshStatus, 30000);

        // Peter state updates every 5 seconds
        updatePeterState();
        setInterval(updatePeterState, 5000);

        // Start random quote scheduler
        scheduleRandomQuote();

        // WebSocket for real-time updates
        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'status') {
                    statusData = data.data;
                    document.getElementById('last-update').textContent =
                        'Last update: ' + new Date().toLocaleTimeString();
                    if (currentView === 'dashboard') renderDashboard();
                }
            };

            ws.onclose = () => {
                console.log('WebSocket closed, reconnecting...');
                setTimeout(connectWebSocket, 5000);
            };
        }

        connectWebSocket();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200)
