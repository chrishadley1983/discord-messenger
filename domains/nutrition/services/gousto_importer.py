"""Import Gousto recipes into Family Fuel DB.

Scrapes recipe pages from Gousto's website via Playwright,
transforms into Family Fuel format, and saves via family_fuel_service.
"""

import asyncio
import re

from logger import logger


# Nutrition key mapping: Gousto table labels → Family Fuel fields
NUTRITION_MAP = {
    "energy": "caloriesPerServing",
    "calories": "caloriesPerServing",
    "kcal": "caloriesPerServing",
    "protein": "proteinPerServing",
    "carbs": "carbsPerServing",
    "carbohydrate": "carbsPerServing",
    "carbohydrates": "carbsPerServing",
    "fat": "fatPerServing",
    "fibre": "fiberPerServing",
    "fiber": "fiberPerServing",
    "sugar": "sugarPerServing",
    "sugars": "sugarPerServing",
}


def _parse_nutrition_value(value: str) -> float:
    """Extract numeric value from nutrition string like '523kcal', '12.5g'."""
    m = re.search(r"([\d.]+)", value)
    return float(m.group(1)) if m else 0


def _parse_gousto_ingredient(text: str) -> dict:
    """Parse a Gousto ingredient line into structured format.

    Gousto format: "1 red onion", "200g chicken breast", "1 tsp cumin"
    """
    text = text.strip()
    if not text:
        return {"ingredientName": text, "quantity": 0, "unit": ""}

    # Common pattern: "200g chicken breast", "1 tsp cumin", "2 cloves garlic"
    m = re.match(
        r"^([\d./½¼¾⅓⅔]+)\s*"
        r"(g|kg|ml|l|tsp|tbsp|bunch|clove|cloves|can|cans|tin|tins|pack|packs|"
        r"pinch|handful|bunch|slice|slices|stick|sticks|cm|piece|pieces)?\s*"
        r"(?:of\s+)?(.*)",
        text,
        re.IGNORECASE,
    )

    if m:
        qty_str = m.group(1)
        unit = (m.group(2) or "").strip()
        name = m.group(3).strip()

        # Parse quantity (handle fractions)
        qty = _parse_fraction(qty_str)

        if not name:
            name = text

        return {
            "ingredientName": name,
            "quantity": qty,
            "unit": unit,
        }

    # No quantity match — treat as a plain ingredient name
    return {"ingredientName": text, "quantity": 0, "unit": ""}


def _parse_fraction(s: str) -> float:
    """Parse a quantity string that may contain fractions."""
    s = s.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    s = s.replace("⅓", ".333").replace("⅔", ".667")
    try:
        if "/" in s:
            parts = s.split("/")
            return float(parts[0]) / float(parts[1])
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0


def _parse_time_mins(time_str: str) -> int:
    """Parse a time string like '30 mins', '1 hour', '1hr 30' into minutes."""
    if not time_str:
        return 0
    total = 0
    hours = re.search(r"(\d+)\s*(?:hour|hr)", time_str, re.I)
    mins = re.search(r"(\d+)\s*(?:min|m\b)", time_str, re.I)
    if hours:
        total += int(hours.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    if not hours and not mins:
        # Try bare number
        m = re.search(r"(\d+)", time_str)
        if m:
            total = int(m.group(1))
    return total


async def scrape_and_save_gousto_recipe(
    recipe_url: str,
    recipe_name: str = "",
) -> dict | None:
    """Scrape a Gousto recipe page and save to Family Fuel.

    Args:
        recipe_url: Gousto cookbook URL (e.g. https://www.gousto.co.uk/cookbook/chicken-fajitas)
        recipe_name: Fallback name if page extraction fails

    Returns:
        Created recipe dict with id, or None if failed.
    """

    def _scrape(url: str) -> dict | None:
        """Sync Playwright scraping — run via asyncio.to_thread."""
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Check for 404
            title = page.text_content("h1") or ""
            if "oh crumbs" in title.lower():
                logger.info(f"Gousto 404 for {url}")
                page.close()
                browser.close()
                return None

            title = title.strip() or recipe_name

            # Extract meta
            body_text = page.text_content("body") or ""
            servings = 2  # Gousto default
            servings_match = re.search(r"(\d+)\s*(?:serving|person|people)", body_text, re.I)
            if servings_match:
                servings = int(servings_match.group(1))

            cook_time_str = ""
            time_match = re.search(r"(\d+)\s*min(?:ute)?s?", body_text, re.I)
            if time_match:
                cook_time_str = time_match.group(0)

            # Extract ingredients
            ingredients_raw = []
            for selector in [
                "[data-testid='ingredients'] li",
                ".ingredients li",
                "[class*='ingredient'] li",
                "[class*='Ingredient'] li",
            ]:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        text = (el.text_content() or "").strip()
                        if text:
                            ingredients_raw.append(text)
                    break

            # Fallback: look for ingredient heading
            if not ingredients_raw:
                ingredients_raw = _extract_section_from_page(page, "ingredient")

            # Extract method
            method_raw = []
            for selector in [
                "[data-testid='method'] li",
                "[data-testid='instructions'] li",
                ".method li",
                "[class*='method'] li",
                "[class*='instruction'] li",
            ]:
                elements = page.query_selector_all(selector)
                if elements:
                    for el in elements:
                        text = (el.text_content() or "").strip()
                        if text:
                            method_raw.append(text)
                    break

            if not method_raw:
                method_raw = _extract_section_from_page(page, "method")

            # Extract nutrition
            nutrition = {}
            for selector in [
                "[data-testid='nutrition'] tr",
                ".nutrition tr",
                "[class*='nutrition'] tr",
                "table tr",
            ]:
                rows = page.query_selector_all(selector)
                if rows and len(rows) > 1:
                    for row in rows:
                        cells = row.query_selector_all("td, th")
                        texts = [(c.text_content() or "").strip() for c in cells if (c.text_content() or "").strip()]
                        if len(texts) >= 2:
                            nutrition[texts[0].lower()] = texts[1]
                    if nutrition:
                        break

            page.close()
            browser.close()

            return {
                "title": title,
                "url": url,
                "servings": servings,
                "cook_time_str": cook_time_str,
                "ingredients": ingredients_raw,
                "method": method_raw,
                "nutrition": nutrition,
            }

        except Exception as e:
            logger.warning(f"Failed to scrape Gousto recipe {url}: {e}")
            return None
        finally:
            p.stop()

    # Scrape the page
    scraped = await asyncio.to_thread(_scrape, recipe_url)
    if not scraped:
        return None

    # Check if recipe already exists in Family Fuel
    from domains.nutrition.services.family_fuel_service import search_recipes, create_recipe

    existing = await search_recipes(query=scraped["title"], limit=3)
    for r in existing:
        if r.get("recipeName", "").lower() == scraped["title"].lower():
            logger.info(f"Gousto recipe '{scraped['title']}' already in Family Fuel: {r['id']}")
            return r

    # Transform to Family Fuel format
    cook_mins = _parse_time_mins(scraped["cook_time_str"])

    # Map nutrition
    recipe_data = {
        "recipeName": scraped["title"],
        "servings": scraped["servings"],
        "cookTimeMinutes": cook_mins,
        "totalTimeMinutes": cook_mins,
        "cuisineType": "",
        "mealType": ["dinner"],
        "recipeSource": "Gousto",
        "sourceUrl": scraped["url"],
        "containsMeat": True,  # Most Gousto meals have meat
        "tags": ["gousto", "meal-kit"],
    }

    for raw_key, raw_val in scraped["nutrition"].items():
        for pattern, field in NUTRITION_MAP.items():
            if pattern in raw_key:
                recipe_data[field] = _parse_nutrition_value(raw_val)
                break

    # Parse ingredients
    ingredients = []
    for i, raw in enumerate(scraped["ingredients"]):
        parsed = _parse_gousto_ingredient(raw)
        parsed["sortOrder"] = i + 1
        if not parsed.get("quantity"):
            parsed["quantity"] = 0
        if not parsed.get("unit"):
            parsed["unit"] = ""
        ingredients.append(parsed)

    # Parse instructions
    instructions = []
    for i, step in enumerate(scraped["method"]):
        instructions.append({
            "stepNumber": i + 1,
            "instruction": step,
        })

    # Save to Family Fuel
    try:
        result = await create_recipe(recipe_data, ingredients, instructions)
        logger.info(f"Saved Gousto recipe to Family Fuel: '{scraped['title']}' (id={result.get('id')})")
        return result
    except Exception as e:
        logger.error(f"Failed to save Gousto recipe '{scraped['title']}' to Family Fuel: {e}")
        return None


def _extract_section_from_page(page, keyword: str) -> list[str]:
    """Find a heading containing keyword, then grab following list items."""
    items = []
    try:
        headings = page.query_selector_all("h2, h3, h4")
        for heading in headings:
            text = (heading.text_content() or "").lower()
            if keyword in text:
                sibling = heading.evaluate_handle("el => el.nextElementSibling")
                if sibling:
                    lis = sibling.query_selector_all("li")
                    for li in lis:
                        t = (li.text_content() or "").strip()
                        if t:
                            items.append(t)
                break
    except Exception:
        pass
    return items
