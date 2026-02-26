"""Generate a printable shopping list PDF.

A4, 2-column layout with blue category headers, underlines, and checkboxes.

Usage (standalone):
    python scripts/generate_shopping_list.py <output.pdf> '<json_categories>' [title]

Usage (as module):
    from scripts.generate_shopping_list import generate_shopping_list_pdf
    generate_shopping_list_pdf(path, categories, title="Shopping List")
"""

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas


# Layout constants
PAGE_W, PAGE_H = A4
MARGIN_TOP = 20 * mm
MARGIN_BOTTOM = 15 * mm
MARGIN_LEFT = 15 * mm
MARGIN_RIGHT = 15 * mm
COL_GAP = 10 * mm

USABLE_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT
COL_W = (USABLE_W - COL_GAP) / 2

# Typography
TITLE_SIZE = 18
CATEGORY_SIZE = 12
ITEM_SIZE = 10
LINE_HEIGHT = ITEM_SIZE + 6
CATEGORY_HEADER_HEIGHT = 10 + 4 + ITEM_SIZE + 4  # gap_before + descender + underline_to_item
CATEGORY_GAP_BEFORE = 10
DESCENDER_CLEAR = 4
UNDERLINE_TO_ITEM = ITEM_SIZE + 4

# Colours
BLUE = HexColor("#2563EB")
DARK = HexColor("#1E293B")
GREY = HexColor("#94A3B8")
UNDERLINE_COLOUR = HexColor("#CBD5E1")

CHECKBOX_SIZE = 3.2 * mm


def _draw_checkbox(c: Canvas, x: float, y: float):
    """Draw a small empty checkbox square."""
    c.setStrokeColor(GREY)
    c.setLineWidth(0.6)
    c.rect(x, y, CHECKBOX_SIZE, CHECKBOX_SIZE, stroke=1, fill=0)


def _category_height(num_items: int) -> float:
    """Total vertical space a category group needs."""
    return CATEGORY_HEADER_HEIGHT + num_items * LINE_HEIGHT


def _draw_category(c: Canvas, x: float, y: float, cat_name: str, items: list[str]) -> float:
    """Draw a category header + items, return the new y position."""
    y -= CATEGORY_GAP_BEFORE

    # Header text
    c.setFont("Helvetica-Bold", CATEGORY_SIZE)
    c.setFillColor(BLUE)
    c.drawString(x, y, cat_name)
    y -= DESCENDER_CLEAR

    # Underline
    c.setStrokeColor(BLUE)
    c.setLineWidth(0.8)
    c.line(x, y, x + COL_W - 5, y)
    y -= UNDERLINE_TO_ITEM

    # Items
    for item in items:
        _draw_checkbox(c, x, y - 1)
        c.setFont("Helvetica", ITEM_SIZE)
        c.setFillColor(DARK)
        c.drawString(x + CHECKBOX_SIZE + 3 * mm, y, item)
        y -= LINE_HEIGHT

    return y


def generate_shopping_list_pdf(
    output_path: str | Path,
    categories: dict[str, list[str]],
    title: str = "Shopping List",
) -> Path:
    """Generate the PDF and return the output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = Canvas(str(output_path), pagesize=A4)

    # ---- Title ----
    y_start = PAGE_H - MARGIN_TOP
    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.setFillColor(DARK)
    c.drawString(MARGIN_LEFT, y_start, title)
    y_start -= TITLE_SIZE + 6

    # Thin rule under title
    c.setStrokeColor(UNDERLINE_COLOUR)
    c.setLineWidth(0.5)
    c.line(MARGIN_LEFT, y_start, PAGE_W - MARGIN_RIGHT, y_start)
    y_start -= 6

    # ---- Pre-calculate heights per category ----
    cat_groups: list[tuple[str, list[str], float]] = []
    for cat_name, items in categories.items():
        h = _category_height(len(items))
        cat_groups.append((cat_name, items, h))

    total_height = sum(h for _, _, h in cat_groups)
    col_space = y_start - MARGIN_BOTTOM

    # ---- Decide column split ----
    # If everything fits in one column, use one column (centred or left-aligned)
    if total_height <= col_space:
        # Single column — render everything in column 1
        y = y_start
        for cat_name, items, _ in cat_groups:
            y = _draw_category(c, MARGIN_LEFT, y, cat_name, items)
    else:
        # Two columns — find the best split point at a category boundary
        target = total_height / 2
        cumulative = 0.0
        split_idx = len(cat_groups)

        for i, (_, _, h) in enumerate(cat_groups):
            cumulative += h
            if cumulative >= target:
                # Pick whichever split is closer to balanced
                over = cumulative - target
                under = target - (cumulative - h)
                if i == 0:
                    split_idx = 1  # never put everything in col 2
                elif under <= over:
                    split_idx = i
                else:
                    split_idx = i + 1
                break

        col1_groups = cat_groups[:split_idx]
        col2_groups = cat_groups[split_idx:]

        # Render column 1
        col1_x = MARGIN_LEFT
        y = y_start
        for cat_name, items, _ in col1_groups:
            y = _draw_category(c, col1_x, y, cat_name, items)

        # Render column 2
        col2_x = MARGIN_LEFT + COL_W + COL_GAP
        y = y_start
        for cat_name, items, _ in col2_groups:
            y = _draw_category(c, col2_x, y, cat_name, items)

    c.save()
    return output_path


# ---- CLI entry point ----
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_shopping_list.py <output.pdf> '<json_categories>' [title]")
        sys.exit(1)

    out = sys.argv[1]
    cats = json.loads(sys.argv[2])
    ttl = sys.argv[3] if len(sys.argv) > 3 else "Shopping List"
    result = generate_shopping_list_pdf(out, cats, ttl)
    print(f"PDF created: {result}")
