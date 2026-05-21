"""Attachment download endpoint for the peter-channel path.

Discord CDN URLs expire and Claude Code running in WSL cannot Read an https
URL — it needs a local path. router_v2 handles this by calling
`_download_attachments` which fetches images/audio to a local temp dir and
returns WSL-formatted paths (plus faster-whisper transcription for voice).

When peter-channel handles the message instead, none of that happens — the
attachment URLs go straight to Claude which then 400s or fails to see them.
This endpoint exposes the existing v2 downloader so the channel path gets
parity.

The peter-channel POSTs a list of attachment dicts (`{url, filename,
content_type, size}`); we return the same shape with `local_path` and/or
`transcription` filled in for media. Caller is responsible for cleaning up
nothing — the temp files persist until next bot restart, same as v2 today.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hadley_api.auth import require_auth
from logger import logger

router = APIRouter(prefix="/attachment", tags=["peter"])


class DownloadRequest(BaseModel):
    attachment_urls: list[dict]


class DownloadResponse(BaseModel):
    attachments: list[dict]
    transcriptions: list[str]


@router.post(
    "/download",
    response_model=DownloadResponse,
    dependencies=[Depends(require_auth)],
)
async def download_attachments(body: DownloadRequest) -> DownloadResponse:
    """Mirror router_v2._download_attachments for channel callers.

    Returns updated attachment list with `local_path` (for images) and
    `transcription` (for audio) filled in. Skips anything that isn't image
    or audio.
    """
    try:
        from domains.peterbot.router_v2 import _download_attachments
    except Exception as e:
        # error not warning: if the downloader can't be imported, every
        # channel media attachment silently degrades to URL-only — visible
        # only by URL Read failures inside the session. Loud is better.
        logger.error(f"Attachment downloader import failed: {e}")
        return DownloadResponse(attachments=body.attachment_urls, transcriptions=[])

    if not body.attachment_urls:
        return DownloadResponse(attachments=[], transcriptions=[])

    try:
        updated, _temp_files = await _download_attachments(body.attachment_urls)
    except Exception as e:
        logger.warning(f"Attachment download failed: {e}")
        return DownloadResponse(attachments=body.attachment_urls, transcriptions=[])

    transcriptions = [
        a["transcription"]
        for a in updated
        if a.get("transcription") and a["transcription"] != "[Voice note — transcription failed]"
    ]

    return DownloadResponse(attachments=updated, transcriptions=transcriptions)
