---
name: github-activity
description: Daily and weekly GitHub activity summary across all repos
trigger:
  - "github activity"
  - "github summary"
  - "what did I commit"
  - "dev activity"
  - "code changes"
scheduled: true
conversational: true
channel: "#peterbot"
---

# GitHub Activity Summary

## Purpose

Summarise recent GitHub activity across Chris's repositories. Runs daily (yesterday's activity) and weekly (full week recap).

## Pre-fetched Data

```json
{
  "mode": "daily|weekly",
  "period": "2026-03-05",
  "repos": {
    "discord-messenger": {
      "commits": [
        {"sha": "abc1234", "message": "feat: add github skill", "author": "Chris", "date": "2026-03-05T14:30:00Z", "url": "https://github.com/..."}
      ],
      "prs_merged": [
        {"number": 42, "title": "Add GitHub integration", "merged_at": "2026-03-05T16:00:00Z", "url": "https://github.com/..."}
      ],
      "commit_count": 5,
      "pr_count": 1
    }
  },
  "totals": {
    "commits": 12,
    "prs_merged": 3,
    "active_repos": 2
  },
  "fetch_time": "2026-03-06 08:08"
}
```

## Output Format - Daily

```
**GitHub Activity** - Wednesday, 5 March

12 commits across 2 repos, 3 PRs merged

**discord-messenger** (5 commits, 1 PR)
- feat: add github skill
- fix: whatsapp webhook timeout
- PR #42: Add GitHub integration

**hadley-bricks-inventory-management** (7 commits, 2 PRs)
- feat: octopus energy charts
- PR #235: Octopus Energy integration
- PR #234: School integration scripts

Busiest repo: hadley-bricks (7 commits)
```

## Output Format - Weekly

Same as daily but covering Mon-Sun, with an added summary line:

```
**Weekly Dev Recap** - w/c 3 March

28 commits across 3 repos, 7 PRs merged

[per-repo breakdown as above]

Top repo: hadley-bricks (15 commits)
Quietest day: Thursday (1 commit)
```

## Rules

- Use the pre-fetched data only
- Show repos sorted by commit count (busiest first)
- Skip repos with zero activity
- Max 5 commit messages per repo (pick the most descriptive, skip merge commits)
- Always show merged PRs with their number and title
- If zero activity across all repos, respond with `NO_REPLY`
- Keep it concise - this is a quick glance, not a changelog
- Use short repo names (drop the org prefix)
