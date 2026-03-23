"""GitHub projects adapter.

Imports README and recent commits from specified GitHub repositories.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

from logger import logger
from ..base import SeedAdapter, SeedItem
from ..runner import register_adapter


# Default repos to import
DEFAULT_REPOS = [
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
        # How far back to fetch commits (days). 0 = no limit (relies on dedup).
        self.days_back = config.get("days_back", 0) if config else 0

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
        """Fetch README, commits, PRs, and issues from repos."""
        items = []

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            # Auto-discover repos if not using explicit list
            repos_to_fetch = self.repos
            if self.config.get("auto_discover", False):
                discovered = await self._discover_repos(client, headers)
                if discovered:
                    repos_to_fetch = discovered
                    logger.info(f"Auto-discovered {len(discovered)} repos")

            for repo_full_name in repos_to_fetch:
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

                    # Import PRs (if days_back set, only recent)
                    prs = await self._fetch_prs(client, headers, repo_full_name, repo)
                    items.extend(prs)

                    # Import issues (if days_back set, only recent)
                    issues = await self._fetch_issues(client, headers, repo_full_name, repo)
                    items.extend(issues)

                    if len(items) >= limit:
                        break

                except Exception as e:
                    logger.error(f"Error fetching {repo_full_name}: {e}")

        logger.info(f"Returning {len(items)} GitHub items for import")
        return items[:limit]

    async def _discover_repos(
        self,
        client: httpx.AsyncClient,
        headers: dict,
    ) -> list[str]:
        """Auto-discover repos by fetching user's recently pushed repos."""
        try:
            response = await client.get(
                "https://api.github.com/user/repos",
                headers=headers,
                params={"sort": "pushed", "per_page": 100, "type": "owner"},
            )
            if response.status_code == 200:
                repos = response.json()
                return [r["full_name"] for r in repos if not r.get("fork")]
        except Exception as e:
            logger.warning(f"Repo auto-discovery failed: {e}")
        return DEFAULT_REPOS

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
                                content_type="code",
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
            # Get recent commits (with optional date windowing)
            params = {"per_page": 50}
            if self.days_back > 0:
                since = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
                params["since"] = since
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/commits",
                headers=headers,
                params=params,
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
                    content_type="commit",
                ))

        except Exception as e:
            logger.warning(f"Failed to fetch commits for {repo_full_name}: {e}")

        return items

    async def _fetch_prs(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        repo_full_name: str,
        repo: dict,
    ) -> list[SeedItem]:
        """Fetch pull requests from repo."""
        items = []
        try:
            params = {"state": "all", "sort": "updated", "per_page": 30, "direction": "desc"}
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/pulls",
                headers=headers,
                params=params,
            )
            if response.status_code != 200:
                return items

            prs = response.json()
            cutoff = None
            if self.days_back > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

            for pr in prs:
                updated_str = pr.get("updated_at", "")
                if updated_str:
                    updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    if cutoff and updated_at < cutoff:
                        continue
                else:
                    updated_at = None

                title = pr.get("title", "")
                body = pr.get("body") or ""
                state = pr.get("state", "open")
                merged = pr.get("merged_at") is not None
                number = pr.get("number")

                status_label = "merged" if merged else state
                content = f"""# PR #{number}: {title}

**Repository:** {repo['name']}
**Status:** {status_label}
**Author:** {pr.get('user', {}).get('login', 'Unknown')}
**Created:** {pr.get('created_at', '')[:10]}
**Updated:** {updated_str[:10] if updated_str else 'Unknown'}

{body[:3000]}
"""
                items.append(SeedItem(
                    title=f"PR [{repo['name']}] #{number}: {title[:50]}",
                    content=content,
                    source_url=pr.get("html_url"),
                    source_id=f"pr-{repo_full_name}-{number}",
                    topics=self._extract_topics(repo) + ["pull-request"],
                    created_at=updated_at,
                    metadata={
                        "type": "pull_request",
                        "repo": repo_full_name,
                        "number": number,
                        "state": status_label,
                    },
                    content_type="code",
                ))

        except Exception as e:
            logger.warning(f"Failed to fetch PRs for {repo_full_name}: {e}")

        return items

    async def _fetch_issues(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        repo_full_name: str,
        repo: dict,
    ) -> list[SeedItem]:
        """Fetch issues (excluding PRs) from repo."""
        items = []
        try:
            params = {"state": "all", "sort": "updated", "per_page": 30, "direction": "desc"}
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/issues",
                headers=headers,
                params=params,
            )
            if response.status_code != 200:
                return items

            issues = response.json()
            cutoff = None
            if self.days_back > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

            for issue in issues:
                # Skip pull requests (GitHub returns PRs in issues endpoint)
                if issue.get("pull_request"):
                    continue

                updated_str = issue.get("updated_at", "")
                if updated_str:
                    updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    if cutoff and updated_at < cutoff:
                        continue
                else:
                    updated_at = None

                title = issue.get("title", "")
                body = issue.get("body") or ""
                state = issue.get("state", "open")
                number = issue.get("number")
                labels = [l.get("name", "") for l in issue.get("labels", [])]

                content = f"""# Issue #{number}: {title}

**Repository:** {repo['name']}
**Status:** {state}
**Labels:** {', '.join(labels) if labels else 'none'}
**Author:** {issue.get('user', {}).get('login', 'Unknown')}
**Created:** {issue.get('created_at', '')[:10]}

{body[:3000]}
"""
                items.append(SeedItem(
                    title=f"Issue [{repo['name']}] #{number}: {title[:50]}",
                    content=content,
                    source_url=issue.get("html_url"),
                    source_id=f"issue-{repo_full_name}-{number}",
                    topics=self._extract_topics(repo) + ["issue"],
                    created_at=updated_at,
                    metadata={
                        "type": "issue",
                        "repo": repo_full_name,
                        "number": number,
                        "state": state,
                    },
                    content_type="code",
                ))

        except Exception as e:
            logger.warning(f"Failed to fetch issues for {repo_full_name}: {e}")

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
