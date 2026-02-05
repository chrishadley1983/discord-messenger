"""Sync WSL config files from version control to WSL location."""

import subprocess
import sys
import os

# Windows: hide console window when running WSL commands
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    STARTUPINFO.wShowWindow = subprocess.SW_HIDE
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    STARTUPINFO = None
    CREATE_NO_WINDOW = 0

# Source (version controlled)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Target (WSL)
WSL_TARGET = "/home/chris_hadley/peterbot"

# Project root (for playbooks)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Files from wsl_config/ (src_file relative to SCRIPT_DIR, dest_subdir in WSL_TARGET)
FILES = [
    # Core config
    ("CLAUDE.md", ""),
    ("PETERBOT_SOUL.md", ""),
    # Phase 7: Schedule and heartbeat
    ("SCHEDULE.md", ""),
    ("HEARTBEAT.md", ""),
    # Skill template
    ("skills/_template/SKILL.md", ".claude/skills/_template"),
    # Skills (Phase 7b)
    ("skills/api-usage/SKILL.md", ".claude/skills/api-usage"),
    ("skills/balance-monitor/SKILL.md", ".claude/skills/balance-monitor"),
    ("skills/health-digest/SKILL.md", ".claude/skills/health-digest"),
    ("skills/heartbeat/SKILL.md", ".claude/skills/heartbeat"),
    ("skills/hydration/SKILL.md", ".claude/skills/hydration"),
    ("skills/monthly-health/SKILL.md", ".claude/skills/monthly-health"),
    ("skills/morning-briefing/SKILL.md", ".claude/skills/morning-briefing"),
    ("skills/news/SKILL.md", ".claude/skills/news"),
    ("skills/nutrition-summary/SKILL.md", ".claude/skills/nutrition-summary"),
    ("skills/school-pickup/SKILL.md", ".claude/skills/school-pickup"),
    ("skills/school-run/SKILL.md", ".claude/skills/school-run"),
    ("skills/weekly-health/SKILL.md", ".claude/skills/weekly-health"),
    ("skills/whatsapp-keepalive/SKILL.md", ".claude/skills/whatsapp-keepalive"),
    ("skills/youtube-digest/SKILL.md", ".claude/skills/youtube-digest"),
    ("skills/self-reflect/SKILL.md", ".claude/skills/self-reflect"),
    # Phase 9: Browser Purchasing
    ("skills/purchase/SKILL.md", ".claude/skills/purchase"),
    # Reminders
    ("skills/remind/SKILL.md", ".claude/skills/remind"),
]

# Playbooks from docs/ folder (relative to PROJECT_ROOT)
PLAYBOOK_FILES = [
    "docs/playbooks/RESEARCH.md",
    "docs/playbooks/REPORTS.md",
    "docs/playbooks/ANALYSIS.md",
    "docs/playbooks/BRIEFINGS.md",
    "docs/playbooks/PLANNING.md",
    "docs/playbooks/EMAIL.md",
    "docs/playbooks/NUTRITION.md",
    "docs/playbooks/TRAINING.md",
    "docs/playbooks/BUSINESS.md",
    "docs/playbooks/TRAVEL.md",
    "docs/playbooks/UTILITIES.md",
]


def _copy_file(src_path: str, wsl_dest: str, label: str):
    """Copy a single file to WSL."""
    wsl_src = src_path.replace("\\", "/").replace("C:", "/mnt/c")
    wsl_dest_dir = os.path.dirname(wsl_dest)

    # Create dir if needed
    mkdir_cmd = f"mkdir -p '{wsl_dest_dir}'"
    subprocess.run(["wsl", "bash", "-c", mkdir_cmd], check=True,
                  startupinfo=STARTUPINFO, creationflags=CREATE_NO_WINDOW)

    # Copy file
    cp_cmd = f"cp '{wsl_src}' '{wsl_dest}'"
    result = subprocess.run(["wsl", "bash", "-c", cp_cmd], capture_output=True, text=True,
                           startupinfo=STARTUPINFO, creationflags=CREATE_NO_WINDOW)

    if result.returncode == 0:
        print(f"[OK] {label} -> {wsl_dest}")
    else:
        print(f"[FAIL] {label}: {result.stderr}")


def sync():
    """Copy all config files to WSL."""
    # Sync files from wsl_config/
    for src_file, dest_subdir in FILES:
        src_path = os.path.join(SCRIPT_DIR, src_file)
        wsl_dest_dir = f"{WSL_TARGET}/{dest_subdir}" if dest_subdir else WSL_TARGET
        wsl_dest = f"{wsl_dest_dir}/{os.path.basename(src_file)}"
        _copy_file(src_path, wsl_dest, src_file)

    # Sync playbooks from docs/
    print("\nSyncing playbooks...")
    for playbook in PLAYBOOK_FILES:
        src_path = os.path.join(PROJECT_ROOT, playbook)
        wsl_dest = f"{WSL_TARGET}/docs/playbooks/{os.path.basename(playbook)}"
        _copy_file(src_path, wsl_dest, playbook)


if __name__ == "__main__":
    print(f"Syncing to {WSL_TARGET}...")
    sync()
    print("Done!")
