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

from datetime import datetime, timedelta

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


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
        self.api_base = config.get("api_base", "http://172.19.64.1:8100") if config else "http://172.19.64.1:8100"
        # Default to 5 years of history
        self.years_back = config.get("years_back", 5) if config else 5
        # Categories to search (default: all)
        self.categories = config.get("categories", list(EMAIL_CATEGORIES.keys())) if config else list(EMAIL_CATEGORIES.keys())
        # Max emails per category
        self.per_category_limit = config.get("per_category_limit", 100) if config else 100

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

    async def fetch(self, limit: int = 2000) -> list[SeedItem]:
        """Fetch emails from all configured categories."""
        items = []
        seen_ids = set()  # Track seen email IDs to avoid duplicates

        # Calculate date range
        after_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y/%m/%d")

        logger.info(f"Fetching emails from {len(self.categories)} categories since {after_date}...")

        async with httpx.AsyncClient(timeout=120) as client:
            for category_name in self.categories:
                if len(items) >= limit:
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

                        item = self._email_to_item(email, category_topics, category_name)
                        if item:
                            items.append(item)

                        if len(items) >= limit:
                            break

                except Exception as e:
                    logger.error(f"Error fetching {category_name} emails: {e}")

        logger.info(f"Returning {len(items)} emails for import")
        return items[:limit]

    def _email_to_item(self, email: dict, category_topics: list[str], category_name: str) -> SeedItem | None:
        """Convert email to SeedItem."""
        try:
            subject = email.get("subject", "No Subject")
            sender = email.get("from", "Unknown")
            date_str = email.get("date", "")
            snippet = email.get("snippet", "")

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

{snippet}
"""

            # Combine category topics with extracted topics
            all_topics = ["email"] + category_topics + self._extract_additional_topics(email)

            return SeedItem(
                title=f"Email: {subject[:60]}",
                content=content,
                source_id=email.get("id"),
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

    def get_default_topics(self) -> list[str]:
        return ["email"]
