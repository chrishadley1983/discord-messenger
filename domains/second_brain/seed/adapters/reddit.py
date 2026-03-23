"""Reddit saved/interacted adapter.

Imports saved posts, upvoted content, and commented threads from Reddit
using the PRAW library.

Setup required:
  pip install praw
  Register app at reddit.com/prefs/apps (script type)
  Set env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
"""

import asyncio
import os
from datetime import datetime, timezone

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class RedditAdapter(SeedAdapter):
    """Import saved, upvoted, and commented Reddit posts."""

    name = "reddit-saved"
    description = "Saved posts, upvotes, and comments from Reddit"
    source_system = "seed:reddit"

    def get_default_topics(self) -> list[str]:
        return ["reddit"]

    async def validate(self) -> tuple[bool, str]:
        try:
            import praw  # noqa: F401
        except ImportError:
            return False, "praw not installed (pip install praw)"

        required_vars = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"]
        missing = [v for v in required_vars if not os.getenv(v)]
        if missing:
            return False, f"Missing env vars: {', '.join(missing)}"
        return True, ""

    async def fetch(self, limit: int = 20) -> list[SeedItem]:
        items = []
        try:
            import praw

            reddit = await asyncio.to_thread(
                lambda: praw.Reddit(
                    client_id=os.getenv("REDDIT_CLIENT_ID"),
                    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
                    username=os.getenv("REDDIT_USERNAME"),
                    password=os.getenv("REDDIT_PASSWORD"),
                    user_agent="second-brain-seed/1.0",
                )
            )

            user = await asyncio.to_thread(reddit.user.me)

            # Saved posts — fetch + convert in thread to avoid blocking
            saved_items = await asyncio.to_thread(
                lambda: [self._post_to_seed_item(p, source="saved")
                         for p in user.saved(limit=limit)]
            )
            for item in saved_items:
                if item:
                    items.append(item)

            # Upvoted posts (only high-value ones)
            if len(items) < limit:
                upvoted_items = await asyncio.to_thread(
                    lambda: [self._post_to_seed_item(p, source="upvoted")
                             for p in user.upvoted(limit=limit)
                             if not hasattr(p, 'score') or p.score >= 10]
                )
                for item in upvoted_items:
                    if item:
                        items.append(item)

            # Recent comments (for context of discussions)
            if len(items) < limit:
                comment_items = await asyncio.to_thread(
                    lambda: [self._comment_to_seed_item(c)
                             for c in user.comments.new(limit=min(limit, 20))]
                )
                for item in comment_items:
                    if item:
                        items.append(item)

        except Exception as e:
            logger.error(f"Reddit fetch failed: {e}")

        logger.info(f"Fetched {len(items)} Reddit items")
        return items[:limit]

    def _post_to_seed_item(self, post, source: str = "saved") -> SeedItem | None:
        """Convert a Reddit submission to a SeedItem."""
        try:
            # Handle both Submission and Comment objects from saved
            if hasattr(post, 'title'):
                # It's a submission
                title = post.title
                selftext = post.selftext or ""
                permalink = f"https://reddit.com{post.permalink}"
                subreddit = str(post.subreddit)
                created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                score = post.score

                # Get top comments for context
                top_comments = []
                try:
                    post.comments.replace_more(limit=0)
                    for comment in post.comments[:3]:
                        if hasattr(comment, 'body'):
                            top_comments.append(comment.body[:500])
                except Exception:
                    pass

                content_parts = [f"# {title}", ""]
                content_parts.append(f"**Subreddit:** r/{subreddit}")
                content_parts.append(f"**Score:** {score}")
                content_parts.append(f"**Source:** {source}")
                content_parts.append("")

                if selftext:
                    content_parts.append(selftext[:3000])
                    content_parts.append("")

                if top_comments:
                    content_parts.append("## Top Comments")
                    for i, c in enumerate(top_comments, 1):
                        content_parts.append(f"\n**Comment {i}:**\n{c}")

                topics = ["reddit", f"r-{subreddit.lower()}"]

                return SeedItem(
                    title=f"Reddit: {title[:60]}",
                    content="\n".join(content_parts),
                    source_url=permalink,
                    source_id=post.id,
                    topics=topics,
                    created_at=created,
                    content_type="social_save",
                )
            else:
                # It's a saved comment — convert to seed item
                return self._comment_to_seed_item(post)

        except Exception as e:
            logger.warning(f"Failed to convert Reddit post: {e}")
            return None

    def _comment_to_seed_item(self, comment) -> SeedItem | None:
        """Convert a Reddit comment to a SeedItem."""
        try:
            if not hasattr(comment, 'body'):
                return None

            body = comment.body
            if len(body) < 50:
                return None

            # Get parent post info
            submission = comment.submission
            post_title = submission.title if hasattr(submission, 'title') else "Unknown"
            subreddit = str(comment.subreddit)
            permalink = f"https://reddit.com{comment.permalink}"
            created = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)

            content = f"""# Comment on: {post_title}

**Subreddit:** r/{subreddit}
**My comment:**

{body[:2000]}
"""

            return SeedItem(
                title=f"Reddit Comment: {post_title[:50]}",
                content=content,
                source_url=permalink,
                source_id=comment.id,
                topics=["reddit", f"r-{subreddit.lower()}"],
                created_at=created,
                content_type="discussion",
            )

        except Exception as e:
            logger.warning(f"Failed to convert Reddit comment: {e}")
            return None
