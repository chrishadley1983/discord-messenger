---
name: knowledge-digest
description: Weekly Second Brain knowledge digest
trigger:
  - "knowledge digest"
  - "brain digest"
  - "second brain summary"
scheduled: true
conversational: true
channel: #peterbot
---

# Knowledge Digest

## Purpose

Weekly summary of Second Brain activity:
- New items saved (explicit and passive)
- New connections discovered
- Items that are fading and need attention
- Most accessed item
- Overall stats

Runs weekly on Sundays to provide a knowledge roundup.

## Pre-fetched Data

Data is fetched from `domains.second_brain.digest.get_digest_for_skill()`:

```json
{
  "total_items": 42,
  "total_connections": 15,
  "new_items_count": 7,
  "new_items": [
    {"title": "LEGO Investing Guide", "capture_type": "explicit", "topics": ["lego", "investing"]},
    ...
  ],
  "new_connections_count": 3,
  "new_connections": [
    {"type": "cross_domain", "description": "Business and fitness overlap", "similarity": 82},
    ...
  ],
  "fading_items": [
    {"title": "Marathon Training Plan", "decay_score": 25},
    ...
  ],
  "most_accessed": {"title": "Tax Self-Assessment Guide", "access_count": 5},
  "formatted_message": "# 🧠 Weekly Second Brain Digest\n..."
}
```

## Output Format

Use the `formatted_message` from pre-fetched data directly if available. Otherwise, format like:

```
# 🧠 Weekly Second Brain Digest

**Total Knowledge:** 42 items | 15 connections

## 📥 New This Week (7 items)

💾 LEGO Investing Guide
💾 Marathon Training Plan
👁️ Reddit Discussion on Tax
*...and 4 more*

## 🔗 Connections Discovered (3)

🔀 Business and fitness overlap (82% match)
🏷️ Shared topics: running, nutrition (78% match)

## ⏳ Fading Knowledge

- Marathon Training Plan (25% relevance)
- Old Tax Notes (18% relevance)

*Use `/recall` to revisit these and boost their relevance*

## ⭐ Most Accessed This Week
**Tax Self-Assessment Guide** (5 accesses)

---
**Commands:** `/save` `/recall` `/knowledge`
```

## Rules

1. Use emoji sparingly: 🧠 💾 👁️ 🔗 🔀 🏷️ ⏳ ⭐
2. Keep under 2000 chars
3. If no new items and no connections, say so briefly
4. Return `NO_REPLY` only if the digest service is completely unavailable

## When to Trigger

- Weekly on Sundays (scheduled)
- On-demand via "knowledge digest" or "brain digest"
