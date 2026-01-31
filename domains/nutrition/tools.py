"""Nutrition domain tools for Claude API."""

from domains.base import ToolDefinition
from .services import (
    insert_meal,
    insert_water,
    get_today_totals,
    get_today_meals,
    get_week_summary,
    get_steps,
    get_weight,
    get_weight_history,
    get_goals,
    update_goal,
    save_favourite,
    get_favourite,
    list_favourites,
    delete_favourite
)

TOOLS = [
    ToolDefinition(
        name="log_meal",
        description="Log a meal to the nutrition database",
        input_schema={
            "type": "object",
            "properties": {
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Type of meal"
                },
                "description": {
                    "type": "string",
                    "description": "What was eaten"
                },
                "calories": {"type": "number", "description": "Calories"},
                "protein_g": {"type": "number", "description": "Protein in grams"},
                "carbs_g": {"type": "number", "description": "Carbs in grams"},
                "fat_g": {"type": "number", "description": "Fat in grams"}
            },
            "required": ["meal_type", "description", "calories", "protein_g", "carbs_g", "fat_g"]
        },
        handler=insert_meal
    ),

    ToolDefinition(
        name="log_water",
        description="Log water intake in ml",
        input_schema={
            "type": "object",
            "properties": {
                "ml": {"type": "number", "description": "Water amount in millilitres"}
            },
            "required": ["ml"]
        },
        handler=insert_water
    ),

    ToolDefinition(
        name="get_today_totals",
        description="Get today's nutrition totals (calories, protein, carbs, fat, water) and progress vs targets",
        input_schema={"type": "object", "properties": {}},
        handler=get_today_totals
    ),

    ToolDefinition(
        name="get_today_meals",
        description="Get list of all meals logged today with times",
        input_schema={"type": "object", "properties": {}},
        handler=get_today_meals
    ),

    ToolDefinition(
        name="get_steps",
        description="Get today's step count from Garmin",
        input_schema={"type": "object", "properties": {}},
        handler=get_steps
    ),

    ToolDefinition(
        name="get_weight",
        description="Get latest weight reading from Withings",
        input_schema={"type": "object", "properties": {}},
        handler=get_weight
    ),

    ToolDefinition(
        name="get_week_summary",
        description="Get daily totals for the past 7 days",
        input_schema={"type": "object", "properties": {}},
        handler=get_week_summary
    ),

    ToolDefinition(
        name="get_weight_history",
        description="Get weight history for trend analysis. Use for daily updates and progress tracking.",
        input_schema={
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to fetch (default 30)",
                    "default": 30
                }
            }
        },
        handler=get_weight_history
    ),

    ToolDefinition(
        name="get_goals",
        description="Get current fitness goals including target weight, deadline, and daily targets",
        input_schema={"type": "object", "properties": {}},
        handler=get_goals
    ),

    ToolDefinition(
        name="update_goal",
        description="Update fitness goals. Use when Chris asks to change targets.",
        input_schema={
            "type": "object",
            "properties": {
                "target_weight_kg": {
                    "type": "number",
                    "description": "New target weight in kg"
                },
                "deadline": {
                    "type": "string",
                    "description": "New deadline in YYYY-MM-DD format"
                },
                "goal_reason": {
                    "type": "string",
                    "description": "Reason/motivation for the goal"
                },
                "calories_target": {
                    "type": "integer",
                    "description": "Daily calorie target"
                },
                "protein_target_g": {
                    "type": "integer",
                    "description": "Daily protein target in grams"
                },
                "carbs_target_g": {
                    "type": "integer",
                    "description": "Daily carbs target in grams"
                },
                "fat_target_g": {
                    "type": "integer",
                    "description": "Daily fat target in grams"
                },
                "water_target_ml": {
                    "type": "integer",
                    "description": "Daily water target in ml"
                },
                "steps_target": {
                    "type": "integer",
                    "description": "Daily steps target"
                }
            }
        },
        handler=update_goal
    ),

    ToolDefinition(
        name="save_favourite",
        description="Save a meal as a favourite/preset for quick logging later. Use when Chris says 'save this as...' or 'remember this as my usual...'",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the favourite (e.g., 'usual breakfast', 'protein shake', 'work lunch')"
                },
                "description": {
                    "type": "string",
                    "description": "What the meal contains"
                },
                "calories": {"type": "number", "description": "Calories"},
                "protein_g": {"type": "number", "description": "Protein in grams"},
                "carbs_g": {"type": "number", "description": "Carbs in grams"},
                "fat_g": {"type": "number", "description": "Fat in grams"},
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "Default meal type for this favourite"
                }
            },
            "required": ["name", "description", "calories", "protein_g", "carbs_g", "fat_g"]
        },
        handler=save_favourite
    ),

    ToolDefinition(
        name="get_favourite",
        description="Get a saved favourite meal by name. Use when Chris says 'usual breakfast', 'my protein shake', etc. Then log it with log_meal.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the favourite to retrieve"
                }
            },
            "required": ["name"]
        },
        handler=get_favourite
    ),

    ToolDefinition(
        name="list_favourites",
        description="List all saved favourite meals. Use when Chris asks 'what are my favourites?' or 'what presets do I have?'",
        input_schema={"type": "object", "properties": {}},
        handler=list_favourites
    ),

    ToolDefinition(
        name="delete_favourite",
        description="Delete a saved favourite meal",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the favourite to delete"
                }
            },
            "required": ["name"]
        },
        handler=delete_favourite
    ),
]
