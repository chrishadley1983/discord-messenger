"""Extract structured recipe data from web pages via Chrome CDP.

Connects to an existing Chrome instance (port 9222) to access paywalled
sites like NYT Cooking using Chris's logged-in session.

Primary extraction: Schema.org JSON-LD (@type: Recipe) — used by NYT Cooking,
BBC Good Food, Jamie Oliver, Mob Kitchen, AllRecipes, and most recipe sites.
"""

import asyncio
import json
import re

from logger import logger

CDP_ENDPOINT = "http://localhost:9222"


def _parse_iso_duration(duration: str) -> int | None:
    """Parse ISO 8601 duration (PT20M, PT1H30M) to minutes."""
    if not duration:
        return None
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes if (hours or minutes) else None


def _parse_nutrition_value(value: str | None) -> int | None:
    """Extract numeric value from nutrition string like '652 calories' or '24g'."""
    if not value:
        return None
    match = re.match(r"([\d.]+)", str(value))
    if match:
        return int(float(match.group(1)))
    return None


def _parse_yield(recipe_yield) -> int | None:
    """Parse recipeYield which can be a string, int, or list."""
    if recipe_yield is None:
        return None
    if isinstance(recipe_yield, int):
        return recipe_yield
    if isinstance(recipe_yield, list):
        recipe_yield = recipe_yield[0] if recipe_yield else None
    if isinstance(recipe_yield, str):
        match = re.search(r"(\d+)", recipe_yield)
        if match:
            return int(match.group(1))
    return None


def _parse_ingredient(text: str) -> dict:
    """Parse a free-text ingredient string into structured data.

    Handles patterns like:
    - '500g chicken breast'
    - '2 tbsp olive oil'
    - '1/2 tsp salt'
    - '3 large onions, sliced'
    """
    text = text.strip()

    # Common unit patterns
    unit_pattern = r"(?:g|kg|ml|l|litre|litres|oz|lb|cup|cups|tbsp|tsp|tablespoon|tablespoons|teaspoon|teaspoons|bunch|bunches|handful|handfuls|pinch|clove|cloves|slice|slices|piece|pieces|can|cans|tin|tins|pack|packs|packet|packets|cm|inch|inches|small|medium|large|x)"

    # Try: number + unit + ingredient
    match = re.match(
        rf"^([\d./½¼¾⅓⅔]+(?:\s*[-–]\s*[\d./½¼¾⅓⅔]+)?)\s*({unit_pattern})\s+(.+?)(?:,\s*(.+))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        qty_str = match.group(1)
        unit = match.group(2)
        name = match.group(3).strip()
        notes = match.group(4)
        return {
            "ingredientName": name,
            "quantity": _parse_quantity(qty_str),
            "unit": unit.lower(),
            "notes": notes.strip() if notes else None,
            "category": _guess_category(name),
        }

    # Try: number + ingredient (no unit)
    match = re.match(
        r"^([\d./½¼¾⅓⅔]+)\s+(.+?)(?:,\s*(.+))?$",
        text,
        re.IGNORECASE,
    )
    if match:
        qty_str = match.group(1)
        name = match.group(2).strip()
        notes = match.group(3)
        return {
            "ingredientName": name,
            "quantity": _parse_quantity(qty_str),
            "unit": "whole",
            "notes": notes.strip() if notes else None,
            "category": _guess_category(name),
        }

    # Fallback: just the name
    return {
        "ingredientName": text,
        "quantity": 0,
        "unit": "",
        "notes": None,
        "category": _guess_category(text),
    }


def _parse_quantity(qty_str: str) -> float:
    """Parse quantity string to float. Handles fractions and unicode."""
    if not qty_str:
        return 0

    # Unicode fractions
    frac_map = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 0.333, "⅔": 0.667}
    for char, val in frac_map.items():
        if char in qty_str:
            # Handle "1½" = 1.5
            rest = qty_str.replace(char, "").strip()
            return float(rest) + val if rest else val

    # Handle "1/2" style fractions
    if "/" in qty_str:
        parts = qty_str.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 0

    # Handle ranges like "2-3" — take the first value
    if "-" in qty_str or "–" in qty_str:
        qty_str = re.split(r"[-–]", qty_str)[0].strip()

    try:
        return float(qty_str)
    except ValueError:
        return 0


CATEGORY_MAP = {
    "meat": ["chicken", "beef", "pork", "lamb", "mince", "steak", "bacon", "sausage", "turkey", "duck", "ham", "chorizo"],
    "fish": ["salmon", "cod", "tuna", "prawn", "shrimp", "fish", "haddock", "mackerel", "crab", "mussel", "squid"],
    "dairy": ["milk", "cream", "cheese", "butter", "yoghurt", "yogurt", "egg", "eggs", "crème", "creme"],
    "vegetables": ["onion", "garlic", "pepper", "tomato", "carrot", "potato", "courgette", "aubergine", "spinach", "broccoli", "mushroom", "celery", "leek", "sweetcorn", "bean", "pea", "lettuce", "cucumber", "avocado", "chilli"],
    "fruit": ["lemon", "lime", "orange", "apple", "banana", "berry", "mango"],
    "carbs": ["rice", "pasta", "noodle", "bread", "flour", "tortilla", "couscous", "quinoa", "wrap"],
    "herbs & spices": ["basil", "oregano", "thyme", "rosemary", "coriander", "parsley", "cumin", "paprika", "turmeric", "ginger", "cinnamon", "chili", "cayenne", "nutmeg"],
    "condiments": ["oil", "vinegar", "soy sauce", "sauce", "ketchup", "mustard", "mayo", "honey", "stock", "paste"],
    "tinned": ["tin", "can", "chopped tomatoes", "coconut milk", "beans"],
}


def _guess_category(name: str) -> str | None:
    """Guess ingredient category from name."""
    name_lower = name.lower()
    for category, keywords in CATEGORY_MAP.items():
        for keyword in keywords:
            if keyword in name_lower:
                return category
    return None


def _extract_recipe_from_jsonld(data) -> dict | None:
    """Recursively find a Recipe object in JSON-LD data."""
    if isinstance(data, list):
        for item in data:
            result = _extract_recipe_from_jsonld(item)
            if result:
                return result
        return None

    if isinstance(data, dict):
        type_val = data.get("@type", "")
        if type_val == "Recipe" or (isinstance(type_val, list) and "Recipe" in type_val):
            return data
        # Check @graph
        if "@graph" in data:
            return _extract_recipe_from_jsonld(data["@graph"])

    return None


def _transform_recipe(jsonld: dict, source_url: str) -> dict:
    """Transform JSON-LD Recipe into Family Fuel format."""
    nutrition = jsonld.get("nutrition", {})

    # Parse ingredients
    raw_ingredients = jsonld.get("recipeIngredient", [])
    ingredients = []
    for i, text in enumerate(raw_ingredients):
        parsed = _parse_ingredient(text)
        parsed["sortOrder"] = i + 1
        ingredients.append(parsed)

    # Parse instructions
    raw_instructions = jsonld.get("recipeInstructions", [])
    instructions = []
    for i, inst in enumerate(raw_instructions):
        if isinstance(inst, dict):
            text = inst.get("text", "")
        else:
            text = str(inst)
        instructions.append({
            "stepNumber": i + 1,
            "instruction": text.strip(),
        })

    # Detect dietary flags from ingredients and keywords
    all_ing_names = " ".join(ing["ingredientName"].lower() for ing in ingredients)
    keywords = " ".join(jsonld.get("keywords", [])) if isinstance(jsonld.get("keywords"), list) else str(jsonld.get("keywords", ""))
    keywords_lower = keywords.lower()

    contains_meat = any(kw in all_ing_names for kw in ["chicken", "beef", "pork", "lamb", "mince", "bacon", "sausage", "turkey", "duck", "ham"])
    contains_seafood = any(kw in all_ing_names for kw in ["salmon", "cod", "tuna", "prawn", "shrimp", "fish", "crab", "mussel"])

    prep_mins = _parse_iso_duration(jsonld.get("prepTime"))
    cook_mins = _parse_iso_duration(jsonld.get("cookTime"))
    total_mins = _parse_iso_duration(jsonld.get("totalTime"))
    if not total_mins and (prep_mins or cook_mins):
        total_mins = (prep_mins or 0) + (cook_mins or 0)

    # Extract cuisine from keywords or category
    cuisine = jsonld.get("recipeCuisine")
    if isinstance(cuisine, list):
        cuisine = cuisine[0] if cuisine else None

    # Extract meal type from category
    category = jsonld.get("recipeCategory")
    meal_type = None
    if category:
        if isinstance(category, list):
            meal_type = [c.lower() for c in category]
        else:
            meal_type = [category.lower()]

    # Parse source domain for recipeSource
    source = "Web"
    if "nytimes.com" in source_url or "cooking.nytimes" in source_url:
        source = "NYT Cooking"
    elif "bbcgoodfood.com" in source_url:
        source = "BBC Good Food"
    elif "jamieoliver.com" in source_url:
        source = "Jamie Oliver"
    elif "mobkitchen.co.uk" in source_url:
        source = "Mob Kitchen"
    elif "allrecipes" in source_url:
        source = "AllRecipes"
    elif "deliciousmagazine" in source_url:
        source = "Delicious Magazine"
    elif "gousto.co.uk" in source_url:
        source = "Gousto"

    # Build tags from keywords
    tags = []
    if isinstance(jsonld.get("keywords"), str):
        tags = [k.strip().lower() for k in jsonld["keywords"].split(",") if k.strip()][:10]
    elif isinstance(jsonld.get("keywords"), list):
        tags = [k.lower() for k in jsonld["keywords"]][:10]

    recipe = {
        "recipeName": jsonld.get("name", "Unknown Recipe"),
        "description": jsonld.get("description"),
        "servings": _parse_yield(jsonld.get("recipeYield")),
        "prepTimeMinutes": prep_mins,
        "cookTimeMinutes": cook_mins,
        "totalTimeMinutes": total_mins,
        "cuisineType": cuisine,
        "mealType": meal_type,
        "caloriesPerServing": _parse_nutrition_value(nutrition.get("calories")),
        "proteinPerServing": _parse_nutrition_value(nutrition.get("proteinContent")),
        "carbsPerServing": _parse_nutrition_value(nutrition.get("carbohydrateContent")),
        "fatPerServing": _parse_nutrition_value(nutrition.get("fatContent")),
        "fiberPerServing": _parse_nutrition_value(nutrition.get("fiberContent")),
        "sugarPerServing": _parse_nutrition_value(nutrition.get("sugarContent")),
        "isVegetarian": "vegetarian" in keywords_lower and not contains_meat,
        "isVegan": "vegan" in keywords_lower,
        "isDairyFree": "dairy-free" in keywords_lower or "dairy free" in keywords_lower,
        "isGlutenFree": "gluten-free" in keywords_lower or "gluten free" in keywords_lower,
        "containsMeat": contains_meat,
        "containsSeafood": contains_seafood,
        "freezable": "freezable" in keywords_lower or "freeze" in keywords_lower,
        "tags": tags,
        "recipeSource": source,
        "sourceUrl": source_url,
        "ingredients": ingredients,
        "instructions": instructions,
    }

    return recipe


def _extract_from_page(url: str) -> dict:
    """Connect to Chrome via CDP, navigate to URL, extract recipe data."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
        ctx = browser.contexts[0]
        page = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # Wait a moment for any dynamic content
            page.wait_for_timeout(1500)

            # Extract all JSON-LD scripts
            scripts = page.query_selector_all('script[type="application/ld+json"]')

            for script in scripts:
                content = script.inner_text()
                try:
                    data = json.loads(content)
                    recipe = _extract_recipe_from_jsonld(data)
                    if recipe:
                        logger.info(f"Extracted recipe '{recipe.get('name')}' from {url}")
                        return _transform_recipe(recipe, url)
                except json.JSONDecodeError:
                    continue

            raise ValueError(f"No Recipe JSON-LD found on {url}")

        finally:
            page.close()
            browser.close()


async def extract_recipe(url: str) -> dict:
    """Extract structured recipe data from a URL using Chrome CDP.

    Returns a dict ready to POST to /recipes (Family Fuel format).
    """
    return await asyncio.to_thread(_extract_from_page, url)
