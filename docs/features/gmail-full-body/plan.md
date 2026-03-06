# Gmail Full Body Retrieval for Email Seed Adapter

## Problem

The email seed adapter (`domains/second_brain/seed/adapters/email.py`) imports emails via the Hadley API's `/gmail/search` endpoint. That endpoint fetches messages with `format='metadata'` and returns only the Gmail `snippet` field (truncated to 150 chars). The `SeedItem.content` therefore contains just headers + a snippet, losing the actual email body. The Second Brain needs the full email text to be useful for recall and search.

## Current State

### Hadley API (`hadley_api/main.py`)

| Endpoint | Format | Returns body? |
|----------|--------|---------------|
| `GET /gmail/search?q=...&limit=N` | `metadata` | No -- only `snippet[:150]` |
| `GET /gmail/get?id=...` | `full` | **Yes** -- plain text or HTML-to-text, capped at 10,000 chars |

The `/gmail/get` endpoint already does exactly what is needed:
- Fetches with `format='full'`
- Recursively extracts `text/plain` or converts `text/html` to plain text
- Returns `body` (up to 10k chars), plus `from`, `to`, `subject`, `date`, `attachments`

### Email Seed Adapter

- Calls `/gmail/search` to get message IDs + metadata
- Builds `SeedItem.content` from subject, from, date, and `snippet`
- Never calls `/gmail/get` to fetch the full body

### OAuth / Scopes

`hadley_api/google_auth.py` already includes `gmail.readonly` (plus `gmail.compose`, `gmail.send`, `gmail.modify`). No scope changes are needed -- the existing token can read full message bodies.

## Plan

### Option A: Use the existing `/gmail/get` endpoint (Recommended)

No changes to the Hadley API are needed. The `/gmail/get` endpoint already returns full message bodies.

**Changes to `domains/second_brain/seed/adapters/email.py`:**

1. After fetching the list of emails from `/gmail/search`, make a second call to `/gmail/get?id={email_id}` for each email to retrieve the full body.

2. Update `_email_to_item()` to accept and use the full body text instead of the snippet.

3. Add rate-limiting / batching to avoid hammering the API (e.g. batch of 10 concurrent requests, short delay between batches).

#### Detailed Changes

**Step 1: Add a `_fetch_full_body` method**

```python
async def _fetch_full_body(self, client: httpx.AsyncClient, email_id: str) -> str | None:
    """Fetch full email body from Hadley API."""
    try:
        response = await client.get(
            f"{self.api_base}/gmail/get",
            params={"id": email_id},
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("body", "")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch body for {email_id}: {e}")
        return None
```

**Step 2: Update `fetch()` to call it**

After the search loop collects email metadata, iterate through the emails and fetch bodies. Use `asyncio.gather` with a semaphore to limit concurrency:

```python
import asyncio

# Inside fetch(), after collecting emails from search:
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent body fetches

async def fetch_with_limit(email):
    async with semaphore:
        body = await self._fetch_full_body(client, email["id"])
        return email["id"], body

tasks = [fetch_with_limit(e) for e in all_emails]
results = await asyncio.gather(*tasks)
body_map = {eid: body for eid, body in results if body is not None}
```

**Step 3: Update `_email_to_item()` signature and content template**

```python
def _email_to_item(self, email: dict, category_topics: list[str],
                   category_name: str, full_body: str | None = None) -> SeedItem | None:
    # ...
    body_text = full_body or snippet  # Fall back to snippet if body fetch failed

    content = f"""# {subject}

**From:** {sender}
**Date:** {date_str}
**Category:** {category_name}

{body_text}
"""
```

**Step 4: Add a config toggle**

Add a `fetch_full_body` config option (default `True`) so the adapter can be run in "headers only" mode for quick testing:

```python
self.fetch_full_body = config.get("fetch_full_body", True) if config else True
```

### Option B: Add a batch endpoint to the Hadley API

If performance is a concern (hundreds of sequential HTTP round-trips), add a batch endpoint:

```
POST /gmail/messages/batch
Body: { "ids": ["id1", "id2", ...] }
Response: { "messages": [ { "id": ..., "body": ..., ... }, ... ] }
```

This would use the Gmail API's batch request support (`service.new_batch_http_request()`) to fetch up to 100 messages per batch call. However, this is an optimisation -- Option A works first and can be upgraded later if needed.

## Scope Changes

None. The existing OAuth refresh token already has `gmail.readonly` which grants access to `messages.get` with `format='full'`.

## Complexity Estimate

| Item | Effort |
|------|--------|
| Option A: Update email adapter to fetch full bodies | **~30 minutes** |
| Option B: Add batch endpoint to Hadley API (optional) | **~1 hour** |
| Testing: Run adapter, verify full body in SeedItems | **~15 minutes** |

**Total (Option A): ~45 minutes**

Option A is straightforward because the Hadley API already has everything needed. The only work is in the email seed adapter -- add a second HTTP call per email and restructure the content template.

## Risks

1. **Volume**: Fetching full bodies for hundreds of emails will be slower than metadata-only. The semaphore-limited concurrency (5 parallel) should keep it manageable. For 500 emails at ~200ms per body fetch, expect ~20 seconds total with concurrency.

2. **Body size**: The `/gmail/get` endpoint caps the body at 10,000 chars. For the Second Brain's chunking pipeline, this is likely sufficient. If longer bodies are needed, the cap in `main.py` line 355 can be increased.

3. **Encoding**: The existing `html_to_text()` function in `/gmail/get` uses regex-based HTML stripping. For complex HTML emails (tables, nested divs), the output can be messy. A future improvement could use `beautifulsoup4` or `html2text` for cleaner conversion, but the current approach is adequate for import.

## Files to Change

| File | Change |
|------|--------|
| `domains/second_brain/seed/adapters/email.py` | Add body fetching, update content template |
| `hadley_api/main.py` | **No changes needed** (existing `/gmail/get` is sufficient) |
| `hadley_api/google_auth.py` | **No changes needed** (scopes already include `gmail.readonly`) |
