"""One-time Spotify OAuth setup script.

Run this once to get a refresh token, then add it to .env as SPOTIFY_REFRESH_TOKEN.

Prerequisites:
  1. Go to https://developer.spotify.com/dashboard
  2. Create an app (name: "Peter Second Brain", redirect URI: http://127.0.0.1:8765/callback)
  3. Copy Client ID and Client Secret into .env as SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET
  4. Run this script: python scripts/spotify_auth.py

The script will open your browser for authorization, then print the refresh token.

Re-auth (refresh token revoked — e.g. 29 Aug 2026 "invalid_grant: Refresh token
revoked" killed the playback poller and nightly spotify-listening import):
  python scripts/spotify_auth.py --write
writes SPOTIFY_REFRESH_TOKEN straight into .env. Then restart discord_bot and
hadley_api (POST :5000/api/restart/<service>) and re-run scripts/encrypt-env.sh.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler

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
        # Never read a cached token: a revoked refresh token in ./.cache made
        # spotipy try to refresh it and die before opening the browser (6 Sep 2026).
        cache_handler=MemoryCacheHandler(),
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

    if "--write" in sys.argv:
        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
        )
        _write_env(env_path, "SPOTIFY_REFRESH_TOKEN", refresh_token)
        print(f"Success! SPOTIFY_REFRESH_TOKEN written to {env_path}")
        print("Now restart discord_bot + hadley_api and re-run scripts/encrypt-env.sh.")
        return

    print("Success! Add this to your .env file:")
    print()
    print(f"SPOTIFY_REFRESH_TOKEN={refresh_token}")
    print()
    print("The adapter will use this refresh token to get new access tokens automatically.")


def _write_env(path: str, key: str, value: str) -> None:
    """Replace (or append) ``KEY=value`` in a dotenv file, preserving the rest."""
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    out, done = [], False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
