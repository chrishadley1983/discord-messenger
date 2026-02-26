"""Withings OAuth Authorization Script.

Run this once to get your Access Token and Refresh Token.

Usage:
    python scripts/withings_auth.py
"""

import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
import httpx
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("WITHINGS_CLIENT_ID")
CLIENT_SECRET = os.getenv("WITHINGS_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8765/callback"
SCOPE = "user.metrics"

authorization_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global authorization_code

        query = parse_qs(urlparse(self.path).query)

        if "code" in query:
            authorization_code = query["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = query.get("error", ["Unknown error"])[0]
            self.wfile.write(f"<html><body><h1>Error: {error}</h1></body></html>".encode())

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Error: WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET must be set in .env")
        return

    print("=" * 60)
    print("Withings OAuth Authorization")
    print("=" * 60)
    print()

    # Step 1: Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": "discord-assistant"
    }
    auth_url = f"https://account.withings.com/oauth2_user/authorize2?{urlencode(auth_params)}"

    print("Opening browser for Withings authorization...")
    print()
    print("If browser doesn't open, visit this URL manually:")
    print(auth_url)
    print()

    webbrowser.open(auth_url)

    # Step 2: Start local server to catch callback
    print("Waiting for authorization callback on http://localhost:8765/callback ...")
    print()

    server = HTTPServer(("localhost", 8765), CallbackHandler)

    while authorization_code is None:
        server.handle_request()

    server.server_close()

    print(f"Received authorization code: {authorization_code[:20]}...")
    print()

    # Step 3: Exchange code for tokens
    print("Exchanging code for tokens...")

    token_response = httpx.post(
        "https://wbsapi.withings.net/v2/oauth2",
        data={
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": authorization_code,
            "redirect_uri": REDIRECT_URI
        }
    )

    data = token_response.json()

    if data.get("status") != 0:
        print(f"Error: {data}")
        return

    access_token = data["body"]["access_token"]
    refresh_token = data["body"]["refresh_token"]
    expires_in = data["body"]["expires_in"]

    # Save to persistent token file (used by withings.py on startup)
    import json
    from pathlib import Path
    token_file = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "withings_tokens.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(json.dumps({
        "access": access_token,
        "refresh": refresh_token,
        "updated_at": __import__("datetime").datetime.now().isoformat()
    }))

    print()
    print("=" * 60)
    print("SUCCESS! Tokens saved.")
    print("=" * 60)
    print()
    print(f"Persistent file: {token_file}")
    print(f"(Access token expires in {expires_in} seconds, auto-refreshes)")
    print()
    print("Restart HadleyAPI to pick up the new tokens:")
    print("  nssm restart HadleyAPI  (run as admin)")
    print()


if __name__ == "__main__":
    main()
