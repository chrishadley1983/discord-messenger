"""Japan Train Status Checker — uses sync subprocess wrapped in asyncio.to_thread."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/scrape-train-status.js")

IS_WINDOWS = sys.platform == "win32"


def _run_scraper_sync(region: str) -> dict:
    """Run train status scraper synchronously."""
    try:
        kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "timeout": 25,
            "cwd": str(SCRIPT_PATH.parent),
        }

        result = subprocess.run(
            ["node", str(SCRIPT_PATH), region],
            **kwargs,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"error": f"No output. rc={result.returncode}. stderr={result.stderr[:200]}"}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout (25s)"}
    except json.JSONDecodeError as e:
        return {"error": f"Bad JSON: {e}. stdout={result.stdout[:100]}"}
    except Exception as e:
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
