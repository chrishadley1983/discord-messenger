"""Generate mobile-friendly recipe card HTML pages.

Each card is a standalone HTML page deployed to hadley-recipes.surge.sh/{id}.html.
Designed for kitchen use: large text, ingredient checkboxes, step-by-step layout.
"""

from html import escape


def generate_recipe_card_html(recipe: dict, back_url: str = None) -> str:
    """Generate a standalone recipe card HTML page.

    Args:
        recipe: Full recipe dict from Family Fuel (includes ingredients, instructions)
        back_url: Optional URL to link back to (e.g., meal plan page)
    """
    name = escape(recipe.get("recipeName") or "Untitled")
    description = escape(recipe.get("description") or "")
    source = escape(recipe.get("recipeSource") or "")
    source_url = recipe.get("sourceUrl") or ""
    servings = recipe.get("servings") or ""
    prep = recipe.get("prepTimeMinutes") or 0
    cook = recipe.get("cookTimeMinutes") or 0
    total = recipe.get("totalTimeMinutes") or (prep + cook) or 0
    cuisine = escape(recipe.get("cuisineType") or "")

    # Macros
    cals = recipe.get("caloriesPerServing") or 0
    protein = recipe.get("proteinPerServing") or 0
    carbs = recipe.get("carbsPerServing") or 0
    fat = recipe.get("fatPerServing") or 0

    # Dietary flags
    flags = []
    if recipe.get("isVegetarian"):
        flags.append("Vegetarian")
    if recipe.get("isVegan"):
        flags.append("Vegan")
    if recipe.get("isDairyFree"):
        flags.append("Dairy-Free")
    if recipe.get("isGlutenFree"):
        flags.append("Gluten-Free")

    # Tags
    tags = recipe.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Ingredients
    ingredients = recipe.get("ingredients", [])
    ingredients_html = ""
    for ing in ingredients:
        ing_name = escape(ing.get("ingredientName") or "")
        qty = ing.get("quantity") or ""
        unit = escape(str(ing.get("unit") or ""))
        qty_str = ""
        if qty and float(qty) > 0:
            # Clean up quantity display
            qty_f = float(qty)
            qty_str = str(int(qty_f)) if qty_f == int(qty_f) else str(qty_f)
        if qty_str and unit:
            label = f"{qty_str}{unit} {ing_name}"
        elif qty_str:
            label = f"{qty_str} {ing_name}"
        else:
            label = ing_name

        ingredients_html += f"""
      <label class="ingredient">
        <input type="checkbox" onchange="toggleDone(this)">
        <span>{escape(label)}</span>
      </label>"""

    # Instructions
    instructions = recipe.get("instructions", [])
    steps_html = ""
    for inst in instructions:
        step_num = inst.get("stepNumber") or ""
        text = escape(inst.get("instruction") or "")
        timer = inst.get("timerMinutes")
        timer_badge = ""
        if timer:
            timer_badge = f' <span class="timer">{timer} min</span>'
        steps_html += f"""
      <div class="step">
        <div class="step-num">{step_num}</div>
        <div class="step-text">{text}{timer_badge}</div>
      </div>"""

    # Meta badges
    badges_html = ""
    if total:
        badges_html += f'<span class="badge time">{total} min</span>'
    if servings:
        badges_html += f'<span class="badge servings">{servings} servings</span>'
    if cuisine:
        badges_html += f'<span class="badge cuisine">{cuisine}</span>'
    for flag in flags:
        badges_html += f'<span class="badge dietary">{escape(flag)}</span>'

    # Macros bar
    macros_html = ""
    if cals or protein:
        macros_html = f"""
    <div class="macros">
      <div class="macro"><span class="macro-val">{cals}</span><span class="macro-label">kcal</span></div>
      <div class="macro"><span class="macro-val">{protein}g</span><span class="macro-label">protein</span></div>
      <div class="macro"><span class="macro-val">{carbs}g</span><span class="macro-label">carbs</span></div>
      <div class="macro"><span class="macro-val">{fat}g</span><span class="macro-label">fat</span></div>
    </div>"""

    # Source link
    source_html = ""
    if source:
        if source_url:
            source_html = f'<a href="{escape(source_url)}" class="source-link" target="_blank">{source}</a>'
        else:
            source_html = f'<span class="source-link">{source}</span>'

    # Back link
    back_html = ""
    if back_url:
        back_html = f'<a href="{escape(back_url)}" class="back-link">&larr; Back to meal plan</a>'

    # Rating
    rating = recipe.get("familyRating")
    rating_html = ""
    if rating:
        rating_html = f'<div class="rating">Family rating: {"&#9733;" * int(rating)}{"&#9734;" * (10 - int(rating))} ({rating}/10)</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; color: #1a1a2e; line-height: 1.5; }}
  .header {{ background: #1a1a2e; color: white; padding: 20px 16px 16px; }}
  .header h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 8px; }}
  .header .desc {{ font-size: 0.85rem; opacity: 0.8; margin-bottom: 10px; }}
  .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
  .badge {{ display: inline-block; font-size: 0.7rem; padding: 3px 10px; border-radius: 12px; font-weight: 500; }}
  .badge.time {{ background: #4f46e5; color: white; }}
  .badge.servings {{ background: #0891b2; color: white; }}
  .badge.cuisine {{ background: #7c3aed; color: white; }}
  .badge.dietary {{ background: #059669; color: white; }}
  .source-link {{ color: #93c5fd; font-size: 0.8rem; text-decoration: none; }}
  .source-link:hover {{ text-decoration: underline; }}
  .back-link {{ display: inline-block; color: #93c5fd; font-size: 0.8rem; text-decoration: none; margin-bottom: 8px; }}
  .macros {{ display: flex; gap: 0; margin: 16px 16px 0; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .macro {{ flex: 1; text-align: center; padding: 12px 4px; border-right: 1px solid #f0f0f0; }}
  .macro:last-child {{ border-right: none; }}
  .macro-val {{ display: block; font-size: 1.1rem; font-weight: 700; color: #1a1a2e; }}
  .macro-label {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px; color: #888; }}
  .section {{ max-width: 600px; margin: 16px auto; padding: 0 12px; }}
  .section-title {{ font-size: 1rem; font-weight: 700; margin-bottom: 10px; padding-left: 4px; }}
  .card {{ background: white; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .ingredient {{ display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f5f5f5; cursor: pointer; -webkit-tap-highlight-color: transparent; font-size: 0.95rem; }}
  .ingredient:last-child {{ border-bottom: none; }}
  .ingredient input {{ margin-top: 3px; width: 20px; height: 20px; accent-color: #4f46e5; flex-shrink: 0; }}
  .ingredient.done span {{ text-decoration: line-through; color: #aaa; }}
  .step {{ display: flex; gap: 14px; padding: 14px 0; border-bottom: 1px solid #f5f5f5; }}
  .step:last-child {{ border-bottom: none; }}
  .step-num {{ flex-shrink: 0; width: 28px; height: 28px; background: #4f46e5; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: 700; margin-top: 2px; }}
  .step-text {{ font-size: 0.95rem; line-height: 1.6; }}
  .timer {{ display: inline-block; background: #fef3c7; color: #92400e; font-size: 0.7rem; padding: 2px 8px; border-radius: 8px; font-weight: 600; margin-left: 4px; }}
  .rating {{ text-align: center; padding: 12px; font-size: 0.85rem; color: #666; }}
  .footer {{ text-align: center; padding: 20px; font-size: 0.75rem; color: #999; }}
</style>
</head>
<body>

<div class="header">
  {back_html}
  <h1>{name}</h1>
  {"<div class='desc'>" + description + "</div>" if description else ""}
  <div class="badges">{badges_html}</div>
  {source_html}
</div>

{macros_html}

{"<div class='section'><div class='section-title'>Ingredients</div><div class='card'>" + ingredients_html + "</div></div>" if ingredients_html else ""}

{"<div class='section'><div class='section-title'>Method</div><div class='card'>" + steps_html + "</div></div>" if steps_html else ""}

{rating_html}

<div class="footer">From Family Fuel &middot; Generated by Peter</div>

<script>
function toggleDone(cb) {{
  cb.parentElement.classList.toggle('done', cb.checked);
  // Persist checked state
  const key = 'recipe-' + location.pathname;
  const states = JSON.parse(localStorage.getItem(key) || '{{}}');
  const idx = Array.from(document.querySelectorAll('.ingredient input')).indexOf(cb);
  states[idx] = cb.checked;
  localStorage.setItem(key, JSON.stringify(states));
}}
// Restore on load
document.addEventListener('DOMContentLoaded', () => {{
  const key = 'recipe-' + location.pathname;
  const states = JSON.parse(localStorage.getItem(key) || '{{}}');
  document.querySelectorAll('.ingredient input').forEach((cb, i) => {{
    if (states[i]) {{ cb.checked = true; cb.parentElement.classList.add('done'); }}
  }});
}});
</script>
</body>
</html>"""
