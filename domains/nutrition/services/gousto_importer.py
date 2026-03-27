"""Import Gousto recipes into Family Fuel DB.

Scrapes recipe pages from Gousto's website via Chrome CDP,
transforms into Family Fuel format, and saves via family_fuel_service.
"""

import asyncio
import json
import re

from logger import logger


# CDP script path (Windows — called via node.exe from WSL)
CDP_SCRIPT = "C:/Users/Chris Hadley/claude-projects/chrome-cdp-skill/skills/chrome-cdp/scripts/cdp.mjs"
CDP_PORT = 9222


async def _cdp_cmd(*args: str) -> str:
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


async def _cdp_create_tab() -> str:
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


async def _cdp_close_tab(tab_id: str) -> None:
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


# Hadley family cooks for 4 — scale all recipes to this
TARGET_SERVINGS = 4


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


def _scale_ingredient_text(text: str, factor: float) -> str:
    """Scale the quantity in an ingredient string by the given factor."""
    if factor == 1.0:
        return text

    # Pattern: "ingredient x2" suffix notation
    xn = re.search(r"(x)(\d+\.?\d*)\s*$", text)
    if xn:
        old_val = float(xn.group(2))
        new_val = old_val * factor
        nice = f"{int(new_val)}" if new_val == int(new_val) else f"{new_val:.1f}".rstrip("0").rstrip(".")
        return text[:xn.start(2)] + nice + text[xn.end(2):]

    # Pattern: leading number
    m = re.match(
        r"^([\d./½¼¾⅓⅔]+)\s*"
        r"(g|kg|ml|l|tsp|tbsp|clove|cloves|can|cans|tin|tins|pack|packs|"
        r"pinch|handful|bunch|slice|slices|stick|sticks|cm|piece|pieces|pcs)?\s*(.*)",
        text, re.IGNORECASE,
    )
    if m:
        old_val = _parse_fraction(m.group(1))
        if old_val > 0:
            new_val = old_val * factor
            nice = f"{int(new_val)}" if new_val == int(new_val) else f"{new_val:.1f}".rstrip("0").rstrip(".")
            unit = m.group(2) or ""
            rest = m.group(3) or ""
            sep = "" if unit else " "
            return f"{nice}{unit}{sep}{rest}".strip()

    return text


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

    async def _scrape_cdp(url: str) -> dict | None:
        """Scrape recipe page via Chrome CDP."""
        tab_id = ""
        try:
            tab_id = await _cdp_create_tab()
            tab = tab_id[:8]
            # Force cdp.mjs daemon to rescan targets so it sees the new tab
            await asyncio.sleep(0.5)
            await _cdp_cmd("list")

            await _cdp_cmd("nav", tab, url)
            await asyncio.sleep(3)

            # Check for 404
            title = await _cdp_cmd("eval", tab, "document.querySelector('h1')?.textContent?.trim() || ''")
            if "oh crumbs" in title.lower():
                logger.info(f"Gousto 404 for {url}")
                return None

            title = title.strip() or recipe_name

            # Extract all recipe data in one eval call
            extract_js = """(function(){
var r = {bodyText: '', ingredients: [], method: [], nutrition: {}};
r.bodyText = (document.body.innerText || '').substring(0, 2000);
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
var mSels = ['[data-testid="method"] li', '[data-testid="instructions"] li', '.method li', '[class*="method"] li', '[class*="instruction"] li'];
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
var nSels = ['[data-testid="nutrition"] tr', '.nutrition tr', '[class*="nutrition"] tr', 'table tr'];
for (var i = 0; i < nSels.length; i++) {
    var rows = document.querySelectorAll(nSels[i]);
    if (rows.length > 1) {
        rows.forEach(function(row) {
            var cells = row.querySelectorAll('td, th');
            var texts = Array.from(cells).map(function(c) { return c.textContent.trim(); }).filter(Boolean);
            if (texts.length >= 2) r.nutrition[texts[0].toLowerCase()] = texts[1];
        });
        if (Object.keys(r.nutrition).length) break;
    }
}
return JSON.stringify(r);
})()"""

            result_json = await _cdp_cmd("eval", tab, extract_js)
            try:
                data = json.loads(result_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse recipe data JSON for {url}")
                data = {}

            body_text = data.get("bodyText", "")
            original_servings = 2  # Gousto default
            servings_match = re.search(r"(\d+)\s*(?:serving|person|people)", body_text, re.I)
            if servings_match:
                original_servings = int(servings_match.group(1))

            # Scale ingredients to target servings (family of 4)
            scale = TARGET_SERVINGS / original_servings if original_servings > 0 else 1.0
            ingredients_raw = data.get("ingredients", [])
            if scale != 1.0:
                ingredients_raw = [_scale_ingredient_text(ing, scale) for ing in ingredients_raw]

            cook_time_str = ""
            time_match = re.search(r"(\d+)\s*min(?:ute)?s?", body_text, re.I)
            if time_match:
                cook_time_str = time_match.group(0)

            return {
                "title": title,
                "url": url,
                "servings": TARGET_SERVINGS,
                "cook_time_str": cook_time_str,
                "ingredients": ingredients_raw,
                "method": data.get("method", []),
                "nutrition": data.get("nutrition", {}),
            }

        except Exception as e:
            logger.warning(f"Failed to scrape Gousto recipe {url}: {e}")
            return None
        finally:
            if tab_id:
                await _cdp_close_tab(tab_id)

    # Scrape the page
    scraped = await _scrape_cdp(recipe_url)
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


