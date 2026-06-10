"""Regenerate or check wsl_config/skills/manifest.json from SKILL.md files.

Usage:
    python scripts/generate_skill_manifest.py           # rewrite manifest.json
    python scripts/generate_skill_manifest.py --check   # report drift, exit 1 if any
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domains.peterbot.skill_manifest import check_consistency, write_manifest


def main() -> int:
    if "--check" in sys.argv:
        result = check_consistency()
        if result["ok"]:
            print("manifest consistent: skill dirs, manifest.json and SCHEDULE.md agree")
            return 0
        print("manifest drift detected:")
        for p in result["problems"]:
            print(f"  - {p}")
        return 1

    manifest = write_manifest()
    print(f"manifest.json regenerated: {len(manifest)} skills")
    result = check_consistency()
    for p in result["problems"]:
        print(f"  warning: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
