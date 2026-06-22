"""Check every fitness_exercises demo video for YouTube availability.

Reports OK / DEAD / no-video per exercise. The dashboard build self-heals dead
videos at build time (domains/fitness/dashboard_site._heal_dead_videos); this is
a standalone spot-check / CI gate. Exit 1 if any video is dead.

Usage: python scripts/check_exercise_videos.py
"""
import os
import sys
import urllib.parse as up
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_KEY"]


def vid(u):
    return up.parse_qs(up.urlparse(u).query).get("v", [None])[0] if u and "watch?v=" in u else None


def main():
    rows = httpx.get(
        f"{URL}/rest/v1/fitness_exercises",
        params={"select": "slug,name,video_url", "order": "slug.asc"},
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=25,
    ).json()
    ok = dead = novid = 0
    deads = []
    with httpx.Client(timeout=15, follow_redirects=True) as c:
        for r in rows:
            v = vid(r.get("video_url"))
            if not v:
                novid += 1
                continue
            code = c.get("https://www.youtube.com/oembed",
                         params={"format": "json", "url": f"https://www.youtube.com/watch?v={v}"}).status_code
            if code == 200:
                ok += 1
            else:
                dead += 1
                deads.append((r["slug"], r["name"], v, code))
    print(f"exercises={len(rows)} ok={ok} no-video={novid} DEAD={dead}")
    for slug, name, v, code in deads:
        print(f"  DEAD: {slug} | {name} | {v} | http {code}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
