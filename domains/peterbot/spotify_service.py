"""Spotify service for Peter.

Provides playback control, search, device management, and recommendations.
All methods are synchronous (spotipy is sync) — callers should use asyncio.to_thread().
"""

import os
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from logger import logger

ALL_SCOPES = " ".join([
    "user-read-recently-played", "user-top-read",
    "user-library-read", "user-library-modify",
    "user-read-playback-state", "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private", "playlist-read-collaborative",
    "playlist-modify-public", "playlist-modify-private",
    "user-follow-read", "user-follow-modify",
    "user-read-private", "user-read-email",
])

# Singleton client
_client: Optional[spotipy.Spotify] = None


def get_client() -> spotipy.Spotify:
    """Get or create authenticated Spotify client."""
    global _client
    if _client is not None:
        return _client

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("Spotify credentials not configured")

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8765/callback",
        scope=ALL_SCOPES,
    )
    auth_manager.refresh_access_token(refresh_token)

    _client = spotipy.Spotify(auth_manager=auth_manager)
    return _client


def reset_client():
    """Force re-auth on next call (e.g. after token refresh failure)."""
    global _client
    _client = None


# --- Playback Control ---

def now_playing() -> dict:
    """Get current playback state."""
    sp = get_client()
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return {"playing": False}

    track = playback["item"]
    artists = ", ".join(a["name"] for a in track.get("artists", []))
    album = track.get("album", {}).get("name", "")
    device = playback.get("device", {})

    result = {
        "playing": playback.get("is_playing", False),
        "track": track.get("name", "Unknown"),
        "artists": artists,
        "album": album,
        "duration_ms": track.get("duration_ms", 0),
        "progress_ms": playback.get("progress_ms", 0),
        "device": device.get("name", "Unknown"),
        "device_type": device.get("type", "Unknown"),
        "volume": device.get("volume_percent"),
        "shuffle": playback.get("shuffle_state", False),
        "repeat": playback.get("repeat_state", "off"),
        "track_uri": track.get("uri"),
        "album_uri": track.get("album", {}).get("uri"),
        "image_url": (track.get("album", {}).get("images", [{}])[0].get("url") if track.get("album", {}).get("images") else None),
    }

    # Audio features for mood (may 403 on newer API versions)
    try:
        features = sp.audio_features([track["id"]])
        if features and features[0]:
            f = features[0]
            result["mood"] = {
                "valence": f.get("valence"),
                "energy": f.get("energy"),
                "danceability": f.get("danceability"),
                "tempo": f.get("tempo"),
                "acousticness": f.get("acousticness"),
                "instrumentalness": f.get("instrumentalness"),
            }
    except Exception as e:
        logger.debug(f"Audio features unavailable: {e}")

    return result


def pause():
    """Pause playback."""
    sp = get_client()
    sp.pause_playback()
    return {"status": "paused"}


def resume():
    """Resume playback."""
    sp = get_client()
    sp.start_playback()
    return {"status": "playing"}


def skip():
    """Skip to next track."""
    sp = get_client()
    sp.next_track()
    return {"status": "skipped"}


def previous():
    """Go to previous track."""
    sp = get_client()
    sp.previous_track()
    return {"status": "previous"}


def volume(level: int):
    """Set volume (0-100)."""
    level = max(0, min(100, level))
    sp = get_client()
    sp.volume(level)
    return {"status": "volume_set", "volume": level}


def seek(position_ms: int):
    """Seek to position in current track."""
    sp = get_client()
    sp.seek_track(position_ms)
    return {"status": "seeked", "position_ms": position_ms}


def shuffle(state: bool):
    """Toggle shuffle."""
    sp = get_client()
    sp.shuffle(state)
    return {"status": "shuffle_on" if state else "shuffle_off"}


def repeat(state: str = "off"):
    """Set repeat mode: off, track, context."""
    sp = get_client()
    sp.repeat(state)
    return {"status": f"repeat_{state}"}


# --- Search & Play ---

def search_and_play(query: str, search_type: str = "track", device_id: str = None) -> dict:
    """Search for content and play the top result.

    Args:
        query: Search query (e.g. "Parachutes Coldplay", "focus playlist")
        search_type: One of track, album, artist, playlist
        device_id: Target device (None = active device)

    Returns:
        Dict with what was played
    """
    sp = get_client()

    # Map search type to Spotify type string
    type_map = {
        "track": "track",
        "album": "album",
        "artist": "artist",
        "playlist": "playlist",
    }
    sp_type = type_map.get(search_type, "track")

    results = sp.search(q=query, type=sp_type, limit=1)
    key = f"{sp_type}s"

    if not results.get(key, {}).get("items"):
        return {"error": f"No {sp_type} found for '{query}'"}

    item = results[key]["items"][0]
    uri = item["uri"]
    name = item.get("name", "Unknown")

    # Get artist name
    if sp_type == "track":
        artist = ", ".join(a["name"] for a in item.get("artists", []))
        sp.start_playback(uris=[uri], device_id=device_id)
        return {"played": "track", "name": name, "artist": artist, "uri": uri}

    elif sp_type == "album":
        artist = ", ".join(a["name"] for a in item.get("artists", []))
        sp.start_playback(context_uri=uri, device_id=device_id)
        return {"played": "album", "name": name, "artist": artist, "uri": uri}

    elif sp_type == "artist":
        sp.start_playback(context_uri=uri, device_id=device_id)
        return {"played": "artist", "name": name, "uri": uri}

    elif sp_type == "playlist":
        owner = item.get("owner", {}).get("display_name", "Unknown")
        sp.start_playback(context_uri=uri, device_id=device_id)
        return {"played": "playlist", "name": name, "owner": owner, "uri": uri}

    return {"error": "Unknown type"}


def play_uri(uri: str, device_id: str = None) -> dict:
    """Play a specific Spotify URI."""
    sp = get_client()
    if uri.startswith("spotify:track:"):
        sp.start_playback(uris=[uri], device_id=device_id)
    else:
        sp.start_playback(context_uri=uri, device_id=device_id)
    return {"status": "playing", "uri": uri}


def queue_track(query: str) -> dict:
    """Search for a track and add it to the queue."""
    sp = get_client()
    results = sp.search(q=query, type="track", limit=1)
    if not results.get("tracks", {}).get("items"):
        return {"error": f"No track found for '{query}'"}

    track = results["tracks"]["items"][0]
    sp.add_to_queue(track["uri"])
    artist = ", ".join(a["name"] for a in track.get("artists", []))
    return {"queued": track["name"], "artist": artist, "uri": track["uri"]}


# --- Devices ---

def get_devices() -> list[dict]:
    """Get available Spotify Connect devices."""
    sp = get_client()
    result = sp.devices()
    devices = []
    for d in result.get("devices", []):
        devices.append({
            "id": d["id"],
            "name": d["name"],
            "type": d["type"],
            "active": d["is_active"],
            "volume": d.get("volume_percent"),
        })
    return devices


def transfer(device_name: str) -> dict:
    """Transfer playback to a device by name (fuzzy match)."""
    sp = get_client()
    devices = sp.devices().get("devices", [])

    # Fuzzy match by name (case-insensitive, partial)
    target = None
    name_lower = device_name.lower()
    for d in devices:
        if name_lower in d["name"].lower():
            target = d
            break

    if not target:
        available = [d["name"] for d in devices]
        return {"error": f"Device '{device_name}' not found. Available: {available}"}

    sp.transfer_playback(target["id"], force_play=True)
    return {"status": "transferred", "device": target["name"], "device_id": target["id"]}


# --- Recommendations & Discovery ---

def recommend_from_current(limit: int = 10) -> dict:
    """Get recommendations based on currently playing track."""
    sp = get_client()
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return {"error": "Nothing currently playing"}

    track = playback["item"]
    seed_tracks = [track["id"]]
    seed_artists = [track["artists"][0]["id"]] if track.get("artists") else []

    recs = sp.recommendations(
        seed_tracks=seed_tracks,
        seed_artists=seed_artists[:1],
        limit=limit,
    )

    tracks = []
    for t in recs.get("tracks", []):
        artist = ", ".join(a["name"] for a in t.get("artists", []))
        tracks.append({
            "name": t["name"],
            "artist": artist,
            "uri": t["uri"],
            "album": t.get("album", {}).get("name", ""),
        })

    return {
        "seed_track": track["name"],
        "seed_artist": ", ".join(a["name"] for a in track.get("artists", [])),
        "recommendations": tracks,
    }


def play_recommendations(limit: int = 20, device_id: str = None) -> dict:
    """Get recommendations from current track and start playing them."""
    recs = recommend_from_current(limit=limit)
    if "error" in recs:
        return recs

    sp = get_client()
    uris = [t["uri"] for t in recs["recommendations"]]
    if not uris:
        return {"error": "No recommendations found"}

    sp.start_playback(uris=uris, device_id=device_id)
    return {
        "status": "playing_recommendations",
        "based_on": f"{recs['seed_track']} by {recs['seed_artist']}",
        "track_count": len(uris),
    }


# --- Playlists ---

def get_playlists(limit: int = 20) -> list[dict]:
    """Get user's playlists."""
    sp = get_client()
    results = sp.current_user_playlists(limit=limit)
    playlists = []
    for p in results.get("items", []):
        playlists.append({
            "name": p.get("name", "Unknown"),
            "uri": p["uri"],
            "id": p["id"],
            "track_count": p.get("tracks", {}).get("total", 0) if isinstance(p.get("tracks"), dict) else 0,
            "owner": p.get("owner", {}).get("display_name", ""),
        })
    return playlists


def play_playlist_by_name(name: str, device_id: str = None) -> dict:
    """Find a playlist by name and play it."""
    sp = get_client()
    # Search user's playlists first
    results = sp.current_user_playlists(limit=50)
    name_lower = name.lower()

    for p in results.get("items", []):
        if name_lower in p.get("name", "").lower():
            sp.start_playback(context_uri=p["uri"], device_id=device_id)
            return {"played": "playlist", "name": p["name"], "uri": p["uri"]}

    # Fallback to global search
    return search_and_play(name, search_type="playlist", device_id=device_id)
