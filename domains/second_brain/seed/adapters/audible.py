"""Audible reading-history adapter.

Imports finished audiobooks (with Chris's star ratings) into the Second
Brain so Peter's memory knows what he reads, what he loved, and which
series he's mid-way through. Auth is shared with the audible-mcp project
(domains/audible/client.py reads its auth.json).

One item per finished book, deduped by audible://<asin> — re-runs only
import newly finished titles.
"""

import asyncio
from datetime import datetime, timezone

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


def _book_content(b: dict) -> str:
    series = ", ".join(
        f"{s['name']} #{s['position']}" for s in b.get("series") or [] if s.get("name")
    )
    lines = [
        f"# {b['title']}",
        "",
        f"**Author(s):** {', '.join(b.get('authors') or [])}",
        f"**Narrator(s):** {', '.join(b.get('narrators') or [])}",
    ]
    if series:
        lines.append(f"**Series:** {series}")
    lines.append(f"**Runtime:** {b.get('runtime_hours')}h")
    if b.get("my_rating"):
        lines.append(f"**Chris's rating:** {b['my_rating']}/5 stars")
    if b.get("average_rating"):
        lines.append(f"**Audible average:** {b['average_rating']}/5")
    if b.get("purchase_date"):
        lines.append(f"**Purchased:** {str(b['purchase_date'])[:10]}")
    summary = (b.get("publisher_summary") or "").strip()
    if summary:
        lines += ["", "## Publisher summary", summary[:1500]]
    return "\n".join(lines)


@register_adapter
class AudibleBooksAdapter(SeedAdapter):
    """Import finished Audible books with ratings."""

    name = "audible-books"
    description = "Finished audiobooks + ratings from Audible"
    source_system = "seed:audible"

    def get_default_topics(self) -> list[str]:
        return ["audible", "books", "reading", "listening"]

    async def validate(self) -> tuple[bool, str]:
        from domains.audible.client import AUTH_FILE

        if not AUTH_FILE.exists():
            return False, (
                f"Audible auth.json not found at {AUTH_FILE} — "
                "run auth_setup.py in the audible-mcp project"
            )
        return True, ""

    async def fetch(self, limit: int = 50) -> list[SeedItem]:
        from domains.audible import client as ac

        books = await asyncio.to_thread(ac.get_finished_books)
        items: list[SeedItem] = []
        for b in books[: max(1, limit)] if limit else books:
            if not b.get("asin"):
                continue
            created = None
            if b.get("purchase_date"):
                try:
                    created = datetime.fromisoformat(
                        str(b["purchase_date"]).replace("Z", "+00:00")
                    )
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            rating = f" — {b['my_rating']}★" if b.get("my_rating") else ""
            items.append(SeedItem(
                title=f"Audible: {b['title']}{rating}",
                content=_book_content(b),
                source_url=f"audible://{b['asin']}",
                topics=self.get_default_topics(),
                created_at=created,
                content_type="listening_history",
            ))

        logger.info(f"Audible adapter: {len(items)} finished books prepared")
        return items
