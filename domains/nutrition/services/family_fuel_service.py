"""Family Fuel recipe CRUD via direct Postgres (psycopg2 + asyncio.to_thread).

Uses the same connection approach as the Second Brain seed adapter (recipes.py).
Provides create, search, and get operations for the Family Fuel Supabase project.
"""

import asyncio
import os
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras

from logger import logger

FAMILY_FUEL_DB_URL = os.getenv(
    "FAMILY_FUEL_DATABASE_URL",
    "postgresql://postgres.pocptwknyxyrtmnfnrph:Emmie2018!!!A@aws-1-eu-west-1.pooler.supabase.com:5432/postgres",
)

# Chris's userId in the Family Fuel app
FAMILY_FUEL_USER_ID = os.getenv(
    "FAMILY_FUEL_USER_ID",
    "e9bbe0e1-acca-44f9-b7ac-f3459c532d27",
)


def _get_conn():
    """Get a fresh Postgres connection."""
    return psycopg2.connect(FAMILY_FUEL_DB_URL, connect_timeout=15)


async def create_recipe(recipe_data: dict, ingredients: list[dict], instructions: list[dict]) -> dict:
    """Create a recipe with ingredients and instructions in one transaction.

    Returns the full recipe with ingredients and instructions.
    """
    def _create():
        conn = _get_conn()
        try:
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            recipe_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            # Auto-calculate totalTimeMinutes if not provided
            prep = recipe_data.get("prepTimeMinutes") or 0
            cook = recipe_data.get("cookTimeMinutes") or 0
            if not recipe_data.get("totalTimeMinutes") and (prep or cook):
                recipe_data["totalTimeMinutes"] = prep + cook

            # Auto-set isQuickMeal based on total time
            total_time = recipe_data.get("totalTimeMinutes") or 0
            is_quick = total_time > 0 and total_time <= 20

            cur.execute("""
                INSERT INTO recipes (
                    id, "userId", "recipeName", description, servings,
                    "prepTimeMinutes", "cookTimeMinutes", "totalTimeMinutes",
                    "cuisineType", "mealType", "difficultyLevel",
                    "caloriesPerServing", "proteinPerServing", "carbsPerServing",
                    "fatPerServing", "fiberPerServing", "sugarPerServing",
                    "isVegetarian", "isVegan", "isDairyFree", "isGlutenFree",
                    "containsMeat", "containsSeafood", "containsNuts",
                    "isQuickMeal", freezable, "reheatingInstructions", "leftoverInstructions",
                    "yieldsMultipleMeals", "mealsYielded",
                    tags, notes, "recipeSource", "sourceUrl",
                    "isArchived", "createdAt", "updatedAt"
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                RETURNING *
            """, (
                recipe_id,
                FAMILY_FUEL_USER_ID,
                recipe_data.get("recipeName"),
                recipe_data.get("description"),
                recipe_data.get("servings", 4),
                recipe_data.get("prepTimeMinutes"),
                recipe_data.get("cookTimeMinutes"),
                recipe_data.get("totalTimeMinutes"),
                recipe_data.get("cuisineType"),
                recipe_data.get("mealType"),
                recipe_data.get("difficultyLevel"),
                recipe_data.get("caloriesPerServing"),
                recipe_data.get("proteinPerServing"),
                recipe_data.get("carbsPerServing"),
                recipe_data.get("fatPerServing"),
                recipe_data.get("fiberPerServing"),
                recipe_data.get("sugarPerServing"),
                recipe_data.get("isVegetarian", False),
                recipe_data.get("isVegan", False),
                recipe_data.get("isDairyFree", False),
                recipe_data.get("isGlutenFree", False),
                recipe_data.get("containsMeat", False),
                recipe_data.get("containsSeafood", False),
                recipe_data.get("containsNuts", False),
                is_quick,
                recipe_data.get("freezable", False),
                recipe_data.get("reheatingInstructions"),
                recipe_data.get("leftoverInstructions"),
                recipe_data.get("yieldsMultipleMeals", False),
                recipe_data.get("mealsYielded"),
                recipe_data.get("tags"),
                recipe_data.get("notes"),
                recipe_data.get("recipeSource"),
                recipe_data.get("sourceUrl"),
                False,  # isArchived
                now,
                now,
            ))
            recipe = dict(cur.fetchone())

            # Insert ingredients
            created_ingredients = []
            for i, ing in enumerate(ingredients):
                ing_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO recipe_ingredients (
                        id, "recipeId", "ingredientName", quantity, unit,
                        category, notes, "sortOrder"
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    ing_id,
                    recipe_id,
                    ing.get("ingredientName"),
                    ing.get("quantity", 0),
                    ing.get("unit", ""),
                    ing.get("category"),
                    ing.get("notes"),
                    ing.get("sortOrder", i + 1),
                ))
                created_ingredients.append(dict(cur.fetchone()))

            # Insert instructions
            created_instructions = []
            for inst in instructions:
                inst_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO recipe_instructions (
                        id, "recipeId", "stepNumber", instruction, "timerMinutes"
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    inst_id,
                    recipe_id,
                    inst.get("stepNumber"),
                    inst.get("instruction"),
                    inst.get("timerMinutes"),
                ))
                created_instructions.append(dict(cur.fetchone()))

            conn.commit()

            recipe["ingredients"] = created_ingredients
            recipe["instructions"] = created_instructions
            return recipe

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    result = await asyncio.to_thread(_create)
    logger.info(f"Created recipe '{result.get('recipeName')}' with {len(ingredients)} ingredients, {len(instructions)} steps")
    return result


async def get_recipe(recipe_id: str) -> dict | None:
    """Get a full recipe with ingredients and instructions."""
    def _get():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cur.execute('SELECT * FROM recipes WHERE id = %s AND "isArchived" = false', (recipe_id,))
            recipe = cur.fetchone()
            if not recipe:
                return None
            recipe = dict(recipe)

            cur.execute(
                'SELECT * FROM recipe_ingredients WHERE "recipeId" = %s ORDER BY "sortOrder"',
                (recipe_id,)
            )
            recipe["ingredients"] = [dict(r) for r in cur.fetchall()]

            cur.execute(
                'SELECT * FROM recipe_instructions WHERE "recipeId" = %s ORDER BY "stepNumber"',
                (recipe_id,)
            )
            recipe["instructions"] = [dict(r) for r in cur.fetchall()]

            return recipe
        finally:
            conn.close()

    return await asyncio.to_thread(_get)


async def search_recipes(
    query: str = None,
    cuisine: str = None,
    meal_type: str = None,
    tags: list[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Search recipes with optional filters."""
    def _search():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            conditions = ['"isArchived" = false']
            params = []

            if query:
                conditions.append('"recipeName" ILIKE %s')
                params.append(f"%{query}%")

            if cuisine:
                conditions.append('"cuisineType" ILIKE %s')
                params.append(f"%{cuisine}%")

            if meal_type:
                conditions.append('%s = ANY("mealType")')
                params.append(meal_type)

            if tags:
                conditions.append('tags @> %s')
                params.append(tags)

            where = " AND ".join(conditions)
            params.append(limit)

            cur.execute(f"""
                SELECT id, "recipeName", "cuisineType", "mealType",
                       "prepTimeMinutes", "cookTimeMinutes", "totalTimeMinutes",
                       servings, "caloriesPerServing", "proteinPerServing",
                       "carbsPerServing", "fatPerServing",
                       "familyRating", "timesUsed", "isFavorite",
                       "isVegetarian", "isVegan", "isDairyFree", "isGlutenFree",
                       "containsMeat", "containsSeafood", freezable,
                       tags, "recipeSource", "sourceUrl"
                FROM recipes
                WHERE {where}
                ORDER BY "familyRating" DESC NULLS LAST,
                         "timesUsed" DESC NULLS LAST,
                         "createdAt" DESC
                LIMIT %s
            """, params)

            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    return await asyncio.to_thread(_search)


async def search_batch_friendly_recipes(limit: int = 10) -> list[dict]:
    """Search for batch-cook-friendly recipes (freezable or yields multiple meals)."""
    def _search():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT id, "recipeName", "cuisineType", "prepTimeMinutes", "cookTimeMinutes",
                       "servings", "caloriesPerServing", "proteinPerServing",
                       "freezable", "yieldsMultipleMeals", "mealsYielded",
                       "familyRating", "timesUsed", "lastUsedDate",
                       "reheatingInstructions", "leftoverInstructions"
                FROM recipes
                WHERE "isArchived" = false
                  AND ("freezable" = true OR "yieldsMultipleMeals" = true)
                  AND "userId" = %s
                ORDER BY "familyRating" DESC NULLS LAST, "timesUsed" DESC
                LIMIT %s
            """, (FAMILY_FUEL_USER_ID, limit))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    return await asyncio.to_thread(_search)


async def update_recipe_usage(recipe_id: str) -> dict:
    """Increment timesUsed and set lastUsedDate to today."""
    def _update():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                UPDATE recipes
                SET "timesUsed" = COALESCE("timesUsed", 0) + 1,
                    "lastUsedDate" = NOW(),
                    "updatedAt" = NOW()
                WHERE id = %s
                RETURNING id, "recipeName", "timesUsed", "lastUsedDate"
            """, (recipe_id,))
            conn.commit()
            result = cur.fetchone()
            return dict(result) if result else None
        finally:
            conn.close()

    result = await asyncio.to_thread(_update)
    if result:
        logger.info(f"Updated usage for recipe '{result.get('recipeName')}': {result.get('timesUsed')} times")
    return result


async def update_recipe_rating(recipe_id: str, rating: int) -> dict:
    """Update the family rating for a recipe (1-10 scale)."""
    def _update():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                UPDATE recipes
                SET "familyRating" = %s, "updatedAt" = NOW()
                WHERE id = %s
                RETURNING id, "recipeName", "familyRating"
            """, (rating, recipe_id))
            conn.commit()
            result = cur.fetchone()
            return dict(result) if result else None
        finally:
            conn.close()

    return await asyncio.to_thread(_update)


async def delete_recipe(recipe_id: str) -> dict | None:
    """Delete a recipe and its ingredients/instructions (soft-delete via isArchived)."""
    def _delete():
        conn = _get_conn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                UPDATE recipes
                SET "isArchived" = true, "updatedAt" = NOW()
                WHERE id = %s AND "isArchived" = false
                RETURNING id, "recipeName"
            """, (recipe_id,))
            conn.commit()
            result = cur.fetchone()
            return dict(result) if result else None
        finally:
            conn.close()

    result = await asyncio.to_thread(_delete)
    if result:
        logger.info(f"Archived recipe '{result.get('recipeName')}'")
    return result
