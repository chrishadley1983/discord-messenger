"""Generate a landscape A4 PDF showing the weekly meal plan grid.

One column per day (Mon–Sun), with meal slots showing adults/kids text
and source tags (Gousto, Out). Today's column gets an accent highlight.

Usage (standalone):
    python scripts/generate_meal_plan_pdf.py <output.pdf> '<json_plan>'

Usage (as module):
    from scripts.generate_meal_plan_pdf import generate_meal_plan_pdf
    generate_meal_plan_pdf(path, plan)
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen.canvas import Canvas


# Layout constants — landscape A4
PAGE_W, PAGE_H = landscape(A4)
MARGIN_TOP = 18 * mm
MARGIN_BOTTOM = 12 * mm
MARGIN_LEFT = 12 * mm
MARGIN_RIGHT = 12 * mm

USABLE_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
USABLE_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM

NUM_COLS = 7
COL_GAP = 2.5 * mm
COL_W = (USABLE_W - COL_GAP * (NUM_COLS - 1)) / NUM_COLS

# Typography
TITLE_SIZE = 16
DAY_HEADER_SIZE = 10
DATE_HEADER_SIZE = 8
MEAL_LABEL_SIZE = 7
MEAL_TEXT_SIZE = 8.5
TAG_SIZE = 6.5

# Colours — matching shopping list palette
BLUE = HexColor("#2563EB")
LIGHT_BLUE = HexColor("#EFF6FF")
DARK = HexColor("#1E293B")
GREY = HexColor("#94A3B8")
LIGHT_GREY = HexColor("#F1F5F9")
UNDERLINE_COLOUR = HexColor("#CBD5E1")
TODAY_BG = HexColor("#DBEAFE")
TODAY_HEADER_BG = HexColor("#2563EB")
HEADER_BG = HexColor("#F8FAFC")
WHITE = HexColor("#FFFFFF")
GOUSTO_BG = HexColor("#F0FDF4")
GOUSTO_TEXT = HexColor("#15803D")
OUT_BG = HexColor("#FEF3C7")
OUT_TEXT = HexColor("#92400E")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float, canvas: Canvas) -> list[str]:
    """Word-wrap text to fit within max_width. Returns list of lines."""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if canvas.stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def generate_meal_plan_pdf(
    output_path: str | Path,
    plan: dict,
    title: str = None,
) -> Path:
    """Generate a landscape meal plan PDF.

    Args:
        output_path: Where to save the PDF
        plan: Full plan dict with 'items' list and 'week_start' string
        title: Optional title override (auto-generated from week_start if None)

    Returns:
        Path to the generated PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = plan.get("items", [])
    week_start = plan.get("week_start", "")

    # Parse week start for title and day dates
    try:
        ws_date = datetime.fromisoformat(week_start).date()
    except (ValueError, TypeError):
        ws_date = date.today()

    if not title:
        title = f"Meal Plan \u2014 w/c {ws_date.strftime('%d %b %Y')}"

    today = date.today()

    # Group items by date
    by_date: dict[str, list[dict]] = {}
    for item in items:
        d = item.get("date", "")
        by_date.setdefault(d, []).append(item)

    # Build 7-day grid from Monday
    days = []
    for i in range(7):
        from datetime import timedelta
        day_date = ws_date + timedelta(days=i)
        day_str = day_date.isoformat()
        meals = sorted(by_date.get(day_str, []), key=lambda m: m.get("meal_slot", 0))
        days.append({
            "date": day_date,
            "date_str": day_str,
            "day_name": DAY_NAMES[i],
            "is_today": day_date == today,
            "meals": meals,
        })

    c = Canvas(str(output_path), pagesize=landscape(A4))

    # ---- Title ----
    y = PAGE_H - MARGIN_TOP
    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.setFillColor(DARK)
    c.drawString(MARGIN_LEFT, y, title)
    y -= TITLE_SIZE + 3

    # Thin rule under title
    c.setStrokeColor(UNDERLINE_COLOUR)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, y, PAGE_W - MARGIN_RIGHT, y)
    y -= 5

    # ---- Column grid ----
    grid_top = y
    grid_bottom = MARGIN_BOTTOM
    grid_height = grid_top - grid_bottom

    # Day header height
    header_h = 22

    for col_idx, day in enumerate(days):
        x = MARGIN_LEFT + col_idx * (COL_W + COL_GAP)
        is_today = day["is_today"]

        # Column background
        if is_today:
            c.setFillColor(TODAY_BG)
        else:
            c.setFillColor(WHITE)
        c.roundRect(x, grid_bottom, COL_W, grid_height, 3, stroke=0, fill=1)

        # Column border
        c.setStrokeColor(UNDERLINE_COLOUR)
        c.setLineWidth(0.4)
        c.roundRect(x, grid_bottom, COL_W, grid_height, 3, stroke=1, fill=0)

        # Day header background
        header_y = grid_top - header_h
        if is_today:
            c.setFillColor(TODAY_HEADER_BG)
        else:
            c.setFillColor(HEADER_BG)

        # Draw header background (top of column)
        c.saveState()
        p = c.beginPath()
        r = 3
        # Top-left rounded, top-right rounded, bottom-right square, bottom-left square
        p.moveTo(x + r, grid_top)
        p.lineTo(x + COL_W - r, grid_top)
        p.arcTo(x + COL_W - 2 * r, grid_top - 2 * r, x + COL_W, grid_top, 0, 90)
        p.lineTo(x + COL_W, header_y)
        p.lineTo(x, header_y)
        p.lineTo(x, grid_top - r)
        p.arcTo(x, grid_top - 2 * r, x + 2 * r, grid_top, 90, 90)
        p.close()
        c.clipPath(p, stroke=0)
        c.rect(x, header_y, COL_W, header_h, stroke=0, fill=1)
        c.restoreState()

        # Day name
        c.setFont("Helvetica-Bold", DAY_HEADER_SIZE)
        c.setFillColor(WHITE if is_today else DARK)
        day_label = day["day_name"]
        c.drawString(x + 4, grid_top - 11, day_label)

        # Date
        c.setFont("Helvetica", DATE_HEADER_SIZE)
        c.setFillColor(WHITE if is_today else GREY)
        date_label = day["date"].strftime("%d %b")
        c.drawString(x + 4, grid_top - 20, date_label)

        # ---- Meals ----
        meal_y = header_y - 6
        text_area_w = COL_W - 8  # padding on each side

        for meal in day["meals"]:
            adults = meal.get("adults_meal", "") or ""
            kids = meal.get("kids_meal", "") or ""
            source_tag = meal.get("source_tag", "")

            # Source tag badge
            if source_tag == "gousto":
                tag_text = "GOUSTO"
                tag_bg = GOUSTO_BG
                tag_fg = GOUSTO_TEXT
            elif source_tag == "chris_out":
                tag_text = "OUT"
                tag_bg = OUT_BG
                tag_fg = OUT_TEXT
            else:
                tag_text = None
                tag_bg = None
                tag_fg = None

            # Draw source tag
            if tag_text:
                c.setFont("Helvetica-Bold", TAG_SIZE)
                tw = c.stringWidth(tag_text, "Helvetica-Bold", TAG_SIZE)
                tag_x = x + 4
                tag_y = meal_y - 1
                # Tag background pill
                c.setFillColor(tag_bg)
                c.roundRect(tag_x - 2, tag_y - 2, tw + 6, TAG_SIZE + 3, 2, stroke=0, fill=1)
                c.setFillColor(tag_fg)
                c.drawString(tag_x + 1, tag_y, tag_text)
                meal_y -= TAG_SIZE + 6

            # Adults meal
            if adults:
                same = adults.strip().lower() == kids.strip().lower() if kids else False
                label = "Everyone" if same else "Adults"

                c.setFont("Helvetica-Bold", MEAL_LABEL_SIZE)
                c.setFillColor(GREY)
                c.drawString(x + 4, meal_y, label)
                meal_y -= MEAL_LABEL_SIZE + 1

                lines = _wrap_text(adults, "Helvetica", MEAL_TEXT_SIZE, text_area_w, c)
                c.setFont("Helvetica", MEAL_TEXT_SIZE)
                c.setFillColor(DARK)
                for line in lines:
                    c.drawString(x + 4, meal_y, line)
                    meal_y -= MEAL_TEXT_SIZE + 2

                if same:
                    # Skip kids — already shown as "Everyone"
                    meal_y -= 4
                    continue

            # Kids meal
            if kids:
                meal_y -= 2
                c.setFont("Helvetica-Bold", MEAL_LABEL_SIZE)
                c.setFillColor(GREY)
                c.drawString(x + 4, meal_y, "Kids")
                meal_y -= MEAL_LABEL_SIZE + 1

                lines = _wrap_text(kids, "Helvetica", MEAL_TEXT_SIZE, text_area_w, c)
                c.setFont("Helvetica", MEAL_TEXT_SIZE)
                c.setFillColor(DARK)
                for line in lines:
                    c.drawString(x + 4, meal_y, line)
                    meal_y -= MEAL_TEXT_SIZE + 2

            # Separator between meals
            meal_y -= 4
            if meal_y > grid_bottom + 5:
                c.setStrokeColor(UNDERLINE_COLOUR)
                c.setLineWidth(0.3)
                c.line(x + 4, meal_y, x + COL_W - 4, meal_y)
                meal_y -= 4

    c.save()
    return output_path


# ---- CLI entry point ----
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_meal_plan_pdf.py <output.pdf> '<json_plan>'")
        sys.exit(1)

    out = sys.argv[1]
    plan_data = json.loads(sys.argv[2])
    result = generate_meal_plan_pdf(out, plan_data)
    print(f"PDF created: {result}")
