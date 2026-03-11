"""Spelling test API routes.

Endpoints for managing school spellings and test results.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import json
import os

router = APIRouter(prefix="/spellings", tags=["spellings"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://modjoikyuhqzouxvieua.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


class AddSpellingsRequest(BaseModel):
    child_name: str
    year_group: str
    academic_year: str = "2025-26"
    week_number: int
    phoneme: Optional[str] = None
    words: list[str]


class AddSentencesRequest(BaseModel):
    sentences: dict[str, str]  # {"word": "sentence using that word", ...}


@router.post("/add")
async def add_spellings(req: AddSpellingsRequest):
    """Add or update spelling words for a child/week. Used by Peter via natural language."""
    async with httpx.AsyncClient() as client:
        # Check if entry already exists for this child/week
        check = await client.get(
            f"{SUPABASE_URL}/rest/v1/school_spellings",
            headers=_headers(),
            params={
                "child_name": f"eq.{req.child_name}",
                "academic_year": f"eq.{req.academic_year}",
                "week_number": f"eq.{req.week_number}",
                "select": "id",
            },
        )
        existing = check.json()

        payload = {
            "child_name": req.child_name,
            "year_group": req.year_group,
            "academic_year": req.academic_year,
            "week_number": req.week_number,
            "phoneme": req.phoneme,
            "words": json.dumps(req.words),
            "source": "manual",
        }

        if existing:
            # Update existing
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/school_spellings?id=eq.{existing[0]['id']}",
                headers={**_headers(), "Prefer": "return=representation"},
                json=payload,
            )
        else:
            # Insert new
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/school_spellings",
                headers={**_headers(), "Prefer": "return=representation"},
                json=payload,
            )

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        action = "updated" if existing else "added"
        return {
            "status": "ok",
            "action": action,
            "child_name": req.child_name,
            "week_number": req.week_number,
            "words": req.words,
        }


@router.get("/current-week")
async def get_current_week():
    """Get the current teaching week number based on term dates.

    Uses exact same logic as data_fetchers.py get_school_data().
    """
    from datetime import date, timedelta

    TERM_DATES_2025_26 = [
        (date(2025, 9, 4),  date(2025, 10, 24)),  # Autumn 1
        (date(2025, 11, 3), date(2025, 12, 19)),   # Autumn 2
        (date(2026, 1, 5),  date(2026, 2, 13)),    # Spring 1
        (date(2026, 2, 23), date(2026, 3, 27)),    # Spring 2
        (date(2026, 4, 13), date(2026, 5, 22)),    # Summer 1
        (date(2026, 6, 1),  date(2026, 7, 22)),    # Summer 2
    ]
    SPELLING_WEEK_OFFSET = -3

    today = date.today()
    teaching_week = 0

    for term_start, term_end in TERM_DATES_2025_26:
        monday = term_start + timedelta(days=(7 - term_start.weekday()) % 7)
        while monday <= min(today, term_end):
            teaching_week += 1
            monday += timedelta(days=7)
        if today <= term_end:
            break

    current_week = max(1, min(36, teaching_week + SPELLING_WEEK_OFFSET))
    return {"academic_year": "2025-26", "week_number": current_week}


@router.post("/sentences")
async def add_sentences(req: AddSentencesRequest):
    """Add or update sentences for spelling words. Used by Peter after adding new words."""
    async with httpx.AsyncClient() as client:
        added = []
        updated = []
        for word, sentence in req.sentences.items():
            word_lower = word.lower().strip()
            # Check if sentence already exists
            check = await client.get(
                f"{SUPABASE_URL}/rest/v1/spelling_sentences",
                headers=_headers(),
                params={"word": f"eq.{word_lower}", "select": "word"},
            )
            payload = {"word": word_lower, "sentence": sentence}

            if check.json():
                resp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/spelling_sentences?word=eq.{word_lower}",
                    headers={**_headers(), "Prefer": "return=representation"},
                    json={"sentence": sentence},
                )
                updated.append(word_lower)
            else:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/spelling_sentences",
                    headers={**_headers(), "Prefer": "return=representation"},
                    json=payload,
                )
                added.append(word_lower)

            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Failed for '{word_lower}': {resp.text}",
                )

        return {
            "status": "ok",
            "added": added,
            "updated": updated,
            "total": len(req.sentences),
        }
