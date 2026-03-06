"""Gousto recipe scraper.

Finds Gousto order summary emails, extracts recipe links,
and scrapes full recipe content (ingredients, method, nutrition)
via Playwright (Gousto pages are fully JS-rendered).

Email format: recipe names appear as plaintext next to clicks.gousto.co.uk
tracking URLs. We extract the tracking URLs (deduplicated), then follow
them in Playwright which redirects to the actual recipe page.
"""

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


class GoustoRecipeScraper(BaseEmailLinkScraper):
    """Scrape Gousto recipe pages from order confirmation emails."""

    name = "gousto"
    gmail_query = 'from:info.gousto.co.uk subject:"summary of your order"'
    default_topics = ["recipe", "gousto", "cooking", "meal-kit"]
    needs_playwright = True

    def __init__(self):
        # Map of tracking URL -> recipe name extracted from email
        self._link_names: dict[str, str] = {}

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
        """Scrape a Gousto recipe page via Playwright.

        Navigates to tracking URL which redirects to the actual recipe page.
        """
        canonical_url = url  # Fallback — overwritten once we know the final URL
        try:
            # Navigate — tracking URL will redirect to actual recipe page
            # Use domcontentloaded, not networkidle — redirect chains hang with networkidle
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for redirects to settle
            await page.wait_for_timeout(2000)

            # Check we landed on a recipe page
            final_url = page.url
            canonical_url = final_url.split("?")[0]  # Strip query params

            if "gousto.co.uk/cookbook" not in final_url:
                logger.debug(f"Tracking URL did not redirect to recipe: {final_url}")
                return None

            # Wait for recipe content to render
            await page.wait_for_selector("h1", timeout=10000)

            # Extract title
            title = await page.text_content("h1") or "Untitled Recipe"
            title = title.strip()

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

            # Extract prep/cook time and servings from meta info
            meta_info = await self._extract_meta(page)

            # Extract ingredients
            ingredients = await self._extract_ingredients(page)

            # Extract method steps
            method = await self._extract_method(page)

            # Extract nutrition
            nutrition = await self._extract_nutrition(page)

            # Build structured markdown
            content = self._format_recipe(
                title=title,
                url=canonical_url,
                meta=meta_info,
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
                    "servings": meta_info.get("servings", ""),
                    "cook_time": meta_info.get("cook_time", ""),
                    "prep_time": meta_info.get("prep_time", ""),
                },
            )

        except Exception as e:
            logger.warning(f"Failed to scrape Gousto recipe {url}: {e}")
            return None

    async def _extract_meta(self, page) -> dict:
        """Extract cooking time, servings, difficulty from recipe page."""
        meta = {}
        try:
            # Gousto renders meta info in various elements — try common selectors
            page_text = await page.text_content("body") or ""

            # Servings
            servings_match = re.search(r"(\d+)\s*(?:serving|person|people)", page_text, re.I)
            if servings_match:
                meta["servings"] = servings_match.group(1)

            # Cook time
            time_match = re.search(r"(\d+)\s*min(?:ute)?s?", page_text, re.I)
            if time_match:
                meta["cook_time"] = f"{time_match.group(1)} mins"

            # Difficulty
            for level in ["easy", "medium", "hard"]:
                if level in page_text.lower():
                    meta["difficulty"] = level.capitalize()
                    break

        except Exception as e:
            logger.debug(f"Meta extraction failed: {e}")
        return meta

    async def _extract_ingredients(self, page) -> list[str]:
        """Extract ingredients list."""
        ingredients = []
        try:
            # Try common ingredient selectors
            for selector in [
                "[data-testid='ingredients'] li",
                ".ingredients li",
                "[class*='ingredient'] li",
                "[class*='Ingredient'] li",
            ]:
                elements = await page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        text = (await el.text_content() or "").strip()
                        if text:
                            ingredients.append(text)
                    break

            # Fallback: look for an ingredients section by heading
            if not ingredients:
                ingredients = await self._extract_section_items(page, "ingredient")

        except Exception as e:
            logger.debug(f"Ingredient extraction failed: {e}")
        return ingredients

    async def _extract_method(self, page) -> list[str]:
        """Extract method/instruction steps."""
        steps = []
        try:
            for selector in [
                "[data-testid='method'] li",
                "[data-testid='instructions'] li",
                ".method li",
                "[class*='method'] li",
                "[class*='instruction'] li",
                "[class*='Method'] li",
            ]:
                elements = await page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        text = (await el.text_content() or "").strip()
                        if text:
                            steps.append(text)
                    break

            if not steps:
                steps = await self._extract_section_items(page, "method")

        except Exception as e:
            logger.debug(f"Method extraction failed: {e}")
        return steps

    async def _extract_nutrition(self, page) -> dict:
        """Extract nutrition information per serving."""
        nutrition = {}
        try:
            for selector in [
                "[data-testid='nutrition'] tr",
                ".nutrition tr",
                "[class*='nutrition'] tr",
                "[class*='Nutrition'] tr",
                "table tr",
            ]:
                rows = await page.query_selector_all(selector)
                if rows and len(rows) > 1:
                    for row in rows:
                        cells = await row.query_selector_all("td, th")
                        texts = []
                        for cell in cells:
                            t = (await cell.text_content() or "").strip()
                            if t:
                                texts.append(t)
                        if len(texts) >= 2:
                            nutrition[texts[0]] = texts[1]
                    if nutrition:
                        break

        except Exception as e:
            logger.debug(f"Nutrition extraction failed: {e}")
        return nutrition

    async def _extract_section_items(self, page, keyword: str) -> list[str]:
        """Fallback: find a heading containing keyword, then grab following list items."""
        items = []
        try:
            headings = await page.query_selector_all("h2, h3, h4")
            for heading in headings:
                text = (await heading.text_content() or "").lower()
                if keyword in text:
                    # Get the next sibling list
                    sibling = await heading.evaluate_handle(
                        "el => el.nextElementSibling"
                    )
                    if sibling:
                        lis = await sibling.query_selector_all("li")  # type: ignore
                        for li in lis:
                            t = (await li.text_content() or "").strip()
                            if t:
                                items.append(t)
                    break
        except Exception:
            pass
        return items

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
            meta_parts.append(f"**Servings:** {meta['servings']}")
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
