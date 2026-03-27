"""SCHEDULE.md atomic read/parse/modify helpers.

Provides structured access to the schedule table without requiring
full-file rewrites through the existing PUT /schedule endpoint.
"""

import re
from pathlib import Path

SCHEDULE_PATH = Path(__file__).parent.parent / "domains" / "peterbot" / "wsl_config" / "SCHEDULE.md"
RELOAD_TRIGGER = Path(__file__).parent.parent / "data" / "schedule_reload.trigger"


def _read_schedule() -> str:
    """Read SCHEDULE.md content."""
    return SCHEDULE_PATH.read_text(encoding="utf-8")


def _write_schedule(content: str):
    """Write SCHEDULE.md and trigger reload."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    SCHEDULE_PATH.write_text(content, encoding="utf-8")
    RELOAD_TRIGGER.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(ZoneInfo("Europe/London"))
    RELOAD_TRIGGER.write_text(f"{now.isoformat()}|schedule_manager", encoding="utf-8")


def parse_schedule_table(content: str | None = None) -> list[dict]:
    """Parse SCHEDULE.md markdown tables into a list of job dicts.

    Returns list of dicts with keys: name, skill, schedule, channel, enabled, section
    where section is 'cron' or 'interval'.
    """
    if content is None:
        content = _read_schedule()

    jobs = []
    current_section = "cron"

    for line in content.splitlines():
        line = line.strip()

        # Detect section
        if "interval" in line.lower() and line.startswith("#"):
            current_section = "interval"
        elif "fixed time" in line.lower() and line.startswith("#"):
            current_section = "cron"

        # Skip non-table rows
        if not line.startswith("|"):
            continue

        # Skip header and separator rows
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 5:
            continue
        if cells[0] in ("Job", "") or set(cells[0]) <= {"-", " "}:
            continue

        jobs.append({
            "name": cells[0],
            "skill": cells[1],
            "schedule": cells[2],
            "channel": cells[3],
            "enabled": cells[4].lower(),
            "section": current_section,
        })

    return jobs


def find_job_by_skill(skill: str, jobs: list[dict] | None = None) -> dict | None:
    """Find a job by its skill name."""
    if jobs is None:
        jobs = parse_schedule_table()
    for job in jobs:
        if job["skill"] == skill:
            return job
    return None


def update_job_field(skill: str, field: str, value: str) -> dict:
    """Update a single field for a job identified by skill name.

    Args:
        skill: The skill name to find
        field: One of 'name', 'skill', 'schedule', 'channel', 'enabled'
        value: New value for the field

    Returns:
        The updated job dict

    Raises:
        ValueError: If skill not found or field invalid
    """
    field_index = {"name": 0, "skill": 1, "schedule": 2, "channel": 3, "enabled": 4}
    if field not in field_index:
        raise ValueError(f"Invalid field: {field}. Must be one of {list(field_index.keys())}")

    content = _read_schedule()
    lines = content.splitlines()
    idx = field_index[field]
    updated_job = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) < 5:
            continue
        if cells[1] == skill:
            cells[idx] = value
            lines[i] = "| " + " | ".join(cells) + " |"
            updated_job = {
                "name": cells[0], "skill": cells[1], "schedule": cells[2],
                "channel": cells[3], "enabled": cells[4].lower(),
            }
            break

    if updated_job is None:
        raise ValueError(f"Skill '{skill}' not found in SCHEDULE.md")

    _write_schedule("\n".join(lines))
    return updated_job


def add_job_row(name: str, skill: str, schedule: str, channel: str, enabled: str = "yes", section: str = "cron") -> dict:
    """Append a new job row to the appropriate section.

    Returns the new job dict.
    """
    content = _read_schedule()
    lines = content.splitlines()

    new_row = f"| {name} | {skill} | {schedule} | {channel} | {enabled} |"
    job = {"name": name, "skill": skill, "schedule": schedule, "channel": channel, "enabled": enabled, "section": section}

    # Find the last table row in the target section
    target_section = "interval" if section == "interval" else "fixed time"
    in_target = False
    last_table_line = -1

    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if lower.startswith("#") and target_section in lower:
            in_target = True
        elif lower.startswith("#") and in_target:
            # Entered next section
            break

        if in_target and line.strip().startswith("|"):
            last_table_line = i

    if last_table_line >= 0:
        lines.insert(last_table_line + 1, new_row)
    else:
        # Fallback: append to end
        lines.append(new_row)

    _write_schedule("\n".join(lines))
    return job


def remove_job_row(skill: str) -> dict | None:
    """Remove a job row by skill name. Returns the removed job or None."""
    content = _read_schedule()
    lines = content.splitlines()
    removed = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) >= 5 and cells[1] == skill:
            removed = {
                "name": cells[0], "skill": cells[1], "schedule": cells[2],
                "channel": cells[3], "enabled": cells[4].lower(),
            }
            lines.pop(i)
            break

    if removed:
        _write_schedule("\n".join(lines))
    return removed
