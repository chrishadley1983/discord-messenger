"""Nutrition Formatters - For Peter's nutrition tracking responses.

These are Peter's most common response types and need special formatting
to look good in Discord.
Based on PETERBOT_SOUL.md templates and RESPONSE.md Section 9.
"""

import re
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class NutritionTotals:
    """Parsed nutrition totals."""
    calories: float = 0
    calories_target: float = 2100
    protein_g: float = 0
    protein_target: float = 160
    carbs_g: float = 0
    carbs_target: float = 263
    fat_g: float = 0
    fat_target: float = 70
    water_ml: float = 0
    water_target: float = 3500


@dataclass
class Meal:
    """Parsed meal entry."""
    meal_type: str
    time: str
    description: str
    calories: float
    protein_g: float = 0


def format_nutrition_summary(text: str, context: Optional[dict] = None) -> str:
    """Format nutrition summary for Discord.

    Expected output format:
    **Today's Nutrition** 🍎

    📊 **Calories:** 1,786 / 2,100 (85%)
    💪 **Protein:** 140g / 160g (87%)
    🍞 **Carbs:** 153g / 263g (58%)
    🧈 **Fat:** 68g / 70g (97%)
    💧 **Water:** 2,250ml / 3,500ml (64%)

    [Optional advice line]
    """
    # Try to parse existing nutrition data from text
    totals = parse_nutrition_totals(text)

    if totals:
        return render_nutrition_summary(totals, text)

    # If can't parse, clean up and return
    return clean_nutrition_text(text)


def format_nutrition_log(text: str, context: Optional[dict] = None) -> str:
    """Format nutrition/meal log for Discord.

    Expected output format:
    **Today's Meals** 🍽️

    ☕ **Breakfast** (8:45am) - Protein bar - 194 cals, 8g protein
    🥗 **Lunch** (12:57pm) - Chicken skewers - 734 cals, 67g protein
    🍝 **Dinner** (6:20pm) - Gammon pasta - 507 cals
    """
    # Try to parse meals from text
    meals = parse_meals(text)

    if meals:
        return render_meals_list(meals)

    # If can't parse, clean up and return
    return clean_nutrition_text(text)


def format_water_log(text: str, context: Optional[dict] = None) -> str:
    """Format water logging confirmation for Discord.

    Expected output format:
    💧 Logged 500ml

    **Progress:** 2,250ml / 3,500ml (64%)
    1,250ml to go - keep sipping!
    """
    # Try to parse water data
    ml_logged = parse_water_amount(text)
    total_ml, target_ml = parse_water_progress(text)

    if ml_logged is not None:
        return render_water_log(ml_logged, total_ml, target_ml)

    # If can't parse, clean up and return
    return clean_nutrition_text(text)


# =============================================================================
# PARSING HELPERS
# =============================================================================

def parse_nutrition_totals(text: str) -> Optional[NutritionTotals]:
    """Parse nutrition totals from text."""
    totals = NutritionTotals()
    found_any = False

    # Calories
    match = re.search(r'calories?\s*:?\s*(\d+(?:,\d+)?)\s*/\s*(\d+(?:,\d+)?)', text, re.IGNORECASE)
    if match:
        totals.calories = float(match.group(1).replace(',', ''))
        totals.calories_target = float(match.group(2).replace(',', ''))
        found_any = True
    else:
        match = re.search(r'calories?\s*:?\s*(\d+(?:,\d+)?)', text, re.IGNORECASE)
        if match:
            totals.calories = float(match.group(1).replace(',', ''))
            found_any = True

    # Protein
    match = re.search(r'protein\s*:?\s*(\d+(?:\.\d+)?)\s*g?\s*/\s*(\d+)', text, re.IGNORECASE)
    if match:
        totals.protein_g = float(match.group(1))
        totals.protein_target = float(match.group(2))
        found_any = True
    else:
        match = re.search(r'protein\s*:?\s*(\d+(?:\.\d+)?)\s*g', text, re.IGNORECASE)
        if match:
            totals.protein_g = float(match.group(1))
            found_any = True

    # Carbs
    match = re.search(r'carbs?\s*:?\s*(\d+(?:\.\d+)?)\s*g?\s*/\s*(\d+)', text, re.IGNORECASE)
    if match:
        totals.carbs_g = float(match.group(1))
        totals.carbs_target = float(match.group(2))
        found_any = True
    else:
        match = re.search(r'carbs?\s*:?\s*(\d+(?:\.\d+)?)\s*g', text, re.IGNORECASE)
        if match:
            totals.carbs_g = float(match.group(1))
            found_any = True

    # Fat
    match = re.search(r'fat\s*:?\s*(\d+(?:\.\d+)?)\s*g?\s*/\s*(\d+)', text, re.IGNORECASE)
    if match:
        totals.fat_g = float(match.group(1))
        totals.fat_target = float(match.group(2))
        found_any = True
    else:
        match = re.search(r'fat\s*:?\s*(\d+(?:\.\d+)?)\s*g', text, re.IGNORECASE)
        if match:
            totals.fat_g = float(match.group(1))
            found_any = True

    # Water
    match = re.search(r'water\s*:?\s*(\d+(?:,\d+)?)\s*ml\s*/\s*(\d+(?:,\d+)?)', text, re.IGNORECASE)
    if match:
        totals.water_ml = float(match.group(1).replace(',', ''))
        totals.water_target = float(match.group(2).replace(',', ''))
        found_any = True
    else:
        match = re.search(r'water\s*:?\s*(\d+(?:,\d+)?)\s*ml', text, re.IGNORECASE)
        if match:
            totals.water_ml = float(match.group(1).replace(',', ''))
            found_any = True

    return totals if found_any else None


def parse_meals(text: str) -> list[Meal]:
    """Parse meal entries from text."""
    meals = []

    # Pattern: meal_type (time) - description - calories, protein
    pattern = re.compile(
        r'(?:☕|🥗|🍝|🥣|🍽️)?\s*\*?\*?'
        r'(breakfast|lunch|dinner|snack)\*?\*?\s*'
        r'\((\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\)\s*[-–]\s*'
        r'([^-–\n]+?)[-–]\s*'
        r'(\d+)\s*(?:cals?|calories?)'
        r'(?:,?\s*(\d+)\s*g?\s*protein)?',
        re.IGNORECASE
    )

    for match in pattern.finditer(text):
        meals.append(Meal(
            meal_type=match.group(1).lower(),
            time=match.group(2),
            description=match.group(3).strip(),
            calories=float(match.group(4)),
            protein_g=float(match.group(5)) if match.group(5) else 0
        ))

    return meals


def parse_water_amount(text: str) -> Optional[float]:
    """Parse the amount of water logged."""
    match = re.search(r'logged\s*(\d+(?:,\d+)?)\s*ml', text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def parse_water_progress(text: str) -> tuple[Optional[float], Optional[float]]:
    """Parse water progress (total, target)."""
    match = re.search(r'(\d+(?:,\d+)?)\s*(?:ml)?\s*/\s*(\d+(?:,\d+)?)\s*ml', text, re.IGNORECASE)
    if match:
        return (
            float(match.group(1).replace(',', '')),
            float(match.group(2).replace(',', ''))
        )
    return None, None


# =============================================================================
# RENDERING HELPERS
# =============================================================================

def render_nutrition_summary(totals: NutritionTotals, original_text: str = '') -> str:
    """Render nutrition summary in Discord format."""

    def pct(value: float, target: float) -> int:
        return int(value / target * 100) if target > 0 else 0

    def indicator(value: float, target: float) -> str:
        p = pct(value, target)
        if p >= 95 and p <= 105:
            return ' ✅'
        elif p > 105:
            return ' ⚠️'
        return ''

    lines = [
        "**Today's Nutrition** 🍎",
        "",
        f"📊 **Calories:** {int(totals.calories):,} / {int(totals.calories_target):,} ({pct(totals.calories, totals.calories_target)}%){indicator(totals.calories, totals.calories_target)}",
        f"💪 **Protein:** {int(totals.protein_g)}g / {int(totals.protein_target)}g ({pct(totals.protein_g, totals.protein_target)}%){indicator(totals.protein_g, totals.protein_target)}",
        f"🍞 **Carbs:** {int(totals.carbs_g)}g / {int(totals.carbs_target)}g ({pct(totals.carbs_g, totals.carbs_target)}%)",
        f"🧈 **Fat:** {int(totals.fat_g)}g / {int(totals.fat_target)}g ({pct(totals.fat_g, totals.fat_target)}%){indicator(totals.fat_g, totals.fat_target)}",
        f"💧 **Water:** {int(totals.water_ml):,}ml / {int(totals.water_target):,}ml ({pct(totals.water_ml, totals.water_target)}%)",
    ]

    # Add advice if present in original text
    advice = extract_advice(original_text)
    if advice:
        lines.extend(["", advice])

    return '\n'.join(lines)


def render_meals_list(meals: list[Meal]) -> str:
    """Render meals list in Discord format."""
    emoji_map = {
        'breakfast': '☕',
        'lunch': '🥗',
        'dinner': '🍝',
        'snack': '🥣',
    }

    lines = ["**Today's Meals** 🍽️", ""]

    for meal in meals:
        emoji = emoji_map.get(meal.meal_type, '🍽️')
        meal_type = meal.meal_type.capitalize()
        protein_str = f", {int(meal.protein_g)}g protein" if meal.protein_g > 0 else ""
        lines.append(
            f"{emoji} **{meal_type}** ({meal.time}) - {meal.description} - {int(meal.calories)} cals{protein_str}"
        )

    return '\n'.join(lines)


def render_water_log(ml_logged: float, total_ml: Optional[float], target_ml: Optional[float]) -> str:
    """Render water log confirmation in Discord format."""
    lines = [f"💧 Logged {int(ml_logged)}ml"]

    if total_ml is not None and target_ml is not None:
        pct = int(total_ml / target_ml * 100) if target_ml > 0 else 0
        remaining = max(0, target_ml - total_ml)
        lines.extend([
            "",
            f"**Progress:** {int(total_ml):,}ml / {int(target_ml):,}ml ({pct}%)",
            f"{int(remaining):,}ml to go - keep sipping!" if remaining > 0 else "Target reached! 🎉"
        ])

    return '\n'.join(lines)


def extract_advice(text: str) -> str:
    """Extract any advice/recommendation from text."""
    # Look for sentences with advice patterns
    advice_patterns = [
        r'(?:room for|you could|try to|consider|push the|keep|great job|smashed|nailed)',
    ]

    for pattern in advice_patterns:
        match = re.search(rf'([^.!?\n]*{pattern}[^.!?\n]*[.!?])', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ''


def clean_nutrition_text(text: str) -> str:
    """Clean up nutrition text that couldn't be parsed."""
    # Remove JSON blocks
    text = re.sub(r'```json[\s\S]*?```', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# =============================================================================
# TESTING
# =============================================================================

def test_nutrition_formatters():
    """Run basic nutrition formatter tests."""
    # Test water log
    water_text = "Logged 500ml water. Progress: 2,250ml / 3,500ml (64%)"
    result = format_water_log(water_text)

    if '💧' in result and '2,250ml' in result:
        print("✓ PASS - Water log formatting")
    else:
        print("✗ FAIL - Water log formatting")
        print(f"  Result: {result}")

    # Test nutrition summary
    nutrition_text = """Today's totals:
Calories: 1,786 / 2,100
Protein: 140g / 160g
Carbs: 153g / 263g
Fat: 68g / 70g
Water: 2,250ml / 3,500ml"""

    result = format_nutrition_summary(nutrition_text)

    if '📊' in result and '💪' in result and '🍎' in result:
        print("✓ PASS - Nutrition summary formatting")
    else:
        print("✗ FAIL - Nutrition summary formatting")
        print(f"  Result: {result}")

    # Test meal parsing
    meals_text = """☕ **Breakfast** (8:45am) - Protein bar - 194 cals, 8g protein
🥗 **Lunch** (12:57pm) - Chicken skewers - 734 cals, 67g protein"""

    meals = parse_meals(meals_text)
    if len(meals) == 2 and meals[0].meal_type == 'breakfast':
        print("✓ PASS - Meal parsing")
    else:
        print("✗ FAIL - Meal parsing")
        print(f"  Found: {len(meals)} meals")

    print("\nNutrition formatter tests complete")


if __name__ == '__main__':
    test_nutrition_formatters()
