"""Service Manager - Ensures single instances of Peter services.

Provides reliable start/stop/restart with:
- NSSM service detection (preferred when available)
- PID file tracking for exact process identification
- Port availability checks before starting
- Process verification before spawning new instances
"""

import os
import subprocess
import time
import socket
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

# NSSM service name mapping (None = not managed by NSSM)
NSSM_SERVICE_NAMES = {
    "hadley_api": "HadleyAPI",
    "discord_bot": "DiscordBot",
    "peter_dashboard": "PeterDashboard",
    "hadley_bricks": None,  # Not NSSM-managed
}


def _get_nssm_status(nssm_name: str) -> Optional[str]:
    """Query NSSM service status. Returns 'running', 'stopped', or None if not found."""
    try:
        result = subprocess.run(
            ["sc", "query", nssm_name],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        output = result.stdout.lower()
        if "running" in output:
            return "running"
        elif "stopped" in output or "stop_pending" in output:
            return "stopped"
        return None
    except Exception:
        return None


def _get_nssm_pid(nssm_name: str) -> Optional[int]:
    """Get the PID of an NSSM-managed service."""
    try:
        result = subprocess.run(
            ["sc", "queryex", nssm_name],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000
        )
        for line in result.stdout.split('\n'):
            if 'PID' in line.upper() and ':' in line:
                pid_str = line.split(':')[-1].strip()
                if pid_str.isdigit():
                    return int(pid_str)
        return None
    except Exception:
        return None

# PID file directory
PID_DIR = Path(__file__).parent / ".pids"
PID_DIR.mkdir(exist_ok=True)

# Service definitions
@dataclass
class ServiceConfig:
    name: str
    pid_file: str
    port: Optional[int]  # None for services that don't bind ports
    start_cmd: list[str]
    cwd: str
    process_pattern: str  # Pattern to identify the process


SERVICES = {
    "hadley_api": ServiceConfig(
        name="Hadley API",
        pid_file="hadley_api.pid",
        port=8100,
        start_cmd=["python", "-m", "uvicorn", "hadley_api.main:app", "--host", "0.0.0.0", "--port", "8100"],
        cwd=str(Path(__file__).parent.parent),
        process_pattern="hadley_api.main:app"
    ),
    "discord_bot": ServiceConfig(
        name="Discord Bot",
        pid_file="discord_bot.pid",
        port=None,
        start_cmd=["python", "bot.py"],
        cwd=str(Path(__file__).parent.parent),
        process_pattern="bot.py"
    ),
    "hadley_bricks": ServiceConfig(
        name="Hadley Bricks",
        pid_file="hadley_bricks.pid",
        port=3000,
        start_cmd=["cmd", "/c", "npm", "run", "dev"],
        cwd=r"C:\Users\Chris Hadley\hadley-bricks-inventory-management",
        process_pattern="next"  # Next.js process pattern
    ),
    "peter_dashboard": ServiceConfig(
        name="Peter Dashboard",
        pid_file="peter_dashboard.pid",
        port=5000,
        start_cmd=["python", "peter_dashboard/app.py"],
        cwd=str(Path(__file__).parent.parent),
        process_pattern="peter_dashboard"
    ),
}


def _get_pid_file(service: str) -> Path:
    """Get PID file path for a service."""
    return PID_DIR / SERVICES[service].pid_file


def _read_pid(service: str) -> Optional[int]:
    """Read PID from file, return None if not exists or invalid."""
    pid_file = _get_pid_file(service)
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        return pid if pid > 0 else None
    except (ValueError, OSError):
        return None


def _write_pid(service: str, pid: int) -> None:
    """Write PID to file."""
    _get_pid_file(service).write_text(str(pid))


def _clear_pid(service: str) -> None:
    """Remove PID file."""
    pid_file = _get_pid_file(service)
    if pid_file.exists():
        pid_file.unlink()


def _is_process_alive(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        # Use tasklist to check if process exists
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _kill_process(pid: int, timeout: float = 5.0) -> bool:
    """Kill a process by PID and wait for it to die."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=5,
            creationflags=0x08000000
        )
    except Exception:
        pass

    # Wait for process to actually die
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_process_alive(pid):
            return True
        time.sleep(0.2)

    return not _is_process_alive(pid)


def _find_process_by_pattern(pattern: str) -> list[int]:
    """Find PIDs of processes matching a command line pattern."""
    pids = []
    try:
        # Use WMIC to find processes (more reliable than tasklist for cmdline)
        result = subprocess.run(
            ["wmic", "process", "where", f"commandline like '%{pattern}%'", "get", "processid"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=0x08000000
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and line.isdigit():
                pids.append(int(line))
    except Exception:
        pass
    return pids


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception:
        return False


def _wait_for_port_free(port: int, timeout: float = 10.0) -> bool:
    """Wait for a port to become available."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _is_port_in_use(port):
            return True
        time.sleep(0.3)
    return False


def get_service_status(service: str) -> dict:
    """Get detailed status of a service."""
    if service not in SERVICES:
        return {"error": f"Unknown service: {service}"}

    config = SERVICES[service]

    # Check if this is an NSSM-managed service
    nssm_name = NSSM_SERVICE_NAMES.get(service)
    if nssm_name:
        nssm_status = _get_nssm_status(nssm_name)
        if nssm_status:
            nssm_pid = _get_nssm_pid(nssm_name)
            return {
                "service": service,
                "name": config.name,
                "pid": nssm_pid,
                "pid_alive": nssm_status == "running",
                "port": config.port,
                "port_in_use": _is_port_in_use(config.port) if config.port else None,
                "status": nssm_status,
                "managed_by": "nssm",
                "nssm_service": nssm_name,
            }

    # Fall back to PID file tracking
    pid = _read_pid(service)

    status = {
        "service": service,
        "name": config.name,
        "pid": pid,
        "pid_alive": _is_process_alive(pid) if pid else False,
        "port": config.port,
        "port_in_use": _is_port_in_use(config.port) if config.port else None,
        "managed_by": "pid_file",
    }

    # Determine overall status
    if status["pid_alive"]:
        status["status"] = "running"
    elif status["port_in_use"]:
        # Port in use but no tracked PID - orphaned process
        status["status"] = "orphaned"
        # Try to find the orphaned process
        orphan_pids = _find_process_by_pattern(config.process_pattern)
        status["orphan_pids"] = orphan_pids
    else:
        status["status"] = "stopped"

    return status


def stop_service(service: str, force_cleanup: bool = True) -> dict:
    """Stop a service, ensuring it's completely terminated.

    Args:
        service: Service name
        force_cleanup: If True, also kills orphaned processes using port/pattern

    Returns:
        Status dict with result
    """
    if service not in SERVICES:
        return {"success": False, "error": f"Unknown service: {service}"}

    config = SERVICES[service]
    killed_pids = []

    # Check if NSSM-managed - use 'net stop' which works without admin in service context
    nssm_name = NSSM_SERVICE_NAMES.get(service)
    if nssm_name and _get_nssm_status(nssm_name):
        try:
            result = subprocess.run(
                ["net", "stop", nssm_name],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=0x08000000
            )
            # Wait for port to be free
            if config.port:
                port_freed = _wait_for_port_free(config.port, timeout=10.0)
            else:
                port_freed = True
            return {
                "success": "stopped successfully" in result.stdout.lower() or port_freed,
                "service": service,
                "managed_by": "nssm",
                "nssm_service": nssm_name,
                "port_freed": port_freed
            }
        except Exception as e:
            return {"success": False, "error": str(e), "managed_by": "nssm"}

    # Fall back to PID-based stop
    # Next.js (hadley_bricks) needs longer timeouts for process termination
    kill_timeout = 10.0 if service == "hadley_bricks" else 5.0

    # 1. Kill tracked PID
    pid = _read_pid(service)
    if pid and _is_process_alive(pid):
        if _kill_process(pid, timeout=kill_timeout):
            killed_pids.append(pid)
    _clear_pid(service)

    # 2. Kill orphaned processes (by pattern)
    if force_cleanup:
        orphan_pids = _find_process_by_pattern(config.process_pattern)
        for opid in orphan_pids:
            if opid not in killed_pids and _is_process_alive(opid):
                if _kill_process(opid, timeout=kill_timeout):
                    killed_pids.append(opid)

    # 3. Wait for port to be free (if applicable)
    if config.port:
        # Next.js (hadley_bricks) needs longer to release port 3000
        port_timeout = 15.0 if service == "hadley_bricks" else 5.0
        port_freed = _wait_for_port_free(config.port, timeout=port_timeout)
    else:
        port_freed = True

    return {
        "success": port_freed,
        "service": service,
        "killed_pids": killed_pids,
        "port_freed": port_freed,
        "managed_by": "pid_file"
    }


def start_service(service: str, headless: bool = True) -> dict:
    """Start a service, ensuring no duplicate instances.

    Args:
        service: Service name
        headless: If True, run without console window

    Returns:
        Status dict with result
    """
    if service not in SERVICES:
        return {"success": False, "error": f"Unknown service: {service}"}

    config = SERVICES[service]

    # Check if already running
    status = get_service_status(service)
    if status["status"] == "running":
        return {
            "success": False,
            "error": "Service already running",
            "pid": status.get("pid")
        }

    # Check if NSSM-managed - use 'net start' which works without admin in service context
    nssm_name = NSSM_SERVICE_NAMES.get(service)
    if nssm_name and _get_nssm_status(nssm_name) is not None:
        try:
            result = subprocess.run(
                ["net", "start", nssm_name],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=0x08000000
            )
            # Wait for service to start
            time.sleep(2.0)
            new_status = get_service_status(service)
            return {
                "success": new_status["status"] == "running",
                "service": service,
                "pid": new_status.get("pid"),
                "port": config.port,
                "managed_by": "nssm",
                "nssm_service": nssm_name
            }
        except Exception as e:
            return {"success": False, "error": str(e), "managed_by": "nssm"}

    # If orphaned, stop first
    if status["status"] == "orphaned":
        stop_result = stop_service(service)
        if not stop_result["success"]:
            return {
                "success": False,
                "error": "Failed to clean up orphaned process",
                "details": stop_result
            }

    # Check port is free
    if config.port and _is_port_in_use(config.port):
        return {
            "success": False,
            "error": f"Port {config.port} is still in use",
            "hint": "Try stop_service with force_cleanup=True"
        }

    # Start the process (PID file mode)
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008

    try:
        if headless:
            proc = subprocess.Popen(
                config.start_cmd,
                cwd=config.cwd,
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            proc = subprocess.Popen(
                config.start_cmd,
                cwd=config.cwd,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )

        # Store PID
        _write_pid(service, proc.pid)

        # Wait briefly and verify it started
        time.sleep(1.0)
        if not _is_process_alive(proc.pid):
            _clear_pid(service)
            return {
                "success": False,
                "error": "Process started but died immediately",
                "pid": proc.pid
            }

        # For port-based services, verify port is listening
        if config.port:
            time.sleep(2.0)  # Give uvicorn time to bind
            if not _is_port_in_use(config.port):
                return {
                    "success": True,
                    "warning": f"Process started but port {config.port} not yet listening",
                    "pid": proc.pid
                }

        return {
            "success": True,
            "service": service,
            "pid": proc.pid,
            "port": config.port,
            "managed_by": "pid_file"
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def restart_service(service: str, headless: bool = True) -> dict:
    """Restart a service (stop then start).

    Returns:
        Status dict with result
    """
    stop_result = stop_service(service, force_cleanup=True)

    # Small delay to ensure resources are released
    time.sleep(0.5)

    start_result = start_service(service, headless=headless)

    return {
        "service": service,
        "stop_result": stop_result,
        "start_result": start_result,
        "success": start_result.get("success", False)
    }


def restart_all(headless: bool = True) -> dict:
    """Restart all services."""
    results = {}
    for service in SERVICES:
        results[service] = restart_service(service, headless=headless)

    return {
        "success": all(r.get("success") for r in results.values()),
        "services": results
    }


def status_all() -> dict:
    """Get status of all services."""
    return {service: get_service_status(service) for service in SERVICES}
