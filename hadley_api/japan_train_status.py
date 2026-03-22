"""Japan Train Status Checker — uses temp file for Windows service compatibility."""

import asyncio
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

SCRIPT_PATH = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/scrape-train-status.js")


def _run_scraper_sync(region: str) -> dict:
    """Run train status scraper — writes output to temp file to avoid Windows PIPE issues."""
    tmp_path = Path(tempfile.gettempdir()) / f"train_status_{uuid.uuid4().hex[:8]}.json"

    # Wrap the script to write output to file instead of stdout
    wrapper = f'''
    const fs = require('fs');
    const orig = console.log;
    let output = '';
    console.log = (s) => {{ output += s; }};
    require('{SCRIPT_PATH.as_posix()}');
    // The script uses console.log in an async IIFE, so wait for it
    setTimeout(() => {{
        fs.writeFileSync('{tmp_path.as_posix()}', output || '{{}}');
        process.exit(0);
    }}, 20000);
    '''

    # Actually, simpler: just redirect stdout to file via shell
    try:
        cmd = f'node "{SCRIPT_PATH}" {region} > "{tmp_path}"'
        subprocess.run(
            cmd,
            shell=True,
            timeout=25,
            cwd=str(SCRIPT_PATH.parent),
        )

        if tmp_path.exists():
            content = tmp_path.read_text(encoding="utf-8").strip()
            tmp_path.unlink(missing_ok=True)
            if content:
                return json.loads(content)
        return {"error": "No output file created"}
    except subprocess.TimeoutExpired:
        tmp_path.unlink(missing_ok=True)
        return {"error": "Timeout (25s)"}
    except json.JSONDecodeError as e:
        tmp_path.unlink(missing_ok=True)
        return {"error": f"Bad JSON: {e}"}
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        return {"error": str(e)}


async def get_train_status(city: str = "all") -> dict:
    """Get train status for a city/region."""
    results = {}

    if city in ("osaka", "kyoto", "all", "kinki"):
        results["jr_west"] = await asyncio.to_thread(_run_scraper_sync, "kinki")

    if city in ("tokyo", "all"):
        results["jr_east"] = await asyncio.to_thread(_run_scraper_sync, "east")

    all_normal = True
    for r in results.values():
        if r.get("error"):
            all_normal = False
            continue
        areas = r.get("areas", [])
        if areas and any(a.get("status") != "Normal" for a in areas):
            all_normal = False
        elif not areas and r.get("status") != "Normal":
            all_normal = False

    return {
        "city": city,
        "all_normal": all_normal,
        "regions": results,
        "summary": "✅ All trains running normally" if all_normal else "⚠️ Some delays — check details",
    }
