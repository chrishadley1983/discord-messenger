"""Email threads adapter.

Imports important/starred email threads from Gmail.
"""

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class EmailThreadsAdapter(SeedAdapter):
    """Import starred/important email threads."""

    name = "email-threads"
    description = "Import starred email threads from Gmail"
    source_system = "seed:email"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_base = config.get("api_base", "http://172.19.64.1:8100") if config else "http://172.19.64.1:8100"

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

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        items = []

        try:
            async with httpx.AsyncClient() as client:
                # Get starred emails
                response = await client.get(
                    f"{self.api_base}/gmail/starred",
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"Gmail API error: {response.status_code}")
                    return items

                emails = response.json()

                for email in emails[:limit]:
                    item = self._email_to_item(email)
                    if item:
                        items.append(item)

        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}")

        return items

    def _email_to_item(self, email: dict) -> SeedItem | None:
        """Convert email to SeedItem."""
        try:
            subject = email.get("subject", "No Subject")
            sender = email.get("from", "Unknown")
            date = email.get("date", "")
            snippet = email.get("snippet", "")
            body = email.get("body", snippet)

            # Truncate very long emails
            if len(body) > 5000:
                body = body[:5000] + "\n\n[Truncated]"

            content = f"""# {subject}

**From:** {sender}
**Date:** {date}

{body}
"""

            return SeedItem(
                title=f"Email: {subject[:60]}",
                content=content,
                source_id=email.get("id"),
                topics=self._extract_topics(email),
                metadata={
                    "from": sender,
                    "date": date,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to parse email: {e}")
            return None

    def _extract_topics(self, email: dict) -> list[str]:
        """Extract topics from email."""
        topics = ["email"]

        subject = (email.get("subject") or "").lower()
        sender = (email.get("from") or "").lower()

        # Categorize by subject/sender
        if any(w in subject for w in ["invoice", "receipt", "order"]):
            topics.append("finance")
        if any(w in subject for w in ["lego", "bricklink", "brick"]):
            topics.extend(["lego", "hadley-bricks"])
        if any(w in subject for w in ["school", "parent"]):
            topics.append("family")
        if any(w in sender for w in ["garmin", "strava", "parkrun"]):
            topics.extend(["fitness", "running"])
        if any(w in subject for w in ["tax", "hmrc", "self-assessment"]):
            topics.extend(["finance", "tax"])

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["email"]
