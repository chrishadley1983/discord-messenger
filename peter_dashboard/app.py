"""Peter Dashboard - Web UI for monitoring the Peterbot system.

Provides real-time visibility into:
- Process status (API, Bot, tmux sessions)
- Log viewing
- Key file viewing/editing
- Context messages being sent
- Service control (restart)
- Background task monitoring
"""

# Ensure parent directory (project root) is in sys.path for imports
import sys
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import asyncio
import subprocess
import shlex
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request

# Service manager for reliable process control
try:
    from . import service_manager
except ImportError:
    import service_manager  # When running directly with uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

# UK timezone for timestamps
UK_TZ = ZoneInfo("Europe/London")

# =============================================================================
# SERVICE HEALTH MONITOR - Independent background alerting
# =============================================================================
# This runs independently of the Discord bot to alert when services go down.
# Uses Discord webhook (no bot token required) for true independence.

# Discord webhook for alerts (set in .env as DISCORD_WEBHOOK_ALERTS)
ALERTS_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_ALERTS")

# Services to monitor and their health check endpoints
# These IDs MUST match the service keys in /api/status and ServicesView.serviceInfo
MONITORED_SERVICES = {
    "hadley_api": {
        "name": "Hadley API",
        "url": "http://localhost:8100/health",
        "critical": True,
    },
    "discord_bot": {
        "name": "Discord Bot",
        "check_type": "process",  # Check via service_manager
        "critical": True,
    },
    "claude_mem": {
        "name": "Memory Worker",
        "url": "http://localhost:37777/health",
        "critical": True,
    },
    "hadley_bricks": {
        "name": "Hadley Bricks",
        "url": "http://localhost:3000/api/health",
        "critical": False,  # Not critical for Peterbot operation
    },
    "peterbot_session": {
        "name": "Peterbot Session",
        "check_type": "tmux",  # Check via tmux session
        "tmux_session": "claude-peterbot",
        "critical": True,
    },
}

# Alert configuration
HEALTH_CHECK_INTERVAL = 60  # Check every 60 seconds
ALERT_AFTER_SECONDS = 300   # Alert if down for 5 minutes (300s)
REALERT_INTERVAL = 1800     # Re-alert every 30 minutes if still down

# Track service states
_service_down_since: dict[str, datetime] = {}
_last_alert_time: dict[str, datetime] = {}
_monitor_task: asyncio.Task = None

# =============================================================================
# HEALTH HISTORY TRACKING - Server-side uptime tracking
# =============================================================================
# Persists health check results to calculate accurate uptime percentages

HEALTH_HISTORY_FILE = Path(__file__).parent.parent / "data" / "health_history.json"
HEALTH_HISTORY_MAX_AGE_HOURS = 24  # Keep 24 hours of history
HEALTH_HISTORY_RECORD_INTERVAL = 60  # Record every 60 seconds (matches HEALTH_CHECK_INTERVAL)

# In-memory health history (loaded from file on startup)
_health_history: dict[str, list[dict]] = {}  # { service_id: [{ timestamp, status }] }
_health_history_loaded = False


def _load_health_history():
    """Load health history from JSON file."""
    global _health_history, _health_history_loaded

    if _health_history_loaded:
        return

    try:
        if HEALTH_HISTORY_FILE.exists():
            with open(HEALTH_HISTORY_FILE, "r") as f:
                data = json.load(f)
                _health_history = data.get("history", {})
                # Prune old entries on load
                _prune_health_history()
        else:
            _health_history = {}
    except Exception as e:
        print(f"[HealthHistory] Error loading history: {e}")
        _health_history = {}

    _health_history_loaded = True
    print(f"[HealthHistory] Loaded {sum(len(v) for v in _health_history.values())} records")


def _save_health_history():
    """Save health history to JSON file."""
    try:
        # Ensure data directory exists
        HEALTH_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(HEALTH_HISTORY_FILE, "w") as f:
            json.dump({
                "last_updated": datetime.now(UK_TZ).isoformat(),
                "history": _health_history
            }, f, indent=2)
    except Exception as e:
        print(f"[HealthHistory] Error saving history: {e}")


def _prune_health_history():
    """Remove entries older than HEALTH_HISTORY_MAX_AGE_HOURS."""
    from datetime import timedelta
    cutoff = datetime.now(UK_TZ) - timedelta(hours=HEALTH_HISTORY_MAX_AGE_HOURS)
    cutoff_ts = cutoff.timestamp() * 1000  # Convert to milliseconds

    for service_id in _health_history:
        _health_history[service_id] = [
            entry for entry in _health_history[service_id]
            if entry.get("timestamp", 0) > cutoff_ts
        ]


def _record_health_check(service_id: str, is_healthy: bool, latency_ms: int = None, error: str = None):
    """Record a health check result."""
    _load_health_history()

    if service_id not in _health_history:
        _health_history[service_id] = []

    entry = {
        "timestamp": int(datetime.now(UK_TZ).timestamp() * 1000),  # milliseconds
        "status": "healthy" if is_healthy else "unhealthy",
    }
    if latency_ms is not None:
        entry["latency_ms"] = latency_ms
    if error:
        entry["error"] = error

    _health_history[service_id].append(entry)

    # Prune and save periodically (every 10 checks to avoid excessive writes)
    total_entries = sum(len(v) for v in _health_history.values())
    if total_entries % 10 == 0:
        _prune_health_history()
        _save_health_history()


def get_health_history(service_id: str = None) -> dict:
    """Get health history for one or all services."""
    _load_health_history()

    if service_id:
        return {service_id: _health_history.get(service_id, [])}
    return _health_history


def calculate_uptime(service_id: str) -> float:
    """Calculate uptime percentage for a service based on health history."""
    _load_health_history()

    history = _health_history.get(service_id, [])
    if not history:
        return 100.0  # No history = assume 100% (new service)

    healthy_count = sum(1 for entry in history if entry.get("status") == "healthy")
    return round((healthy_count / len(history)) * 100, 1)


async def _check_service_health(service_id: str, config: dict) -> bool:
    """Check if a service is healthy. Returns True if up, False if down."""
    try:
        check_type = config.get("check_type")
        if check_type == "process":
            # Check via service_manager for process-based services
            status = service_manager.get_service_status(service_id)
            return status.get("status") == "running"
        elif check_type == "tmux":
            # Check via tmux session
            tmux_session_name = config.get("tmux_session")
            sessions = get_tmux_sessions()
            return any(s["name"] == tmux_session_name for s in sessions)
        else:
            # HTTP health check
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(config["url"])
                return response.status_code == 200
    except Exception:
        return False


async def _send_alert(message: str, is_recovery: bool = False):
    """Send alert to Discord via webhook."""
    if not ALERTS_WEBHOOK_URL:
        print(f"[ServiceMonitor] No webhook configured, would alert: {message}")
        return

    # Format message with emoji
    emoji = "✅" if is_recovery else "🔴"
    timestamp = datetime.now(UK_TZ).strftime("%H:%M:%S")

    payload = {
        "content": f"{emoji} **[{timestamp}]** {message}",
        "username": "Peter Service Monitor",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(ALERTS_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"[ServiceMonitor] Failed to send alert: {e}")


async def _health_monitor_loop():
    """Background loop that checks service health and sends alerts."""
    print("[ServiceMonitor] Starting health monitor loop")

    while True:
        try:
            now = datetime.now(UK_TZ)

            for service_id, config in MONITORED_SERVICES.items():
                is_healthy = await _check_service_health(service_id, config)
                service_name = config["name"]

                # Record health check for uptime tracking
                _record_health_check(service_id, is_healthy)

                if is_healthy:
                    # Service is up - check if it was down and send recovery alert
                    if service_id in _service_down_since:
                        down_duration = (now - _service_down_since[service_id]).total_seconds()
                        await _send_alert(
                            f"**{service_name}** is back online (was down for {int(down_duration)}s)",
                            is_recovery=True
                        )
                        del _service_down_since[service_id]
                        if service_id in _last_alert_time:
                            del _last_alert_time[service_id]
                else:
                    # Service is down
                    if service_id not in _service_down_since:
                        # First detection of downtime
                        _service_down_since[service_id] = now

                    down_duration = (now - _service_down_since[service_id]).total_seconds()

                    # Check if we should alert
                    should_alert = False
                    if down_duration >= ALERT_AFTER_SECONDS:
                        if service_id not in _last_alert_time:
                            # First alert
                            should_alert = True
                        elif (now - _last_alert_time[service_id]).total_seconds() >= REALERT_INTERVAL:
                            # Re-alert interval passed
                            should_alert = True

                    if should_alert:
                        await _send_alert(
                            f"**{service_name}** is DOWN (for {int(down_duration)}s). "
                            f"Check dashboard: http://localhost:5000"
                        )
                        _last_alert_time[service_id] = now

        except Exception as e:
            print(f"[ServiceMonitor] Error in health check loop: {e}")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown tasks."""
    global _monitor_task

    # Startup: Start the health monitor background task
    _monitor_task = asyncio.create_task(_health_monitor_loop())
    print("[ServiceMonitor] Health monitor started")

    yield

    # Shutdown: Cancel the background task
    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
    print("[ServiceMonitor] Health monitor stopped")


# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Peter Dashboard", version="1.0.0", lifespan=lifespan)

# Register rate limit exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - restricted to localhost only for security
# Prevents CSRF attacks from malicious websites
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5000",   # Dashboard
        "http://127.0.0.1:5000",
        "http://localhost:8100",   # Hadley API may call dashboard
        "http://127.0.0.1:8100",
    ],
    allow_credentials=False,  # No cookies needed for local API
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# =============================================================================
# Static Files and Templates Setup (Redesigned Dashboard v2)
# =============================================================================
# Determine the dashboard directory for static files and templates
_dashboard_dir = Path(__file__).parent

# Mount static files directory (CSS, JS, assets)
_static_dir = _dashboard_dir / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Setup Jinja2 templates
_templates_dir = _dashboard_dir / "templates"
templates = Jinja2Templates(directory=str(_templates_dir)) if _templates_dir.exists() else None

# =============================================================================
# API Router Imports
# =============================================================================
# Import modular API routes from api/ subpackage
try:
    from .api import jobs as jobs_api
    from .api import logs as logs_api
except ImportError:
    from api import jobs as jobs_api  # When running directly with uvicorn
    from api import logs as logs_api

# Register API routers
app.include_router(jobs_api.router)
app.include_router(logs_api.router, prefix="/api/logs")

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

# Security: Allowed tmux session names (prevent command injection)
ALLOWED_TMUX_SESSIONS = {"claude-peterbot", "claude-code"}

# Security: Max lines for tmux capture (prevent DoS)
MAX_TMUX_LINES = 500


def run_wsl_command(cmd: str, timeout: int = 10) -> tuple[str, str, int]:
    """Run a command in WSL and return stdout, stderr, returncode."""
    CREATE_NO_WINDOW = 0x08000000
    try:
        result = subprocess.run(
            ["wsl", "bash", "-c", cmd],
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW
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
    CREATE_NO_WINDOW = 0x08000000
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW
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


def validate_wsl_path(wsl_path: str) -> bool:
    """Validate WSL path is in the allowed list (prevents path traversal attacks)."""
    # Only allow paths explicitly listed in WSL_FILES
    return wsl_path in WSL_FILES.values()


def read_wsl_file(wsl_path: str, tail_lines: int = 100, skip_validation: bool = False) -> dict:
    """Read file content from WSL.

    Security: Path must be in WSL_FILES allowlist (unless skip_validation=True for internal use).
    Uses shlex.quote to prevent command injection.
    """
    try:
        # Security: Validate path against allowlist
        if not skip_validation and not validate_wsl_path(wsl_path):
            return {"exists": False, "error": "Access denied: path not in allowlist"}

        # Security: Validate tail_lines
        if tail_lines and not (1 <= tail_lines <= 10000):
            return {"exists": False, "error": "Invalid tail_lines value (1-10000)"}

        # Security: Use shlex.quote for all path arguments
        safe_path = shlex.quote(wsl_path)

        if tail_lines:
            cmd = f"tail -n {tail_lines} {safe_path} 2>/dev/null || cat {safe_path} 2>/dev/null || echo 'File not found'"
        else:
            cmd = f"cat {safe_path} 2>/dev/null || echo 'File not found'"

        stdout, stderr, code = run_wsl_command(cmd)

        if code == 0 and stdout != 'File not found\n':
            # Get file stats
            stat_cmd = f"stat -c '%s %Y' {safe_path} 2>/dev/null || echo '0 0'"
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
async def dashboard(request: Request):
    """Serve the dashboard HTML.

    Uses the new template-based frontend if available (v2), otherwise falls back
    to the legacy inline HTML (v1).
    """
    # Try to serve the new redesigned dashboard (v2)
    if templates and (_templates_dir / "index.html").exists():
        return templates.TemplateResponse("index.html", {"request": request})

    # Fallback to legacy inline HTML
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/health")
async def health_check():
    """Health check for the dashboard itself."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
async def get_system_status():
    """Get overall system status with PID tracking."""
    # Check HTTP services in parallel
    hadley_task = check_http_service(f"{CONFIG['hadley_api_url']}/health")
    mem_task = check_http_service(f"{CONFIG['claude_mem_url']}/health")

    hadley_http_status, mem_status = await asyncio.gather(hadley_task, mem_task)

    # Get process-level status from service_manager
    svc_status = service_manager.status_all()

    # Check tmux sessions
    sessions = get_tmux_sessions()
    peterbot_session = next((s for s in sessions if s["name"] == "claude-peterbot"), None)

    # Check Hadley Bricks status
    hb_http_status = await check_http_service("http://localhost:3000/", timeout=3.0)

    return {
        "timestamp": datetime.now().isoformat(),
        "services": {
            "hadley_api": {
                "status": hadley_http_status.get("status", "down"),
                "latency_ms": hadley_http_status.get("latency_ms"),
                "pid": svc_status.get("hadley_api", {}).get("pid"),
                "port": 8100,
                "process_status": svc_status.get("hadley_api", {}).get("status", "unknown")
            },
            "hadley_bricks": {
                "status": hb_http_status.get("status", "down"),
                "latency_ms": hb_http_status.get("latency_ms"),
                "pid": svc_status.get("hadley_bricks", {}).get("pid"),
                "port": 3000,
                "process_status": svc_status.get("hadley_bricks", {}).get("status", "unknown")
            },
            "claude_mem": mem_status,
            "discord_bot": {
                "status": "up" if svc_status.get("discord_bot", {}).get("status") == "running" else "down",
                "pid": svc_status.get("discord_bot", {}).get("pid"),
                "process_status": svc_status.get("discord_bot", {}).get("status", "unknown")
            },
            "peterbot_session": {
                "status": "up" if peterbot_session else "down",
                "attached": peterbot_session["attached"] if peterbot_session else False
            }
        },
        "tmux_sessions": sessions
    }


@app.get("/api/service-status")
async def get_service_status():
    """Get detailed process status for all managed services."""
    return service_manager.status_all()


@app.get("/api/health-history")
async def get_health_history_endpoint(service: str = None):
    """Get health check history for services.

    Returns history with timestamps and status for uptime calculation.
    Optionally filter by service ID.
    """
    history = get_health_history(service)

    # Calculate uptimes
    uptimes = {}
    for svc_id in history:
        uptimes[svc_id] = calculate_uptime(svc_id)

    return {
        "history": history,
        "uptimes": uptimes,
        "max_age_hours": HEALTH_HISTORY_MAX_AGE_HOURS,
    }


@app.post("/api/stop/{service}")
async def stop_service_endpoint(service: str):
    """Stop a service completely."""
    if service in ("hadley_api", "discord_bot", "hadley_bricks"):
        result = service_manager.stop_service(service, force_cleanup=True)
        if result["success"]:
            return {"status": "stopped", "details": result}
        else:
            raise HTTPException(500, f"Failed to stop {service}")

    elif service == "peterbot_session":
        run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
        return {"status": "stopped", "message": "Peterbot session killed"}

    else:
        raise HTTPException(400, f"Unknown service: {service}")


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
        # Security: Use shlex.quote even for controlled paths (defense-in-depth)
        safe_path = shlex.quote(path)
        stat_cmd = f"stat -c '%Y' {safe_path} 2>/dev/null || echo '0'"
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


@app.get("/api/claude-code-health")
async def get_claude_code_health():
    """Get Claude Code health metrics for dashboard.

    Returns job success rate, clear success rate, response quality,
    recent job history, and alert status.
    """
    try:
        # Import the health tracker
        import sys
        project_root = str(Path(__file__).parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from jobs.claude_code_health import get_health_tracker
        tracker = get_health_tracker()
        return tracker.get_health_stats()
    except ImportError as e:
        return {
            "error": f"Health tracker not available: {e}",
            "job_success_rate": 0,
            "clear_success_rate": 0,
            "garbage_rate": 0,
            "consecutive_failures": 0,
            "total_jobs_tracked": 0,
            "recent_jobs": [],
            "recent_clears": [],
            "alerts": {
                "consecutive_failure_alert": False,
                "clear_rate_alert": False,
                "recent_garbage": False,
            }
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/logs/bot")
async def get_bot_logs():
    """Get recent Discord bot logs."""
    # Try to read from Windows logs directory
    log_path = os.path.join(CONFIG["windows_project_path"], "logs", "bot.log")
    if os.path.exists(log_path):
        return read_file_content(os.path.join("logs", "bot.log"), tail_lines=200)
    return {"exists": False, "error": "Log file not found"}


@app.get("/api/screen/{session}")
@limiter.limit("60/minute")
async def get_tmux_screen(request: Request, session: str, lines: int = 60):
    """Capture current tmux screen content.

    Security: Session name is validated against allowlist to prevent command injection.
    Rate limited to 60 requests/minute.
    """
    # Security: Validate session name against allowlist
    if session not in ALLOWED_TMUX_SESSIONS:
        raise HTTPException(400, f"Invalid session. Allowed: {list(ALLOWED_TMUX_SESSIONS)}")

    # Security: Validate lines is reasonable integer
    if not (1 <= lines <= MAX_TMUX_LINES):
        raise HTTPException(400, f"Lines must be between 1 and {MAX_TMUX_LINES}")

    # Use shlex.quote for defense-in-depth (even though session is from allowlist)
    cmd = f"tmux capture-pane -t {shlex.quote(session)} -p -S -{lines} 2>/dev/null || echo 'Session not found'"
    stdout, stderr, code = run_wsl_command(cmd)

    if code == 0 and stdout != 'Session not found\n':
        return {"content": stdout, "lines": lines}
    return {"error": "Session not found or not accessible"}


@app.post("/api/restart/{service}")
@limiter.limit("5/minute")
async def restart_service_endpoint(request: Request, service: str):
    """Restart a service with proper single-instance enforcement.

    Rate limited to 5 requests/minute to prevent abuse.
    """
    if service in ("hadley_api", "discord_bot", "hadley_bricks"):
        # Use service manager for Windows services (headless = no console window)
        result = service_manager.restart_service(service, headless=True)
        if result["success"]:
            return {
                "status": "restarting",
                "message": f"{service} restart completed",
                "details": result
            }
        else:
            raise HTTPException(500, f"Failed to restart {service}: {result.get('error', 'Unknown error')}")

    elif service == "peterbot_session":
        # Kill and recreate tmux session (WSL - unchanged)
        run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
        run_wsl_command(f"tmux new-session -d -s claude-peterbot -c {CONFIG['wsl_peterbot_path']}")
        run_wsl_command("tmux send-keys -t claude-peterbot 'source ~/.profile && claude --permission-mode bypassPermissions' Enter")
        return {"status": "restarting", "message": "Peterbot session recreated"}

    else:
        raise HTTPException(400, f"Unknown service: {service}")


@app.post("/api/restart-all")
@limiter.limit("2/minute")
async def restart_all_services(request: Request):
    """Restart all Peter-related services (headless - no console windows).

    Uses service_manager for reliable single-instance enforcement.
    Rate limited to 2 requests/minute to prevent abuse.
    """
    results = {}

    # 1. Restart Windows services via service_manager (headless)
    for svc in ("hadley_api", "discord_bot", "hadley_bricks"):
        result = service_manager.restart_service(svc, headless=True)
        results[svc] = {
            "status": "running" if result["success"] else "failed",
            "pid": result.get("start_result", {}).get("pid"),
            "error": result.get("start_result", {}).get("error") if not result["success"] else None
        }

    # 2. Restart Peterbot tmux session (WSL)
    run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
    run_wsl_command(f"tmux new-session -d -s claude-peterbot -c {CONFIG['wsl_peterbot_path']}")
    run_wsl_command("tmux send-keys -t claude-peterbot 'source ~/.profile && claude --permission-mode bypassPermissions' Enter")
    results["peterbot_session"] = {"status": "restarting"}

    all_success = all(
        r.get("status") in ("running", "restarting")
        for r in results.values()
    )

    return {
        "status": "restarting",  # Frontend expects "restarting" to show success
        "message": "All services restart initiated" if all_success else "Some services failed to restart",
        "services": results,
        "all_success": all_success
    }


@app.post("/api/send/{session}")
@limiter.limit("30/minute")
async def send_to_session(request: Request, session: str, text: str):
    """Send text to a tmux session.

    Security: Session name is validated against allowlist to prevent command injection.
    Text is properly escaped using shlex.quote.
    Rate limited to 30 requests/minute.
    """
    # Security: Validate session name against allowlist
    if session not in ALLOWED_TMUX_SESSIONS:
        raise HTTPException(400, f"Invalid session. Allowed: {list(ALLOWED_TMUX_SESSIONS)}")

    # Security: Limit text length to prevent DoS
    if len(text) > 10000:
        raise HTTPException(400, "Text too long (max 10000 characters)")

    # Use shlex.quote for proper escaping
    safe_session = shlex.quote(session)
    safe_text = shlex.quote(text)
    cmd = f"tmux send-keys -t {safe_session} -l {safe_text} && tmux send-keys -t {safe_session} Enter"
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


def parse_observation_ids(data):
    """Parse observation IDs from MCP search response."""
    import re
    ids = []
    if data.get("content") and len(data["content"]) > 0:
        text = data["content"][0].get("text", "")
        # Match IDs like: | #548 |
        pattern = r'\| #(\d+) \|'
        matches = re.findall(pattern, text)
        ids = [int(m) for m in matches]
    return ids


def format_observation(obs, source):
    """Format observation for frontend display."""
    return {
        "id": obs.get("id"),
        "title": obs.get("title", ""),
        "subtitle": obs.get("subtitle", ""),
        "type": obs.get("type", "observation"),
        "category": obs.get("category", ""),
        "project": obs.get("project", ""),
        "narrative": obs.get("narrative", ""),
        "facts": obs.get("facts", "[]"),
        "created_at": obs.get("created_at", ""),
        "is_active": obs.get("is_active", 1),
        "source": source
    }


@app.get("/api/memory/peter")
async def get_peter_memories(limit: int = 50):
    """Get recent memory observations from peterbot project with full details."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First get the list of recent observation IDs
            search_response = await client.get(
                f"{CONFIG['claude_mem_url']}/api/search",
                params={"project": "peterbot", "limit": str(limit), "orderBy": "id_desc"}
            )
            if search_response.status_code != 200:
                return {"error": f"Search status {search_response.status_code}", "observations": [], "source": "peterbot"}

            # Parse IDs from search response
            search_data = search_response.json()
            ids = parse_observation_ids(search_data)

            if not ids:
                return {"observations": [], "count": 0, "source": "peterbot"}

            # Fetch full observation details
            details_response = await client.post(
                f"{CONFIG['claude_mem_url']}/api/observations",
                json={"ids": ids[:limit]}
            )
            if details_response.status_code == 200:
                observations = details_response.json()
                return {
                    "observations": [format_observation(obs, "peterbot") for obs in observations],
                    "count": len(observations),
                    "source": "peterbot"
                }
            return {"error": f"Details status {details_response.status_code}", "observations": [], "source": "peterbot"}
    except Exception as e:
        logger.error(f"Error fetching peter memories: {e}")
        return {"error": str(e), "observations": [], "source": "peterbot"}


@app.get("/api/memory/claude")
async def get_claude_memories(limit: int = 50):
    """Get recent memory observations from all Claude Code projects."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Search without project filter to get all recent observations
            search_response = await client.get(
                f"{CONFIG['claude_mem_url']}/api/search",
                params={"limit": str(limit), "orderBy": "id_desc"}
            )
            if search_response.status_code != 200:
                return {"error": f"Search status {search_response.status_code}", "observations": [], "source": "claude"}

            # Parse IDs from search response
            search_data = search_response.json()
            ids = parse_observation_ids(search_data)

            if not ids:
                return {"observations": [], "count": 0, "source": "claude"}

            # Fetch full observation details
            details_response = await client.post(
                f"{CONFIG['claude_mem_url']}/api/observations",
                json={"ids": ids[:limit]}
            )
            if details_response.status_code == 200:
                observations = details_response.json()
                return {
                    "observations": [format_observation(obs, "claude") for obs in observations],
                    "count": len(observations),
                    "source": "claude"
                }
            return {"error": f"Details status {details_response.status_code}", "observations": [], "source": "claude"}
    except Exception as e:
        logger.error(f"Error fetching claude memories: {e}")
        return {"error": str(e), "observations": [], "source": "claude"}


@app.get("/api/memory/recent")
async def get_recent_memories(limit: int = 50):
    """Get recent memory observations from claude-mem (peterbot project)."""
    return await get_peter_memories(limit=limit)


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


def parse_skill_metadata(content: str) -> dict:
    """Parse SKILL.md content to extract metadata.

    Supports two formats:
    1. YAML frontmatter (between --- markers)
    2. Markdown headers (## sections)
    """
    metadata = {
        "description": None,
        "scheduled": False,
        "triggers": None,
        "conversational": False
    }

    # Check for YAML frontmatter (between --- markers)
    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)

        # Parse description
        desc_match = re.search(r'^description:\s*(.+)$', frontmatter, re.MULTILINE)
        if desc_match:
            metadata["description"] = desc_match.group(1).strip()

        # Parse scheduled
        sched_match = re.search(r'^scheduled:\s*(true|false)$', frontmatter, re.MULTILINE | re.IGNORECASE)
        if sched_match:
            metadata["scheduled"] = sched_match.group(1).lower() == "true"

        # Parse conversational
        conv_match = re.search(r'^conversational:\s*(true|false)$', frontmatter, re.MULTILINE | re.IGNORECASE)
        if conv_match:
            metadata["conversational"] = conv_match.group(1).lower() == "true"

        # Parse triggers (YAML list format)
        trigger_match = re.search(r'^trigger:\s*\n((?:\s+-\s*.+\n?)+)', frontmatter, re.MULTILINE)
        if trigger_match:
            triggers_text = trigger_match.group(1)
            triggers = re.findall(r'-\s*["\']?([^"\'\n]+)["\']?', triggers_text)
            metadata["triggers"] = [t.strip() for t in triggers if t.strip()]
    else:
        # No frontmatter - parse markdown style
        # Look for ## Purpose section as description
        purpose_match = re.search(r'##\s*Purpose\s*\n+(.+?)(?=\n##|\n\n\n|$)', content, re.DOTALL)
        if purpose_match:
            # Get first paragraph/sentence
            purpose_text = purpose_match.group(1).strip()
            first_line = purpose_text.split('\n')[0].strip()
            metadata["description"] = first_line

        # Look for ## Triggers section
        triggers_match = re.search(r'##\s*Triggers?\s*\n+(.+?)(?=\n##|$)', content, re.DOTALL)
        if triggers_match:
            triggers_text = triggers_match.group(1)
            triggers = re.findall(r'-\s*["\']?([^"\'\n,]+)["\']?', triggers_text)
            metadata["triggers"] = [t.strip() for t in triggers if t.strip() and not t.startswith('#')]

        # Look for ## Schedule section
        schedule_match = re.search(r'##\s*Schedule', content)
        if schedule_match:
            metadata["scheduled"] = True

        # Look for ## Conversational section
        conv_match = re.search(r'##\s*Conversational\s*\n+\s*(Yes|True)', content, re.IGNORECASE)
        if conv_match:
            metadata["conversational"] = True

    return metadata


@app.get("/api/skills")
async def list_skills():
    """List available Peterbot skills with metadata parsed from SKILL.md files."""
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

                # Read the SKILL.md file to parse metadata
                safe_path = shlex.quote(path)
                read_cmd = f"cat {safe_path} 2>/dev/null"
                content_out, _, read_code = run_wsl_command(read_cmd)

                skill_data = {
                    "name": name,
                    "path": path,
                    "description": None,
                    "scheduled": False,
                    "triggers": None,
                    "conversational": False
                }

                if read_code == 0 and content_out:
                    metadata = parse_skill_metadata(content_out)
                    skill_data.update(metadata)

                skills.append(skill_data)

    # Sort by name
    skills.sort(key=lambda s: s["name"])

    return {"skills": skills, "count": len(skills)}


@app.get("/api/skill/{name}")
async def get_skill(name: str):
    """Get skill content by name.

    Skills are in a fixed directory structure, so we validate the name
    and use skip_validation=True for the WSL file read.
    """
    # Security: Validate skill name contains only safe characters
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise HTTPException(400, "Invalid skill name")

    path = f"/home/chris_hadley/peterbot/.claude/skills/{name}/SKILL.md"
    return read_wsl_file(path, tail_lines=0, skip_validation=True)


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
# Parser System API endpoints
# ============================================================================

@app.get("/api/parser/debug")
async def get_parser_debug():
    """Debug endpoint to check parser system setup."""
    import sys
    import os
    import traceback

    result = {
        "cwd": os.getcwd(),
        "data_dir_exists": os.path.exists("data"),
        "db_exists": os.path.exists("data/parser_fixtures.db"),
        "python_path_sample": sys.path[:5],
    }

    # Try imports one by one
    try:
        from domains.peterbot.capture_parser import get_parser_capture_store, _get_connection
        result["import_capture_parser"] = "OK"
    except Exception as e:
        result["import_capture_parser"] = f"FAIL: {e}"
        result["import_capture_parser_tb"] = traceback.format_exc()

    try:
        from domains.peterbot.feedback_processor import get_feedback_processor
        result["import_feedback"] = "OK"
    except Exception as e:
        result["import_feedback"] = f"FAIL: {e}"

    try:
        from domains.peterbot.scheduled_output_scorer import get_scheduled_output_scorer
        result["import_scorer"] = "OK"
    except Exception as e:
        result["import_scorer"] = f"FAIL: {e}"

    # Try DB access
    try:
        from domains.peterbot.capture_parser import _get_connection
        conn = _get_connection()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        result["db_tables"] = [t[0] for t in tables]
    except Exception as e:
        result["db_access"] = f"FAIL: {e}"

    return result


@app.get("/api/parser/status")
async def get_parser_status():
    """Get overall parser system status for summary cards."""
    import traceback
    import sys
    import os

    debug_info = {
        "cwd": os.getcwd(),
        "python_path": sys.path[:3],
        "step": "init"
    }

    try:
        debug_info["step"] = "import_capture_parser"
        from domains.peterbot.capture_parser import get_parser_capture_store, _get_connection

        debug_info["step"] = "import_feedback"
        from domains.peterbot.feedback_processor import get_feedback_processor

        debug_info["step"] = "import_scorer"
        from domains.peterbot.scheduled_output_scorer import get_scheduled_output_scorer

        debug_info["step"] = "get_store"
        store = get_parser_capture_store()

        debug_info["step"] = "get_feedback"
        feedback = get_feedback_processor()

        debug_info["step"] = "get_scorer"
        scorer = get_scheduled_output_scorer()

        debug_info["step"] = "fixture_stats"
        fixture_stats = store.get_fixture_stats()

        debug_info["step"] = "capture_stats"
        capture_stats = store.get_capture_stats(hours=24)

        debug_info["step"] = "feedback_summary"
        feedback_summary = feedback.get_pending_summary()

        debug_info["step"] = "cycles_query"
        conn = _get_connection()
        cursor = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN committed = 1 THEN 1 ELSE 0 END) as committed,
                   MAX(started_at) as last_cycle
            FROM improvement_cycles
        """)
        row = cursor.fetchone()
        cycles_total = row['total'] if row else 0
        cycles_committed = row['committed'] if row else 0

        debug_info["step"] = "human_reviewed_query"
        cursor = conn.execute("""
            SELECT COUNT(*) as since_review
            FROM improvement_cycles
            WHERE human_reviewed = 0
        """)
        row = cursor.fetchone()
        cycles_since_review = row['since_review'] if row else 0

        debug_info["step"] = "drift_alerts"
        drift_alerts = scorer.get_drift_alerts(hours=24)

        return {
            "fixtures": {
                "total": fixture_stats.get('total', 0),
                "passing": fixture_stats.get('passing', 0),
                "failing": fixture_stats.get('failing', 0),
                "untested": fixture_stats.get('untested', 0),
                "pass_rate": fixture_stats.get('pass_rate', 0)
            },
            "captures_24h": {
                "total": capture_stats.get('total', 0),
                "failures": capture_stats.get('failures', 0),
                "empty": capture_stats.get('empty', 0),
                "ansi": capture_stats.get('ansi', 0),
                "echo": capture_stats.get('echo', 0),
                "reacted": capture_stats.get('reacted', 0)
            },
            "feedback": {
                "pending": feedback_summary.get('total', 0),
                "high_priority": feedback_summary.get('high_priority', 0),
                "by_category": feedback_summary.get('by_category', {})
            },
            "cycles": {
                "total": cycles_total,
                "committed": cycles_committed,
                "since_review": cycles_since_review
            },
            "drift_alerts": len(drift_alerts)
        }
    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"Error getting parser status at step {debug_info['step']}: {e}\n{error_tb}")
        return {
            "error": str(e),
            "step": debug_info["step"],
            "debug": debug_info,
            "traceback": error_tb
        }


@app.get("/api/parser/fixtures")
async def get_parser_fixtures():
    """Get fixture details for the Fixtures tab."""
    try:
        from domains.peterbot.capture_parser import get_parser_capture_store

        store = get_parser_capture_store()
        fixtures = store.get_fixtures()

        # Group by category
        by_category = {}
        chronic_failures = []
        recent_results = []

        for f in fixtures:
            cat = f.category
            if cat not in by_category:
                by_category[cat] = {"total": 0, "passed": 0}
            by_category[cat]["total"] += 1
            if f.last_pass:
                by_category[cat]["passed"] += 1

            # Track chronic failures
            if f.fail_count >= 3:
                chronic_failures.append({
                    "id": f.id,
                    "category": f.category,
                    "fail_count": f.fail_count,
                    "notes": f.notes
                })

            # Include in recent results
            recent_results.append({
                "id": f.id,
                "category": f.category,
                "passed": f.last_pass,
                "fail_count": f.fail_count,
                "last_run_at": f.last_run_at
            })

        return {
            "by_category": by_category,
            "chronic_failures": chronic_failures,
            "recent_results": recent_results[:20]  # Most recent 20
        }
    except Exception as e:
        logger.error(f"Error getting parser fixtures: {e}")
        return {"error": str(e)}


@app.get("/api/parser/captures")
async def get_parser_captures(hours: int = 24):
    """Get recent captures for the Captures tab."""
    try:
        from domains.peterbot.capture_parser import get_parser_capture_store, _get_connection

        store = get_parser_capture_store()
        stats = store.get_capture_stats(hours=hours)

        # Get recent captures
        conn = _get_connection()
        cursor = conn.execute("""
            SELECT id, captured_at, channel_name, skill_name,
                   was_empty, had_ansi, had_echo, user_reacted,
                   promoted, quality_score
            FROM captures
            WHERE captured_at >= datetime('now', ?)
            ORDER BY captured_at DESC
            LIMIT 100
        """, (f'-{hours} hours',))

        captures = []
        for row in cursor:
            captures.append({
                "id": row['id'],
                "captured_at": row['captured_at'],
                "channel_name": row['channel_name'],
                "skill_name": row['skill_name'],
                "was_empty": bool(row['was_empty']),
                "had_ansi": bool(row['had_ansi']),
                "had_echo": bool(row['had_echo']),
                "user_reacted": row['user_reacted'],
                "promoted": bool(row['promoted']),
                "quality_score": row['quality_score']
            })

        return {
            "captures": captures,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting parser captures: {e}")
        return {"error": str(e)}


@app.get("/api/parser/feedback")
async def get_parser_feedback():
    """Get pending feedback for the Feedback tab."""
    try:
        from domains.peterbot.feedback_processor import get_feedback_processor

        processor = get_feedback_processor()
        pending = processor.get_pending()
        summary = processor.get_pending_summary()

        feedback_list = []
        for fb in pending:
            feedback_list.append({
                "id": fb.id,
                "created_at": fb.created_at,
                "input_method": fb.input_method,
                "category": fb.category,
                "skill_name": fb.skill_name,
                "description": fb.description,
                "priority": fb.priority,
                "status": "pending"  # All items from get_pending() are pending
            })

        return {
            "feedback": feedback_list,
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Error getting parser feedback: {e}")
        return {"error": str(e)}


@app.get("/api/parser/cycles")
async def get_parser_cycles():
    """Get improvement cycle history for the Cycles tab."""
    try:
        from domains.peterbot.capture_parser import _get_connection

        conn = _get_connection()

        # Get recent cycles
        cursor = conn.execute("""
            SELECT id, started_at, target_stage, committed,
                   score_before, score_after, fixtures_improved,
                   regressions, human_reviewed
            FROM improvement_cycles
            ORDER BY started_at DESC
            LIMIT 20
        """)

        cycles = []
        for row in cursor:
            cycles.append({
                "id": row['id'],
                "started_at": row['started_at'],
                "target_stage": row['target_stage'],
                "committed": bool(row['committed']),
                "score_before": row['score_before'],
                "score_after": row['score_after'],
                "fixtures_improved": row['fixtures_improved'],
                "regressions": row['regressions'],
                "human_reviewed": bool(row['human_reviewed'])
            })

        # Review status
        cursor = conn.execute("""
            SELECT COUNT(*) as since_review
            FROM improvement_cycles
            WHERE human_reviewed = 0
        """)
        row = cursor.fetchone()
        cycles_since_review = row['since_review'] if row else 0

        return {
            "cycles": cycles,
            "review_status": {
                "cycles_since_review": cycles_since_review,
                "review_required": cycles_since_review >= 5,
                "max_without_review": 5
            }
        }
    except Exception as e:
        logger.error(f"Error getting parser cycles: {e}")
        return {"error": str(e)}


@app.get("/api/parser/drift")
async def get_parser_drift():
    """Get format drift status for the Drift tab."""
    try:
        from domains.peterbot.scheduled_output_scorer import get_scheduled_output_scorer

        scorer = get_scheduled_output_scorer()
        skill_health = scorer.get_skill_health()
        drift_alerts = scorer.get_drift_alerts(hours=24)

        return {
            "skill_health": skill_health,
            "alerts": drift_alerts
        }
    except Exception as e:
        logger.error(f"Error getting parser drift: {e}")
        return {"error": str(e)}


@app.post("/api/parser/run-regression")
async def run_parser_regression():
    """Trigger a regression test run."""
    try:
        from domains.peterbot.parser_regression import RegressionRunner

        runner = RegressionRunner()
        report = runner.run()
        return {
            "success": True,
            "result": report.to_dict()
        }
    except Exception as e:
        logger.error(f"Error running parser regression: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/parser/mark-reviewed")
async def mark_parser_reviewed():
    """Mark human review complete."""
    try:
        from domains.peterbot.capture_parser import _transaction

        with _transaction() as conn:
            conn.execute("""
                UPDATE improvement_cycles
                SET human_reviewed = 1
                WHERE human_reviewed = 0
            """)

        return {"success": True, "message": "All cycles marked as reviewed"}
    except Exception as e:
        logger.error(f"Error marking reviewed: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/parser/feedback/{feedback_id}/resolve")
async def resolve_parser_feedback(feedback_id: str, resolution: str = "Resolved via dashboard"):
    """Resolve a feedback item."""
    try:
        from domains.peterbot.feedback_processor import get_feedback_processor

        processor = get_feedback_processor()
        processor.resolve(feedback_id, resolution=resolution)
        return {"success": True}
    except Exception as e:
        logger.error(f"Error resolving feedback: {e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Knowledge Search API endpoints (same methods Peter uses)
# ============================================================================

@app.get("/api/search/memory")
async def search_peterbot_memory(query: str):
    """Search peterbot-mem - exact same method Peter uses for memory context.

    This calls the claude-mem worker's context injection endpoint.
    """
    import aiohttp
    from domains.peterbot import config

    try:
        params = {
            "project": config.PROJECT_ID,
            "query": query
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                config.CONTEXT_ENDPOINT,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    context = await resp.text()
                    return {
                        "success": True,
                        "query": query,
                        "project": config.PROJECT_ID,
                        "endpoint": config.CONTEXT_ENDPOINT,
                        "context": context,
                        "length": len(context)
                    }
                else:
                    text = await resp.text()
                    return {
                        "success": False,
                        "error": f"API returned {resp.status}: {text}",
                        "endpoint": config.CONTEXT_ENDPOINT
                    }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Connection error: {str(e)}",
            "endpoint": config.CONTEXT_ENDPOINT
        }
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/search/second-brain")
async def search_second_brain(
    query: str,
    limit: int = 5,
    min_similarity: float = 0.7
):
    """Search Second Brain - exact same method Peter uses for knowledge context.

    This calls the semantic_search function from domains/second_brain.
    """
    try:
        from domains.second_brain import semantic_search, format_context_for_claude

        results = await semantic_search(
            query=query,
            min_similarity=min_similarity,
            limit=limit
        )

        # Format results for display
        items = []
        for result in results:
            item = result.item
            items.append({
                "id": str(item.id) if item.id else None,
                "title": item.title,
                "summary": item.summary,
                "topics": item.topics or [],
                "source": item.source,
                "content_type": item.content_type.value if item.content_type else None,
                "capture_type": item.capture_type.value if item.capture_type else None,
                "similarity": result.best_similarity,
                "decay_score": item.decay_score,
                "excerpts": result.relevant_excerpts[:2] if result.relevant_excerpts else []
            })

        # Also get the formatted context (what Peter would see)
        formatted_context = format_context_for_claude(results)

        return {
            "success": True,
            "query": query,
            "count": len(items),
            "items": items,
            "formatted_context": formatted_context
        }
    except Exception as e:
        logger.error(f"Error searching Second Brain: {e}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/api/search/second-brain/stats")
async def get_second_brain_stats():
    """Get Second Brain statistics."""
    try:
        from domains.second_brain import (
            get_total_active_count,
            get_total_connection_count,
            get_topics_with_counts,
            get_recent_items
        )

        total_items = await get_total_active_count()
        total_connections = await get_total_connection_count()
        topics_raw = await get_topics_with_counts()
        topics = [{"topic": t[0], "count": t[1]} for t in topics_raw[:20]]
        recent = await get_recent_items(limit=10)

        recent_items = []
        for item in recent:
            # Handle created_at which may be datetime or string
            created = getattr(item, 'created_at', None)
            if created and hasattr(created, 'isoformat'):
                created = created.isoformat()
            elif created:
                created = str(created)

            recent_items.append({
                "id": str(item.id) if item.id else None,
                "title": getattr(item, 'title', None) or "Untitled",
                "content_type": str(getattr(item, 'content_type', None) or ''),
                "capture_type": str(getattr(item, 'capture_type', None) or ''),
                "created_at": created,
                "topics": getattr(item, 'topics', None) or []
            })

        return {
            "success": True,
            "total_items": total_items,
            "total_connections": total_connections,
            "topics": topics,
            "recent_items": recent_items
        }
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


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

        /* ══════════════════════════════════════════════════════════════════
           TASK BOARD STYLES
           ══════════════════════════════════════════════════════════════════ */

        .task-board {
            height: calc(100vh - 160px);
            display: flex;
            flex-direction: column;
            background: #f7f6f3;
            border-radius: 12px;
            overflow: hidden;
        }

        .task-header {
            background: linear-gradient(135deg, #1a2744 0%, #253561 100%);
            padding: 12px 20px;
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .task-header-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            flex: 1;
        }

        .task-logo {
            width: 34px;
            height: 34px;
            border-radius: 9px;
            background: linear-gradient(135deg, #f59e0b, #ea580c);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }

        .task-header-title {
            font-size: 16px;
            font-weight: 800;
            color: #fff;
            letter-spacing: -0.3px;
        }

        .task-header-subtitle {
            font-size: 10px;
            font-weight: 500;
            color: #94a3b8;
            letter-spacing: 0.5px;
        }

        .task-search {
            position: relative;
            width: 220px;
        }

        .task-search input {
            width: 100%;
            padding: 7px 12px 7px 32px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.08);
            color: #fff;
            font-size: 12px;
            outline: none;
        }

        .task-search input::placeholder {
            color: #64748b;
        }

        .task-search-icon {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            color: #64748b;
            font-size: 14px;
        }

        .task-add-btn {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 8px;
            border: none;
            background: linear-gradient(135deg, #f59e0b, #ea580c);
            color: #fff;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s;
            letter-spacing: 0.3px;
        }

        .task-add-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
        }

        /* Task Tabs */
        .task-tabs {
            background: #fff;
            border-bottom: 1px solid #e8e5df;
            padding: 0 20px;
            display: flex;
            gap: 0;
        }

        .task-tab {
            display: flex;
            align-items: center;
            gap: 7px;
            padding: 12px 18px;
            border: none;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s;
            position: relative;
            background: transparent;
            color: #64748b;
            border-bottom: 2.5px solid transparent;
        }

        .task-tab:hover {
            color: #1e293b;
        }

        .task-tab.active {
            font-weight: 700;
            border-bottom-color: currentColor;
        }

        .task-tab[data-list="personal_todo"] { --tab-accent: #2563eb; }
        .task-tab[data-list="peter_queue"] { --tab-accent: #d97706; }
        .task-tab[data-list="idea"] { --tab-accent: #7c3aed; }
        .task-tab[data-list="research"] { --tab-accent: #059669; }

        .task-tab.active[data-list="personal_todo"] { color: #2563eb; }
        .task-tab.active[data-list="peter_queue"] { color: #d97706; }
        .task-tab.active[data-list="idea"] { color: #7c3aed; }
        .task-tab.active[data-list="research"] { color: #059669; }

        .task-tab-icon {
            font-size: 15px;
        }

        .task-tab-count {
            font-size: 10px;
            font-weight: 700;
            padding: 1px 7px;
            border-radius: 99px;
            font-family: 'Consolas', monospace;
            background: #f1f5f9;
            color: #94a3b8;
        }

        .task-tab.active .task-tab-count {
            background: currentColor;
            background: color-mix(in srgb, currentColor 15%, transparent);
            color: currentColor;
        }

        /* Kanban Board */
        .task-kanban {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding: 16px 20px 20px;
            flex: 1;
        }

        .task-column {
            min-width: 260px;
            max-width: 280px;
            flex: 0 0 260px;
            display: flex;
            flex-direction: column;
            border-radius: 12px;
            border: 2px solid transparent;
            transition: all 0.25s ease;
            overflow: hidden;
        }

        .task-column.drag-over {
            border-style: dashed;
        }

        .task-column-header {
            padding: 14px 14px 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .task-column-dot {
            width: 10px;
            height: 10px;
            border-radius: 99px;
            flex-shrink: 0;
        }

        .task-column-dot.pulse {
            animation: pulse-glow 2.5s infinite;
        }

        @keyframes pulse-glow {
            0%, 100% { box-shadow: 0 0 0 0 rgba(245,158,11,0.35); }
            50% { box-shadow: 0 0 10px 4px rgba(245,158,11,0); }
        }

        .task-column-label {
            font-size: 12px;
            font-weight: 700;
            color: #334155;
            letter-spacing: 0.3px;
            text-transform: uppercase;
            flex: 1;
        }

        .task-column-count {
            font-size: 11px;
            font-weight: 700;
            padding: 1px 8px;
            border-radius: 99px;
            font-family: 'Consolas', monospace;
        }

        .task-column-cards {
            flex: 1;
            overflow-y: auto;
            padding: 0 8px 8px;
            min-height: 80px;
        }

        /* Task Card */
        .task-card {
            background: #fff;
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 8px;
            cursor: grab;
            transition: opacity 0.2s, transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            position: relative;
        }

        .task-card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-1px);
        }

        .task-card.dragging {
            opacity: 0.35;
            transform: rotate(1.5deg) scale(0.98);
        }

        .task-card-title {
            font-size: 13px;
            font-weight: 600;
            color: #1e293b;
            line-height: 1.4;
            margin-bottom: 8px;
        }

        .task-card-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 8px;
            align-items: center;
        }

        /* Priority Pills */
        .priority-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 2px 8px;
            border-radius: 99px;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }

        .priority-pill .dot {
            width: 6px;
            height: 6px;
            border-radius: 99px;
        }

        .priority-pill.critical { color: #dc2626; background: #fef2f2; }
        .priority-pill.critical .dot { background: #dc2626; }

        .priority-pill.high { color: #ea580c; background: #fff7ed; }
        .priority-pill.high .dot { background: #ea580c; }

        .priority-pill.medium { color: #d97706; background: #fffbeb; }
        .priority-pill.medium .dot { background: #d97706; }

        .priority-pill.low { color: #2563eb; background: #eff6ff; }
        .priority-pill.low .dot { background: #2563eb; }

        .priority-pill.someday { color: #9ca3af; background: #f9fafb; }
        .priority-pill.someday .dot { background: #9ca3af; }

        /* Effort Badge */
        .effort-badge {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 2px 7px;
            border-radius: 99px;
            font-size: 10px;
            font-weight: 500;
            color: #64748b;
            background: #f1f5f9;
            font-family: 'Consolas', monospace;
        }

        /* Category Badges */
        .task-categories {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-bottom: 8px;
        }

        .category-badge {
            display: inline-flex;
            align-items: center;
            padding: 1px 8px;
            border-radius: 99px;
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 0.2px;
            white-space: nowrap;
        }

        /* Task Card Footer */
        .task-card-footer {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            font-size: 11px;
            color: #94a3b8;
            font-family: 'Consolas', monospace;
        }

        .task-card-footer .spacer {
            flex: 1;
        }

        .task-card-footer .by-peter {
            font-size: 10px;
            color: #94a3b8;
            font-style: italic;
            font-family: inherit;
        }

        .task-date {
            display: inline-flex;
            align-items: center;
            gap: 3px;
        }

        .task-date.overdue {
            color: #dc2626;
            background: #fef2f2;
            padding: 1px 6px;
            border-radius: 4px;
        }

        .heartbeat-date {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            font-weight: 600;
            color: #d97706;
            background: #fef9e7;
            padding: 1px 6px;
            border-radius: 4px;
        }

        /* Task Card Actions */
        .task-card-actions {
            display: flex;
            gap: 4px;
            margin-top: 10px;
            border-top: 1px solid #f1f5f9;
            padding-top: 8px;
        }

        .task-action-btn {
            display: inline-flex;
            align-items: center;
            gap: 3px;
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            background: #fff;
            color: #64748b;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .task-action-btn:hover {
            border-color: #16a34a;
            color: #16a34a;
        }

        .task-action-btn.heartbeat {
            border: 1.5px solid #f59e0b;
            background: linear-gradient(135deg, #fffbeb, #fef3c7);
            color: #b45309;
            font-weight: 600;
        }

        .task-action-btn.heartbeat:hover {
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            transform: scale(1.02);
        }

        /* Heartbeat Dropdown */
        .heartbeat-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            z-index: 50;
            width: 300px;
            margin-top: 4px;
            background: #fff;
            border-radius: 12px;
            border: 1.5px solid #fde68a;
            box-shadow: 0 12px 40px rgba(0,0,0,0.15), 0 0 0 1px rgba(245,158,11,0.1);
            overflow: hidden;
        }

        .heartbeat-dropdown-header {
            padding: 12px 16px 8px;
            border-bottom: 1px solid #fef3c7;
            background: linear-gradient(135deg, #fffbeb, #fef9e7);
        }

        .heartbeat-dropdown-title {
            font-size: 13px;
            font-weight: 700;
            color: #92400e;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .heartbeat-dropdown-actions {
            padding: 8px;
        }

        .heartbeat-action {
            width: 100%;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            border-radius: 8px;
            border: none;
            background: transparent;
            color: #475569;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            text-align: left;
            transition: all 0.15s;
        }

        .heartbeat-action:hover {
            background: #f8fafc;
        }

        .heartbeat-action.primary {
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            color: #92400e;
            font-weight: 600;
        }

        .heartbeat-action.primary:hover {
            background: linear-gradient(135deg, #fde68a, #fbbf24);
        }

        .heartbeat-action-icon {
            width: 28px;
            height: 28px;
            border-radius: 7px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }

        .heartbeat-action.primary .heartbeat-action-icon {
            background: #f59e0b;
            color: #fff;
        }

        .heartbeat-action-label {
            flex: 1;
        }

        .heartbeat-action-sublabel {
            font-size: 10px;
            font-weight: 400;
            color: #94a3b8;
            margin-top: 1px;
        }

        .heartbeat-dates-label {
            padding: 4px 16px 6px;
            font-size: 10px;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .heartbeat-dates-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 4px;
            padding: 0 8px 12px;
        }

        .heartbeat-date-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 6px 2px;
            border-radius: 8px;
            border: 1px solid #f1f5f9;
            background: #fff;
            cursor: pointer;
            transition: all 0.15s;
            gap: 2px;
        }

        .heartbeat-date-btn:hover {
            background: #fef9e7;
            border-color: #fde68a;
        }

        .heartbeat-date-btn .day {
            font-size: 9px;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
        }

        .heartbeat-date-btn .num {
            font-size: 15px;
            font-weight: 700;
            color: #1e293b;
        }

        .heartbeat-date-dots {
            display: flex;
            gap: 2px;
            min-height: 6px;
        }

        .heartbeat-date-dot {
            width: 5px;
            height: 5px;
            border-radius: 99px;
            background: #f59e0b;
        }

        /* Quick Add Modal */
        .task-modal-overlay {
            position: fixed;
            inset: 0;
            z-index: 100;
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding-top: 80px;
            background: rgba(15,23,42,0.4);
            backdrop-filter: blur(4px);
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s;
        }

        .task-modal-overlay.show {
            opacity: 1;
            visibility: visible;
        }

        .task-modal {
            width: 420px;
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.2);
            overflow: hidden;
            transform: translateY(-12px);
            transition: transform 0.25s ease;
        }

        .task-modal-overlay.show .task-modal {
            transform: translateY(0);
        }

        .task-modal-header {
            padding: 16px 20px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .task-modal-title {
            font-size: 15px;
            font-weight: 700;
            color: #1e293b;
        }

        .task-modal-close {
            background: none;
            border: none;
            cursor: pointer;
            color: #94a3b8;
            padding: 4px;
            font-size: 18px;
        }

        .task-modal-body {
            padding: 16px 20px;
        }

        .task-modal-input {
            width: 100%;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1.5px solid #e2e8f0;
            font-size: 14px;
            outline: none;
            box-sizing: border-box;
            transition: border-color 0.15s;
        }

        .task-modal-input:focus {
            border-color: #d97706;
        }

        .task-modal-list-selector {
            display: flex;
            gap: 6px;
            margin-top: 14px;
        }

        .task-modal-list-btn {
            flex: 1;
            padding: 8px 4px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            transition: all 0.15s;
            border: 2px solid #f1f5f9;
            background: #fff;
            color: #64748b;
        }

        .task-modal-list-btn.active {
            border-color: var(--list-accent, #d97706);
            background: color-mix(in srgb, var(--list-accent, #d97706) 10%, transparent);
            color: var(--list-accent, #d97706);
        }

        .task-modal-list-icon {
            font-size: 16px;
            margin-bottom: 2px;
            display: block;
        }

        .task-modal-section-label {
            font-size: 11px;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin: 14px 0 6px;
        }

        .task-modal-priority-selector {
            display: flex;
            gap: 4px;
        }

        .task-modal-priority-btn {
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s;
            border: 2px solid transparent;
            background: #f8fafc;
            color: #94a3b8;
        }

        .task-modal-priority-btn.active {
            border-color: var(--priority-color);
            background: var(--priority-bg);
            color: var(--priority-color);
        }

        .task-modal-footer {
            padding: 12px 20px 16px;
            display: flex;
            justify-content: flex-end;
            gap: 8px;
        }

        .task-modal-btn {
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
        }

        .task-modal-btn.secondary {
            border: 1px solid #e2e8f0;
            background: #fff;
            color: #64748b;
        }

        .task-modal-btn.primary {
            border: none;
            background: linear-gradient(135deg, #1a2744, #2d4a7a);
            color: #fff;
            font-weight: 600;
        }

        .task-modal-btn.primary:hover {
            transform: translateY(-1px);
        }

        /* Task Toast */
        .task-toast {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(-10px);
            z-index: 200;
            padding: 10px 20px;
            border-radius: 10px;
            background: #1e293b;
            color: #fff;
            font-size: 13px;
            font-weight: 600;
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            gap: 8px;
            opacity: 0;
            visibility: hidden;
            transition: all 0.2s ease;
        }

        .task-toast.show {
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) translateY(0);
        }

        /* Empty State */
        .task-column-empty {
            padding: 24px 16px;
            text-align: center;
            color: #94a3b8;
            font-size: 12px;
        }

        /* Scrollbar styling for task board */
        .task-kanban::-webkit-scrollbar,
        .task-column-cards::-webkit-scrollbar {
            width: 5px;
            height: 5px;
        }

        .task-kanban::-webkit-scrollbar-track,
        .task-column-cards::-webkit-scrollbar-track {
            background: transparent;
        }

        .task-kanban::-webkit-scrollbar-thumb,
        .task-column-cards::-webkit-scrollbar-thumb {
            background: #d1d5db;
            border-radius: 99px;
        }

        .task-kanban::-webkit-scrollbar-thumb:hover,
        .task-column-cards::-webkit-scrollbar-thumb:hover {
            background: #9ca3af;
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
                <div class="nav-item" data-view="tasks">
                    ⚡ Tasks
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
                <div class="nav-item" data-view="parser">
                    🔧 Parser System
                </div>
                <div class="nav-item" data-view="search">
                    🔍 Knowledge Search
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

        // Claude Code Health Panel
        async function refreshClaudeHealth() {
            const container = document.getElementById('claude-health-content');
            if (!container) return;

            try {
                const health = await api('/claude-code-health');

                if (health.error) {
                    container.innerHTML = '<p style="color: var(--warning);">Health data unavailable: ' + health.error + '</p>';
                    return;
                }

                // Determine overall health status
                const isHealthy = health.job_success_rate >= 80 && health.clear_success_rate >= 80 && !health.alerts.recent_garbage;
                const isWarning = (health.job_success_rate >= 50 && health.job_success_rate < 80) || (health.clear_success_rate >= 50 && health.clear_success_rate < 80);
                const statusColor = isHealthy ? 'var(--success)' : (isWarning ? 'var(--warning)' : 'var(--error)');
                const statusText = isHealthy ? 'Healthy' : (isWarning ? 'Degraded' : 'Unhealthy');

                // Build alerts list
                let alertsHtml = '';
                if (health.alerts.consecutive_failure_alert) {
                    alertsHtml += '<div style="padding: 0.5rem; background: rgba(239,68,68,0.2); border-radius: 4px; margin-bottom: 0.5rem;">⚠️ ' + health.consecutive_failures + ' consecutive job failures</div>';
                }
                if (health.alerts.clear_rate_alert) {
                    alertsHtml += '<div style="padding: 0.5rem; background: rgba(239,68,68,0.2); border-radius: 4px; margin-bottom: 0.5rem;">⚠️ /clear success rate low (' + health.clear_success_rate + '%)</div>';
                }
                if (health.alerts.recent_garbage) {
                    alertsHtml += '<div style="padding: 0.5rem; background: rgba(251,191,36,0.2); border-radius: 4px; margin-bottom: 0.5rem;">⚠️ Recent garbage responses detected</div>';
                }

                // Build recent jobs table
                let jobsHtml = '';
                if (health.recent_jobs && health.recent_jobs.length > 0) {
                    jobsHtml = '<table style="width: 100%; font-size: 0.85rem; margin-top: 1rem;"><thead><tr><th style="text-align: left; padding: 0.25rem;">Time</th><th style="text-align: left; padding: 0.25rem;">Job</th><th style="text-align: center; padding: 0.25rem;">Status</th><th style="text-align: right; padding: 0.25rem;">Duration</th></tr></thead><tbody>';
                    health.recent_jobs.forEach(job => {
                        const statusIcon = job.success && !job.is_garbage ? '✅' : (job.is_garbage ? '🗑️' : '❌');
                        const statusTitle = job.success ? (job.is_garbage ? 'Garbage response' : 'Success') : (job.error || 'Failed');
                        jobsHtml += '<tr><td style="padding: 0.25rem; color: var(--text-secondary);">' + job.timestamp + '</td><td style="padding: 0.25rem;">' + job.name + '</td><td style="text-align: center; padding: 0.25rem;" title="' + statusTitle + '">' + statusIcon + '</td><td style="text-align: right; padding: 0.25rem;">' + job.duration + 's</td></tr>';
                    });
                    jobsHtml += '</tbody></table>';
                } else {
                    jobsHtml = '<p style="color: var(--text-secondary); margin-top: 1rem;">No recent jobs recorded</p>';
                }

                container.innerHTML = \`
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1rem;">
                        <div style="text-align: center;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: \${statusColor};">\${statusText}</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">Overall Status</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: \${health.job_success_rate >= 80 ? 'var(--success)' : (health.job_success_rate >= 50 ? 'var(--warning)' : 'var(--error)')};">\${health.job_success_rate}%</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">Job Success Rate</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: \${health.clear_success_rate >= 80 ? 'var(--success)' : (health.clear_success_rate >= 50 ? 'var(--warning)' : 'var(--error)')};">\${health.clear_success_rate}%</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">/clear Success</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: \${health.garbage_rate <= 5 ? 'var(--success)' : (health.garbage_rate <= 20 ? 'var(--warning)' : 'var(--error)')};">\${health.garbage_rate}%</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">Garbage Rate</div>
                        </div>
                    </div>
                    \${alertsHtml}
                    <div style="font-weight: 600; font-size: 0.9rem;">Recent Jobs (last \${health.recent_jobs?.length || 0})</div>
                    \${jobsHtml}
                \`;
            } catch (err) {
                container.innerHTML = '<p style="color: var(--error);">Error loading health data: ' + err.message + '</p>';
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

                <!-- Claude Code Health Panel -->
                <div id="claude-health-panel" class="card" style="margin-bottom: 1.5rem;">
                    <div class="card-header">
                        <span class="card-title">🩺 Claude Code Health</span>
                        <button class="btn btn-sm btn-secondary" onclick="refreshClaudeHealth()">Refresh</button>
                    </div>
                    <div id="claude-health-content">Loading health data...</div>
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

            // Load Claude health data
            refreshClaudeHealth();
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

        // ====================================================================
        // Parser System Functions
        // ====================================================================

        let parserTab = 'fixtures';

        async function renderParser() {
            const content = document.getElementById('content');
            content.innerHTML = '<h2>Loading parser system...</h2>';

            const status = await api('/parser/status');

            if (status.error) {
                content.innerHTML = `
                    <h2>🔧 Parser System</h2>
                    <div class="card">
                        <p style="color: var(--error);">Error: ${escapeHtml(status.error)}</p>
                    </div>
                `;
                return;
            }

            const passRate = status.fixtures.total > 0
                ? (status.fixtures.pass_rate * 100).toFixed(1)
                : '0.0';
            const passClass = passRate >= 90 ? 'success' : passRate >= 70 ? 'warning' : 'error';

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>🔧 Parser System</h2>
                    <button class="btn btn-secondary" onclick="renderParser()">Refresh</button>
                </div>

                <!-- Summary Cards -->
                <div class="grid grid-4" style="margin-bottom: 1.5rem;">
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Pass Rate</span>
                        </div>
                        <div style="font-size: 2rem; color: var(--${passClass});">
                            ${passRate}%
                        </div>
                        <div style="color: var(--text-secondary);">
                            ${status.fixtures.passing}/${status.fixtures.total} fixtures
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Captures (24h)</span>
                        </div>
                        <div style="font-size: 2rem;">
                            ${status.captures_24h.total}
                        </div>
                        <div style="color: var(--text-secondary);">
                            ${status.captures_24h.failures} failures
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Feedback</span>
                        </div>
                        <div style="font-size: 2rem;">
                            ${status.feedback.pending}
                        </div>
                        <div style="color: var(--text-secondary);">
                            ${status.feedback.high_priority} high priority
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">Cycles</span>
                        </div>
                        <div style="font-size: 2rem;">
                            ${status.cycles.total}
                        </div>
                        <div style="color: var(--text-secondary);">
                            ${status.cycles.committed} committed
                        </div>
                    </div>
                </div>

                <!-- Tabs -->
                <div class="memory-tabs" style="margin-bottom: 1rem;">
                    <div class="memory-tab ${parserTab === 'fixtures' ? 'active' : ''}"
                         onclick="switchParserTab('fixtures')">Fixtures</div>
                    <div class="memory-tab ${parserTab === 'captures' ? 'active' : ''}"
                         onclick="switchParserTab('captures')">Captures</div>
                    <div class="memory-tab ${parserTab === 'feedback' ? 'active' : ''}"
                         onclick="switchParserTab('feedback')">Feedback</div>
                    <div class="memory-tab ${parserTab === 'cycles' ? 'active' : ''}"
                         onclick="switchParserTab('cycles')">Cycles</div>
                    <div class="memory-tab ${parserTab === 'drift' ? 'active' : ''}"
                         onclick="switchParserTab('drift')">Drift</div>
                </div>

                <!-- Tab Content -->
                <div id="parser-tab-content"></div>

                <!-- Actions -->
                <div style="margin-top: 1.5rem; display: flex; gap: 0.5rem;">
                    <button class="btn btn-primary" onclick="runParserRegression()">
                        Run Regression
                    </button>
                    <button class="btn btn-secondary" onclick="markParserReviewed()">
                        Mark Reviewed
                    </button>
                </div>
            `;

            await loadParserTab(parserTab);
        }

        async function switchParserTab(tab) {
            parserTab = tab;
            document.querySelectorAll('#content .memory-tab').forEach(t => {
                t.classList.toggle('active', t.textContent.toLowerCase() === tab);
            });
            await loadParserTab(tab);
        }

        async function loadParserTab(tab) {
            const container = document.getElementById('parser-tab-content');
            container.innerHTML = '<div class="card"><p style="color: var(--text-secondary);">Loading...</p></div>';

            switch(tab) {
                case 'fixtures': await renderFixturesTab(container); break;
                case 'captures': await renderCapturesTab(container); break;
                case 'feedback': await renderFeedbackTab(container); break;
                case 'cycles': await renderCyclesTab(container); break;
                case 'drift': await renderDriftTab(container); break;
            }
        }

        async function renderFixturesTab(container) {
            const data = await api('/parser/fixtures');

            if (data.error) {
                container.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Category breakdown
            const categories = Object.entries(data.by_category || {});
            let categoryHtml = '<p style="color: var(--text-secondary);">No fixtures found</p>';

            if (categories.length > 0) {
                categoryHtml = `
                    <div class="grid grid-3">
                        ${categories.map(([cat, stats]) => {
                            const rate = stats.total > 0 ? (stats.passed / stats.total * 100).toFixed(0) : 0;
                            const rateClass = rate >= 90 ? 'success' : rate >= 70 ? 'warning' : 'error';
                            return `
                                <div class="card">
                                    <div class="card-header">
                                        <span class="card-title">${escapeHtml(cat)}</span>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                                        <div style="flex: 1; height: 8px; background: var(--border); border-radius: 4px;">
                                            <div style="width: ${rate}%; height: 100%; background: var(--${rateClass}); border-radius: 4px;"></div>
                                        </div>
                                        <span style="color: var(--${rateClass}); font-weight: 600;">${rate}%</span>
                                    </div>
                                    <div style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.5rem;">
                                        ${stats.passed}/${stats.total} passing
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }

            // Chronic failures
            let failuresHtml = '';
            if (data.chronic_failures && data.chronic_failures.length > 0) {
                failuresHtml = `
                    <div class="card" style="margin-top: 1rem;">
                        <div class="card-header">
                            <span class="card-title">⚠️ Chronic Failures (3+ fails)</span>
                        </div>
                        <div style="max-height: 200px; overflow-y: auto;">
                            ${data.chronic_failures.map(f => `
                                <div style="padding: 0.5rem; border-bottom: 1px solid var(--border);">
                                    <div style="display: flex; justify-content: space-between;">
                                        <span style="font-family: monospace; font-size: 0.85rem;">${escapeHtml(f.id.substring(0, 8))}</span>
                                        <span style="color: var(--error);">${f.fail_count} fails</span>
                                    </div>
                                    <div style="color: var(--text-secondary); font-size: 0.85rem;">${escapeHtml(f.category)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            container.innerHTML = categoryHtml + failuresHtml;
        }

        async function renderCapturesTab(container) {
            const data = await api('/parser/captures');

            if (data.error) {
                container.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Quality signal counts
            const stats = data.stats || {};
            const signalHtml = `
                <div class="grid grid-4" style="margin-bottom: 1rem;">
                    <div class="card" style="text-align: center;">
                        <div style="font-size: 1.5rem;">${stats.empty || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">Empty</div>
                    </div>
                    <div class="card" style="text-align: center;">
                        <div style="font-size: 1.5rem;">${stats.ansi || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">ANSI</div>
                    </div>
                    <div class="card" style="text-align: center;">
                        <div style="font-size: 1.5rem;">${stats.echo || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">Echo</div>
                    </div>
                    <div class="card" style="text-align: center;">
                        <div style="font-size: 1.5rem;">${stats.reacted || 0}</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">Reacted</div>
                    </div>
                </div>
            `;

            // Captures table
            let capturesHtml = '<p style="color: var(--text-secondary);">No captures in last 24h</p>';
            if (data.captures && data.captures.length > 0) {
                capturesHtml = `
                    <div class="card" style="max-height: 400px; overflow-y: auto;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="border-bottom: 1px solid var(--border);">
                                    <th style="text-align: left; padding: 0.5rem;">Time</th>
                                    <th style="text-align: left; padding: 0.5rem;">Channel</th>
                                    <th style="text-align: left; padding: 0.5rem;">Skill</th>
                                    <th style="text-align: center; padding: 0.5rem;">Flags</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.captures.map(c => {
                                    const time = new Date(c.captured_at).toLocaleTimeString();
                                    const flags = [];
                                    if (c.was_empty) flags.push('⬜');
                                    if (c.had_ansi) flags.push('🔴');
                                    if (c.had_echo) flags.push('🔄');
                                    if (c.user_reacted) flags.push(c.user_reacted);
                                    return `
                                        <tr style="border-bottom: 1px solid var(--border);">
                                            <td style="padding: 0.5rem; font-size: 0.85rem;">${time}</td>
                                            <td style="padding: 0.5rem; font-size: 0.85rem;">${escapeHtml(c.channel_name || '-')}</td>
                                            <td style="padding: 0.5rem; font-size: 0.85rem;">${escapeHtml(c.skill_name || '-')}</td>
                                            <td style="padding: 0.5rem; text-align: center;">${flags.join(' ') || '-'}</td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            container.innerHTML = signalHtml + capturesHtml;
        }

        async function renderFeedbackTab(container) {
            const data = await api('/parser/feedback');

            if (data.error) {
                container.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Summary
            const summary = data.summary || {};
            const summaryHtml = `
                <div class="card" style="margin-bottom: 1rem;">
                    <div style="display: flex; gap: 2rem;">
                        <div>
                            <span style="font-size: 1.5rem; font-weight: 600;">${summary.total || 0}</span>
                            <span style="color: var(--text-secondary);"> pending</span>
                        </div>
                        <div>
                            <span style="font-size: 1.5rem; font-weight: 600; color: var(--error);">${summary.high_priority || 0}</span>
                            <span style="color: var(--text-secondary);"> high priority</span>
                        </div>
                    </div>
                </div>
            `;

            // Feedback list
            let feedbackHtml = '<p style="color: var(--text-secondary);">No pending feedback</p>';
            if (data.feedback && data.feedback.length > 0) {
                feedbackHtml = `
                    <div class="card" style="max-height: 400px; overflow-y: auto;">
                        ${data.feedback.map(f => {
                            const time = new Date(f.created_at).toLocaleString();
                            const priorityColor = f.priority === 'high' ? 'error' : f.priority === 'normal' ? 'warning' : 'text-secondary';
                            return `
                                <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                                    <div style="display: flex; justify-content: space-between; align-items: start;">
                                        <div>
                                            <span style="font-weight: 600;">${escapeHtml(f.category)}</span>
                                            ${f.skill_name ? `<span style="color: var(--text-secondary);"> • ${escapeHtml(f.skill_name)}</span>` : ''}
                                        </div>
                                        <div style="display: flex; gap: 0.5rem; align-items: center;">
                                            <span style="color: var(--${priorityColor}); font-size: 0.75rem;">${escapeHtml(f.priority)}</span>
                                            <button class="btn btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;"
                                                    onclick="resolveFeedback('${f.id}')">Resolve</button>
                                        </div>
                                    </div>
                                    ${f.description ? `<div style="margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.85rem;">${escapeHtml(f.description)}</div>` : ''}
                                    <div style="margin-top: 0.25rem; color: var(--text-secondary); font-size: 0.75rem;">
                                        ${escapeHtml(f.input_method)} • ${time}
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }

            container.innerHTML = summaryHtml + feedbackHtml;
        }

        async function renderCyclesTab(container) {
            const data = await api('/parser/cycles');

            if (data.error) {
                container.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Review status
            const review = data.review_status || {};
            const reviewClass = review.review_required ? 'error' : 'success';
            const reviewHtml = `
                <div class="card" style="margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 1.5rem; font-weight: 600;">${review.cycles_since_review || 0}</span>
                            <span style="color: var(--text-secondary);"> cycles since last review</span>
                        </div>
                        <div style="color: var(--${reviewClass});">
                            ${review.review_required ? '⚠️ Review Required' : '✅ Up to date'}
                        </div>
                    </div>
                </div>
            `;

            // Cycles table
            let cyclesHtml = '<p style="color: var(--text-secondary);">No improvement cycles yet</p>';
            if (data.cycles && data.cycles.length > 0) {
                cyclesHtml = `
                    <div class="card" style="max-height: 400px; overflow-y: auto;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="border-bottom: 1px solid var(--border);">
                                    <th style="text-align: left; padding: 0.5rem;">Date</th>
                                    <th style="text-align: left; padding: 0.5rem;">Target</th>
                                    <th style="text-align: center; padding: 0.5rem;">Score</th>
                                    <th style="text-align: center; padding: 0.5rem;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.cycles.map(c => {
                                    const date = new Date(c.started_at).toLocaleDateString();
                                    const scoreBefore = c.score_before ? (c.score_before * 100).toFixed(1) : '-';
                                    const scoreAfter = c.score_after ? (c.score_after * 100).toFixed(1) : '-';
                                    const scoreChange = c.score_before && c.score_after
                                        ? ((c.score_after - c.score_before) * 100).toFixed(1)
                                        : null;
                                    const changeClass = scoreChange > 0 ? 'success' : scoreChange < 0 ? 'error' : 'text-secondary';
                                    return `
                                        <tr style="border-bottom: 1px solid var(--border);">
                                            <td style="padding: 0.5rem; font-size: 0.85rem;">${date}</td>
                                            <td style="padding: 0.5rem; font-size: 0.85rem;">${escapeHtml(c.target_stage || '-')}</td>
                                            <td style="padding: 0.5rem; text-align: center; font-size: 0.85rem;">
                                                ${scoreBefore}%
                                                ${scoreChange !== null ? `<span style="color: var(--${changeClass});">(${scoreChange > 0 ? '+' : ''}${scoreChange})</span>` : ''}
                                            </td>
                                            <td style="padding: 0.5rem; text-align: center;">
                                                ${c.committed ? '✅' : '❌'}
                                                ${c.human_reviewed ? '👁️' : ''}
                                            </td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            container.innerHTML = reviewHtml + cyclesHtml;
        }

        async function renderDriftTab(container) {
            const data = await api('/parser/drift');

            if (data.error) {
                container.innerHTML = `<div class="card"><p style="color: var(--error);">Error: ${escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Skill health grid
            let healthHtml = '<p style="color: var(--text-secondary);">No skill health data</p>';
            if (data.skill_health && data.skill_health.length > 0) {
                healthHtml = `
                    <div class="grid grid-3" style="margin-bottom: 1rem;">
                        ${data.skill_health.map(s => {
                            const score = s.avg_score ? (s.avg_score * 100).toFixed(0) : '-';
                            const statusClass = s.status === 'healthy' ? 'success' : s.status === 'warning' ? 'warning' : 'error';
                            return `
                                <div class="card">
                                    <div class="card-header">
                                        <span class="card-title">${escapeHtml(s.display_name || s.skill_name)}</span>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <span style="font-size: 1.5rem; color: var(--${statusClass});">${score}%</span>
                                        <span style="color: var(--text-secondary); font-size: 0.85rem;">${s.drift_count || 0} drifts</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }

            // Drift alerts
            let alertsHtml = '';
            if (data.alerts && data.alerts.length > 0) {
                alertsHtml = `
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">⚠️ Recent Drift Alerts</span>
                        </div>
                        <div style="max-height: 300px; overflow-y: auto;">
                            ${data.alerts.map(a => {
                                const time = new Date(a.captured_at).toLocaleString();
                                const score = a.format_score ? (a.format_score * 100).toFixed(0) : '-';
                                return `
                                    <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                                        <div style="display: flex; justify-content: space-between;">
                                            <span style="font-weight: 600;">${escapeHtml(a.skill_name)}</span>
                                            <span style="color: var(--error);">${score}%</span>
                                        </div>
                                        ${a.drift_details ? `<div style="margin-top: 0.5rem; color: var(--text-secondary); font-size: 0.85rem;">${escapeHtml(a.drift_details.join(', '))}</div>` : ''}
                                        <div style="margin-top: 0.25rem; color: var(--text-secondary); font-size: 0.75rem;">${time}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                `;
            } else {
                alertsHtml = '<div class="card"><p style="color: var(--success);">✅ No drift alerts in last 24h</p></div>';
            }

            container.innerHTML = healthHtml + alertsHtml;
        }

        async function runParserRegression() {
            showToast('Running regression tests...');
            const result = await api('/parser/run-regression', { method: 'POST' });
            if (result.success) {
                showToast('Regression complete!');
                await renderParser();
            } else {
                showToast('Regression failed: ' + (result.error || 'Unknown error'));
            }
        }

        async function markParserReviewed() {
            const result = await api('/parser/mark-reviewed', { method: 'POST' });
            if (result.success) {
                showToast('Marked as reviewed');
                await loadParserTab('cycles');
            } else {
                showToast('Error: ' + (result.error || 'Unknown error'));
            }
        }

        async function resolveFeedback(feedbackId) {
            const result = await api(`/parser/feedback/${feedbackId}/resolve`, { method: 'POST' });
            if (result.success) {
                showToast('Feedback resolved');
                await loadParserTab('feedback');
            } else {
                showToast('Error: ' + (result.error || 'Unknown error'));
            }
        }

        // ====================================================================
        // Knowledge Search Functions
        // ====================================================================

        let searchTab = 'memory';

        async function renderSearch() {
            const content = document.getElementById('content');

            content.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2>🔍 Knowledge Search</h2>
                </div>

                <p style="margin-bottom: 1rem; color: var(--text-secondary);">
                    Search Peter's knowledge systems using the exact same methods Peter uses.
                </p>

                <!-- Tabs -->
                <div class="memory-tabs" style="margin-bottom: 1rem;">
                    <div class="memory-tab ${searchTab === 'memory' ? 'active' : ''}"
                         onclick="switchSearchTab('memory')">🧠 Peterbot Memory</div>
                    <div class="memory-tab ${searchTab === 'brain' ? 'active' : ''}"
                         onclick="switchSearchTab('brain')">📚 Second Brain</div>
                </div>

                <!-- Search Input -->
                <div class="card" style="margin-bottom: 1rem;">
                    <div style="display: flex; gap: 0.5rem;">
                        <input type="text" id="search-query"
                               style="flex: 1; padding: 0.75rem; background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 1rem;"
                               placeholder="Enter your search query..."
                               onkeypress="if(event.key==='Enter') runKnowledgeSearch()">
                        <button class="btn btn-primary" onclick="runKnowledgeSearch()">Search</button>
                    </div>
                </div>

                <!-- Results -->
                <div id="search-results"></div>

                <!-- Stats (for Second Brain tab) -->
                <div id="search-stats" style="margin-top: 1rem;"></div>
            `;

            // Load stats for Second Brain if that tab is active
            if (searchTab === 'brain') {
                await loadSecondBrainStats();
            }
        }

        async function switchSearchTab(tab) {
            searchTab = tab;
            document.querySelectorAll('#content .memory-tab').forEach(t => {
                const isMemory = t.textContent.includes('Memory');
                const isBrain = t.textContent.includes('Brain');
                t.classList.toggle('active', (tab === 'memory' && isMemory) || (tab === 'brain' && isBrain));
            });

            // Clear results when switching tabs
            document.getElementById('search-results').innerHTML = '';
            document.getElementById('search-stats').innerHTML = '';

            // Load stats for Second Brain
            if (tab === 'brain') {
                await loadSecondBrainStats();
            }
        }

        async function runKnowledgeSearch() {
            const query = document.getElementById('search-query').value.trim();
            if (!query) {
                showToast('Please enter a search query');
                return;
            }

            const resultsDiv = document.getElementById('search-results');
            resultsDiv.innerHTML = '<div class="card"><p style="color: var(--text-secondary);">Searching...</p></div>';

            if (searchTab === 'memory') {
                await searchMemory(query, resultsDiv);
            } else {
                await searchSecondBrain(query, resultsDiv);
            }
        }

        async function searchMemory(query, resultsDiv) {
            const data = await api(`/search/memory?query=${encodeURIComponent(query)}`);

            if (!data.success) {
                resultsDiv.innerHTML = `
                    <div class="card">
                        <p style="color: var(--error);">Error: ${escapeHtml(data.error || 'Unknown error')}</p>
                        ${data.endpoint ? `<p style="color: var(--text-secondary); font-size: 0.85rem;">Endpoint: ${escapeHtml(data.endpoint)}</p>` : ''}
                    </div>
                `;
                return;
            }

            resultsDiv.innerHTML = `
                <div class="card">
                    <div class="card-header">
                        <span class="card-title">🧠 Memory Context Result</span>
                        <span style="color: var(--text-secondary); font-size: 0.85rem;">
                            ${data.length} chars | Project: ${escapeHtml(data.project)}
                        </span>
                    </div>
                    <div style="margin-top: 0.5rem; font-size: 0.75rem; color: var(--text-secondary);">
                        Endpoint: ${escapeHtml(data.endpoint)}
                    </div>
                    <div class="code-viewer" style="margin-top: 1rem;">
                        <div class="code-header">
                            <span>Context Injected to Peter</span>
                        </div>
                        <div class="code-content" style="max-height: 500px; overflow-y: auto;">
                            <pre style="white-space: pre-wrap;">${escapeHtml(data.context || '(empty)')}</pre>
                        </div>
                    </div>
                </div>
            `;
        }

        async function searchSecondBrain(query, resultsDiv) {
            const data = await api(`/search/second-brain?query=${encodeURIComponent(query)}&limit=10`);

            if (!data.success) {
                resultsDiv.innerHTML = `
                    <div class="card">
                        <p style="color: var(--error);">Error: ${escapeHtml(data.error || 'Unknown error')}</p>
                        ${data.traceback ? `<pre style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem; white-space: pre-wrap;">${escapeHtml(data.traceback)}</pre>` : ''}
                    </div>
                `;
                return;
            }

            // Individual items
            let itemsHtml = '';
            if (data.items && data.items.length > 0) {
                itemsHtml = data.items.map((item, i) => {
                    const similarity = item.similarity ? (item.similarity * 100).toFixed(1) : '?';
                    const simClass = item.similarity >= 0.85 ? 'success' : item.similarity >= 0.75 ? 'warning' : 'text-secondary';
                    return `
                        <div class="card" style="margin-bottom: 0.5rem;">
                            <div style="display: flex; justify-content: space-between; align-items: start;">
                                <div>
                                    <span style="font-weight: 600;">${i + 1}. ${escapeHtml(item.title || 'Untitled')}</span>
                                    <span style="color: var(--${simClass}); font-size: 0.85rem; margin-left: 0.5rem;">
                                        ${similarity}% match
                                    </span>
                                </div>
                                <span style="color: var(--text-secondary); font-size: 0.75rem;">
                                    ${escapeHtml(item.content_type || '')} / ${escapeHtml(item.capture_type || '')}
                                </span>
                            </div>
                            ${item.summary ? `<p style="margin-top: 0.5rem; color: var(--text-secondary);">${escapeHtml(item.summary.substring(0, 300))}${item.summary.length > 300 ? '...' : ''}</p>` : ''}
                            ${item.topics && item.topics.length > 0 ? `<div style="margin-top: 0.5rem;"><span style="color: var(--text-secondary); font-size: 0.75rem;">Tags: ${item.topics.slice(0, 5).map(t => escapeHtml(t)).join(', ')}</span></div>` : ''}
                            ${item.excerpts && item.excerpts.length > 0 ? `<blockquote style="margin-top: 0.5rem; padding-left: 0.75rem; border-left: 2px solid var(--border); color: var(--text-secondary); font-size: 0.85rem;">${escapeHtml(item.excerpts[0].substring(0, 200))}...</blockquote>` : ''}
                        </div>
                    `;
                }).join('');
            } else {
                itemsHtml = '<div class="card"><p style="color: var(--text-secondary);">No results found</p></div>';
            }

            resultsDiv.innerHTML = `
                <div style="margin-bottom: 1rem;">
                    <span style="font-weight: 600;">${data.count} results found</span>
                </div>

                ${itemsHtml}

                ${data.formatted_context ? `
                    <div class="card" style="margin-top: 1rem;">
                        <div class="card-header">
                            <span class="card-title">📝 Formatted Context (What Peter Sees)</span>
                        </div>
                        <div class="code-viewer" style="margin-top: 0.5rem;">
                            <div class="code-content" style="max-height: 400px; overflow-y: auto;">
                                <pre style="white-space: pre-wrap;">${escapeHtml(data.formatted_context)}</pre>
                            </div>
                        </div>
                    </div>
                ` : ''}
            `;
        }

        async function loadSecondBrainStats() {
            const statsDiv = document.getElementById('search-stats');
            statsDiv.innerHTML = '<div class="card"><p style="color: var(--text-secondary);">Loading stats...</p></div>';

            const data = await api('/search/second-brain/stats');

            if (!data.success) {
                statsDiv.innerHTML = `<div class="card"><p style="color: var(--error);">Error loading stats: ${escapeHtml(data.error || 'Unknown')}</p></div>`;
                return;
            }

            // Topics cloud
            let topicsHtml = '';
            if (data.topics && data.topics.length > 0) {
                topicsHtml = data.topics.map(t => `
                    <span style="display: inline-block; padding: 0.25rem 0.5rem; margin: 0.25rem; background: var(--bg-tertiary); border-radius: 4px; font-size: 0.85rem; cursor: pointer;"
                          onclick="document.getElementById('search-query').value='${escapeHtml(t.topic)}'; runKnowledgeSearch();">
                        ${escapeHtml(t.topic)} <span style="color: var(--text-secondary);">(${t.count})</span>
                    </span>
                `).join('');
            }

            // Recent items
            let recentHtml = '';
            if (data.recent_items && data.recent_items.length > 0) {
                recentHtml = data.recent_items.map(item => `
                    <div style="padding: 0.5rem 0; border-bottom: 1px solid var(--border);">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: 500;">${escapeHtml(item.title || 'Untitled')}</span>
                            <span style="color: var(--text-secondary); font-size: 0.75rem;">${escapeHtml(item.capture_type || '')}</span>
                        </div>
                        ${item.topics && item.topics.length > 0 ? `<div style="color: var(--text-secondary); font-size: 0.75rem;">${item.topics.slice(0, 3).join(', ')}</div>` : ''}
                    </div>
                `).join('');
            }

            statsDiv.innerHTML = `
                <div class="grid grid-2">
                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">📊 Stats</span>
                        </div>
                        <div style="font-size: 1.5rem; margin: 0.5rem 0;">${data.total_items || 0}</div>
                        <div style="color: var(--text-secondary);">Knowledge Items</div>
                        <div style="margin-top: 1rem;">
                            <span style="font-size: 1.25rem;">${data.total_connections || 0}</span>
                            <span style="color: var(--text-secondary);"> connections</span>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header">
                            <span class="card-title">🏷️ Top Topics (click to search)</span>
                        </div>
                        <div style="max-height: 150px; overflow-y: auto;">
                            ${topicsHtml || '<p style="color: var(--text-secondary);">No topics found</p>'}
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top: 1rem;">
                    <div class="card-header">
                        <span class="card-title">🕐 Recent Items</span>
                    </div>
                    <div style="max-height: 250px; overflow-y: auto;">
                        ${recentHtml || '<p style="color: var(--text-secondary);">No recent items</p>'}
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

        // ════════════════════════════════════════════════════════════════════
        // TASK BOARD
        // ════════════════════════════════════════════════════════════════════

        let taskActiveList = 'peter_queue';
        let taskData = { tasks: [], categories: [] };
        let taskDraggedId = null;
        let taskDragOverCol = null;
        let taskHeartbeatTarget = null;
        let taskSearchQuery = '';

        const TASK_PRIORITY = {
            critical: { label: 'Critical', color: '#dc2626', bg: '#fef2f2' },
            high: { label: 'High', color: '#ea580c', bg: '#fff7ed' },
            medium: { label: 'Medium', color: '#d97706', bg: '#fffbeb' },
            low: { label: 'Low', color: '#2563eb', bg: '#eff6ff' },
            someday: { label: 'Someday', color: '#9ca3af', bg: '#f9fafb' }
        };

        const TASK_CATEGORY = {
            'peterbot': { label: 'Peterbot', color: '#6366f1', bg: '#eef2ff' },
            'hadley-bricks': { label: 'Hadley Bricks', color: '#b45309', bg: '#fef3c7' },
            'ebay': { label: 'eBay', color: '#dc2626', bg: '#fef2f2' },
            'bricklink': { label: 'BrickLink', color: '#2563eb', bg: '#eff6ff' },
            'vinted': { label: 'Vinted', color: '#0d9488', bg: '#f0fdfa' },
            'running': { label: 'Running', color: '#16a34a', bg: '#f0fdf4' },
            'finance': { label: 'Finance', color: '#ca8a04', bg: '#fefce8' },
            'personal': { label: 'Personal', color: '#7c3aed', bg: '#f5f3ff' },
            'infrastructure': { label: 'Infrastructure', color: '#6b7280', bg: '#f9fafb' },
            'familyfuel': { label: 'FamilyFuel', color: '#10b981', bg: '#ecfdf5' },
            'amazon': { label: 'Amazon', color: '#f97316', bg: '#fff7ed' },
            'home': { label: 'Home', color: '#78716c', bg: '#f5f5f4' }
        };

        const TASK_LISTS = [
            { id: 'personal_todo', label: 'My Todos', icon: '📋', accent: '#2563eb' },
            { id: 'peter_queue', label: 'Peter Queue', icon: '🤖', accent: '#d97706' },
            { id: 'idea', label: 'Ideas', icon: '💡', accent: '#7c3aed' },
            { id: 'research', label: 'Research', icon: '🔬', accent: '#059669' }
        ];

        const TASK_COLUMNS = {
            personal_todo: [
                { id: 'inbox', label: 'Inbox', color: '#94a3b8', bg: '#f8fafc' },
                { id: 'scheduled', label: 'Scheduled', color: '#2563eb', bg: '#f0f6ff' },
                { id: 'in_progress', label: 'In Progress', color: '#d97706', bg: '#fefbf0' },
                { id: 'done', label: 'Done', color: '#16a34a', bg: '#f0fdf2' }
            ],
            peter_queue: [
                { id: 'queued', label: 'Queued', color: '#64748b', bg: '#f8fafc' },
                { id: 'heartbeat_scheduled', label: 'Heartbeat Scheduled', color: '#d97706', bg: '#fefbf0', pulse: true },
                { id: 'in_heartbeat', label: 'In Heartbeat', color: '#ea580c', bg: '#fff5ed', pulse: true },
                { id: 'in_progress', label: 'In Progress', color: '#2563eb', bg: '#f0f6ff' },
                { id: 'review', label: 'Review', color: '#7c3aed', bg: '#f6f3ff' },
                { id: 'done', label: 'Done', color: '#16a34a', bg: '#f0fdf2' }
            ],
            idea: [
                { id: 'inbox', label: 'Captured', color: '#94a3b8', bg: '#f8fafc' },
                { id: 'scheduled', label: 'Refined', color: '#2563eb', bg: '#f0f6ff' },
                { id: 'review', label: 'Approved', color: '#7c3aed', bg: '#f6f3ff' },
                { id: 'done', label: 'Promoted', color: '#16a34a', bg: '#f0fdf2' }
            ],
            research: [
                { id: 'queued', label: 'Queued', color: '#64748b', bg: '#f8fafc' },
                { id: 'in_progress', label: 'Researching', color: '#d97706', bg: '#fefbf0' },
                { id: 'findings_ready', label: 'Findings Ready', color: '#7c3aed', bg: '#f6f3ff' },
                { id: 'done', label: 'Actioned', color: '#16a34a', bg: '#f0fdf2' }
            ]
        };

        const TASK_EFFORT_LABELS = {
            trivial: 'Trivial', '30min': '30 min', '2hr': '2 hr',
            half_day: 'Half day', multi_day: 'Multi-day'
        };

        const HADLEY_API = 'http://localhost:8100';

        function formatTaskDate(dateStr) {
            if (!dateStr) return null;
            const d = new Date(dateStr);
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const diff = Math.round((d - today) / 86400000);
            if (diff === 0) return 'Today';
            if (diff === 1) return 'Tomorrow';
            if (diff === -1) return 'Yesterday';
            if (diff < -1) return Math.abs(diff) + 'd overdue';
            if (diff <= 7) return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' });
            return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        }

        function isTaskOverdue(dateStr) {
            if (!dateStr) return false;
            const d = new Date(dateStr);
            const today = new Date();
            today.setHours(23, 59, 59, 999);
            return d < today;
        }

        function getUpcomingDays() {
            const days = [];
            for (let i = 0; i < 10; i++) {
                const d = new Date();
                d.setDate(d.getDate() + i + 1);
                days.push({
                    date: d,
                    label: d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }),
                    iso: d.toISOString().split('T')[0]
                });
            }
            return days;
        }

        async function loadTasks() {
            try {
                const [tasksResp, catsResp, countsResp] = await Promise.all([
                    fetch(HADLEY_API + '/ptasks/list/' + taskActiveList + '?include_done=true'),
                    fetch(HADLEY_API + '/ptasks/categories'),
                    fetch(HADLEY_API + '/ptasks/counts')
                ]);

                const tasksData = await tasksResp.json();
                const catsData = await catsResp.json();
                const countsData = await countsResp.json();

                taskData.tasks = tasksData.tasks || [];
                taskData.categories = catsData.categories || [];
                taskData.counts = countsData.counts || {};
            } catch (e) {
                console.error('Failed to load tasks:', e);
                taskData.tasks = [];
                taskData.counts = {};
            }
        }

        function renderTaskCard(task) {
            const p = TASK_PRIORITY[task.priority] || TASK_PRIORITY.medium;
            const isQueue = taskActiveList === 'peter_queue';
            const scheduledLabel = formatTaskDate(task.scheduled_date);
            const dueDateLabel = formatTaskDate(task.due_date);
            const overdue = isTaskOverdue(task.due_date);
            const hbLabel = task.heartbeat_scheduled_for ? formatTaskDate(task.heartbeat_scheduled_for) : null;

            let categoriesHtml = '';
            if (task.categories && task.categories.length > 0) {
                categoriesHtml = '<div class="task-categories">';
                task.categories.forEach(slug => {
                    const cat = TASK_CATEGORY[slug];
                    if (cat) {
                        categoriesHtml += '<span class="category-badge" style="color: ' + cat.color + '; background: ' + cat.bg + '; border: 1px solid ' + cat.color + '22;">' + cat.label + '</span>';
                    }
                });
                categoriesHtml += '</div>';
            }

            let footerHtml = '<div class="task-card-footer">';
            if (task.attachments > 0) {
                footerHtml += '<span>📎 ' + task.attachments + '</span>';
            }
            if (task.comments > 0) {
                footerHtml += '<span>💬 ' + task.comments + '</span>';
            }
            if (scheduledLabel) {
                footerHtml += '<span class="scheduled-date">🗓️ ' + scheduledLabel + '</span>';
            }
            if (dueDateLabel) {
                footerHtml += '<span class="task-date' + (overdue ? ' overdue' : '') + '">⏰ ' + dueDateLabel + '</span>';
            }
            if (hbLabel) {
                footerHtml += '<span class="heartbeat-date">⚡ ' + hbLabel + '</span>';
            }
            footerHtml += '<span class="spacer"></span>';
            if (task.created_by === 'peter') {
                footerHtml += '<span class="by-peter">by Peter</span>';
            }
            footerHtml += '</div>';

            let actionsHtml = '<div class="task-card-actions">';
            if (isQueue && task.status === 'queued') {
                actionsHtml += '<button class="task-action-btn heartbeat" onclick="event.stopPropagation(); toggleTaskHeartbeat(\\'' + task.id + '\\')">⚡ Add to Heartbeat</button>';
            }
            if (task.status !== 'done') {
                actionsHtml += '<button class="task-action-btn" onclick="event.stopPropagation(); markTaskDone(\\'' + task.id + '\\')">✓ Done</button>';
            }
            actionsHtml += '</div>';

            return '<div class="task-card" data-task-id="' + task.id + '" draggable="true" ' +
                   'onclick="showEditTaskModal(\\'' + task.id + '\\')" ' +
                   'ondragstart="onTaskDragStart(event, \\'' + task.id + '\\')" ' +
                   'ondragend="onTaskDragEnd(event)" ' +
                   'style="border-left: 3.5px solid ' + p.color + '; cursor: pointer;">' +
                   '<div class="task-card-title">' + (task.is_pinned ? '⭐ ' : '') + escapeHtml(task.title) + '</div>' +
                   '<div class="task-card-meta">' +
                   '<span class="priority-pill ' + task.priority + '"><span class="dot"></span>' + p.label + '</span>' +
                   (task.estimated_effort ? '<span class="effort-badge">🕐 ' + (TASK_EFFORT_LABELS[task.estimated_effort] || task.estimated_effort) + '</span>' : '') +
                   '</div>' +
                   categoriesHtml +
                   footerHtml +
                   actionsHtml +
                   (taskHeartbeatTarget === task.id ? renderHeartbeatDropdown(task.id) : '') +
                   '</div>';
        }

        function renderHeartbeatDropdown(taskId) {
            const days = getUpcomingDays();
            const scheduledCounts = {};
            taskData.tasks.filter(t => t.heartbeat_scheduled_for).forEach(t => {
                const d = t.heartbeat_scheduled_for.split('T')[0];
                scheduledCounts[d] = (scheduledCounts[d] || 0) + 1;
            });

            let datesHtml = '';
            days.slice(0, 10).forEach(d => {
                const count = scheduledCounts[d.iso] || 0;
                let dotsHtml = '';
                for (let i = 0; i < Math.min(count, 4); i++) {
                    dotsHtml += '<span class="heartbeat-date-dot"></span>';
                }
                datesHtml += '<button class="heartbeat-date-btn" onclick="event.stopPropagation(); scheduleTaskHeartbeat(\\'' + taskId + '\\', \\'' + d.iso + '\\')">' +
                             '<span class="day">' + d.date.toLocaleDateString('en-GB', { weekday: 'short' }) + '</span>' +
                             '<span class="num">' + d.date.getDate() + '</span>' +
                             '<div class="heartbeat-date-dots">' + dotsHtml + '</div></button>';
            });

            return '<div class="heartbeat-dropdown" onclick="event.stopPropagation();">' +
                   '<div class="heartbeat-dropdown-header">' +
                   '<div class="heartbeat-dropdown-title">⚡ Schedule for Heartbeat</div></div>' +
                   '<div class="heartbeat-dropdown-actions">' +
                   '<button class="heartbeat-action primary" onclick="scheduleTaskHeartbeat(\\'' + taskId + '\\', null)">' +
                   '<span class="heartbeat-action-icon">⚡</span>' +
                   '<div class="heartbeat-action-label">Add to Current Heartbeat<div class="heartbeat-action-sublabel">Start working on this now</div></div></button>' +
                   '<button class="heartbeat-action" onclick="scheduleTaskHeartbeat(\\'' + taskId + '\\', \\'' + days[0].iso + '\\')">' +
                   '<span class="heartbeat-action-icon" style="background: #f1f5f9;">▶</span>' +
                   '<div class="heartbeat-action-label">Next Heartbeat — ' + days[0].label + '<div class="heartbeat-action-sublabel">Queue for the next cycle</div></div></button>' +
                   '</div>' +
                   '<div class="heartbeat-dates-label">Pick a day</div>' +
                   '<div class="heartbeat-dates-grid">' + datesHtml + '</div></div>';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function renderTasks() {
            loadTasks().then(() => {
                const columns = TASK_COLUMNS[taskActiveList] || [];
                const filteredTasks = taskData.tasks.filter(t => {
                    if (taskSearchQuery && !t.title.toLowerCase().includes(taskSearchQuery.toLowerCase())) return false;
                    return true;
                });

                const getListCount = (listId) => {
                    return taskData.counts[listId] || 0;
                };

                let tabsHtml = '';
                TASK_LISTS.forEach(l => {
                    const active = taskActiveList === l.id;
                    tabsHtml += '<button class="task-tab' + (active ? ' active' : '') + '" data-list="' + l.id + '" onclick="switchTaskList(\\'' + l.id + '\\')">' +
                               '<span class="task-tab-icon">' + l.icon + '</span>' +
                               l.label +
                               '<span class="task-tab-count">' + getListCount(l.id) + '</span></button>';
                });

                let columnsHtml = '';
                columns.forEach(col => {
                    const colTasks = filteredTasks.filter(t => t.status === col.id).sort((a, b) => {
                        const pOrder = { critical: 0, high: 1, medium: 2, low: 3, someday: 4 };
                        return (pOrder[a.priority] || 2) - (pOrder[b.priority] || 2);
                    });

                    let cardsHtml = '';
                    colTasks.forEach(task => {
                        cardsHtml += renderTaskCard(task);
                    });

                    if (colTasks.length === 0) {
                        cardsHtml = '<div class="task-column-empty">No tasks</div>';
                    }

                    columnsHtml += '<div class="task-column" data-col="' + col.id + '" style="background: ' + col.bg + ';" ' +
                                  'ondragover="onTaskDragOver(event, \\'' + col.id + '\\')" ' +
                                  'ondrop="onTaskDrop(event, \\'' + col.id + '\\')">' +
                                  '<div class="task-column-header">' +
                                  '<div class="task-column-dot' + (col.pulse ? ' pulse' : '') + '" style="background: ' + col.color + ';"></div>' +
                                  '<span class="task-column-label">' + col.label + '</span>' +
                                  '<span class="task-column-count" style="color: ' + col.color + '; background: ' + col.color + '18;">' + colTasks.length + '</span>' +
                                  '</div>' +
                                  '<div class="task-column-cards">' + cardsHtml + '</div></div>';
                });

                document.getElementById('content').innerHTML =
                    '<div class="task-board">' +
                    '<div class="task-header">' +
                    '<div class="task-header-brand">' +
                    '<div class="task-logo">⚡</div>' +
                    '<div><div class="task-header-title">Tasks</div>' +
                    '<div class="task-header-subtitle">HADLEY BRICKS</div></div></div>' +
                    '<div class="task-search">' +
                    '<span class="task-search-icon">🔍</span>' +
                    '<input type="text" placeholder="Search tasks..." value="' + taskSearchQuery + '" onkeyup="onTaskSearch(event)">' +
                    '</div>' +
                    '<button class="task-add-btn" onclick="showTaskModal()">+ Add Task</button>' +
                    '<button class="task-add-btn" style="background: #475569; margin-left: 8px;" onclick="showCategoryConfig()">⚙️ Tags</button>' +
                    '</div>' +
                    '<div class="task-tabs">' + tabsHtml + '</div>' +
                    '<div class="task-kanban">' + columnsHtml + '</div>' +
                    '</div>' +
                    '<div class="task-modal-overlay" id="task-modal" onclick="hideTaskModal()">' +
                    '<div class="task-modal" onclick="event.stopPropagation()">' +
                    '<div class="task-modal-header">' +
                    '<span class="task-modal-title">New Task</span>' +
                    '<button class="task-modal-close" onclick="hideTaskModal()">✕</button>' +
                    '</div>' +
                    '<div class="task-modal-body">' +
                    '<input type="text" class="task-modal-input" id="task-title-input" placeholder="What needs to be done?">' +
                    '<div class="task-modal-list-selector">' +
                    TASK_LISTS.map(l => '<button class="task-modal-list-btn' + (taskActiveList === l.id ? ' active' : '') + '" style="--list-accent: ' + l.accent + ';" data-list="' + l.id + '" onclick="selectTaskModalList(\\'' + l.id + '\\')">' +
                        '<span class="task-modal-list-icon">' + l.icon + '</span>' + l.label + '</button>').join('') +
                    '</div>' +
                    '<div class="task-modal-section-label">Priority</div>' +
                    '<div class="task-modal-priority-selector">' +
                    Object.entries(TASK_PRIORITY).map(([key, p]) => '<button class="task-modal-priority-btn' + (key === 'medium' ? ' active' : '') + '" style="--priority-color: ' + p.color + '; --priority-bg: ' + p.bg + ';" data-priority="' + key + '" onclick="selectTaskModalPriority(\\'' + key + '\\')">' + p.label + '</button>').join('') +
                    '</div>' +
                    '</div>' +
                    '<div class="task-modal-footer">' +
                    '<button class="task-modal-btn secondary" onclick="hideTaskModal()">Cancel</button>' +
                    '<button class="task-modal-btn primary" onclick="createTask()">Create Task</button>' +
                    '</div></div></div>' +
                    '<div class="task-toast" id="task-toast"></div>';
            });
        }

        function switchTaskList(listId) {
            taskActiveList = listId;
            taskSearchQuery = '';
            taskHeartbeatTarget = null;
            renderTasks();
        }

        function onTaskSearch(event) {
            taskSearchQuery = event.target.value;
            renderTasks();
        }

        function toggleTaskHeartbeat(taskId) {
            taskHeartbeatTarget = taskHeartbeatTarget === taskId ? null : taskId;
            renderTasks();
        }

        async function scheduleTaskHeartbeat(taskId, dateStr) {
            try {
                const body = dateStr ? { schedule_date: dateStr } : {};
                await fetch(HADLEY_API + '/ptasks/' + taskId + '/heartbeat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                taskHeartbeatTarget = null;
                showTaskToast(dateStr ? 'Scheduled for heartbeat on ' + formatTaskDate(dateStr) : 'Added to current heartbeat ⚡');
                renderTasks();
            } catch (e) {
                showTaskToast('Failed to schedule heartbeat');
            }
        }

        async function markTaskDone(taskId) {
            try {
                await fetch(HADLEY_API + '/ptasks/' + taskId + '/status', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: 'done', actor: 'chris' })
                });
                showTaskToast('Marked as done ✓');
                renderTasks();
            } catch (e) {
                showTaskToast('Failed to update task');
            }
        }

        let taskModalListType = null;
        let taskModalPriority = 'medium';

        function showTaskModal() {
            taskModalListType = taskActiveList;
            taskModalPriority = 'medium';
            document.getElementById('task-modal').classList.add('show');
            setTimeout(() => document.getElementById('task-title-input').focus(), 100);
        }

        function hideTaskModal() {
            document.getElementById('task-modal').classList.remove('show');
            document.getElementById('task-title-input').value = '';
        }

        function selectTaskModalList(listId) {
            taskModalListType = listId;
            document.querySelectorAll('.task-modal-list-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.list === listId);
            });
        }

        function selectTaskModalPriority(priority) {
            taskModalPriority = priority;
            document.querySelectorAll('.task-modal-priority-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.priority === priority);
            });
        }

        async function createTask() {
            const title = document.getElementById('task-title-input').value.trim();
            if (!title) {
                showTaskToast('Please enter a task title');
                return;
            }

            try {
                await fetch(HADLEY_API + '/ptasks', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        list_type: taskModalListType || taskActiveList,
                        title: title,
                        priority: taskModalPriority,
                        created_by: 'chris'
                    })
                });
                hideTaskModal();
                showTaskToast('Task created');
                renderTasks();
            } catch (e) {
                showTaskToast('Failed to create task');
            }
        }

        // Edit task functionality
        let editingTaskId = null;
        let editTaskData = null;

        function showEditTaskModal(taskId) {
            const task = taskData.tasks.find(t => t.id === taskId);
            if (!task) return;

            editingTaskId = taskId;
            editTaskData = { ...task };

            // Create edit modal HTML
            const columns = TASK_COLUMNS[task.list_type] || [];
            const statusOptions = columns.map(col =>
                '<option value="' + col.id + '"' + (task.status === col.id ? ' selected' : '') + '>' + col.label + '</option>'
            ).join('');

            const priorityOptions = Object.entries(TASK_PRIORITY).map(([key, p]) =>
                '<option value="' + key + '"' + (task.priority === key ? ' selected' : '') + '>' + p.label + '</option>'
            ).join('');

            const effortOptions = ['', 'trivial', '30min', '2hr', 'half_day', 'multi_day'].map(e =>
                '<option value="' + e + '"' + (task.estimated_effort === e ? ' selected' : '') + '>' + (TASK_EFFORT_LABELS[e] || 'None') + '</option>'
            ).join('');

            const modal = document.createElement('div');
            modal.className = 'task-modal-overlay show';
            modal.id = 'task-edit-modal';
            modal.onclick = function(e) { if (e.target === modal) hideEditTaskModal(); };
            modal.innerHTML =
                '<div class="task-modal" style="max-width: 500px;" onclick="event.stopPropagation()">' +
                '<div class="task-modal-header">' +
                '<span class="task-modal-title">Edit Task</span>' +
                '<button class="task-modal-close" onclick="hideEditTaskModal()">✕</button>' +
                '</div>' +
                '<div class="task-modal-body">' +
                '<label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">Title</label>' +
                '<input type="text" class="task-modal-input" id="edit-task-title" value="' + escapeHtml(task.title) + '">' +
                '<label style="display: block; margin: 12px 0 4px; color: #94a3b8; font-size: 12px;">Description</label>' +
                '<textarea class="task-modal-input" id="edit-task-desc" rows="3" style="resize: vertical;">' + escapeHtml(task.description || '') + '</textarea>' +
                '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">' +
                '<div><label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">Status</label>' +
                '<select class="task-modal-input" id="edit-task-status" style="padding: 8px;">' + statusOptions + '</select></div>' +
                '<div><label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">Priority</label>' +
                '<select class="task-modal-input" id="edit-task-priority" style="padding: 8px;">' + priorityOptions + '</select></div>' +
                '</div>' +
                '<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-top: 12px;">' +
                '<div><label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">📅 Scheduled</label>' +
                '<input type="date" class="task-modal-input" id="edit-task-scheduled" value="' + (task.scheduled_date ? task.scheduled_date.split('T')[0] : '') + '" style="padding: 8px;"></div>' +
                '<div><label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">⏰ Due Date</label>' +
                '<input type="date" class="task-modal-input" id="edit-task-due" value="' + (task.due_date ? task.due_date.split('T')[0] : '') + '" style="padding: 8px;"></div>' +
                '<div><label style="display: block; margin-bottom: 4px; color: #94a3b8; font-size: 12px;">🕐 Effort</label>' +
                '<select class="task-modal-input" id="edit-task-effort" style="padding: 8px;">' + effortOptions + '</select></div>' +
                '</div>' +
                '</div>' +
                '<div class="task-modal-footer">' +
                '<button class="task-modal-btn" style="background: #dc2626; margin-right: auto;" onclick="deleteTask(\\'' + taskId + '\\')">Delete</button>' +
                '<button class="task-modal-btn secondary" onclick="hideEditTaskModal()">Cancel</button>' +
                '<button class="task-modal-btn primary" onclick="saveTask()">Save</button>' +
                '</div></div>';

            document.body.appendChild(modal);
        }

        function hideEditTaskModal() {
            const modal = document.getElementById('task-edit-modal');
            if (modal) modal.remove();
            editingTaskId = null;
            editTaskData = null;
        }

        async function saveTask() {
            if (!editingTaskId) return;

            const title = document.getElementById('edit-task-title').value.trim();
            const description = document.getElementById('edit-task-desc').value.trim();
            const status = document.getElementById('edit-task-status').value;
            const priority = document.getElementById('edit-task-priority').value;
            const scheduledDate = document.getElementById('edit-task-scheduled').value;
            const dueDate = document.getElementById('edit-task-due').value;
            const effort = document.getElementById('edit-task-effort').value;

            if (!title) {
                showTaskToast('Title is required');
                return;
            }

            try {
                // Update task details
                await fetch(HADLEY_API + '/ptasks/' + editingTaskId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: title,
                        description: description || null,
                        priority: priority,
                        scheduled_date: scheduledDate || null,
                        due_date: dueDate || null,
                        estimated_effort: effort || null
                    })
                });

                // Update status if changed
                if (status !== editTaskData.status) {
                    await fetch(HADLEY_API + '/ptasks/' + editingTaskId + '/status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: status, actor: 'chris' })
                    });
                }

                hideEditTaskModal();
                showTaskToast('Task updated');
                renderTasks();
            } catch (e) {
                console.error('Failed to save task:', e);
                showTaskToast('Failed to save task');
            }
        }

        async function deleteTask(taskId) {
            if (!confirm('Delete this task?')) return;

            try {
                await fetch(HADLEY_API + '/ptasks/' + taskId, { method: 'DELETE' });
                hideEditTaskModal();
                showTaskToast('Task deleted');
                renderTasks();
            } catch (e) {
                showTaskToast('Failed to delete task');
            }
        }

        // Category Config Functions
        async function showCategoryConfig() {
            const cats = taskData.categories || [];

            let catsHtml = '';
            cats.forEach(cat => {
                catsHtml += '<div class="cat-config-row" data-cat-id="' + cat.id + '">' +
                    '<div class="cat-config-color" style="background: ' + cat.color + ';" onclick="pickCatColor(\\'' + cat.id + '\\')"></div>' +
                    '<input type="text" class="cat-config-name" value="' + escapeHtml(cat.name) + '" data-cat-id="' + cat.id + '" onchange="updateCatName(\\'' + cat.id + '\\', this.value)">' +
                    '<span class="cat-config-slug">' + cat.slug + '</span>' +
                    '<button class="cat-config-delete" onclick="deleteCat(\\'' + cat.id + '\\')">🗑️</button>' +
                    '</div>';
            });

            const modal = document.createElement('div');
            modal.className = 'task-modal-overlay show';
            modal.id = 'cat-config-modal';
            modal.onclick = function(e) { if (e.target === modal) hideCategoryConfig(); };
            modal.innerHTML =
                '<div class="task-modal" style="max-width: 500px;" onclick="event.stopPropagation()">' +
                '<div class="task-modal-header">' +
                '<span class="task-modal-title">⚙️ Manage Tags</span>' +
                '<button class="task-modal-close" onclick="hideCategoryConfig()">✕</button>' +
                '</div>' +
                '<div class="task-modal-body" style="max-height: 400px; overflow-y: auto;">' +
                '<div class="cat-config-list">' + catsHtml + '</div>' +
                '<div class="cat-config-add">' +
                '<input type="color" id="new-cat-color" value="#6366F1" style="width: 40px; height: 36px; border: none; cursor: pointer;">' +
                '<input type="text" class="task-modal-input" id="new-cat-name" placeholder="New tag name..." style="flex: 1;">' +
                '<button class="task-modal-btn primary" style="padding: 8px 16px;" onclick="createCat()">Add</button>' +
                '</div>' +
                '</div>' +
                '<div class="task-modal-footer">' +
                '<button class="task-modal-btn primary" onclick="hideCategoryConfig()">Done</button>' +
                '</div></div>' +
                '<style>' +
                '.cat-config-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }' +
                '.cat-config-row { display: flex; align-items: center; gap: 10px; padding: 8px; background: #1e293b; border-radius: 6px; }' +
                '.cat-config-color { width: 28px; height: 28px; border-radius: 6px; cursor: pointer; flex-shrink: 0; }' +
                '.cat-config-name { flex: 1; background: transparent; border: 1px solid #334155; border-radius: 4px; padding: 6px 10px; color: #e2e8f0; font-size: 14px; }' +
                '.cat-config-name:focus { border-color: #6366f1; outline: none; }' +
                '.cat-config-slug { color: #64748b; font-size: 12px; min-width: 80px; }' +
                '.cat-config-delete { background: none; border: none; cursor: pointer; font-size: 16px; opacity: 0.6; }' +
                '.cat-config-delete:hover { opacity: 1; }' +
                '.cat-config-add { display: flex; gap: 10px; align-items: center; padding-top: 12px; border-top: 1px solid #334155; }' +
                '</style>';

            document.body.appendChild(modal);
        }

        function hideCategoryConfig() {
            const modal = document.getElementById('cat-config-modal');
            if (modal) modal.remove();
        }

        async function createCat() {
            const name = document.getElementById('new-cat-name').value.trim();
            const color = document.getElementById('new-cat-color').value;

            if (!name) {
                showTaskToast('Enter a tag name');
                return;
            }

            try {
                const resp = await fetch(HADLEY_API + '/ptasks/categories', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, color: color })
                });

                if (!resp.ok) throw new Error('Failed to create');

                showTaskToast('Tag created');
                hideCategoryConfig();
                renderTasks(); // Reload to get new categories
            } catch (e) {
                showTaskToast('Failed to create tag');
            }
        }

        async function updateCatName(catId, newName) {
            if (!newName.trim()) return;

            try {
                await fetch(HADLEY_API + '/ptasks/categories/' + catId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newName.trim() })
                });
                showTaskToast('Tag updated');
            } catch (e) {
                showTaskToast('Failed to update tag');
            }
        }

        function pickCatColor(catId) {
            const input = document.createElement('input');
            input.type = 'color';
            input.style.position = 'absolute';
            input.style.opacity = '0';
            document.body.appendChild(input);

            input.addEventListener('change', async function() {
                try {
                    await fetch(HADLEY_API + '/ptasks/categories/' + catId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ color: input.value })
                    });
                    // Update the color swatch immediately
                    const row = document.querySelector('.cat-config-row[data-cat-id="' + catId + '"]');
                    if (row) {
                        row.querySelector('.cat-config-color').style.background = input.value;
                    }
                    showTaskToast('Color updated');
                } catch (e) {
                    showTaskToast('Failed to update color');
                }
                document.body.removeChild(input);
            });

            input.click();
        }

        async function deleteCat(catId) {
            if (!confirm('Delete this tag? It will be removed from all tasks.')) return;

            try {
                await fetch(HADLEY_API + '/ptasks/categories/' + catId, { method: 'DELETE' });
                // Remove the row from UI
                const row = document.querySelector('.cat-config-row[data-cat-id="' + catId + '"]');
                if (row) row.remove();
                showTaskToast('Tag deleted');
            } catch (e) {
                showTaskToast('Failed to delete tag');
            }
        }

        function showTaskToast(message) {
            const toast = document.getElementById('task-toast');
            toast.textContent = '⚡ ' + message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 2500);
        }

        // Drag and drop
        function onTaskDragStart(event, taskId) {
            taskDraggedId = taskId;
            event.target.classList.add('dragging');
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', taskId);
        }

        function onTaskDragEnd(event) {
            taskDraggedId = null;
            event.target.classList.remove('dragging');
            document.querySelectorAll('.task-column').forEach(col => col.classList.remove('drag-over'));
        }

        function onTaskDragOver(event, colId) {
            event.preventDefault();
            taskDragOverCol = colId;
            const col = document.querySelector('.task-column[data-col="' + colId + '"]');
            if (col) {
                document.querySelectorAll('.task-column').forEach(c => c.classList.remove('drag-over'));
                col.classList.add('drag-over');
                col.style.borderColor = getColumnColor(colId);
            }
        }

        function getColumnColor(colId) {
            const columns = TASK_COLUMNS[taskActiveList] || [];
            const col = columns.find(c => c.id === colId);
            return col ? col.color : '#64748b';
        }

        async function onTaskDrop(event, colId) {
            event.preventDefault();
            if (!taskDraggedId) return;

            const task = taskData.tasks.find(t => t.id === taskDraggedId);
            if (!task || task.status === colId) {
                taskDraggedId = null;
                return;
            }

            try {
                // For heartbeat scheduling via drag
                if (colId === 'in_heartbeat' && task.status === 'queued') {
                    await fetch(HADLEY_API + '/ptasks/' + taskDraggedId + '/heartbeat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({})
                    });
                } else {
                    await fetch(HADLEY_API + '/ptasks/' + taskDraggedId + '/status', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: colId, actor: 'chris' })
                    });
                }

                const columns = TASK_COLUMNS[taskActiveList] || [];
                const colName = columns.find(c => c.id === colId)?.label || colId;
                showTaskToast('Task moved to ' + colName);
                renderTasks();
            } catch (e) {
                console.error('Failed to move task:', e);
                showTaskToast('Failed to move task');
            }

            taskDraggedId = null;
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
                case 'tasks': renderTasks(); break;
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
                case 'parser': renderParser(); break;
                case 'search': renderSearch(); break;
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
    uvicorn.run(app, host="0.0.0.0", port=5000)
