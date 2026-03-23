"""Family Fuel recipe adapter.

Imports recipes from the Family Fuel (Family Meal Planner) Supabase project
into Second Brain as searchable knowledge items.

Each recipe becomes a rich markdown document with ingredients, method,
nutrition, dietary tags, and usage history — making them semantically
searchable via queries like "quick high-protein dinner" or "freezable
vegetarian batch cook".

Requires FAMILY_FUEL_DATABASE_URL env var (Postgres connection string).
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter

# Default connection string (can be overridden via config)
FAMILY_FUEL_DB_URL = os.getenv(
    "FAMILY_FUEL_DATABASE_URL",
    "postgresql://postgres.pocptwknyxyrtmnfnrph:Emmie2018!!!A@aws-1-eu-west-1.pooler.supabase.com:5432/postgres",
)

# Thread pool for sync psycopg2 calls
_executor = ThreadPoolExecutor(max_workers=2)


def _format_quantity(qty: float, unit: str) -> str:
    """Format ingredient quantity nicely (e.g. 1.0 -> '1', 0.5 -> '1/2')."""
    if qty == int(qty):
        return f"{int(qty)} {unit}".strip()
    # Common fractions
    fracs = {0.25: "1/4", 0.33: "1/3", 0.5: "1/2", 0.67: "2/3", 0.75: "3/4"}
    for val, label in fracs.items():
        if abs(qty - val) < 0.02:
            return f"{label} {unit}".strip()
    return f"{qty:.1f} {unit}".strip()


@register_adapter
class RecipeAdapter(SeedAdapter):
    """Import recipes from Family Fuel into Second Brain."""

    name = "family-fuel-recipes"
    description = "Import recipes from Family Fuel meal planner"
    source_system = "seed:familyfuel"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.db_url = (config or {}).get("database_url", FAMILY_FUEL_DB_URL)

    async def validate(self) -> tuple[bool, str]:
        try:
            import psycopg2
            def _check():
                conn = psycopg2.connect(self.db_url, connect_timeout=10)
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM recipes WHERE \"isArchived\" = false")
                count = cur.fetchone()[0]
                conn.close()
                return count
            count = await asyncio.get_event_loop().run_in_executor(_executor, _check)
            return True, f"{count} active recipes"
        except Exception as e:
            return False, f"Cannot connect to Family Fuel DB: {e}"

    async def fetch(self, limit: int = 500) -> list[SeedItem]:
        """Fetch all active recipes with ingredients and instructions."""
        try:
            import psycopg2
        except ImportError:
            logger.error("psycopg2 not installed — cannot fetch recipes")
            return []

        def _fetch_all():
            conn = psycopg2.connect(self.db_url, connect_timeout=15)
            cur = conn.cursor()

            # Fetch recipes
            cur.execute(f"""
                SELECT id, "recipeName", description, servings,
                       "prepTimeMinutes", "cookTimeMinutes", "totalTimeMinutes",
                       "cuisineType", "mealType", "difficultyLevel",
                       "caloriesPerServing", "proteinPerServing", "carbsPerServing",
                       "fatPerServing", "fiberPerServing", "sugarPerServing",
                       "isVegetarian", "isVegan", "isDairyFree", "isGlutenFree",
                       "containsMeat", "containsSeafood", "containsNuts",
                       "familyRating", "timesUsed", "lastUsedDate",
                       "isFavorite", freezable, "reheatingInstructions",
                       "leftoverInstructions", "yieldsMultipleMeals", "mealsYielded",
                       tags, notes, "recipeSource", "sourceUrl",
                       "updatedAt", "createdAt"
                FROM recipes
                WHERE "isArchived" = false
                ORDER BY "updatedAt" DESC
                LIMIT {limit}
            """)
            recipe_cols = [d[0] for d in cur.description]
            recipes = [dict(zip(recipe_cols, row)) for row in cur.fetchall()]

            if not recipes:
                conn.close()
                return []

            recipe_ids = [r["id"] for r in recipes]

            # Fetch all ingredients for these recipes
            placeholders = ",".join(["%s"] * len(recipe_ids))
            cur.execute(f"""
                SELECT "recipeId", "ingredientName", quantity, unit, category, notes, "sortOrder"
                FROM recipe_ingredients
                WHERE "recipeId" IN ({placeholders})
                ORDER BY "recipeId", "sortOrder"
            """, recipe_ids)
            ingredients_by_recipe: dict[str, list] = {}
            for row in cur.fetchall():
                rid = row[0]
                ingredients_by_recipe.setdefault(rid, []).append({
                    "name": row[1], "quantity": row[2], "unit": row[3],
                    "category": row[4], "notes": row[5],
                })

            # Fetch all instructions
            cur.execute(f"""
                SELECT "recipeId", "stepNumber", instruction, "timerMinutes"
                FROM recipe_instructions
                WHERE "recipeId" IN ({placeholders})
                ORDER BY "recipeId", "stepNumber"
            """, recipe_ids)
            instructions_by_recipe: dict[str, list] = {}
            for row in cur.fetchall():
                rid = row[0]
                instructions_by_recipe.setdefault(rid, []).append({
                    "step": row[1], "text": row[2], "timer": row[3],
                })

            conn.close()
            return recipes, ingredients_by_recipe, instructions_by_recipe

        result = await asyncio.get_event_loop().run_in_executor(_executor, _fetch_all)
        if not result:
            return []

        recipes, ingredients_by_recipe, instructions_by_recipe = result
        logger.info(f"Fetched {len(recipes)} recipes from Family Fuel")

        items = []
        for recipe in recipes:
            ingredients = ingredients_by_recipe.get(recipe["id"], [])
            instructions = instructions_by_recipe.get(recipe["id"], [])
            item = self._recipe_to_item(recipe, ingredients, instructions)
            if item:
                items.append(item)

        logger.info(f"Built {len(items)} SeedItems from recipes")
        return items

    def _recipe_to_item(self, recipe: dict, ingredients: list, instructions: list) -> SeedItem | None:
        """Convert a recipe + ingredients + instructions into a SeedItem."""
        try:
            name = recipe["recipeName"]
            recipe_id = recipe["id"]

            # Build metadata line
            meta_parts = []
            if recipe.get("cuisineType"):
                meta_parts.append(f"**Cuisine:** {recipe['cuisineType']}")
            if recipe.get("mealType"):
                meals = recipe["mealType"]
                if isinstance(meals, list):
                    meta_parts.append(f"**Meal:** {', '.join(meals)}")
                elif meals:
                    meta_parts.append(f"**Meal:** {meals}")
            if recipe.get("difficultyLevel"):
                meta_parts.append(f"**Difficulty:** {recipe['difficultyLevel']}")
            meta_line = " | ".join(meta_parts) if meta_parts else ""

            # Timing
            timing_parts = []
            if recipe.get("prepTimeMinutes"):
                timing_parts.append(f"**Prep:** {recipe['prepTimeMinutes']} min")
            if recipe.get("cookTimeMinutes"):
                timing_parts.append(f"**Cook:** {recipe['cookTimeMinutes']} min")
            total = recipe.get("totalTimeMinutes")
            if total:
                timing_parts.append(f"**Total:** {total} min")
            if recipe.get("servings"):
                timing_parts.append(f"**Servings:** {recipe['servings']}")
            timing_line = " | ".join(timing_parts) if timing_parts else ""

            # Usage & rating
            usage_parts = []
            if recipe.get("familyRating"):
                usage_parts.append(f"**Rating:** {recipe['familyRating']}/10")
            if recipe.get("timesUsed"):
                usage_parts.append(f"**Times made:** {recipe['timesUsed']}")
            if recipe.get("lastUsedDate"):
                last = recipe["lastUsedDate"]
                if isinstance(last, datetime):
                    usage_parts.append(f"**Last made:** {last.strftime('%Y-%m-%d')}")
            if recipe.get("isFavorite"):
                usage_parts.append("**Favourite**")
            usage_line = " | ".join(usage_parts) if usage_parts else ""

            # Dietary tags
            dietary = []
            if recipe.get("isVegetarian"):
                dietary.append("Vegetarian")
            if recipe.get("isVegan"):
                dietary.append("Vegan")
            if recipe.get("isDairyFree"):
                dietary.append("Dairy-Free")
            if recipe.get("isGlutenFree"):
                dietary.append("Gluten-Free")
            if recipe.get("containsMeat"):
                dietary.append("Contains Meat")
            if recipe.get("containsSeafood"):
                dietary.append("Contains Seafood")
            if recipe.get("containsNuts"):
                dietary.append("Contains Nuts")
            dietary_line = f"**Dietary:** {', '.join(dietary)}" if dietary else ""

            # Nutrition
            nutrition_parts = []
            if recipe.get("caloriesPerServing"):
                nutrition_parts.append(f"{recipe['caloriesPerServing']} cal")
            if recipe.get("proteinPerServing"):
                nutrition_parts.append(f"{recipe['proteinPerServing']}g protein")
            if recipe.get("carbsPerServing"):
                nutrition_parts.append(f"{recipe['carbsPerServing']}g carbs")
            if recipe.get("fatPerServing"):
                nutrition_parts.append(f"{recipe['fatPerServing']}g fat")
            if recipe.get("fiberPerServing"):
                nutrition_parts.append(f"{recipe['fiberPerServing']}g fibre")
            nutrition_line = f"**Nutrition (per serving):** {' | '.join(nutrition_parts)}" if nutrition_parts else ""

            # Ingredients section
            ingredients_text = ""
            if ingredients:
                lines = []
                for ing in ingredients:
                    qty_str = _format_quantity(ing["quantity"], ing["unit"]) if ing.get("quantity") else ""
                    note = f" ({ing['notes']})" if ing.get("notes") else ""
                    lines.append(f"- {qty_str} {ing['name']}{note}".strip())
                ingredients_text = "\n## Ingredients\n" + "\n".join(lines)

            # Instructions section
            instructions_text = ""
            if instructions:
                lines = []
                for inst in instructions:
                    timer = f" (timer: {inst['timer']} min)" if inst.get("timer") else ""
                    lines.append(f"{inst['step']}. {inst['text']}{timer}")
                instructions_text = "\n## Method\n" + "\n".join(lines)

            # Storage info
            storage_parts = []
            if recipe.get("freezable"):
                storage_parts.append("Freezable")
            if recipe.get("yieldsMultipleMeals"):
                meals = recipe.get("mealsYielded", "multiple")
                storage_parts.append(f"Yields {meals} meals")
            if recipe.get("leftoverInstructions"):
                storage_parts.append(f"Leftovers: {recipe['leftoverInstructions']}")
            if recipe.get("reheatingInstructions"):
                storage_parts.append(f"Reheating: {recipe['reheatingInstructions']}")
            storage_text = "\n## Storage\n" + "\n".join(f"- {s}" for s in storage_parts) if storage_parts else ""

            # Description / notes
            desc_text = ""
            if recipe.get("description"):
                desc_text = f"\n{recipe['description']}\n"
            if recipe.get("notes"):
                desc_text += f"\n**Notes:** {recipe['notes']}\n"

            # Assemble full content
            sections = [f"# {name}"]
            if meta_line:
                sections.append(meta_line)
            if timing_line:
                sections.append(timing_line)
            if usage_line:
                sections.append(usage_line)
            if dietary_line:
                sections.append(dietary_line)
            if nutrition_line:
                sections.append(nutrition_line)
            if desc_text:
                sections.append(desc_text)
            if ingredients_text:
                sections.append(ingredients_text)
            if instructions_text:
                sections.append(instructions_text)
            if storage_text:
                sections.append(storage_text)

            content = "\n".join(sections)

            # Build topics
            topics = ["recipe", "familyfuel", "cooking"]
            if recipe.get("cuisineType"):
                topics.append(recipe["cuisineType"].lower())
            if recipe.get("mealType"):
                meals = recipe["mealType"]
                if isinstance(meals, list):
                    topics.extend(m.lower() for m in meals)
                elif meals:
                    topics.append(meals.lower())
            if recipe.get("isVegetarian"):
                topics.append("vegetarian")
            if recipe.get("isVegan"):
                topics.append("vegan")
            if recipe.get("isGlutenFree"):
                topics.append("gluten-free")
            if recipe.get("freezable"):
                topics.append("batch-cook")
            if recipe.get("isFavorite"):
                topics.append("favourite")
            # Add key ingredient categories
            ingredient_categories = set()
            for ing in ingredients:
                cat = (ing.get("category") or "").lower()
                if cat and cat not in ("other", "seasoning", "pantry"):
                    ingredient_categories.add(cat)
            topics.extend(list(ingredient_categories)[:3])
            # Deduplicate
            topics = list(dict.fromkeys(topics))[:10]

            # Parse updatedAt for created_at
            created_at = recipe.get("createdAt")
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_at = None

            return SeedItem(
                title=f"Recipe: {name}",
                content=content,
                source_url=f"familyfuel://recipe/{recipe_id}",
                source_id=recipe_id,
                topics=topics,
                created_at=created_at,
                metadata={
                    "cuisine": recipe.get("cuisineType"),
                    "meal_type": recipe.get("mealType"),
                    "rating": recipe.get("familyRating"),
                    "times_used": recipe.get("timesUsed"),
                    "calories": recipe.get("caloriesPerServing"),
                    "protein": recipe.get("proteinPerServing"),
                },
                content_type="recipe",
            )

        except Exception as e:
            logger.warning(f"Failed to build SeedItem for recipe: {e}")
            return None

    def get_default_topics(self) -> list[str]:
        return ["recipe", "familyfuel", "cooking"]
