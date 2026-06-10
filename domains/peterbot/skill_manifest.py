"""Skill manifest generation and consistency checking.

The manifest (wsl_config/skills/manifest.json) is what Peter reads to discover
conversational skills, so drift between it, the skill directories, and
SCHEDULE.md silently hides capabilities. This module makes SKILL.md the source
of truth:

- build_manifest()      — regenerate the manifest dict from skill dirs
- write_manifest()      — build and write manifest.json
- check_consistency()   — report drift (used by system-health pre-fetch)

Precedence per skill: SKILL.md YAML frontmatter > existing manifest entry >
values derived from markdown sections (## Purpose, ## Triggers). The
`scheduled` flag and `channel` are always taken from SCHEDULE.md, which is
authoritative for what actually runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "domains" / "peterbot" / "wsl_config" / "skills"
SCHEDULE_MD = REPO_ROOT / "domains" / "peterbot" / "wsl_config" / "SCHEDULE.md"
MANIFEST_PATH = SKILLS_DIR / "manifest.json"

EXCLUDED_DIRS = {"_template", "__pycache__"}


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse the YAML frontmatter block, with a minimal fallback parser
    (key: value and '- item' lists) so we don't hard-require pyyaml."""
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(block)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in block.splitlines():
        if re.match(r"^\s*-\s+", line) and current_key:
            item = line.split("-", 1)[1].strip().strip("\"'")
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(item)
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            current_key = key
            if val == "":
                data[key] = []
            elif val.lower() in ("true", "false"):
                data[key] = val.lower() == "true"
            else:
                data[key] = val.strip("\"'")
    return data


def _parse_markdown_sections(text: str) -> dict[str, Any]:
    """Derive description and triggers from ## Purpose / ## Triggers sections."""
    out: dict[str, Any] = {}
    purpose = re.search(r"^##\s+Purpose\s*\n+(.+?)(?:\n\n|\n##)", text, re.DOTALL | re.MULTILINE)
    if purpose:
        first_line = purpose.group(1).strip().splitlines()[0].strip()
        out["description"] = first_line.rstrip(".")
    triggers_sec = re.search(r"^##\s+Triggers\s*\n(.*?)(?:\n##|\Z)", text, re.DOTALL | re.MULTILINE)
    if triggers_sec:
        triggers: list[str] = []
        for line in triggers_sec.group(1).splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            quoted = re.findall(r'"([^"]+)"', line)
            if quoted:
                triggers.extend(quoted)
            else:
                bare = line.lstrip("- ").strip()
                if bare:
                    triggers.append(bare)
        out["triggers"] = triggers
    return out


def _parse_schedule() -> dict[str, dict[str, Any]]:
    """Return {skill: {scheduled: bool, channel: str|None}} from SCHEDULE.md.

    A skill is scheduled if it has at least one enabled row. The channel comes
    from the first enabled row. The '-' skill (e.g. Claude History Reminder)
    is ignored.
    """
    info: dict[str, dict[str, Any]] = {}
    if not SCHEDULE_MD.exists():
        return info
    for line in SCHEDULE_MD.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        # | Job | Skill | Schedule | Channel | Enabled | -> 7 cells with edges
        if len(cells) < 7 or cells[1] in ("Job", "----", "") or set(cells[1]) <= {"-"}:
            continue
        skill = cells[2]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill):
            continue
        enabled = cells[5].lower() == "yes"
        entry = info.setdefault(skill, {"scheduled": False, "channel": None})
        if enabled and not entry["scheduled"]:
            entry["scheduled"] = True
            entry["channel"] = cells[4]
    return info


def _normalise_triggers(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(t) for t in raw]
    return []


def build_manifest() -> dict[str, dict[str, Any]]:
    existing: dict[str, Any] = {}
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}

    schedule = _parse_schedule()
    manifest: dict[str, dict[str, Any]] = {}

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in EXCLUDED_DIRS:
            continue
        name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""

        fm = _parse_frontmatter(text)
        md = _parse_markdown_sections(text)
        old = existing.get(name, {})

        triggers = (
            _normalise_triggers(fm.get("trigger") or fm.get("triggers"))
            or _normalise_triggers(old.get("triggers"))
            or _normalise_triggers(md.get("triggers"))
        )
        description = (
            fm.get("description")
            or old.get("description")
            or md.get("description")
            or name.replace("-", " ")
        )
        sched_info = schedule.get(name, {})
        scheduled = bool(sched_info.get("scheduled", False))
        channel = sched_info.get("channel") or old.get("channel")

        if "conversational" in fm:
            conversational = bool(fm["conversational"])
        elif "conversational" in old:
            conversational = bool(old["conversational"])
        else:
            conversational = bool(triggers)

        manifest[name] = {
            "triggers": triggers,
            "conversational": conversational,
            "scheduled": scheduled,
            "description": str(description),
            "channel": channel,
        }

    return manifest


def write_manifest() -> dict[str, dict[str, Any]]:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def check_consistency() -> dict[str, Any]:
    """Drift report between skill dirs, manifest.json, and SCHEDULE.md.

    Returns {"ok": bool, "problems": [str, ...]} — consumed by the
    system-health pre-fetch so drift shows up in the daily ops report.
    """
    problems: list[str] = []

    dirs = {
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name not in EXCLUDED_DIRS
    }
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"ok": False, "problems": [f"manifest.json unreadable: {e}"]}

    missing_from_manifest = sorted(dirs - set(manifest))
    if missing_from_manifest:
        problems.append(
            f"skill dirs missing from manifest: {', '.join(missing_from_manifest)}"
        )

    ghost_entries = sorted(set(manifest) - dirs)
    if ghost_entries:
        problems.append(f"manifest entries with no skill dir: {', '.join(ghost_entries)}")

    schedule = _parse_schedule()
    broken_refs = sorted(set(schedule) - dirs)
    if broken_refs:
        problems.append(f"SCHEDULE.md references missing skills: {', '.join(broken_refs)}")

    no_skill_md = sorted(d for d in dirs if not (SKILLS_DIR / d / "SKILL.md").exists())
    if no_skill_md:
        problems.append(f"skill dirs without SKILL.md: {', '.join(no_skill_md)}")

    flag_mismatch = sorted(
        name
        for name, entry in manifest.items()
        if name in dirs
        and bool(entry.get("scheduled")) != bool(schedule.get(name, {}).get("scheduled"))
    )
    if flag_mismatch:
        problems.append(
            f"manifest 'scheduled' flag disagrees with SCHEDULE.md: {', '.join(flag_mismatch)}"
        )

    return {"ok": not problems, "problems": problems}
