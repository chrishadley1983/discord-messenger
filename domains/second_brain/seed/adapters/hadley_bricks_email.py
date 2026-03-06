"""Hadley Bricks email import adapter.

Imports business emails from the chris@hadleybricks.co.uk Google Workspace
account via the Hadley API (account=hadley-bricks).

Categories use sender/content-based Gmail queries:
- sales — Amazon seller notifications (sold, dispatch, cancellation)
- operations — Hadley Bricks system emails (parcel collection, reports, imports)
- marketplace-alerts — Amazon Seller Central alerts, Buy Box, policy changes
- business-tools — Helium 10, Amazon Business deals
"""

import asyncio
from datetime import datetime, timedelta

import httpx

from logger import logger
from ...config import HADLEY_API_BASE
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Content-based queries for Hadley Bricks email categories
HB_CATEGORIES = {
    "sales": {
        "query": 'from:seller-notification@amazon.co.uk ("Sold, dispatch now" OR "order cancellation")',
        "topics": ["hadley-bricks", "sales", "amazon"],
    },
    "operations": {
        "query": 'from:onboarding@resend.dev (parcel OR "delivery report" OR "purchase import" OR "vercel usage" OR "review queue")',
        "topics": ["hadley-bricks", "operations"],
    },
    "marketplace-alerts": {
        "query": 'from:seller-notification@amazon.co.uk -"Sold, dispatch" -"order cancellation"',
        "topics": ["hadley-bricks", "marketplace-alerts", "amazon"],
    },
    "business-tools": {
        "query": '(from:helium10.com OR from:business.amazon.co.uk OR from:sellerboard.com)',
        "topics": ["hadley-bricks", "business-tools"],
    },
    "ebay": {
        "query": '(from:ebay.co.uk OR from:ebay.com)',
        "topics": ["hadley-bricks", "ebay"],
    },
    "vinted": {
        "query": '(from:vinted.co.uk OR from:vinted.com OR from:vinted.fr)',
        "topics": ["hadley-bricks", "vinted"],
    },
    "shipping": {
        "query": '(from:inpost OR from:royalmail OR from:evri.com OR from:hermes)',
        "topics": ["hadley-bricks", "shipping", "logistics"],
    },
}


@register_adapter
class HadleyBricksEmailAdapter(SeedAdapter):
    """Import Hadley Bricks business emails from the HB Google Workspace account."""

    name = "hadley-bricks-email"
    description = "Import Hadley Bricks business emails (sales, operations, marketplace alerts, tools)"
    source_system = "seed:hadley-bricks-email"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_base = config.get("api_base", HADLEY_API_BASE) if config else HADLEY_API_BASE
        self.years_back = config.get("years_back", 2) if config else 2
        self.categories = config.get("categories", list(HB_CATEGORIES.keys())) if config else list(HB_CATEGORIES.keys())
        self.per_category_limit = config.get("per_category_limit", 200) if config else 200
        self.fetch_full_body = config.get("fetch_full_body", True) if config else True

    async def validate(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient() as client:
                # Just check we can reach the HB account's Gmail
                response = await client.get(
                    f"{self.api_base}/gmail/search",
                    params={"q": "in:anywhere", "limit": 1, "account": "hadley-bricks"},
                    timeout=10,
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
                params={"id": email_id, "account": "hadley-bricks"},
                timeout=30,
            )
            if response.status_code == 200:
                return response.json().get("body", "")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch body for {email_id}: {e}")
            return None

    async def fetch(self, limit: int = 2000) -> list[SeedItem]:
        """Fetch emails from all configured HB categories."""
        items = []
        seen_ids = set()
        all_emails: list[tuple[dict, list[str], str]] = []

        after_date = (datetime.now() - timedelta(days=365 * self.years_back)).strftime("%Y/%m/%d")

        logger.info(f"Fetching Hadley Bricks emails from {len(self.categories)} categories since {after_date}...")

        async with httpx.AsyncClient(timeout=120) as client:
            for category_name in self.categories:
                if len(all_emails) >= limit:
                    break

                category = HB_CATEGORIES.get(category_name)
                if not category:
                    continue

                query = f"{category['query']} after:{after_date}"
                category_topics = category["topics"]

                logger.info(f"Searching HB category: {category_name}...")

                try:
                    response = await client.get(
                        f"{self.api_base}/gmail/search",
                        params={"q": query, "limit": self.per_category_limit, "account": "hadley-bricks"},
                        timeout=60,
                    )

                    if response.status_code != 200:
                        logger.warning(f"Gmail search failed for HB/{category_name}: {response.status_code}")
                        continue

                    data = response.json()
                    emails = data.get("emails", [])

                    logger.info(f"  Found {len(emails)} emails in HB/{category_name}")

                    for email in emails:
                        email_id = email.get("id")
                        if email_id in seen_ids:
                            continue
                        seen_ids.add(email_id)

                        all_emails.append((email, category_topics, category_name))

                        if len(all_emails) >= limit:
                            break

                except Exception as e:
                    logger.error(f"Error fetching HB/{category_name} emails: {e}")

            # Fetch full bodies in parallel
            body_map: dict[str, str] = {}
            if self.fetch_full_body and all_emails:
                logger.info(f"Fetching full bodies for {len(all_emails)} HB emails...")
                semaphore = asyncio.Semaphore(5)

                async def fetch_with_limit(email_id: str) -> tuple[str, str | None]:
                    async with semaphore:
                        body = await self._fetch_full_body(client, email_id)
                        return email_id, body

                tasks = [fetch_with_limit(e[0].get("id")) for e in all_emails if e[0].get("id")]
                results = await asyncio.gather(*tasks)
                body_map = {eid: body for eid, body in results if body is not None}
                logger.info(f"Fetched {len(body_map)}/{len(all_emails)} full bodies")

        for email, category_topics, category_name in all_emails:
            email_id = email.get("id")
            full_body = body_map.get(email_id) if email_id else None
            item = self._email_to_item(email, category_topics, category_name, full_body=full_body)
            if item:
                items.append(item)

        logger.info(f"Returning {len(items)} Hadley Bricks emails for import")
        return items[:limit]

    def _email_to_item(self, email: dict, category_topics: list[str], category_name: str, full_body: str | None = None) -> SeedItem | None:
        """Convert email to SeedItem."""
        try:
            subject = email.get("subject", "No Subject")
            sender = email.get("from", "Unknown")
            date_str = email.get("date", "")
            snippet = email.get("snippet", "")

            body_text = full_body or snippet

            created_at = None
            if date_str:
                try:
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
**Category:** HB/{category_name}

{body_text}
"""

            all_topics = ["email", "hadley-bricks"] + category_topics + self._extract_business_topics(email, category_name)

            email_id = email.get("id")
            return SeedItem(
                title=f"HB Email: {subject[:60]}",
                content=content,
                source_url=f"gmail-hb://{email_id}" if email_id else None,
                source_id=email_id,
                topics=list(set(all_topics)),
                created_at=created_at,
                metadata={
                    "from": sender,
                    "date": date_str,
                    "category": f"HB/{category_name}",
                    "business": "hadley-bricks",
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse HB email: {e}")
            return None

    def _extract_business_topics(self, email: dict, category_name: str) -> list[str]:
        """Extract business-specific topics from email content."""
        topics = []

        subject = (email.get("subject") or "").lower()
        sender = (email.get("from") or "").lower()
        snippet = (email.get("snippet") or "").lower()
        combined = f"{subject} {sender} {snippet}"

        # Platform detection
        if "vinted" in combined:
            topics.append("vinted")
        if "ebay" in combined:
            topics.append("ebay")
        if "amazon" in combined:
            topics.append("amazon")
        if "bricklink" in combined or "brick link" in combined:
            topics.append("bricklink")
        if "brick owl" in combined or "brickowl" in combined:
            topics.append("brickowl")

        # Shipping providers
        if "inpost" in combined:
            topics.append("inpost")
        if "royal mail" in combined:
            topics.append("royal-mail")
        if "evri" in combined or "hermes" in combined:
            topics.append("evri")

        # Business tools
        if "helium" in combined:
            topics.append("helium-10")
        if "sellerboard" in combined:
            topics.append("sellerboard")

        # Operations
        if "vercel" in combined:
            topics.append("vercel")
        if "supabase" in combined:
            topics.append("supabase")
        if "delivery report" in combined:
            topics.append("delivery-report")

        return topics

    def get_default_topics(self) -> list[str]:
        return ["email", "hadley-bricks"]
