"""Standalone Reset Cut dashboard build + deploy.

Loads .env BEFORE importing the fitness service (which reads SUPABASE_URL at
import time), then runs build_and_deploy. Useful for an out-of-band rebuild +
surge push without going through the HadleyAPI process.

Usage: python scripts/run_dashboard_build.py [--no-deploy]
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

deploy = "--no-deploy" not in sys.argv
res = asyncio.run(build_and_deploy(deploy=deploy))
print(json.dumps(res, indent=2))
