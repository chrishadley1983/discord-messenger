"""Japan Train Status Checker.

Uses Playwright to scrape JR West/East/Central status pages.
Returns structured status data that Peter can use to answer train delay questions.

Called via: GET /japan/trains/status?region=kinki
"""

import asyncio
import subprocess
import json
import sys
from pathlib import Path

# Playwright is installed in the japan-family-guide project
PLAYWRIGHT_NODE = "node"
JAPAN_GUIDE_DIR = Path("C:/Users/Chris Hadley/claude-projects/japan-family-guide")
# Ensure node_modules/.bin is on PATH for Playwright
import os
NODE_ENV = os.environ.copy()
NODE_ENV["PATH"] = str(JAPAN_GUIDE_DIR / "node_modules" / ".bin") + os.pathsep + NODE_ENV.get("PATH", "")


async def check_jr_west_kinki() -> dict:
    """Check JR West Kinki area (Kyoto/Osaka/Kobe) train status."""
    script = """
    const { chromium } = require('playwright');
    (async () => {
        const browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        try {
            await page.goto('https://trafficinfo.westjr.co.jp/kinki.html', { waitUntil: 'networkidle', timeout: 15000 });
            await page.waitForTimeout(2000);
            const text = await page.evaluate(() => document.body.innerText);

            // Parse status
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            const result = { region: 'JR West Kinki', areas: [], timestamp: '', raw: '' };

            // Find timestamp
            const timeMatch = text.match(/(\\d+時\\d+分現在)/);
            if (timeMatch) result.timestamp = timeMatch[1];

            // Check for normal operation or delays
            const areas = ['京阪神地区', '和歌山地区', '北近畿地区'];
            for (const area of areas) {
                const idx = text.indexOf(area);
                if (idx >= 0) {
                    const after = text.substring(idx, idx + 100);
                    const isNormal = after.includes('平常運転');
                    const areaNames = { '京阪神地区': 'Keihanshin (Kyoto/Osaka/Kobe)', '和歌山地区': 'Wakayama', '北近畿地区': 'North Kinki' };
                    result.areas.push({
                        name: areaNames[area] || area,
                        status: isNormal ? 'Normal' : 'Disruption',
                        details: isNormal ? 'All lines running normally' : after.substring(area.length, 80).trim()
                    });
                }
            }

            // Check for any notices
            if (text.includes('お知らせはありません')) {
                result.notices = 'No current notices';
            }

            result.raw = text.substring(0, 500);
            console.log(JSON.stringify(result));
        } catch (e) {
            console.log(JSON.stringify({ error: e.message }));
        }
        await browser.close();
    })();
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            PLAYWRIGHT_NODE, "-e", script,
            cwd=str(JAPAN_GUIDE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=NODE_ENV,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        output = stdout.decode("utf-8").strip()
        if output:
            return json.loads(output)
        return {"error": "No output from scraper"}
    except asyncio.TimeoutError:
        return {"error": "Timeout scraping JR West"}
    except Exception as e:
        return {"error": str(e)}


async def check_jr_east() -> dict:
    """Check JR East (Tokyo area) train status."""
    script = """
    const { chromium } = require('playwright');
    (async () => {
        const browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        try {
            await page.goto('https://traininfo.jreast.co.jp/train_info/e/', { waitUntil: 'networkidle', timeout: 15000 });
            await page.waitForTimeout(2000);
            const text = await page.evaluate(() => document.body.innerText);

            const result = { region: 'JR East (Tokyo)', lines: [], timestamp: '', raw: '' };

            // Parse delay info - JR East English shows delayed lines
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 3);
            const delayLines = lines.filter(l => l.includes('delay') || l.includes('suspend') || l.includes('Delay') || l.includes('Suspend'));

            if (delayLines.length === 0) {
                result.status = 'Normal';
                result.summary = 'All JR East lines running normally';
            } else {
                result.status = 'Delays';
                result.summary = delayLines.join('; ');
                result.lines = delayLines;
            }

            // Check for "currently operating normally" type messages
            if (text.includes('currently operating normally') || text.includes('No delays')) {
                result.status = 'Normal';
                result.summary = 'All lines running normally';
            }

            result.raw = text.substring(0, 500);
            console.log(JSON.stringify(result));
        } catch (e) {
            console.log(JSON.stringify({ error: e.message }));
        }
        await browser.close();
    })();
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            PLAYWRIGHT_NODE, "-e", script,
            cwd=str(JAPAN_GUIDE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=NODE_ENV,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        output = stdout.decode("utf-8").strip()
        if output:
            return json.loads(output)
        return {"error": "No output from scraper"}
    except asyncio.TimeoutError:
        return {"error": "Timeout scraping JR East"}
    except Exception as e:
        return {"error": str(e)}


async def get_train_status(city: str = "all") -> dict:
    """Get train status for a city/region.

    Args:
        city: "tokyo", "osaka", "kyoto", or "all"

    Returns:
        Dict with status per region
    """
    results = {}

    if city in ("osaka", "kyoto", "all", "kinki"):
        results["jr_west"] = await check_jr_west_kinki()

    if city in ("tokyo", "all"):
        results["jr_east"] = await check_jr_east()

    # Build summary
    all_normal = all(
        r.get("status") == "Normal" or all(a.get("status") == "Normal" for a in r.get("areas", []))
        for r in results.values()
        if not r.get("error")
    )

    return {
        "city": city,
        "all_normal": all_normal,
        "regions": results,
        "summary": "✅ All trains running normally" if all_normal else "⚠️ Some delays — check details",
    }
