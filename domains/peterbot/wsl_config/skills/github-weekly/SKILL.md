---
name: github-weekly
description: Weekly GitHub activity recap across all repos
trigger:
  - "weekly dev recap"
  - "weekly github"
  - "week's commits"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Weekly GitHub Activity Recap

## Purpose

Sunday evening recap of the full week's GitHub activity across all Chris's repos. Covers commits, merged PRs, and highlights the busiest repo and quietest day.

## Pre-fetched Data

Same structure as github-activity but with `mode: "weekly"` and 7 days of data.

## Output Format

```
**Weekly Dev Recap** - w/c 3 March

28 commits across 3 repos, 7 PRs merged

**hadley-bricks-inventory-management** (15 commits, 4 PRs)
- feat: octopus energy charts and billing
- feat: school integration scripts
- PR #235: Octopus Energy integration
- PR #234: School integration
- PR #233: Interactive picklists
- PR #232: Delivery report pipeline

**discord-messenger** (10 commits, 2 PRs)
- feat: github activity skill
- fix: whatsapp webhook LID handling
- PR #48: GitHub activity integration
- PR #47: Evolution API groups

**family-meal-planner** (3 commits, 1 PR)
- feat: Gousto recipe import
- PR #12: Gousto integration

Top repo: hadley-bricks (15 commits)
```

## Rules

- Use the pre-fetched data only
- Show repos sorted by commit count (busiest first)
- Skip repos with zero activity
- Max 6 commit messages per repo (pick the most descriptive)
- Always show merged PRs with number and title
- If zero activity across all repos, respond with `NO_REPLY`
- Add "Top repo" line at the end
- Keep it concise - overview not changelog
