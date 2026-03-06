"""One-time Spotify OAuth setup script.

Run this once to get a refresh token, then add it to .env as SPOTIFY_REFRESH_TOKEN.

Prerequisites:
  1. Go to https://developer.spotify.com/dashboard
  2. Create an app (name: "Peter Second Brain", redirect URI: http://127.0.0.1:8765/callback)
  3. Copy Client ID and Client Secret into .env as SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
  4. Run this script: python scripts/spotify_auth.py

The script will open your browser for authorization, then print the refresh token.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from spotipy.oauth2 import SpotifyOAuth

SCOPES = " ".join([
    # Listening history
    "user-read-recently-played",
    "user-top-read",
    # Library
    "user-library-read",
    "user-library-modify",
    # Playback control (Premium)
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    # Playlists
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    # Follow
    "user-follow-read",
    "user-follow-modify",
    # Profile
    "user-read-private",
    "user-read-email",
])
REDIRECT_URI = "http://127.0.0.1:8765/callback"


def main():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env first.")
        print()
        print("Steps:")
        print("  1. Go to https://developer.spotify.com/dashboard")
        print("  2. Create an app")
        print("  3. Set redirect URI to: http://127.0.0.1:8765/callback")
        print("  4. Copy Client ID and Client Secret into .env")
        sys.exit(1)

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
        open_browser=True,
    )

    print("Opening browser for Spotify authorization...")
    print(f"If browser doesn't open, visit: {auth_manager.get_authorize_url()}")
    print()

    # This will open the browser, wait for callback, and exchange the code
    token_info = auth_manager.get_access_token(as_dict=True)

    if not token_info:
        print("ERROR: Failed to get token. Try again.")
        sys.exit(1)

    refresh_token = token_info.get("refresh_token")
    if not refresh_token:
        print("ERROR: No refresh token in response.")
        print(f"Token info: {token_info}")
        sys.exit(1)

    print("Success! Add this to your .env file:")
    print()
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print()
    print("The adapter will use this refresh token to get new access tokens automatically.")


if __name__ == "__main__":
    main()
