"""GitHub starred repos adapter.

Imports starred repositories as knowledge items.
"""

import os
from datetime import datetime

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


@register_adapter
class GitHubStarsAdapter(SeedAdapter):
    """Import starred GitHub repositories."""

    name = "github-stars"
    description = "Import starred GitHub repositories"
    source_system = "seed:github"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.token = config.get("token") if config else None
        self.username = config.get("username") if config else None

        # Try environment variables
        if not self.token:
            self.token = os.getenv("GITHUB_TOKEN")
        if not self.username:
            self.username = os.getenv("GITHUB_USERNAME")

    async def validate(self) -> tuple[bool, str]:
        if not self.token:
            return False, "GitHub token not configured"
        if not self.username:
            return False, "GitHub username not configured"
        return True, ""

    async def fetch(self, limit: int = 100) -> list[SeedItem]:
        items = []

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient() as client:
            page = 1
            per_page = min(limit, 100)

            while len(items) < limit:
                response = await client.get(
                    f"https://api.github.com/users/{self.username}/starred",
                    headers=headers,
                    params={"page": page, "per_page": per_page},
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"GitHub API error: {response.status_code}")
                    break

                repos = response.json()
                if not repos:
                    break

                for repo in repos:
                    # Build content from repo info
                    content_parts = [
                        f"# {repo['full_name']}",
                        "",
                        repo.get("description") or "No description",
                        "",
                        f"**Language:** {repo.get('language') or 'Unknown'}",
                        f"**Stars:** {repo.get('stargazers_count', 0)}",
                        f"**Forks:** {repo.get('forks_count', 0)}",
                    ]

                    if repo.get("topics"):
                        content_parts.append(f"**Topics:** {', '.join(repo['topics'])}")

                    items.append(SeedItem(
                        title=repo["full_name"],
                        content="\n".join(content_parts),
                        source_url=repo["html_url"],
                        source_id=str(repo["id"]),
                        topics=self._extract_topics(repo),
                        created_at=datetime.fromisoformat(
                            repo["created_at"].replace("Z", "+00:00")
                        ) if repo.get("created_at") else None,
                        metadata={
                            "stars": repo.get("stargazers_count", 0),
                            "language": repo.get("language"),
                        },
                    ))

                    if len(items) >= limit:
                        break

                page += 1

        return items

    def _extract_topics(self, repo: dict) -> list[str]:
        """Extract relevant topics from repo."""
        topics = ["github"]

        # Add language as topic
        if repo.get("language"):
            topics.append(repo["language"].lower())

        # Add repo topics
        if repo.get("topics"):
            topics.extend(repo["topics"][:5])

        # Categorize by common patterns
        name_lower = repo["full_name"].lower()
        desc_lower = (repo.get("description") or "").lower()

        if any(w in name_lower or w in desc_lower for w in ["lego", "brick"]):
            topics.append("lego")
        if any(w in name_lower or w in desc_lower for w in ["running", "fitness", "workout"]):
            topics.append("fitness")
        if any(w in name_lower or w in desc_lower for w in ["ai", "ml", "machine-learning"]):
            topics.append("tech")

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["github", "development"]
