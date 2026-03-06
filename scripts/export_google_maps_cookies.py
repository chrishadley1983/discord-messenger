"""Export Google Maps cookies from Chrome for locationsharinglib.

Extracts cookies for .google.com from Chrome's cookie database
and saves them in Netscape cookie format.

Run: python scripts/export_google_maps_cookies.py
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

# Chrome cookie DB path (Windows)
CHROME_COOKIE_DB = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "google_maps_cookies.txt"


def export_cookies():
    """Export .google.com cookies from Chrome to Netscape format."""
    if not CHROME_COOKIE_DB.exists():
        print(f"Chrome cookie DB not found: {CHROME_COOKIE_DB}")
        print("Make sure Chrome is installed and you've logged into google.com/maps")
        return False

    # Chrome locks its DB, so copy it first
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        shutil.copy2(CHROME_COOKIE_DB, tmp_path)
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()

        # Query cookies for google.com domains
        cursor.execute("""
            SELECT host_key, name, path, expires_utc, is_secure, value
            FROM cookies
            WHERE host_key LIKE '%google.com%'
            ORDER BY host_key, name
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("No Google cookies found. Make sure you're logged into google.com/maps in Chrome.")
            return False

        # Write Netscape cookie format
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write("# https://curl.haxx.se/docs/http-cookies.html\n\n")

            count = 0
            for host, name, path, expires, secure, value in rows:
                if not value:
                    continue
                domain_dot = "TRUE" if host.startswith(".") else "FALSE"
                secure_str = "TRUE" if secure else "FALSE"
                # Chrome stores expiry as microseconds since 1601-01-01
                # Convert to Unix epoch
                if expires > 0:
                    unix_expires = int((expires / 1_000_000) - 11644473600)
                else:
                    unix_expires = 0
                f.write(f"{host}\t{domain_dot}\t{path}\t{secure_str}\t{unix_expires}\t{name}\t{value}\n")
                count += 1

        print(f"Exported {count} Google cookies to {OUTPUT_FILE}")
        return True

    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    # Note: Chrome encrypts cookie values on Windows using DPAPI.
    # If values come out empty, use the Chrome extension method instead:
    #   1. Install "Get cookies.txt LOCALLY" Chrome extension
    #   2. Go to google.com/maps
    #   3. Click the extension → Export → save as data/google_maps_cookies.txt
    print("Attempting direct Chrome DB export...")
    success = export_cookies()
    if not success:
        print("\n--- Alternative method ---")
        print("1. Install 'Get cookies.txt LOCALLY' Chrome extension")
        print("2. Go to https://www.google.com/maps in Chrome (make sure you're logged in)")
        print("3. Click the extension icon → Export")
        print(f"4. Save the file as: {OUTPUT_FILE}")
