"""Email import adapter.

Imports important emails from Gmail across multiple categories:
- Travel & accommodation bookings
- Purchases & receipts
- Financial (bank, tax, insurance)
- Health (NHS, dentist, medical)
- School communications
- BrickLink/LEGO orders
- Vehicle (MOT, insurance, service)
- Subscriptions & renewals
"""

import asyncio
import re
from datetime import datetime, timedelta

import httpx

from logger import logger
from ...config import HADLEY_API_BASE
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# ── Marketing email filter ──────────────────────────────────────────────
# Senders whose emails are always promotional (no-reply marketing addresses)
MARKETING_SENDERS = {
    "no-reply@e.premierinn.com",
    "reservations.nyc@acehotel.com",
    "news@sigmasports.com",
    "marketing@",
    "noreply@marketing.",
    "newsletter@",
    "promotions@",
    "offers@",
    "deals@",
    "campaigns@",
    "info@e.",
    "no-reply@e.",
    "noreply@em.",
}

# Subject line patterns that indicate marketing/promotional content
MARKETING_SUBJECT_PATTERNS = [
    r"% off\b",
    r"\bsale\b.*\bnow\b",
    r"\bflash sale\b",
    r"\blimited time\b",
    r"\bexclusive offer\b",
    r"\bdon'?t miss\b",
    r"\bbook now\b.*\bsave\b",
    r"\bfree delivery\b",
    r"\bnew collection\b",
    r"\bjust landed\b",
    r"\bget lucky\b",
    r"\bunsubscribe\b",
    r"\bshop now\b",
]

_MARKETING_RE = re.compile("|".join(MARKETING_SUBJECT_PATTERNS), re.IGNORECASE)


def _is_marketing_email(email: dict) -> bool:
    """Detect promotional/marketing emails that shouldn't be saved."""
    sender = (email.get("from") or "").lower()
    subject = (email.get("subject") or "").lower()
    snippet = (email.get("snippet") or "").lower()

    # Check sender against known marketing addresses
    for pattern in MARKETING_SENDERS:
        if pattern in sender:
            return True

    # Check subject line for promotional patterns
    if _MARKETING_RE.search(subject):
        return True

    # Check snippet for bulk-email signals (invisible spacer chars, many repeated chars)
    # These are common in HTML marketing emails
    spacer_count = snippet.count("\u034f") + snippet.count("\u200c") + snippet.count("\u200b")
    if spacer_count > 5:
        return True

    return False


# Gmail search queries for different categories
EMAIL_CATEGORIES = {
    "travel": {
        "query": "(flight OR hotel OR booking OR reservation OR airbnb OR \"train ticket\" OR easyjet OR ryanair OR british airways OR travelodge OR premier inn OR booking.com)",
        "topics": ["travel", "booking"],
    },
    "accommodation": {
        "query": "(hotel OR airbnb OR \"holiday let\" OR cottage OR villa OR apartment booking OR \"check-in\" OR \"your stay\")",
        "topics": ["travel", "accommodation"],
    },
    "purchases": {
        "query": "(\"order confirmation\" OR \"your order\" OR \"order dispatched\" OR \"order shipped\" OR \"delivery confirmation\" OR amazon OR ebay)",
        "topics": ["purchase", "shopping"],
    },
    "receipts": {
        "query": "(receipt OR invoice OR \"payment received\" OR \"payment confirmation\" OR \"transaction\")",
        "topics": ["finance", "receipt"],
    },
    "financial": {
        "query": "(bank statement OR \"direct debit\" OR \"standing order\" OR mortgage OR loan OR credit card statement OR nationwide OR barclays OR hsbc OR lloyds)",
        "topics": ["finance", "banking"],
    },
    "tax": {
        "query": "(HMRC OR \"self assessment\" OR \"tax return\" OR \"tax refund\" OR P60 OR P45 OR \"national insurance\")",
        "topics": ["finance", "tax"],
    },
    "insurance": {
        "query": "(insurance OR \"policy renewal\" OR \"insurance quote\" OR \"your policy\" OR admiral OR aviva OR directline OR \"legal & general\")",
        "topics": ["finance", "insurance"],
    },
    "health": {
        "query": "(NHS OR \"GP appointment\" OR dentist OR doctor OR hospital OR prescription OR optician OR specsavers OR \"medical appointment\")",
        "topics": ["health", "medical"],
    },
    "school": {
        "query": "(school OR \"parents evening\" OR \"school trip\" OR \"school newsletter\" OR \"term dates\" OR teacher OR homework OR \"school report\")",
        "topics": ["family", "school"],
    },
    "lego": {
        "query": "(bricklink OR lego OR \"brick owl\" OR rebrickable OR \"lego set\" OR minifigure OR brickowl)",
        "topics": ["lego", "hadley-bricks"],
    },
    "vehicle": {
        "query": "(MOT OR \"car service\" OR \"vehicle tax\" OR DVLA OR \"car insurance\" OR breakdown OR RAC OR AA OR kwik-fit OR halfords)",
        "topics": ["vehicle", "car"],
    },
    "subscriptions": {
        "query": "(subscription OR renewal OR \"membership\" OR \"your plan\" OR netflix OR spotify OR amazon prime OR \"annual fee\")",
        "topics": ["subscription"],
    },
    "fitness": {
        "query": "(garmin OR strava OR parkrun OR \"race entry\" OR marathon OR \"running event\" OR gym membership)",
        "topics": ["fitness", "running"],
    },
    "utilities": {
        "query": "(\"electricity bill\" OR \"gas bill\" OR \"water bill\" OR \"council tax\" OR broadband OR \"mobile bill\" OR EDF OR british gas OR thames water)",
        "topics": ["finance", "utilities"],
    },
}


@register_adapter
class EmailImportAdapter(SeedAdapter):
    """Import important emails from Gmail across multiple categories."""

    name = "email-import"
    description = "Import important emails (travel, purchases, finance, health, etc.)"
    source_system = "seed:email"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_base = config.get("api_base", HADLEY_API_BASE) if config else HADLEY_API_BASE
        # Default to 5 years of history
        self.years_back = config.get("years_back", 5) if config else 5
        # Categories to search (default: all)
        self.categories = config.get("categories", list(EMAIL_CATEGORIES.keys())) if config else list(EMAIL_CATEGORIES.keys())
        # Max emails per category
        self.per_category_limit = config.get("per_category_limit", 100) if config else 100
        # Fetch full email bodies (default: True)
        self.fetch_full_body = config.get("fetch_full_body", True) if config else True

    async def validate(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_base}/gmail/labels",
                    timeout=5,
                )
                if response.status_code == 200:
                    return True, ""
                return False, f"Gmail API returned {response.status_code}"
        except Exception as e:
            return False, f"Cannot reach Gmail API: {e}"

    async def _fetch_full_body(self, client: httpx.AsyncClient, email_id: str) -> str | None:
        """Fetch full email body from Hadley API."""
        try:
            response = await client.get(
                f"{self.api_base}/gmail/get",
                params={"id": email_id},
                timeout=30,
            )
            if response.status_code == 200:
                return response.json().get("body", "")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch body for {email_id}: {e}")
            return None

    async def fetch(self, limit: int = 2000) -> list[SeedItem]:
        """Fetch emails from all configured categories."""
        items = []
        seen_ids = set()  # Track seen email IDs to avoid duplicates
        # Collect all unique emails with their category info before body fetching
        all_emails: list[tuple[dict, list[str], str]] = []

        # Calculate date range
        after_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y/%m/%d")

        logger.info(f"Fetching emails from {len(self.categories)} categories since {after_date}...")

        async with httpx.AsyncClient(timeout=120) as client:
            for category_name in self.categories:
                if len(all_emails) >= limit:
                    break

                category = EMAIL_CATEGORIES.get(category_name)
                if not category:
                    continue

                # Add date filter to query
                query = f"{category['query']} after:{after_date}"
                category_topics = category["topics"]

                logger.info(f"Searching category: {category_name}...")

                try:
                    response = await client.get(
                        f"{self.api_base}/gmail/search",
                        params={"q": query, "limit": self.per_category_limit},
                        timeout=60,
                    )

                    if response.status_code != 200:
                        logger.warning(f"Gmail search failed for {category_name}: {response.status_code}")
                        continue

                    data = response.json()
                    emails = data.get("emails", [])

                    logger.info(f"  Found {len(emails)} emails in {category_name}")

                    for email in emails:
                        # Skip duplicates (email might match multiple categories)
                        email_id = email.get("id")
                        if email_id in seen_ids:
                            continue
                        seen_ids.add(email_id)

                        # Skip marketing/promotional emails
                        if _is_marketing_email(email):
                            logger.debug(f"  Skipping marketing email: {email.get('subject', '')[:60]}")
                            continue

                        all_emails.append((email, category_topics, category_name))

                        if len(all_emails) >= limit:
                            break

                except Exception as e:
                    logger.error(f"Error fetching {category_name} emails: {e}")

            # Fetch full bodies in parallel with concurrency limit
            body_map: dict[str, str] = {}
            if self.fetch_full_body and all_emails:
                logger.info(f"Fetching full bodies for {len(all_emails)} emails...")
                semaphore = asyncio.Semaphore(5)

                async def fetch_with_limit(email_id: str) -> tuple[str, str | None]:
                    async with semaphore:
                        body = await self._fetch_full_body(client, email_id)
                        return email_id, body

                tasks = [fetch_with_limit(e[0].get("id")) for e in all_emails if e[0].get("id")]
                results = await asyncio.gather(*tasks)
                body_map = {eid: body for eid, body in results if body is not None}
                logger.info(f"Fetched {len(body_map)}/{len(all_emails)} full bodies")

        # Build SeedItems
        for email, category_topics, category_name in all_emails:
            email_id = email.get("id")
            full_body = body_map.get(email_id) if email_id else None
            item = self._email_to_item(email, category_topics, category_name, full_body=full_body)
            if item:
                items.append(item)

        logger.info(f"Returning {len(items)} emails for import")
        return items[:limit]

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Extract readable text from HTML email body."""
        import html as html_module
        # Remove style/script blocks
        text = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Convert common block elements to newlines
        text = re.sub(r'<(br|p|div|h[1-6]|li|tr)[^>]*/?>', '\n', text, flags=re.IGNORECASE)
        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        text = html_module.unescape(text)
        # Remove invisible spacer characters used in marketing emails
        text = re.sub(r'[\u034f\u200c\u200b\u00a0]+', ' ', text)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _email_to_item(self, email: dict, category_topics: list[str], category_name: str, full_body: str | None = None) -> SeedItem | None:
        """Convert email to SeedItem."""
        try:
            subject = email.get("subject", "No Subject")
            sender = email.get("from", "Unknown")
            date_str = email.get("date", "")
            snippet = email.get("snippet", "")

            # Use full body if available, fall back to snippet
            # Strip HTML if the body contains tags
            body_text = full_body or snippet
            if body_text and '<' in body_text and '>' in body_text:
                body_text = self._html_to_text(body_text)

            # Parse date for created_at
            created_at = None
            if date_str:
                try:
                    # Try common email date formats
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"]:
                        try:
                            created_at = datetime.strptime(date_str.split(" (")[0].strip(), fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            content = f"""# {subject}

**From:** {sender}
**Date:** {date_str}
**Category:** {category_name}

{body_text}
"""

            # Combine category topics with extracted topics
            all_topics = ["email"] + category_topics + self._extract_additional_topics(email)

            email_id = email.get("id")
            return SeedItem(
                title=f"Email: {subject[:60]}",
                content=content,
                source_url=f"gmail://{email_id}" if email_id else None,
                source_id=email_id,
                topics=list(set(all_topics)),
                created_at=created_at,
                metadata={
                    "from": sender,
                    "date": date_str,
                    "category": category_name,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse email: {e}")
            return None

    def _extract_additional_topics(self, email: dict) -> list[str]:
        """Extract additional topics from email content."""
        topics = []

        subject = (email.get("subject") or "").lower()
        sender = (email.get("from") or "").lower()
        snippet = (email.get("snippet") or "").lower()
        combined = f"{subject} {sender} {snippet}"

        # Specific service/company detection
        if "amazon" in combined:
            topics.append("amazon")
        if "ebay" in combined:
            topics.append("ebay")
        if "bricklink" in combined or "brick owl" in combined:
            topics.extend(["bricklink", "lego"])
        if "garmin" in combined or "strava" in combined:
            topics.append("fitness")
        if "parkrun" in combined:
            topics.extend(["parkrun", "running"])
        if any(w in combined for w in ["max", "emmie", "school"]):
            topics.append("family")
        if "hmrc" in combined:
            topics.append("tax")
        if any(w in combined for w in ["nationwide", "barclays", "hsbc", "lloyds", "santander"]):
            topics.append("banking")

        return topics

    async def backfill_bodies(self, dry_run: bool = False) -> dict:
        """Backfill full email bodies for existing items that only have snippets.

        Finds all knowledge_items with source_url starting with 'gmail://',
        fetches the full body for each, and updates the content field.

        Returns:
            Dict with counts: found, updated, skipped, failed
        """
        from ...db import update_knowledge_item

        stats = {"found": 0, "updated": 0, "skipped": 0, "failed": 0}

        # Query all email items from Supabase
        from config import SUPABASE_URL, SUPABASE_KEY
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            # Paginate through all gmail items (filter by source_system to avoid URL encoding issues)
            all_items = []
            offset = 0
            page_size = 100

            while True:
                response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/knowledge_items",
                    headers=headers,
                    params={
                        "source_system": "eq.seed:email",
                        "select": "id,source_url,full_text",
                        "order": "created_at.asc",
                        "offset": offset,
                        "limit": page_size,
                    },
                )
                if response.status_code != 200:
                    logger.error(f"Failed to query email items: {response.status_code}")
                    break

                rows = response.json()
                if not rows:
                    break

                all_items.extend(rows)
                offset += page_size
                if len(rows) < page_size:
                    break

            stats["found"] = len(all_items)
            logger.info(f"Found {len(all_items)} email items to check for backfill")

            # Fetch full bodies concurrently
            semaphore = asyncio.Semaphore(5)

            async def backfill_one(item: dict) -> None:
                source_url = item.get("source_url", "")
                if not source_url.startswith("gmail://"):
                    stats["skipped"] += 1
                    return
                email_id = source_url.replace("gmail://", "")
                full_text = item.get("full_text", "")

                # Heuristic: if body portion is short (under ~250 chars), it likely
                # only contains headers + snippet and needs backfill
                body_start = full_text.find("\n\n", full_text.find("**Category:**"))
                body_text = full_text[body_start:].strip() if body_start > 0 else ""
                if len(body_text) > 250:
                    stats["skipped"] += 1
                    return

                async with semaphore:
                    full_body = await self._fetch_full_body(client, email_id)

                if not full_body:
                    stats["failed"] += 1
                    logger.warning(f"Could not fetch body for {email_id}")
                    return

                if len(full_body.strip()) <= len(body_text.strip()):
                    stats["skipped"] += 1
                    return

                # Rebuild full_text with full body
                # Extract header block (everything before the body text)
                if body_start > 0:
                    header_block = full_text[:body_start].rstrip()
                    new_content = f"{header_block}\n\n{full_body}\n"
                else:
                    new_content = full_text.replace(body_text, full_body) if body_text else full_text

                if dry_run:
                    logger.info(f"[dry-run] Would update {email_id} ({len(body_text)} -> {len(full_body)} chars)")
                    stats["updated"] += 1
                    return

                try:
                    from uuid import UUID as UUIDType
                    await update_knowledge_item(UUIDType(item["id"]), full_text=new_content)
                    stats["updated"] += 1
                    logger.debug(f"Backfilled {email_id} ({len(body_text)} -> {len(full_body)} chars)")
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"Failed to update {email_id}: {e}")

            tasks = [backfill_one(item) for item in all_items]
            await asyncio.gather(*tasks)

        logger.info(
            f"Backfill complete: {stats['found']} found, {stats['updated']} updated, "
            f"{stats['skipped']} skipped, {stats['failed']} failed"
        )
        return stats

    def get_default_topics(self) -> list[str]:
        return ["email"]
