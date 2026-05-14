"""Scrape the rendered Prolific /studies list via CDP."""

from __future__ import annotations

import re
from dataclasses import dataclass

from logger import logger

from .chrome import cdp_page
from .config import NAV_TIMEOUT_MS, RENDER_WAIT_MS, STUDIES_URL


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


async def fetch_studies() -> list[Study]:
    """Navigate to /studies and return all visible study cards."""
    async with cdp_page(headless=True) as page:
        await page.goto(STUDIES_URL, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        await page.wait_for_timeout(RENDER_WAIT_MS)

        if "/login" in page.url:
            logger.warning("Prolific session expired — login page hit. Run: python -m domains.prolific.login")
            return []

        raw_cards = await page.evaluate(_EXTRACT_JS)

    studies: list[Study] = []
    for card in raw_cards:
        try:
            parsed = _parse_card(card["text"], card["reward"], card["hourly"], card["id"])
            if parsed:
                studies.append(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse Prolific card {card.get('id')}: {e}")

    return studies
