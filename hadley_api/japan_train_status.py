"""Japan Train Status Checker.

Calls a standalone Node.js script that uses Playwright to scrape train status pages.
Returns structured status data for Peter to report.
"""

import asyncio
import json
import os
from pathlib import Path

SCRIPT_PATH = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide/scrape-train-status.js")


async def _run_scraper(region: str) -> dict:
    """Run the train status scraper script."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", str(SCRIPT_PATH), region,
            cwd=str(SCRIPT_PATH.parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
        output = stdout.decode("utf-8").strip()
        if output:
            return json.loads(output)
        return {"error": f"No output. stderr: {stderr.decode('utf-8','ignore')[:200]}"}
    except asyncio.TimeoutError:
        return {"error": "Timeout (25s)"}
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON: {output[:100]}"}
    except Exception as e:
        return {"error": str(e)}


async def get_train_status(city: str = "all") -> dict:
    """Get train status for a city/region."""
    results = {}

    if city in ("osaka", "kyoto", "all", "kinki"):
        results["jr_west"] = await _run_scraper("kinki")

    if city in ("tokyo", "all"):
        results["jr_east"] = await _run_scraper("east")

    # Build summary
    all_normal = True
    for r in results.values():
        if r.get("error"):
            all_normal = False
            continue
        areas = r.get("areas", [])
        if areas:
            if any(a.get("status") != "Normal" for a in areas):
                all_normal = False
        elif r.get("status") != "Normal":
            all_normal = False

    return {
        "city": city,
        "all_normal": all_normal,
        "regions": results,
        "summary": "✅ All trains running normally" if all_normal else "⚠️ Some delays — check details",
    }
