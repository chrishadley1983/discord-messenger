"""Weekly Second Brain Audit Report.

Generates a branded HTML email report auditing the quality of
Second Brain imports over the past 7 days. Covers:
- Summary stats (items added, by source, by type)
- Items grouped by category with richness scoring
- Tagging quality analysis (misclassified, generic tags)
- Flagged issues and recommendations
- Email body extraction quality

Uses the same Hadley Bricks visual style as the Amazon Delivery Report.
"""

import json
import re
import smtplib
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from logger import logger
from .db import get_items_since, get_total_active_count, get_topics_with_counts
from .types import KnowledgeItem

# ── Brand Tokens (matching delivery report) ──────────────────────────
GOLDEN_YELLOW = "#F5A623"
BRICK_ORANGE = "#E8912D"
NAVY_BLUE = "#1E3A5F"
LIGHT_YELLOW = "#FFF8E7"
CREAM = "#FFFDF7"
OFF_WHITE = "#F9FAFB"
WHITE = "#FFFFFF"
SUCCESS_GREEN = "#22C55E"
ALERT_RED = "#EF4444"
INFO_BLUE = "#3B82F6"
WARN_AMBER = "#F59E0B"
DARK_GRAY = "#1F2937"
WARM_GRAY = "#6B7280"
MEDIUM_GRAY = "#9CA3AF"
LIGHT_GRAY = "#E5E7EB"
CARD_BORDER = f"1px solid {LIGHT_GRAY}"
CARD_RADIUS = "12px"

# ── SMTP Config ──────────────────────────────────────────────────────
SMTP_CONFIG_PATH = None  # Set at runtime or use default

# ── Richness thresholds ──────────────────────────────────────────────
RICH_WORD_COUNT = 50     # Items with >= this many words are "rich"
THIN_WORD_COUNT = 20     # Items with < this many words are "thin"

# ── Known ephemeral patterns (shouldn't be stored) ───────────────────
EPHEMERAL_PATTERNS = [
    r"weather",
    r"what time",
    r"what day",
]

# ── Generic tags that indicate poor classification ───────────────────
GENERIC_TAGS = {"general", "untagged", "email"}

# ── Misclassification rules ──────────────────────────────────────────
# (tag_present, content_signal) -> expected_tag
MISCLASS_RULES = [
    # Tech newsletters tagged as purchases
    ({"purchase", "shopping"}, r"techpresso|newsletter|bulletin|digest", "news"),
    # School stuff tagged as tutorial
    ({"tutorial"}, r"school|spelling|homework|emmie|max", "school"),
    # Marketing tagged as purchases
    ({"purchase", "shopping"}, r"unsubscribe|view in browser|email preferences", "marketing"),
]


def _classify_source(item: KnowledgeItem) -> str:
    """Classify item by its data source."""
    source = item.source or ""
    if source.startswith("gmail://"):
        return "Gmail"
    if source.startswith("gcal://"):
        return "Google Calendar"
    if source.startswith("discord://"):
        return "Discord"
    if source.startswith("http"):
        return "Web"
    return "Other"


def _richness_score(item: KnowledgeItem) -> str:
    """Score item richness based on word count and content quality."""
    wc = item.word_count or 0
    if wc >= RICH_WORD_COUNT:
        return "rich"
    if wc >= THIN_WORD_COUNT:
        return "adequate"
    return "thin"


def _richness_color(score: str) -> tuple[str, str]:
    """Return (bg, text) color for richness badge."""
    if score == "rich":
        return "#DCFCE7", "#166534"
    if score == "adequate":
        return "#FEF3C7", "#92400E"
    return "#FEE2E2", "#991B1B"


def _check_tagging_issues(item: KnowledgeItem) -> list[str]:
    """Check for tagging issues on an item."""
    issues = []
    topics = set(item.topics or [])
    text = (item.full_text or item.summary or "").lower()
    title = (item.title or "").lower()
    combined = f"{title} {text}"

    # Check for overly generic tags
    if topics and topics.issubset(GENERIC_TAGS):
        issues.append("Only generic tags")

    # Check misclassification rules
    for bad_tags, content_pattern, expected in MISCLASS_RULES:
        if bad_tags & topics and re.search(content_pattern, combined, re.IGNORECASE):
            issues.append(f"Tagged as {'/'.join(bad_tags & topics)} but looks like {expected}")

    # Check for ephemeral content
    for pattern in EPHEMERAL_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            issues.append("Ephemeral content (low future value)")
            break

    return issues


async def generate_audit_data(days_back: int = 7) -> dict:
    """Generate audit data for the past N days.

    Returns dict with all audit metrics and item details.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    items = await get_items_since(since)
    total_active = await get_total_active_count()

    # Group by source
    by_source: dict[str, list[KnowledgeItem]] = {}
    for item in items:
        src = _classify_source(item)
        by_source.setdefault(src, []).append(item)

    # Group by content type
    by_type: Counter[str] = Counter()
    for item in items:
        ct = item.content_type.value if hasattr(item.content_type, "value") else str(item.content_type)
        by_type[ct] += 1

    # Group by capture type
    by_capture: Counter[str] = Counter()
    for item in items:
        ct = item.capture_type.value if hasattr(item.capture_type, "value") else str(item.capture_type)
        by_capture[ct] += 1

    # Richness analysis
    richness_counts = Counter(_richness_score(item) for item in items)
    thin_items = [item for item in items if _richness_score(item) == "thin"]

    # Tagging analysis
    all_tags: Counter[str] = Counter()
    items_with_issues: list[tuple[KnowledgeItem, list[str]]] = []
    for item in items:
        all_tags.update(item.topics or [])
        issues = _check_tagging_issues(item)
        if issues:
            items_with_issues.append((item, issues))

    # Tag diversity (how many unique tags per item on average)
    avg_tags = (
        sum(len(item.topics or []) for item in items) / len(items)
        if items else 0
    )

    # Word count stats
    word_counts = [item.word_count or 0 for item in items]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    median_words = sorted(word_counts)[len(word_counts) // 2] if word_counts else 0

    return {
        "period_start": since,
        "period_end": datetime.now(timezone.utc),
        "days_back": days_back,
        "total_items": len(items),
        "total_active": total_active,
        "items": items,
        "by_source": by_source,
        "by_type": by_type,
        "by_capture": by_capture,
        "richness": richness_counts,
        "thin_items": thin_items,
        "all_tags": all_tags,
        "items_with_issues": items_with_issues,
        "avg_tags_per_item": round(avg_tags, 1),
        "avg_words": round(avg_words),
        "median_words": median_words,
    }


def _score_badge(label: str, bg: str, color: str) -> str:
    return (
        f'<span style="background-color:{bg};color:{color};padding:4px 10px;'
        f'border-radius:4px;font-weight:500;font-size:11px;white-space:nowrap;">'
        f"{label}</span>"
    )


def _summary_card(label: str, value: str, color: str = NAVY_BLUE) -> str:
    return f"""<td width="25%" style="padding:0 6px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:{WHITE};border:{CARD_BORDER};border-radius:{CARD_RADIUS};text-align:center;">
            <tr><td style="padding:16px;text-align:center;">
                <div style="font-family:'Poppins',sans-serif;font-size:11px;color:{WARM_GRAY};font-weight:500;">{label}</div>
                <div style="font-family:'Poppins',sans-serif;font-size:28px;font-weight:700;color:{color};margin-top:6px;">{value}</div>
            </td></tr>
        </table>
    </td>"""


def _health_card(label: str, value: str, sub: str, border_color: str) -> str:
    return f"""<td width="33%" style="padding:0 6px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:{WHITE};border:{CARD_BORDER};border-radius:{CARD_RADIUS};border-top:4px solid {border_color};text-align:center;">
            <tr><td style="padding:18px 12px;text-align:center;">
                <div style="font-family:'Poppins',sans-serif;font-size:10px;color:{WARM_GRAY};font-weight:500;text-transform:uppercase;letter-spacing:0.5px;">{label}</div>
                <div style="font-family:'Poppins',sans-serif;font-size:28px;font-weight:700;color:{DARK_GRAY};margin-top:6px;">{value}</div>
                <div style="font-family:'Poppins',sans-serif;font-size:10px;color:{MEDIUM_GRAY};margin-top:4px;">{sub}</div>
            </td></tr>
        </table>
    </td>"""


def build_audit_email(data: dict) -> str:
    """Build the HTML email body for the audit report."""
    period_str = data["period_start"].strftime("%d %b") + " - " + data["period_end"].strftime("%d %b %Y")
    total = data["total_items"]
    rich = data["richness"].get("rich", 0)
    adequate = data["richness"].get("adequate", 0)
    thin = data["richness"].get("thin", 0)
    issue_count = len(data["items_with_issues"])

    # Richness percentage
    rich_pct = round((rich / total) * 100) if total else 0
    # Issue percentage
    issue_pct = round((issue_count / total) * 100) if total else 0

    # Overall health score (0-100)
    health = 100
    if total > 0:
        health -= int(issue_pct * 0.5)  # Issues penalise
        health -= int(((thin / total) * 100) * 0.3)  # Thin items penalise
        health = max(0, min(100, health))

    health_color = SUCCESS_GREEN if health >= 80 else (WARN_AMBER if health >= 60 else ALERT_RED)

    # ── Source breakdown rows ──
    source_rows = ""
    for src in ["Gmail", "Google Calendar", "Discord", "Web", "Other"]:
        items_list = data["by_source"].get(src, [])
        if not items_list:
            continue
        count = len(items_list)
        rich_in_src = sum(1 for i in items_list if _richness_score(i) == "rich")
        thin_in_src = sum(1 for i in items_list if _richness_score(i) == "thin")
        avg_wc = round(sum(i.word_count or 0 for i in items_list) / count) if count else 0
        source_rows += f"""<tr>
            <td style="padding:10px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:13px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};font-weight:600;">{src}</td>
            <td style="padding:10px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:13px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};text-align:center;">{count}</td>
            <td style="padding:10px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:13px;font-family:'Poppins',sans-serif;color:{SUCCESS_GREEN};text-align:center;">{rich_in_src}</td>
            <td style="padding:10px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:13px;font-family:'Poppins',sans-serif;color:{ALERT_RED if thin_in_src > 0 else DARK_GRAY};text-align:center;">{thin_in_src}</td>
            <td style="padding:10px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:13px;font-family:'Poppins',sans-serif;color:{WARM_GRAY};text-align:center;">{avg_wc}</td>
        </tr>"""

    # ── Items detail rows (grouped by source) ──
    # Only show items that have issues or are thin, plus a capped sample of others
    # This keeps the email under Gmail's ~102KB clip threshold
    MAX_DETAIL_PER_SOURCE = 10
    detail_rows = ""
    detail_total_shown = 0
    detail_total_omitted = 0
    for src in ["Gmail", "Google Calendar", "Discord", "Web", "Other"]:
        items_list = data["by_source"].get(src, [])
        if not items_list:
            continue

        # Prioritise: items with issues first, then thin, then the rest
        flagged = [i for i in items_list if _check_tagging_issues(i) or _richness_score(i) == "thin"]
        others = [i for i in items_list if i not in flagged]
        show = flagged + others[:max(0, MAX_DETAIL_PER_SOURCE - len(flagged))]
        omitted = len(items_list) - len(show)
        detail_total_omitted += omitted

        # Source group header
        detail_rows += f"""<tr>
            <td colspan="4" style="padding:12px 14px 6px;border-bottom:2px solid {GOLDEN_YELLOW};font-size:12px;font-family:'Poppins',sans-serif;color:{GOLDEN_YELLOW};font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">{src} ({len(items_list)})</td>
        </tr>"""
        for item in show:
            title = (item.title or "Untitled")[:55]
            if len(item.title or "") > 55:
                title += "..."
            topics = ", ".join(item.topics[:4]) if item.topics else "-"
            wc = item.word_count or 0
            rs = _richness_score(item)
            rs_bg, rs_color = _richness_color(rs)

            # Check for issues
            issues = _check_tagging_issues(item)
            issue_badge = ""
            if issues:
                issue_badge = f' <span style="background-color:#FEE2E2;color:#991B1B;padding:2px 6px;border-radius:3px;font-size:9px;">{issues[0][:30]}</span>'

            detail_rows += f"""<tr>
                <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};">{title}{issue_badge}</td>
                <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:11px;font-family:'Poppins',sans-serif;color:{WARM_GRAY};">{topics}</td>
                <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};text-align:center;">{wc}</td>
                <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};text-align:center;">{_score_badge(rs, rs_bg, rs_color)}</td>
            </tr>"""
            detail_total_shown += 1

        if omitted > 0:
            detail_rows += f"""<tr>
                <td colspan="4" style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:11px;font-family:'Poppins',sans-serif;color:{MEDIUM_GRAY};font-style:italic;">+ {omitted} more items (all rich, no issues)</td>
            </tr>"""

    # ── Top tags ──
    top_tags_html = ""
    for tag, count in data["all_tags"].most_common(15):
        is_generic = tag in GENERIC_TAGS
        tag_style = f"color:{ALERT_RED};font-weight:600;" if is_generic else f"color:{DARK_GRAY};"
        top_tags_html += f"""<tr>
            <td style="padding:6px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;{tag_style}">{tag}{"  (generic)" if is_generic else ""}</td>
            <td style="padding:6px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};text-align:center;">{count}</td>
        </tr>"""

    # ── Issues table ──
    issues_section = ""
    if data["items_with_issues"]:
        issue_rows = ""
        for item, issues in data["items_with_issues"][:15]:
            title = (item.title or "Untitled")[:45]
            if len(item.title or "") > 45:
                title += "..."
            for issue in issues:
                issue_rows += f"""<tr>
                    <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;color:{DARK_GRAY};">{title}</td>
                    <td style="padding:8px 14px;border-bottom:1px solid {LIGHT_GRAY};font-size:12px;font-family:'Poppins',sans-serif;color:{ALERT_RED};">{issue}</td>
                </tr>"""

        issues_section = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
            <tr><td style="padding:0 0 12px 0;">
                <span style="font-family:'Poppins',sans-serif;font-size:18px;font-weight:600;color:{DARK_GRAY};">Flagged issues ({issue_count})</span>
            </td></tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LIGHT_GRAY};border-radius:8px;border-collapse:separate;overflow:hidden;">
            <thead><tr style="background-color:{OFF_WHITE};">
                <th style="padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Item</th>
                <th style="padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Issue</th>
            </tr></thead>
            <tbody>{issue_rows}</tbody>
        </table>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:{CREAM};font-family:'Poppins',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:{CREAM};padding:20px 0;">
<tr><td align="center">
<table width="700" cellpadding="0" cellspacing="0" style="background-color:{WHITE};border:1px solid {LIGHT_GRAY};border-radius:12px;overflow:hidden;">

    <!-- Header -->
    <tr><td style="border-bottom:3px solid {GOLDEN_YELLOW};padding:24px 30px;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td style="vertical-align:middle;">
                    <span style="font-family:'Poppins',sans-serif;font-size:22px;font-weight:700;color:{GOLDEN_YELLOW};">Second Brain</span>
                    <span style="font-family:'Poppins',sans-serif;font-size:22px;font-weight:700;color:{DARK_GRAY};"> — Weekly audit</span>
                </td>
                <td style="vertical-align:middle;text-align:right;">
                    <span style="background-color:{LIGHT_YELLOW};border:1px solid #FDE68A;color:#92400E;padding:6px 14px;border-radius:6px;font-size:13px;font-weight:500;font-family:'Poppins',sans-serif;">{period_str}</span>
                </td>
            </tr>
        </table>
    </td></tr>

    <!-- Body -->
    <tr><td style="padding:30px;">

        <!-- Summary Cards -->
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                {_summary_card("Items added", str(total), NAVY_BLUE)}
                {_summary_card("Rich", str(rich), SUCCESS_GREEN)}
                {_summary_card("Thin", str(thin), ALERT_RED if thin > 0 else WARM_GRAY)}
                {_summary_card("Issues", str(issue_count), ALERT_RED if issue_count > 0 else WARM_GRAY)}
            </tr>
        </table>

        <!-- Health Score Cards -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;">
            <tr><td style="padding:0 0 12px 0;">
                <span style="font-family:'Poppins',sans-serif;font-size:18px;font-weight:600;color:{DARK_GRAY};">Import health</span>
            </td></tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="table-layout:fixed;">
            <tr>
                {_health_card("Health score", f"{health}%", "Overall import quality", health_color)}
                {_health_card("Avg words", str(data['avg_words']), f"Median: {data['median_words']}", INFO_BLUE)}
                {_health_card("Tags / item", str(data['avg_tags_per_item']), f"{len(data['all_tags'])} unique tags", NAVY_BLUE)}
            </tr>
        </table>

        <!-- Source Breakdown -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
            <tr><td style="padding:0 0 12px 0;">
                <span style="font-family:'Poppins',sans-serif;font-size:18px;font-weight:600;color:{DARK_GRAY};">By source</span>
            </td></tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LIGHT_GRAY};border-radius:8px;border-collapse:separate;overflow:hidden;">
            <thead><tr style="background-color:{OFF_WHITE};">
                <th style="padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Source</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Count</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Rich</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Thin</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Avg words</th>
            </tr></thead>
            <tbody>{source_rows}</tbody>
        </table>

        {issues_section}

        <!-- Top Tags -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
            <tr><td style="padding:0 0 12px 0;">
                <span style="font-family:'Poppins',sans-serif;font-size:18px;font-weight:600;color:{DARK_GRAY};">Top tags</span>
                <span style="font-family:'Poppins',sans-serif;font-size:12px;color:{WARM_GRAY};margin-left:8px;">This period only</span>
            </td></tr>
        </table>
        <table width="50%" cellpadding="0" cellspacing="0" style="border:1px solid {LIGHT_GRAY};border-radius:8px;border-collapse:separate;overflow:hidden;">
            <thead><tr style="background-color:{OFF_WHITE};">
                <th style="padding:8px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Tag</th>
                <th style="padding:8px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};">Uses</th>
            </tr></thead>
            <tbody>{top_tags_html}</tbody>
        </table>

        <!-- Items Detail (flagged + thin prioritised, capped per source) -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
            <tr><td style="padding:0 0 12px 0;">
                <span style="font-family:'Poppins',sans-serif;font-size:18px;font-weight:600;color:{DARK_GRAY};">Items detail</span>
                <span style="font-family:'Poppins',sans-serif;font-size:12px;color:{WARM_GRAY};margin-left:8px;">Showing {detail_total_shown} of {total} — flagged and thin items shown first</span>
            </td></tr>
        </table>
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LIGHT_GRAY};border-radius:8px;border-collapse:separate;overflow:hidden;">
            <thead><tr style="background-color:{OFF_WHITE};">
                <th style="padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};width:40%;">Title</th>
                <th style="padding:10px 14px;text-align:left;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};width:30%;">Topics</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};width:10%;">Words</th>
                <th style="padding:10px 14px;text-align:center;font-family:'Poppins',sans-serif;font-size:11px;font-weight:600;color:{WARM_GRAY};text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid {LIGHT_GRAY};width:20%;">Richness</th>
            </tr></thead>
            <tbody>{detail_rows}</tbody>
        </table>

    </td></tr>

    <!-- Footer -->
    <tr><td style="padding:16px 30px;background-color:{OFF_WHITE};border-top:1px solid {LIGHT_GRAY};">
        <span style="font-family:'Poppins',sans-serif;font-size:11px;color:{MEDIUM_GRAY};">
            Generated automatically by Second Brain audit monitor | {data['total_active']} total items in knowledge base
        </span>
    </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    return html


def build_full_report(data: dict) -> str:
    """Build a full HTML report for PDF conversion.

    Unlike the email version this uses a <style> block, shows ALL items
    (no cap), and is sized for A4 portrait.
    """
    period_str = data["period_start"].strftime("%d %b") + " - " + data["period_end"].strftime("%d %b %Y")
    total = data["total_items"]
    rich = data["richness"].get("rich", 0)
    adequate = data["richness"].get("adequate", 0)
    thin = data["richness"].get("thin", 0)
    issue_count = len(data["items_with_issues"])
    rich_pct = round((rich / total) * 100) if total else 0
    issue_pct = round((issue_count / total) * 100) if total else 0

    health = 100
    if total > 0:
        health -= int(issue_pct * 0.5)
        health -= int(((thin / total) * 100) * 0.3)
        health = max(0, min(100, health))
    health_color = SUCCESS_GREEN if health >= 80 else (WARN_AMBER if health >= 60 else ALERT_RED)

    # Source breakdown rows
    source_rows = ""
    for src in ["Gmail", "Google Calendar", "Discord", "Web", "Other"]:
        items_list = data["by_source"].get(src, [])
        if not items_list:
            continue
        count = len(items_list)
        rich_in_src = sum(1 for i in items_list if _richness_score(i) == "rich")
        thin_in_src = sum(1 for i in items_list if _richness_score(i) == "thin")
        avg_wc = round(sum(i.word_count or 0 for i in items_list) / count) if count else 0
        thin_class = ' class="alert"' if thin_in_src > 0 else ""
        source_rows += f"""<tr>
            <td style="font-weight:600;">{src}</td>
            <td class="center">{count}</td>
            <td class="center" style="color:{SUCCESS_GREEN};">{rich_in_src}</td>
            <td class="center"{thin_class}>{thin_in_src}</td>
            <td class="center">{avg_wc}</td>
        </tr>"""

    # Issues rows
    issue_rows = ""
    for item, issues in data["items_with_issues"]:
        title = (item.title or "Untitled")[:55]
        if len(item.title or "") > 55:
            title += "..."
        for issue in issues:
            issue_rows += f"""<tr>
                <td>{title}</td>
                <td class="alert">{issue}</td>
            </tr>"""

    # Top tags
    top_tags_rows = ""
    for tag, count in data["all_tags"].most_common(20):
        is_generic = tag in GENERIC_TAGS
        cls = ' class="alert"' if is_generic else ""
        suffix = "  (generic)" if is_generic else ""
        top_tags_rows += f"<tr><td{cls}>{tag}{suffix}</td><td class=\"center\">{count}</td></tr>"

    # ALL items detail — no cap
    detail_rows = ""
    for src in ["Gmail", "Google Calendar", "Discord", "Web", "Other"]:
        items_list = data["by_source"].get(src, [])
        if not items_list:
            continue
        detail_rows += f"""<tr>
            <td colspan="4" class="group-header">{src} ({len(items_list)})</td>
        </tr>"""
        for item in items_list:
            title = (item.title or "Untitled")[:65]
            if len(item.title or "") > 65:
                title += "..."
            topics = ", ".join(item.topics[:5]) if item.topics else "-"
            wc = item.word_count or 0
            rs = _richness_score(item)
            rs_cls = {"rich": "badge-green", "adequate": "badge-amber", "thin": "badge-red"}[rs]
            issues = _check_tagging_issues(item)
            issue_badge = ""
            if issues:
                issue_badge = f' <span class="badge-red" style="font-size:7px;">{issues[0][:25]}</span>'
            detail_rows += f"""<tr>
                <td>{title}{issue_badge}</td>
                <td style="color:{WARM_GRAY};">{topics}</td>
                <td class="center">{wc}</td>
                <td class="center"><span class="{rs_cls}">{rs}</span></td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Second Brain — Weekly Audit</title>
    <style>
        @page {{ size: A4 portrait; margin: 15mm 12mm; }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; background: {WHITE}; color: {DARK_GRAY}; font-size: 10px; line-height: 1.5; }}
        .container {{ max-width: 100%; }}
        .header {{ border-bottom: 3px solid {GOLDEN_YELLOW}; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ font-size: 18px; font-weight: 700; }}
        .header h1 .brand {{ color: {GOLDEN_YELLOW}; }}
        .date-badge {{ background: {LIGHT_YELLOW}; border: 1px solid #FDE68A; color: #92400E; padding: 4px 12px; border-radius: 6px; font-size: 10px; font-weight: 500; }}
        .content {{ padding: 14px 20px; }}
        .section {{ margin-bottom: 18px; }}
        .section-title {{ font-size: 13px; font-weight: 600; margin-bottom: 8px; }}
        .section-sub {{ font-size: 9px; color: {WARM_GRAY}; margin-bottom: 8px; }}
        .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 16px; }}
        .card {{ background: {WHITE}; border: {CARD_BORDER}; border-radius: 8px; padding: 10px 6px; text-align: center; }}
        .card-value {{ font-size: 20px; font-weight: 700; margin: 2px 0; }}
        .card-label {{ font-size: 9px; color: {WARM_GRAY}; font-weight: 500; }}
        .card-sub {{ font-size: 8px; color: {MEDIUM_GRAY}; }}
        .health-cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }}
        .health-card {{ background: {WHITE}; border: {CARD_BORDER}; border-radius: 8px; padding: 12px 6px; text-align: center; }}
        .health-card .card-value {{ font-size: 22px; }}
        .health-card .card-label {{ text-transform: uppercase; letter-spacing: 0.5px; font-size: 8px; }}
        table.data {{ width: 100%; border-collapse: collapse; font-size: 9px; table-layout: fixed; }}
        table.data thead {{ background: {OFF_WHITE}; border-bottom: 2px solid {LIGHT_GRAY}; }}
        table.data th {{ padding: 5px 6px; text-align: left; font-weight: 600; color: {WARM_GRAY}; text-transform: uppercase; letter-spacing: 0.3px; font-size: 7px; }}
        table.data td {{ padding: 4px 6px; border-bottom: 1px solid {LIGHT_GRAY}; overflow-wrap: break-word; }}
        table.data tbody tr {{ page-break-inside: avoid; }}
        .center {{ text-align: center; }}
        .alert {{ color: {ALERT_RED}; font-weight: 600; }}
        .group-header {{ padding: 8px 6px 4px !important; border-bottom: 2px solid {GOLDEN_YELLOW} !important; color: {GOLDEN_YELLOW}; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; font-size: 9px; }}
        .badge-green {{ background: #DCFCE7; color: #166534; padding: 2px 8px; border-radius: 3px; font-size: 8px; font-weight: 500; }}
        .badge-amber {{ background: #FEF3C7; color: #92400E; padding: 2px 8px; border-radius: 3px; font-size: 8px; font-weight: 500; }}
        .badge-red {{ background: #FEE2E2; color: #991B1B; padding: 2px 8px; border-radius: 3px; font-size: 8px; font-weight: 500; }}
        .footer {{ padding: 8px 20px; background: {OFF_WHITE}; border-top: 1px solid {LIGHT_GRAY}; font-size: 8px; color: {MEDIUM_GRAY}; }}
        .half {{ width: 50%; }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1><span class="brand">Second Brain</span> — Weekly audit</h1>
        <div class="date-badge">{period_str}</div>
    </div>
    <div class="content">
        <div class="section">
            <div class="cards">
                <div class="card"><div class="card-label">Items added</div><div class="card-value" style="color:{NAVY_BLUE};">{total}</div></div>
                <div class="card"><div class="card-label">Rich</div><div class="card-value" style="color:{SUCCESS_GREEN};">{rich}</div></div>
                <div class="card"><div class="card-label">Thin</div><div class="card-value" style="color:{ALERT_RED if thin > 0 else WARM_GRAY};">{thin}</div></div>
                <div class="card"><div class="card-label">Issues</div><div class="card-value" style="color:{ALERT_RED if issue_count > 0 else WARM_GRAY};">{issue_count}</div></div>
            </div>
        </div>
        <div class="section">
            <div class="section-title">Import health</div>
            <div class="health-cards">
                <div class="health-card" style="border-top:4px solid {health_color};"><div class="card-label">Health score</div><div class="card-value">{health}%</div><div class="card-sub">Overall import quality</div></div>
                <div class="health-card" style="border-top:4px solid {INFO_BLUE};"><div class="card-label">Avg words</div><div class="card-value">{data['avg_words']}</div><div class="card-sub">Median: {data['median_words']}</div></div>
                <div class="health-card" style="border-top:4px solid {NAVY_BLUE};"><div class="card-label">Tags / item</div><div class="card-value">{data['avg_tags_per_item']}</div><div class="card-sub">{len(data['all_tags'])} unique tags</div></div>
            </div>
        </div>
        <div class="section">
            <div class="section-title">By source</div>
            <table class="data">
                <thead><tr><th>Source</th><th class="center">Count</th><th class="center">Rich</th><th class="center">Thin</th><th class="center">Avg words</th></tr></thead>
                <tbody>{source_rows}</tbody>
            </table>
        </div>
        {"" if not issue_rows else f'''<div class="section">
            <div class="section-title">Flagged issues ({issue_count})</div>
            <table class="data">
                <thead><tr><th style="width:45%;">Item</th><th style="width:55%;">Issue</th></tr></thead>
                <tbody>{issue_rows}</tbody>
            </table>
        </div>'''}
        <div class="section">
            <div class="section-title">Top tags</div>
            <table class="data half">
                <thead><tr><th>Tag</th><th class="center">Uses</th></tr></thead>
                <tbody>{top_tags_rows}</tbody>
            </table>
        </div>
        <div class="section">
            <div class="section-title">All items ({total})</div>
            <table class="data">
                <thead><tr><th style="width:40%;">Title</th><th style="width:30%;">Topics</th><th class="center" style="width:10%;">Words</th><th class="center" style="width:20%;">Richness</th></tr></thead>
                <tbody>{detail_rows}</tbody>
            </table>
        </div>
    </div>
    <div class="footer">Generated automatically by Second Brain audit monitor | {data['total_active']} total items in knowledge base</div>
</div>
</body>
</html>"""
    return html


def html_to_pdf(html_content: str) -> bytes:
    """Convert HTML report to PDF bytes using Playwright CLI."""
    import subprocess
    import tempfile
    import os

    logger.info("Converting audit report to PDF via Playwright CLI")

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = os.path.join(tmpdir, "report.html")
        pdf_path = os.path.join(tmpdir, "report.pdf")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        file_url = "file:///" + html_path.replace(os.sep, "/")
        result = subprocess.run(
            f'npx playwright pdf "{file_url}" "{pdf_path}"',
            capture_output=True, text=True, timeout=60, shell=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Playwright PDF failed: {result.stderr}")

        with open(pdf_path, "rb") as f:
            return f.read()


def _load_smtp_config() -> dict:
    """Load SMTP config from the shared config file."""
    import os
    path = SMTP_CONFIG_PATH or os.path.expanduser(
        "~/.skills/skills/amazon-delivery-performance/smtp_config.json"
    )
    with open(path) as f:
        return json.load(f)


def send_audit_email(
    html_body: str,
    data: dict,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "report.pdf",
) -> None:
    """Send the audit report via Gmail SMTP with optional PDF attachment."""
    from email.mime.application import MIMEApplication

    config = _load_smtp_config()

    total = data["total_items"]
    issue_count = len(data["items_with_issues"])
    rich = data["richness"].get("rich", 0)
    rich_pct = round((rich / total) * 100) if total else 0

    subject = (
        f"Second Brain Audit — "
        f"{data['period_end'].strftime('%d %b %Y')} "
        f"({total} items, {rich_pct}% rich, {issue_count} issues)"
    )

    if pdf_bytes:
        msg = MIMEMultipart("mixed")
    else:
        msg = MIMEMultipart("alternative")

    msg["From"] = config["sender_email"]
    msg["To"] = config["default_recipient"]
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    if pdf_bytes:
        attachment = MIMEApplication(pdf_bytes)
        attachment.add_header(
            "Content-Disposition", "attachment", filename=pdf_filename
        )
        msg.attach(attachment)

    password = config["app_password"].replace(" ", "")
    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        server.starttls()
        server.login(config["sender_email"], password)
        server.sendmail(config["sender_email"], [config["default_recipient"]], msg.as_string())

    logger.info(f"Audit report sent — subject: {subject}")


async def run_weekly_audit(days_back: int = 7, send_email: bool = True) -> dict:
    """Run the full weekly audit: generate data, build email HTML + PDF, send.

    Args:
        days_back: Number of days to audit (default 7)
        send_email: Whether to send the email (default True)

    Returns:
        Audit data dict
    """
    logger.info(f"Running Second Brain audit for past {days_back} days")
    data = await generate_audit_data(days_back)

    # Email body (inline CSS, capped items for Gmail size limit)
    email_html = build_audit_email(data)

    # Full report for PDF (style block, all items, A4 layout)
    full_html = build_full_report(data)
    pdf_bytes = html_to_pdf(full_html)

    date_str = data["period_end"].strftime("%Y-%m-%d")
    pdf_filename = f"Second_Brain_Audit_{date_str}.pdf"

    if send_email:
        send_audit_email(email_html, data, pdf_bytes, pdf_filename)

    return data
