#!/usr/bin/env python3
"""
Kia Connect Authentication Setup Script

Run this once to test Kia Connect API access.
Tokens are managed automatically by the library.

Usage:
    python setup_kia_auth.py
"""

import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN_FILE = Path(__file__).parent / "kia_token.json"


async def main():
    print("=" * 50)
    print("Kia Connect Authentication Test")
    print("=" * 50)
    print()

    from hyundai_kia_connect_api import VehicleManager

    # Get credentials
    email = os.getenv("KIA_EMAIL")
    password = os.getenv("KIA_PASSWORD")
    pin = os.getenv("KIA_PIN")

    if not email:
        email = input("Enter your Kia Connect email: ").strip()
    else:
        print(f"Using email from .env: {email}")

    if not password:
        password = input("Enter your Kia Connect password: ").strip()

    if not pin:
        pin = input("Enter your 4-digit Kia PIN: ").strip()

    print("\nConnecting to Kia...")

    try:
        # Region 1 = Europe, Brand 1 = Kia
        manager = VehicleManager(
            region=1,
            brand=1,
            username=email,
            password=password,
            pin=pin
        )

        print("Checking credentials and fetching vehicles...")
        await manager.check_and_refresh_token()

        # Try to update vehicles
        await manager.update_all_vehicles_with_cached_state()

        if not manager.vehicles:
            print("\nNo vehicles found. Check your Kia Connect app to verify setup.")
            return

        print(f"\nFound {len(manager.vehicles)} vehicle(s):")

        for vid, vehicle in manager.vehicles.items():
            print(f"\n  {vehicle.name or 'Unnamed'}")
            print(f"  Model: {vehicle.model}")
            print(f"  VIN: {vehicle.VIN}")

            # Try to get status
            print("\n  Fetching latest status...")
            try:
                await manager.force_refresh_vehicle_state(vehicle.id)
                await manager.update_vehicle_with_cached_state(vehicle.id)

                print(f"  Battery: {vehicle.ev_battery_percentage}%")
                print(f"  Range: {vehicle.ev_driving_range} km")
                print(f"  Charging: {vehicle.ev_battery_is_charging}")
                print(f"  Plugged in: {vehicle.ev_battery_is_plugged_in}")
            except Exception as e:
                print(f"  Could not fetch status: {e}")

        # Save token info
        token_data = {
            "email": email,
            "pin": pin,
            "vehicles": list(manager.vehicles.keys()),
            "setup_complete": True
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
        print(f"\nConfiguration saved to: {TOKEN_FILE}")

        # Save credentials to .env if not already there
        if not os.getenv("KIA_EMAIL"):
            print("\nAdd these to your .env file:")
            print(f"  KIA_EMAIL={email}")
            print(f"  KIA_PASSWORD=<your_password>")
            print(f"  KIA_PIN={pin}")

        print("\nSetup complete! Kia data will now be available via /kia/status")

    except Exception as e:
        print(f"\nAuthentication failed: {e}")
        print("\nPossible issues:")
        print("  - Wrong email/password/PIN")
        print("  - Kia Connect servers may be temporarily down")
        print("  - Your account may need to be set up in the Kia Connect app first")


if __name__ == "__main__":
    asyncio.run(main())
