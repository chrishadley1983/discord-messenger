"""CLI runner for the reset-cut dashboard generator.

Loads .env BEFORE importing the fitness modules (which read SUPABASE_URL at
import time), then builds + deploys. Use --no-deploy to build locally only.

    python scripts/build_dashboard.py            # build + deploy to surge
    python scripts/build_dashboard.py --no-deploy
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from domains.fitness.dashboard_site import build_and_deploy  # noqa: E402

if __name__ == "__main__":
    deploy = "--no-deploy" not in sys.argv
    res = asyncio.run(build_and_deploy(deploy=deploy))
    print(json.dumps(res, indent=2))
