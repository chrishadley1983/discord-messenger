---
name: orphan-embed
description: Embed orphaned Second Brain items that have no chunks
scheduled: true
conversational: false
channel: #alerts
---

# Orphan Embed

## Purpose

Nightly maintenance job that finds active knowledge items with no chunks
(making them invisible to semantic search) and backfills their embeddings.

Items become orphaned when save paths bypass the chunking pipeline or when
embedding generation fails at save time.

## Pre-fetched Data

- `data.orphan_count`: Number of orphaned items found
- `data.embedded`: Number successfully embedded
- `data.skipped`: Number skipped (no text content)
- `data.breakdown`: Type breakdown string (e.g. "note: 5, recipe: 2")
- `data.summary`: Human-readable summary line
- `data.error`: Error message if the job failed

## Output Format

If `data.orphan_count` is 0:
```
NO_REPLY
```

If orphans were found and embedded:
```
Second Brain Maintenance -- {date}

Embedded {n} orphaned items: {breakdown}
```

If there was an error:
```
Second Brain Maintenance -- {date}

Error embedding orphans: {error}
```

## Rules

- NO_REPLY when zero orphans (most nights)
- Only post to #alerts when work was actually done or an error occurred
- Keep message concise -- one line summary
