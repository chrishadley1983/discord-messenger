"""Scrape the rendered Prolific /studies list via CDP.

Uses a single long-lived page held open inside the headless Chrome-Prolific
session. Prolific's own SPA polls /api/v1/studies internally to keep the
DOM fresh, so we never have to send our own HTTP — each "scrape" is a pure
JS evaluation against the in-memory DOM. That removes any rate-limit /
bot-detection exposure.

Session lifecycle is best-effort: we cache the page, reload it every 15 min
as defence-in-depth, and tear it down + recreate on any error or session
expiry.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass

from logger import logger

from .chrome import ensure_chrome_running
from .config import (
    CDP_PORT,
    NAV_TIMEOUT_MS,
    PAGE_RELOAD_INTERVAL_SECONDS,
    RENDER_WAIT_MS,
    STUDIES_URL,
)


@dataclass
class Study:
    study_id: str
    title: str
    researcher: str
    reward_pence: int | None        # in the source currency, native pence
    hourly_rate_pence: int | None   # in the source currency, native pence
    reward_currency: str            # "GBP" or "USD"
    duration_mins: int | None
    places: int | None
    tags: list[str]
    url: str

    @property
    def _symbol(self) -> str:
        return "£" if self.reward_currency == "GBP" else "$"

    @property
    def reward_str(self) -> str:
        return f"{self._symbol}{self.reward_pence / 100:.2f}" if self.reward_pence is not None else "?"

    @property
    def hourly_str(self) -> str:
        return f"{self._symbol}{self.hourly_rate_pence / 100:.2f}/hr" if self.hourly_rate_pence is not None else "?"


# Pulls every visible study card. Stable selectors as of 2026-05:
# - li.list-item with data-testid="study-<id>" is the card root (and source of the ID)
# - [data-testid="base-card"] is the visible card body
# - [data-testid="study-tag-reward"] and "study-tag-reward-per-hour" carry the explicit prices
_EXTRACT_JS = r"""
() => {
  const lis = document.querySelectorAll('li.list-item[data-testid^="study-"]');
  return Array.from(lis).map(li => {
    const m = li.getAttribute('data-testid').match(/^study-([a-z0-9]+)$/i);
    const id = m ? m[1] : null;
    const card = li.querySelector('[data-testid="base-card"]') || li;
    const text = (card.innerText || '').trim();
    const rewardEl = card.querySelector('[data-testid="study-tag-reward"]');
    const hourlyEl = card.querySelector('[data-testid="study-tag-reward-per-hour"]');
    return {
      id,
      text,
      reward: rewardEl ? (rewardEl.innerText || '').trim() : '',
      hourly: hourlyEl ? (hourlyEl.innerText || '').trim() : '',
    };
  }).filter(c => c.id);
}
"""

# Permissive single-amount matcher: "£1.44" or "$10.80" — the explicit spans
# isolate one number each, so we don't need to parse the combined "X • Y/hr" line.
_AMOUNT_RE = re.compile(r"([£$])\s*(\d+(?:\.\d{1,2})?)")
_DURATION_RE = re.compile(r"(\d+)\s*mins?\b", re.I)
_PLACES_RE = re.compile(r"(\d+)\s*places?\b", re.I)
_TAG_TOKENS = {
    "Survey", "Experiment", "Interview", "Task", "Diary",
    "In-study screening", "Content warning", "Pre-screened",
}


def _to_pence(value_str: str) -> int:
    return int(round(float(value_str) * 100))


def _parse_amount(text: str) -> tuple[int | None, str | None]:
    """Returns (pence, currency) from text like '£1.44' or '$10.80'."""
    if not text:
        return None, None
    m = _AMOUNT_RE.search(text)
    if not m:
        return None, None
    sym, val = m.group(1), m.group(2)
    currency = "GBP" if sym == "£" else "USD"
    return _to_pence(val), currency


def _parse_card(card_text: str, reward_text: str, hourly_text: str, study_id: str) -> Study | None:
    lines = [ln.strip() for ln in card_text.splitlines() if ln.strip()]
    if not lines:
        return None

    title = lines[0]

    # Researcher line: looks like "By <Name>" or "By <Name>Prolific partner"
    researcher = ""
    for ln in lines[1:5]:
        if ln.lower().startswith("by "):
            r = ln[3:].strip()
            # Strip trailing "Prolific partner" badge if Prolific concatenates it
            for suffix in ("Prolific partner", "Researcher"):
                if r.endswith(suffix):
                    r = r[: -len(suffix)].strip()
            researcher = r
            break

    reward_pence, reward_ccy = _parse_amount(reward_text)
    hourly_pence, hourly_ccy = _parse_amount(hourly_text)

    # Prefer the reward's currency; fall back to hourly's; default to GBP.
    currency = reward_ccy or hourly_ccy or "GBP"

    duration_match = _DURATION_RE.search(card_text)
    duration_mins = int(duration_match.group(1)) if duration_match else None
    places_match = _PLACES_RE.search(card_text)
    places = int(places_match.group(1)) if places_match else None

    tags = [t for t in _TAG_TOKENS if t.lower() in card_text.lower()]

    return Study(
        study_id=study_id,
        title=title,
        researcher=researcher,
        reward_pence=reward_pence,
        hourly_rate_pence=hourly_pence,
        reward_currency=currency,
        duration_mins=duration_mins,
        places=places,
        tags=tags,
        url=f"https://app.prolific.com/studies/{study_id}",
    )


# Persistent page state. The Playwright + browser + page handles all stay
# alive between scheduler ticks so we keep one /studies tab loaded and let
# Prolific's own SPA refresh the DOM.
_state: dict = {
    "playwright": None,
    "browser": None,
    "page": None,
    "loaded_at": 0.0,
    "session_expired_logged": False,
}
_state_lock = asyncio.Lock()


async def _teardown() -> None:
    """Disconnect Playwright from the running Chrome (Chrome itself keeps running)."""
    page = _state.get("page")
    if page is not None:
        try:
            await page.close()
        except Exception:
            pass
    browser = _state.get("browser")
    if browser is not None:
        try:
            await browser.close()
        except Exception:
            pass
    pw = _state.get("playwright")
    if pw is not None:
        try:
            await pw.stop()
        except Exception:
            pass
    _state["playwright"] = None
    _state["browser"] = None
    _state["page"] = None
    _state["loaded_at"] = 0.0


async def _open_persistent_page():
    """Bring up Chrome if needed, attach via CDP, open /studies, render, cache."""
    await asyncio.to_thread(ensure_chrome_running, True)
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    contexts = browser.contexts
    ctx = contexts[0] if contexts else await browser.new_context()
    page = await ctx.new_page()
    await page.goto(STUDIES_URL, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    await page.wait_for_timeout(RENDER_WAIT_MS)

    _state["playwright"] = pw
    _state["browser"] = browser
    _state["page"] = page
    _state["loaded_at"] = time.time()
    _state["session_expired_logged"] = False


async def _ensure_page():
    """Return a healthy /studies page, recreating if needed."""
    page = _state.get("page")
    needs_create = page is None or page.is_closed()
    needs_reload = (
        not needs_create
        and (time.time() - _state.get("loaded_at", 0.0)) > PAGE_RELOAD_INTERVAL_SECONDS
    )

    if needs_create:
        await _teardown()
        await _open_persistent_page()
        return _state["page"]

    if needs_reload:
        try:
            await page.reload(timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
            await page.wait_for_timeout(RENDER_WAIT_MS)
            _state["loaded_at"] = time.time()
            _state["session_expired_logged"] = False
        except Exception as e:
            logger.warning(f"Prolific page reload failed ({e}) — recreating from scratch")
            await _teardown()
            await _open_persistent_page()

    return _state["page"]


async def fetch_studies() -> list[Study]:
    """Read the current /studies DOM and return visible study cards.

    No HTTP to Prolific between calls — Prolific's own SPA keeps the DOM
    fresh. We just evaluate the extractor JS against the in-memory page.
    """
    async with _state_lock:
        try:
            page = await _ensure_page()
        except Exception as e:
            logger.error(f"Prolific page setup failed: {e}")
            await _teardown()
            return []

        try:
            current_url = page.url
        except Exception:
            current_url = ""

        if "/login" in current_url:
            if not _state.get("session_expired_logged"):
                logger.warning("Prolific session expired — login page hit. Run: python -m domains.prolific.login")
                _state["session_expired_logged"] = True
            return []

        try:
            raw_cards = await page.evaluate(_EXTRACT_JS)
        except Exception as e:
            logger.warning(f"Prolific page.evaluate failed ({e}) — tearing down for fresh attempt next tick")
            await _teardown()
            return []

    studies: list[Study] = []
    for card in raw_cards:
        try:
            parsed = _parse_card(card["text"], card["reward"], card["hourly"], card["id"])
            if parsed:
                studies.append(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse Prolific card {card.get('id')}: {e}")

    return studies
