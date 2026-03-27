"""Gousto recipe scraper.

Finds Gousto order summary emails, extracts recipe links,
and scrapes full recipe content (ingredients, method, nutrition)
via Chrome CDP (Gousto pages are fully JS-rendered).

Email format: recipe names appear as plaintext next to clicks.gousto.co.uk
tracking URLs. We extract the tracking URLs (deduplicated), then follow
them in CDP Chrome which redirects to the actual recipe page.
"""

import asyncio
import json
import re
from typing import Optional

from logger import logger
from .base import BaseEmailLinkScraper, ScrapedItem


# Match tracking redirect URLs from Gousto emails
TRACKING_URL_PATTERN = re.compile(
    r"https?://clicks\.gousto\.co\.uk/f/a/[A-Za-z0-9_~-]+/[A-Za-z0-9_~/-]+"
)

# Match direct recipe URLs (final destination after redirect)
RECIPE_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?gousto\.co\.uk/cookbook/[\w-]+"
)

# CDP script path (Windows — called via node.exe from WSL)
CDP_SCRIPT = "C:/Users/Chris Hadley/claude-projects/chrome-cdp-skill/skills/chrome-cdp/scripts/cdp.mjs"
CDP_PORT = 9222

# Hadley family cooks for 4 — scale all recipes to this
TARGET_SERVINGS = 4


def _scale_ingredient(text: str, factor: float) -> str:
    """Scale the quantity in an ingredient string by the given factor.

    Handles: "200g chicken breast" → "400g chicken breast"
             "Spring onion x2" → "Spring onion x4"
             "1 tsp cumin" → "2 tsp cumin"
             "½ lemon" → "1 lemon"
    """
    if factor == 1.0:
        return text

    # Pattern: "ingredient x2" suffix notation
    xn = re.search(r"(x)(\d+\.?\d*)\s*$", text)
    if xn:
        old_val = float(xn.group(2))
        new_val = old_val * factor
        nice = _nice_number(new_val)
        return text[:xn.start(2)] + nice + text[xn.end(2):]

    # Pattern: leading number (with optional fraction/unicode)
    m = re.match(
        r"^([\d./½¼¾⅓⅔]+)\s*"
        r"(g|kg|ml|l|tsp|tbsp|clove|cloves|can|cans|tin|tins|pack|packs|"
        r"pinch|handful|bunch|slice|slices|stick|sticks|cm|piece|pieces|pcs|"
        r"tbsp\b|tsp\b)?\s*(.*)",
        text, re.IGNORECASE,
    )
    if m:
        old_val = _parse_fraction(m.group(1))
        if old_val > 0:
            new_val = old_val * factor
            nice = _nice_number(new_val)
            unit = m.group(2) or ""
            rest = m.group(3) or ""
            sep = "" if unit else " "
            return f"{nice}{unit}{sep}{rest}".strip()

    return text


def _parse_fraction(s: str) -> float:
    """Parse a quantity string that may contain unicode fractions."""
    s = s.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    s = s.replace("⅓", ".333").replace("⅔", ".667")
    try:
        if "/" in s:
            parts = s.split("/")
            return float(parts[0]) / float(parts[1])
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0


def _nice_number(val: float) -> str:
    """Format a number nicely — '2' not '2.0', '1.5' not '1.50'."""
    if val == int(val):
        return str(int(val))
    # One decimal place max
    return f"{val:.1f}".rstrip("0").rstrip(".")


def _scale_nutrition_value(text: str, factor: float) -> str:
    """Scale a nutrition value string like '523kcal' or '12.5g'."""
    if factor == 1.0:
        return text
    m = re.match(r"([\d.]+)(.*)", text)
    if m:
        new_val = float(m.group(1)) * factor
        return f"{_nice_number(new_val)}{m.group(2)}"
    return text

# JS to extract all recipe data in a single eval call
EXTRACT_RECIPE_JS = """(function(){
var r = {url: location.href, title: '', bodyText: '', ingredients: [], method: [], nutrition: {}};
var h1 = document.querySelector('h1');
r.title = h1 ? h1.textContent.trim() : '';
r.bodyText = (document.body.innerText || '').substring(0, 2000);

// Ingredients
var iSels = ['[data-testid="ingredients"] li', '.ingredients li', '[class*="ingredient"] li', '[class*="Ingredient"] li'];
for (var i = 0; i < iSels.length; i++) {
    var els = document.querySelectorAll(iSels[i]);
    if (els.length) { els.forEach(function(el) { var t = el.textContent.trim(); if (t) r.ingredients.push(t); }); break; }
}
if (!r.ingredients.length) {
    var hs = document.querySelectorAll('h2, h3, h4');
    for (var i = 0; i < hs.length; i++) {
        if (hs[i].textContent.toLowerCase().includes('ingredient')) {
            var sib = hs[i].nextElementSibling;
            if (sib) { sib.querySelectorAll('li').forEach(function(li) { var t = li.textContent.trim(); if (t) r.ingredients.push(t); }); }
            break;
        }
    }
}

// Method
var mSels = ['[data-testid="method"] li', '[data-testid="instructions"] li', '.method li', '[class*="method"] li', '[class*="instruction"] li', '[class*="Method"] li'];
for (var i = 0; i < mSels.length; i++) {
    var els = document.querySelectorAll(mSels[i]);
    if (els.length) { els.forEach(function(el) { var t = el.textContent.trim(); if (t) r.method.push(t); }); break; }
}
if (!r.method.length) {
    var hs = document.querySelectorAll('h2, h3, h4');
    for (var i = 0; i < hs.length; i++) {
        if (hs[i].textContent.toLowerCase().includes('method')) {
            var sib = hs[i].nextElementSibling;
            if (sib) { sib.querySelectorAll('li').forEach(function(li) { var t = li.textContent.trim(); if (t) r.method.push(t); }); }
            break;
        }
    }
}

// Nutrition
var nSels = ['[data-testid="nutrition"] tr', '.nutrition tr', '[class*="nutrition"] tr', '[class*="Nutrition"] tr', 'table tr'];
for (var i = 0; i < nSels.length; i++) {
    var rows = document.querySelectorAll(nSels[i]);
    if (rows.length > 1) {
        rows.forEach(function(row) {
            var cells = row.querySelectorAll('td, th');
            var texts = Array.from(cells).map(function(c) { return c.textContent.trim(); }).filter(Boolean);
            if (texts.length >= 2) r.nutrition[texts[0]] = texts[1];
        });
        if (Object.keys(r.nutrition).length) break;
    }
}

return JSON.stringify(r);
})()"""


class GoustoRecipeScraper(BaseEmailLinkScraper):
    """Scrape Gousto recipe pages from order confirmation emails."""

    name = "gousto"
    gmail_query = 'from:info.gousto.co.uk subject:"summary of your order"'
    default_topics = ["recipe", "gousto", "cooking", "meal-kit"]
    needs_playwright = False  # Uses Chrome CDP instead

    def __init__(self):
        # Map of tracking URL -> recipe name extracted from email
        self._link_names: dict[str, str] = {}
        self._cdp_tab_id: str = ""

    async def _cdp(self, *args: str) -> str:
        """Run a CDP command via cdp.mjs (Windows Node from WSL)."""
        proc = await asyncio.create_subprocess_exec(
            "node.exe", CDP_SCRIPT, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"CDP {' '.join(args[:1])}: {err}")
        return stdout.decode("utf-8", errors="replace").strip()

    async def _cdp_create_tab(self) -> str:
        """Create a new Chrome tab via CDP HTTP API, return tab ID."""
        js = (
            f"fetch('http://localhost:{CDP_PORT}/json/new',{{method:'PUT'}})"
            ".then(r=>r.json()).then(t=>console.log(t.id))"
        )
        proc = await asyncio.create_subprocess_exec(
            "node.exe", "-e", js,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        tab_id = stdout.decode("utf-8", errors="replace").strip()
        if not tab_id:
            raise RuntimeError("Failed to create CDP tab")
        return tab_id

    async def _cdp_close_tab(self, tab_id: str) -> None:
        """Close a Chrome tab via CDP HTTP API."""
        js = (
            f"fetch('http://localhost:{CDP_PORT}/json/close/{tab_id}',"
            "{method:'PUT'}).then(r=>r.text()).then(console.log)"
        )
        await asyncio.create_subprocess_exec(
            "node.exe", "-e", js,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def setup(self):
        """Create a fresh CDP tab for recipe scraping."""
        try:
            self._cdp_tab_id = await self._cdp_create_tab()
            # Force cdp.mjs daemon to rescan targets so it sees the new tab
            await asyncio.sleep(0.5)
            await self._cdp("list")
            logger.info(f"Gousto scraper: CDP tab created ({self._cdp_tab_id[:8]})")
        except Exception as e:
            raise RuntimeError(f"Gousto scraper: cannot create CDP tab — is Chrome CDP running? {e}")

    async def teardown(self):
        """Close the CDP tab."""
        if self._cdp_tab_id:
            try:
                await self._cdp_close_tab(self._cdp_tab_id)
                logger.info(f"Gousto scraper: CDP tab closed ({self._cdp_tab_id[:8]})")
            except Exception:
                pass
            self._cdp_tab_id = ""

    def extract_links(self, email_body: str) -> list[str]:
        """Extract Gousto tracking URLs that appear next to recipe names.

        The email contains clicks.gousto.co.uk tracking URLs that redirect
        to the actual recipe pages. We extract unique tracking URLs that
        appear near recipe content (cook time, eat-by-date patterns).

        Also populates self._link_names with recipe names extracted from
        the email text (used as fallback when Gousto returns a 404 page).
        """
        # Strip HTML tags for recipe name extraction
        plain = re.sub(r"<[^>]+>", " ", email_body)
        plain = re.sub(r"\s+", " ", plain)

        # Find all tracking URLs
        all_urls = TRACKING_URL_PATTERN.findall(email_body)
        # Also check for direct recipe URLs (in case format changes)
        direct = RECIPE_URL_PATTERN.findall(email_body)
        if direct:
            return list(dict.fromkeys(direct))  # Deduplicate preserving order

        # Deduplicate tracking URLs preserving order
        seen = set()
        unique_urls = []
        for url in all_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        # Filter: only keep URLs that appear near recipe content
        # Recipe sections have "Cooking time:" and "Eat-by-date:" nearby
        recipe_urls = []
        for url in unique_urls:
            # Find URL position in email body
            pos = email_body.find(url)
            if pos == -1:
                continue
            # Check 500 chars around this URL for recipe indicators
            context = email_body[max(0, pos - 200):pos + len(url) + 300]
            if re.search(r"(cooking time|eat-by-date|see recipe)", context, re.I):
                recipe_urls.append(url)

        # If context filtering was too aggressive, fall back to all unique URLs
        # but exclude obvious non-recipe links (social media, tracking box)
        if not recipe_urls:
            for url in unique_urls:
                pos = email_body.find(url)
                if pos == -1:
                    continue
                context = email_body[max(0, pos - 100):pos + len(url) + 100].lower()
                # Skip social media and box tracking links
                if any(kw in context for kw in ["instagram", "tik tok", "facebook", "track box", "track my"]):
                    continue
                recipe_urls.append(url)

        # Extract recipe names from plaintext near each recipe URL
        # Email format: "Recipe Name ( https://clicks.gousto.co.uk/... )"
        for url in recipe_urls:
            pos = plain.find(url)
            if pos == -1:
                continue
            # Look at the text before this URL for the recipe name
            before = plain[max(0, pos - 200):pos].strip().rstrip("(").strip()
            # The recipe name is the last "sentence" before the URL
            # Split on common delimiters that separate recipes
            # (e.g. "See recipe" from previous entry, or "mins" from cook time)
            # Recipe name appears after: "See recipe", "XX mins", "START DROOLING",
            # or "~ )" (end of previous tracking URL)
            name_match = re.search(
                r"(?:See recipe|mins|START DROOLING|~\s*\))\s+(.+?)$",
                before, re.I
            )
            if name_match:
                name = name_match.group(1).strip()
                # Clean up: remove "START DROOLING" if it leaked into the name
                name = re.sub(r"^START DROOLING\s+", "", name, flags=re.I)
                if name and len(name) > 3 and name.lower() not in ("see recipe",):
                    self._link_names[url] = name

        return recipe_urls

    async def scrape_link(self, page, url: str) -> Optional[ScrapedItem]:
        """Scrape a Gousto recipe page via Chrome CDP.

        Navigates to tracking URL which redirects to the actual recipe page.
        The `page` argument is unused (kept for interface compatibility).
        """
        if not self._cdp_tab_id:
            logger.warning("Gousto scraper: no CDP tab available, skipping")
            return None

        canonical_url = url  # Fallback — overwritten once we know the final URL
        tab = self._cdp_tab_id[:8]  # Abbreviated tab ID

        try:
            # Navigate — tracking URL will redirect to actual recipe page
            await self._cdp("nav", tab, url)

            # Wait for redirects to settle
            await asyncio.sleep(3)

            # Get the final URL
            final_url = await self._cdp("eval", tab, "window.location.href")
            canonical_url = final_url.split("?")[0]  # Strip query params

            if "gousto.co.uk/cookbook" not in final_url:
                logger.debug(f"Tracking URL did not redirect to recipe: {final_url}")
                return None

            # Wait for recipe content to render (poll for h1 up to 10s)
            title = ""
            for _ in range(5):
                title = await self._cdp("eval", tab, "document.querySelector('h1')?.textContent?.trim() || ''")
                if title:
                    break
                await asyncio.sleep(2)

            if not title:
                title = "Untitled Recipe"

            # Detect Gousto 404 page ("Oh crumbs!" = recipe removed from cookbook)
            if "oh crumbs" in title.lower():
                email_name = self._link_names.get(url)
                if email_name:
                    logger.info(f"Gousto 404 for {canonical_url} — using email name: {email_name}")
                    title = email_name
                    content = self._format_recipe(
                        title=title,
                        url=canonical_url,
                        meta={},
                        ingredients=[],
                        method=[],
                        nutrition={},
                        note="Recipe no longer available on Gousto's website.",
                    )
                    return ScrapedItem(
                        title=title,
                        content=content,
                        url=canonical_url,
                        topics=self.default_topics.copy(),
                        metadata={"source": "gousto", "status": "removed"},
                    )
                else:
                    logger.debug(f"Gousto 404 with no email name for {canonical_url}, skipping")
                    return None

            # Extract all recipe data in one CDP eval call
            result_json = await self._cdp("eval", tab, EXTRACT_RECIPE_JS)
            try:
                data = json.loads(result_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse recipe data JSON for {canonical_url}")
                data = {}

            body_text = data.get("bodyText", "")
            ingredients = data.get("ingredients", [])
            method = data.get("method", [])
            nutrition = data.get("nutrition", {})

            # Extract meta from body text
            meta = {}
            original_servings = 2  # Gousto default
            servings_match = re.search(r"(\d+)\s*(?:serving|person|people)", body_text, re.I)
            if servings_match:
                original_servings = int(servings_match.group(1))

            # Scale to target servings (family of 4)
            scale = TARGET_SERVINGS / original_servings if original_servings > 0 else 1.0
            meta["servings"] = str(TARGET_SERVINGS)
            if scale != 1.0:
                ingredients = [_scale_ingredient(ing, scale) for ing in ingredients]
                nutrition = {k: _scale_nutrition_value(v, scale) for k, v in nutrition.items()}
                meta["scaled_from"] = str(original_servings)

            time_match = re.search(r"(\d+)\s*min(?:ute)?s?", body_text, re.I)
            if time_match:
                meta["cook_time"] = f"{time_match.group(1)} mins"
            for level in ["easy", "medium", "hard"]:
                if level in body_text.lower():
                    meta["difficulty"] = level.capitalize()
                    break

            # Build structured markdown
            content = self._format_recipe(
                title=title,
                url=canonical_url,
                meta=meta,
                ingredients=ingredients,
                method=method,
                nutrition=nutrition,
            )

            return ScrapedItem(
                title=title,
                content=content,
                url=canonical_url,
                topics=self.default_topics.copy(),
                metadata={
                    "source": "gousto",
                    "servings": str(TARGET_SERVINGS),
                    "cook_time": meta.get("cook_time", ""),
                    "prep_time": meta.get("prep_time", ""),
                },
            )

        except Exception as e:
            logger.warning(f"Failed to scrape Gousto recipe {url}: {e}")
            return None

    def _format_recipe(
        self,
        title: str,
        url: str,
        meta: dict,
        ingredients: list[str],
        method: list[str],
        nutrition: dict,
        note: str = "",
    ) -> str:
        """Format recipe as structured markdown."""
        lines = [f"# {title}"]
        lines.append(f"**Source:** Gousto | **URL:** {url}")

        if note:
            lines.append(f"*{note}*")

        meta_parts = []
        if meta.get("servings"):
            serving_note = f"**Servings:** {meta['servings']}"
            if meta.get("scaled_from"):
                serving_note += f" (scaled from {meta['scaled_from']})"
            meta_parts.append(serving_note)
        if meta.get("cook_time"):
            meta_parts.append(f"**Cook Time:** {meta['cook_time']}")
        if meta.get("prep_time"):
            meta_parts.append(f"**Prep Time:** {meta['prep_time']}")
        if meta.get("difficulty"):
            meta_parts.append(f"**Difficulty:** {meta['difficulty']}")
        if meta_parts:
            lines.append(" | ".join(meta_parts))

        lines.append("")

        if ingredients:
            lines.append("## Ingredients")
            for ing in ingredients:
                lines.append(f"- {ing}")
            lines.append("")

        if method:
            lines.append("## Method")
            for i, step in enumerate(method, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        if nutrition:
            lines.append("## Nutrition (per serving)")
            lines.append("| Nutrient | Amount |")
            lines.append("|----------|--------|")
            for nutrient, amount in nutrition.items():
                lines.append(f"| {nutrient} | {amount} |")
            lines.append("")

        return "\n".join(lines)
