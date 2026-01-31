"""
Project registry - friendly names to paths.
Stored in JSON for persistence. Manage via Discord commands.
"""

import json
from pathlib import Path
from typing import Optional
from .config import DATA_DIR


PROJECTS_PATH = DATA_DIR / "projects.json"


def _load() -> dict[str, str]:
    """Load projects from disk."""
    if PROJECTS_PATH.exists():
        try:
            return json.loads(PROJECTS_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save(projects: dict[str, str]):
    """Save projects to disk."""
    PROJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_PATH.write_text(json.dumps(projects, indent=2))


def resolve_path(name_or_path: str) -> str:
    """
    Resolve a project name to its path.
    If not found in registry, returns the input unchanged (assumes it's a path).
    """
    projects = _load()
    return projects.get(name_or_path.lower().strip(), name_or_path)


def list_projects() -> dict[str, str]:
    """Return all registered projects."""
    return _load()


def add_project(name: str, path: str) -> str:
    """Add or update a project. Returns confirmation message."""
    projects = _load()
    name = name.lower().strip()
    projects[name] = path
    _save(projects)
    return f"✅ Registered `{name}` → `{path}`"


def remove_project(name: str) -> str:
    """Remove a project. Returns confirmation message."""
    projects = _load()
    name = name.lower().strip()
    if name not in projects:
        return f"❌ Project `{name}` not found"
    del projects[name]
    _save(projects)
    return f"🗑️ Removed `{name}`"


def get_project(name: str) -> Optional[str]:
    """Get path for a project, or None if not found."""
    projects = _load()
    return projects.get(name.lower().strip())
