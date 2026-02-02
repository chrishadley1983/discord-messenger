"""GitHub projects adapter.

Imports README and recent commits from specified GitHub repositories.
"""

import os
from datetime import datetime

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Default repos to import
DEFAULT_REPOS = [
    "chrishadley1983/peterbot-mem",
    "chrishadley1983/discord-messenger",
    "chrishadley1983/finance-tracker",
    "chrishadley1983/family-meal-planner",
    "chrishadley1983/hadley-bricks-inventory-management",
]


@register_adapter
class GitHubProjectsAdapter(SeedAdapter):
    """Import README and commits from specified GitHub repositories."""

    name = "github-projects"
    description = "Import README and commits from your GitHub projects"
    source_system = "seed:github"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.token = config.get("token") if config else None
        self.repos = config.get("repos", DEFAULT_REPOS) if config else DEFAULT_REPOS

        # Try environment variable for token
        if not self.token:
            self.token = os.getenv("GITHUB_TOKEN")

    async def validate(self) -> tuple[bool, str]:
        if not self.token:
            return False, "GitHub token not configured (GITHUB_TOKEN)"
        if not self.repos:
            return False, "No repositories configured"
        return True, ""

    async def fetch(self, limit: int = 500) -> list[SeedItem]:
        """Fetch README and recent commits from each repo."""
        items = []

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            for repo_full_name in self.repos:
                logger.info(f"Fetching from {repo_full_name}...")

                try:
                    # Get repo info
                    repo_response = await client.get(
                        f"https://api.github.com/repos/{repo_full_name}",
                        headers=headers,
                    )

                    if repo_response.status_code != 200:
                        logger.warning(f"Could not fetch repo {repo_full_name}: {repo_response.status_code}")
                        continue

                    repo = repo_response.json()

                    # Import README as a knowledge item
                    readme_item = await self._fetch_readme(client, headers, repo_full_name, repo)
                    if readme_item:
                        items.append(readme_item)

                    # Import recent commits
                    commits = await self._fetch_commits(client, headers, repo_full_name, repo)
                    items.extend(commits)

                    if len(items) >= limit:
                        break

                except Exception as e:
                    logger.error(f"Error fetching {repo_full_name}: {e}")

        logger.info(f"Returning {len(items)} GitHub items for import")
        return items[:limit]

    async def _fetch_readme(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        repo_full_name: str,
        repo: dict,
    ) -> SeedItem | None:
        """Fetch README file from repo."""
        try:
            # Try README.md first
            for readme_name in ["README.md", "readme.md", "README", "readme"]:
                response = await client.get(
                    f"https://api.github.com/repos/{repo_full_name}/contents/{readme_name}",
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()

                    # Fetch raw content
                    if data.get("download_url"):
                        content_response = await client.get(data["download_url"])
                        if content_response.status_code == 200:
                            readme_content = content_response.text

                            # Truncate very long READMEs
                            if len(readme_content) > 10000:
                                readme_content = readme_content[:10000] + "\n\n[Truncated]"

                            return SeedItem(
                                title=f"README: {repo['name']}",
                                content=f"# {repo['name']} - README\n\n{repo.get('description', '')}\n\n---\n\n{readme_content}",
                                source_url=repo["html_url"],
                                source_id=f"readme-{repo['id']}",
                                topics=self._extract_topics(repo),
                                created_at=datetime.fromisoformat(
                                    repo["created_at"].replace("Z", "+00:00")
                                ) if repo.get("created_at") else None,
                                metadata={
                                    "type": "readme",
                                    "repo": repo_full_name,
                                    "language": repo.get("language"),
                                },
                            )
                    break

        except Exception as e:
            logger.warning(f"Failed to fetch README for {repo_full_name}: {e}")

        return None

    async def _fetch_commits(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        repo_full_name: str,
        repo: dict,
    ) -> list[SeedItem]:
        """Fetch recent commits from repo."""
        items = []

        try:
            # Get last 50 commits
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/commits",
                headers=headers,
                params={"per_page": 50},
            )

            if response.status_code != 200:
                return items

            commits = response.json()

            for commit in commits:
                commit_data = commit.get("commit", {})
                message = commit_data.get("message", "")
                author = commit_data.get("author", {})
                sha = commit.get("sha", "")[:7]

                # Skip merge commits and trivial commits
                if message.startswith("Merge ") or len(message) < 10:
                    continue

                # Parse date
                date_str = author.get("date", "")
                created_at = None
                if date_str:
                    try:
                        created_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass

                content = f"""# Commit: {message.split(chr(10))[0][:60]}

**Repository:** {repo['name']}
**SHA:** {sha}
**Author:** {author.get('name', 'Unknown')}
**Date:** {date_str[:10] if date_str else 'Unknown'}

{message}
"""

                items.append(SeedItem(
                    title=f"Commit [{repo['name']}]: {message.split(chr(10))[0][:50]}",
                    content=content,
                    source_url=commit.get("html_url"),
                    source_id=commit.get("sha"),
                    topics=self._extract_topics(repo) + ["commit"],
                    created_at=created_at,
                    metadata={
                        "type": "commit",
                        "repo": repo_full_name,
                        "sha": commit.get("sha"),
                    },
                ))

        except Exception as e:
            logger.warning(f"Failed to fetch commits for {repo_full_name}: {e}")

        return items

    def _extract_topics(self, repo: dict) -> list[str]:
        """Extract relevant topics from repo."""
        topics = ["github", "code"]

        # Add language as topic
        if repo.get("language"):
            topics.append(repo["language"].lower())

        # Add repo topics
        if repo.get("topics"):
            topics.extend(repo["topics"][:5])

        # Categorize by repo name
        name_lower = repo["name"].lower()
        desc_lower = (repo.get("description") or "").lower()

        if "peterbot" in name_lower or "discord" in name_lower:
            topics.extend(["peterbot", "discord"])
        if "lego" in name_lower or "brick" in name_lower or "hadley-bricks" in name_lower:
            topics.extend(["lego", "hadley-bricks"])
        if "finance" in name_lower or "money" in name_lower:
            topics.append("finance")
        if "meal" in name_lower or "recipe" in name_lower:
            topics.extend(["family", "food"])

        return list(set(topics))

    def get_default_topics(self) -> list[str]:
        return ["github", "code", "development"]
