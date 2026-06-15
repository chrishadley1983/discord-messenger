"""Shared configuration for the Octopus Energy domain.

Consolidated into discord-messenger (Jun 2026) from
hadley-bricks-inventory-management/scripts/energy — cross-repo script
dependencies silently killed the WhatsApp and school pipelines, so energy
lives here now. Secrets come from this repo's .env (SOPS-managed at rest),
with a one-time fallback to the old HB .env.local so nothing breaks if the
.env additions are lost in a re-encrypt.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

_HB_ENV = (
    PROJECT_ROOT.parent / "hadley-bricks-inventory-management" / "apps" / "web" / ".env.local"
)


def _fallback(var: str) -> str:
    if _HB_ENV.exists():
        for line in _HB_ENV.read_text().splitlines():
            if line.strip().startswith(f"{var}="):
                return line.split("=", 1)[1].strip()
    return ""


SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://modjoikyuhqzouxvieua.supabase.co")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or _fallback("SUPABASE_SERVICE_ROLE_KEY")
)

OCTOPUS_API_KEY = os.environ.get("OCTOPUS_API_KEY") or _fallback("OCTOPUS_API_KEY")
OCTOPUS_ACCOUNT = os.environ.get("OCTOPUS_ACCOUNT", "A-8B718918")
OCTOPUS_REST_BASE = "https://api.octopus.energy/v1"
OCTOPUS_GRAPHQL_URL = "https://api.octopus.energy/v1/graphql/"

# Meter details (identifiers, not secrets)
ELECTRICITY_MPAN = "1900006287208"
ELECTRICITY_SERIAL = "20L3260811"
GAS_MPRN = "686296406"
GAS_SERIAL = "E6S12746312061"

# Home Mini smart device (live telemetry source)
SMART_DEVICE_ID = os.environ.get("OCTOPUS_DEVICE_ID", "30-EB-5A-FF-FF-4E-02-D0")

# Tariff details
ELECTRICITY_PRODUCT = "INTELLI-VAR-24-10-29"
ELECTRICITY_TARIFF = "E-1R-INTELLI-VAR-24-10-29-J"
GAS_PRODUCT = "VAR-22-11-01"
GAS_TARIFF = "G-1R-VAR-22-11-01-J"

# Intelligent Go rate boundaries (UTC)
OFFPEAK_START_HOUR = 23
OFFPEAK_START_MIN = 30
OFFPEAK_END_HOUR = 5
OFFPEAK_END_MIN = 30

# Gas conversion: SMETS2 meters report m³ (~×11.1 for kWh)
GAS_M3_TO_KWH = 11.1

# EV detection fallback: off-peak electricity above this = EV charge day
EV_OFFPEAK_THRESHOLD_KWH = 5.0

# Telemetry: a day is only "complete" with this many half-hourly intervals
COMPLETE_DAY_INTERVALS = 46  # 48 ideal; tolerate a couple of meter gaps

DISCORD_ENERGY_WEBHOOK = os.environ.get("DISCORD_ENERGY_WEBHOOK", "")

# Local telemetry log (raw 10s samples, ring-trimmed by the poller)
TELEMETRY_LOG = PROJECT_ROOT / "data" / "energy_telemetry.jsonl"
