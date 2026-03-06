"""Spotify API Routes for Peter.

Provides playback control, search, device management, and recommendations.
All endpoints proxy to domains.peterbot.spotify_service.
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from domains.peterbot import spotify_service as spotify

router = APIRouter(prefix="/spotify", tags=["Spotify"])


# --- Request Models ---

class PlayRequest(BaseModel):
    query: str
    type: str = "track"  # track, album, artist, playlist
    device: Optional[str] = None


class QueueRequest(BaseModel):
    query: str


class VolumeRequest(BaseModel):
    level: int


class TransferRequest(BaseModel):
    device: str


class SeekRequest(BaseModel):
    position_ms: int


class ShuffleRequest(BaseModel):
    state: bool


class RepeatRequest(BaseModel):
    state: str = "off"  # off, track, context


class PlayUriRequest(BaseModel):
    uri: str
    device: Optional[str] = None


# --- Endpoints ---

@router.get("/now-playing")
async def now_playing():
    """Get current playback state with mood data."""
    try:
        return await asyncio.to_thread(spotify.now_playing)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/play")
async def play(req: PlayRequest):
    """Search and play content.

    Examples:
        {"query": "Parachutes Coldplay", "type": "album"}
        {"query": "Yellow Coldplay", "type": "track"}
        {"query": "focus music", "type": "playlist"}
    """
    try:
        result = await asyncio.to_thread(
            spotify.search_and_play, req.query, req.type, req.device
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/play-uri")
async def play_uri(req: PlayUriRequest):
    """Play a specific Spotify URI."""
    try:
        return await asyncio.to_thread(spotify.play_uri, req.uri, req.device)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue")
async def queue(req: QueueRequest):
    """Add a track to the queue."""
    try:
        result = await asyncio.to_thread(spotify.queue_track, req.query)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause")
async def pause():
    """Pause playback."""
    try:
        return await asyncio.to_thread(spotify.pause)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def resume():
    """Resume playback."""
    try:
        return await asyncio.to_thread(spotify.resume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skip")
async def skip():
    """Skip to next track."""
    try:
        return await asyncio.to_thread(spotify.skip)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/previous")
async def previous():
    """Go to previous track."""
    try:
        return await asyncio.to_thread(spotify.previous)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/volume")
async def set_volume(req: VolumeRequest):
    """Set volume (0-100)."""
    try:
        return await asyncio.to_thread(spotify.volume, req.level)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/seek")
async def seek(req: SeekRequest):
    """Seek to position in current track."""
    try:
        return await asyncio.to_thread(spotify.seek, req.position_ms)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shuffle")
async def set_shuffle(req: ShuffleRequest):
    """Toggle shuffle on/off."""
    try:
        return await asyncio.to_thread(spotify.shuffle, req.state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/repeat")
async def set_repeat(req: RepeatRequest):
    """Set repeat mode: off, track, context."""
    try:
        return await asyncio.to_thread(spotify.repeat, req.state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices")
async def devices():
    """Get available Spotify Connect devices."""
    try:
        return await asyncio.to_thread(spotify.get_devices)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transfer")
async def transfer(req: TransferRequest):
    """Transfer playback to a device by name (fuzzy match)."""
    try:
        result = await asyncio.to_thread(spotify.transfer, req.device)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommend")
async def recommend():
    """Get recommendations based on currently playing track."""
    try:
        result = await asyncio.to_thread(spotify.recommend_from_current)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/play-similar")
async def play_similar():
    """Play recommendations based on current track."""
    try:
        result = await asyncio.to_thread(spotify.play_recommendations)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/playlists")
async def playlists(limit: int = 20):
    """Get user's playlists."""
    try:
        return await asyncio.to_thread(spotify.get_playlists, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/play-playlist")
async def play_playlist(req: PlayRequest):
    """Find a playlist by name and play it."""
    try:
        result = await asyncio.to_thread(
            spotify.play_playlist_by_name, req.query, req.device
        )
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
