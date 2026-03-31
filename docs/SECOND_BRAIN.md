# Second Brain -- Knowledge Management System

Unified long-term memory system built on Supabase PostgreSQL with pgvector for semantic search. Stores conversation memories, articles, notes, recipes, travel plans, fitness data, financial summaries, and more. 2,943+ knowledge items with gte-base (768-dim) embeddings.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Model](#data-model)
3. [Processing Pipeline](#processing-pipeline)
4. [Embedding Strategy](#embedding-strategy)
5. [Search System](#search-system)
6. [Decay and Relevance Model](#decay-and-relevance-model)
7. [Connection Discovery](#connection-discovery)
8. [Capture Flows](#capture-flows)
9. [Seed Adapters](#seed-adapters)
10. [MCP Servers](#mcp-servers)
11. [Hadley API Endpoints](#hadley-api-endpoints)
12. [Health Monitoring](#health-monitoring)
13. [Weekly Digest](#weekly-digest)
14. [Contextual Surfacing](#contextual-surfacing)
15. [Configuration Reference](#configuration-reference)
16. [File Reference](#file-reference)

---

## Architecture Overview

```
Content Sources                    Pipeline                         Storage & Retrieval
+------------------+    +------------------------+    +----------------------+
| Passive capture  |    | pipeline.py            |    | Supabase PostgreSQL  |
| (conversations)  |--->| extract -> chunk ->    |--->| knowledge_items      |
|                  |    | summarise -> tag ->    |    | knowledge_chunks     |
| Seed adapters    |    | structured_extract ->  |    | knowledge_connections|
| (email, calendar,|    | embed -> connect       |    | (pgvector 0.8.0)     |
|  github, garmin, |    +------------------------+    +----------+-----------+
|  spotify, etc.)  |                                            |
|                  |    +------------------------+    +---------v-----------+
| Manual saves     |    | MCP Server             |    | Hybrid search        |
| (save_to_brain)  |    | (second_brain_mcp.py)  |<---| (vector + keyword)   |
|                  |    +------------------------+    |                      |
| Hadley API       |                                  | MMR re-ranking       |
| (/brain/save)    |    +------------------------+    | (diversity control)  |
+------------------+    | Contextual surfacing   |    +---------------------+
                        | (surfacing.py)         |
                        | Injects into Peter's   |
                        | response context       |
                        +------------------------+
```

### Key Design Decisions

- **Supabase REST API over SDK**: All database operations use raw `httpx` calls to Supabase's REST API (`/rest/v1/`) and RPCs (`/rpc/`), not the Supabase Python SDK. This provides full control over connection pooling and timeout behaviour.
- **HuggingFace Inference API for embeddings**: The Supabase Edge Function `embed` was planned but never deployed. Embeddings use HuggingFace's `router.huggingface.co` endpoint for gte-base.
- **Claude via Hadley API**: Summarisation, tagging, and structured extraction all use a local Claude proxy (`/claude/extract` on Hadley API) which calls `claude -p` CLI under the hood -- no API key needed.
- **Graceful degradation**: Every pipeline step has fallbacks. If summarisation fails, the first 200 characters are used. If tagging fails, keyword-based fallback tags are generated. If embedding fails, the item is stored as `pending` for later reprocessing.

---

## Data Model

### knowledge_items

The primary table storing all knowledge content.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `content_type` | text | Article, note, recipe, fitness, email, etc. (see ContentType enum) |
| `capture_type` | text | `explicit`, `passive`, `seed`, `imported`, `manual` |
| `title` | text | Generated or extracted title |
| `source_url` | text | URL or `direct_input` identifier |
| `source_message_id` | text | Discord message ID for conversation captures |
| `source_system` | text | Origin system (e.g. `discord`, `seed:github`, `mcp:claude-code`) |
| `full_text` | text | Complete content text |
| `summary` | text | 2-3 sentence AI-generated summary |
| `topics` | text[] | 3-8 auto-extracted topic tags |
| `base_priority` | float | Priority multiplier: explicit=1.0, seed=0.8, passive=0.3 |
| `decay_score` | float | Current relevance score (time-decay + access boost) |
| `access_count` | int | Number of times accessed/surfaced |
| `last_accessed_at` | timestamptz | Last access timestamp |
| `status` | text | `pending`, `active`, `archived` |
| `facts` | jsonb | Extracted factual statements (up to 12) |
| `concepts` | jsonb | Extracted insights with type/label/detail (up to 5) |
| `user_note` | text | Optional user annotation |
| `site_name` | text | Source website name |
| `word_count` | int | Content word count |
| `promoted_at` | timestamptz | When passive item was promoted to active |
| `created_at` | timestamptz | Creation timestamp |
| `updated_at` | timestamptz | Last update timestamp |

### knowledge_chunks

Searchable text segments linked to parent items. Each item is split into ~300-word overlapping chunks, each with its own embedding vector for fine-grained semantic search.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `parent_id` | UUID (FK) | References knowledge_items.id |
| `chunk_index` | int | Position within parent item |
| `content` | text | Chunk text (~300 words) |
| `embedding` | vector(768) | gte-base embedding for semantic search |
| `created_at` | timestamptz | Creation timestamp |

### knowledge_connections

Discovered relationships between knowledge items.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `item_a_id` | UUID (FK) | First item |
| `item_b_id` | UUID (FK) | Second item |
| `connection_type` | text | `semantic`, `topic_overlap`, `cross_domain` |
| `description` | text | Human-readable description |
| `similarity_score` | float | Cosine similarity between items |
| `surfaced` | bool | Whether connection has been shown to user |
| `surfaced_at` | timestamptz | When surfaced |
| `created_at` | timestamptz | Discovery timestamp |

### Content Types (ContentType Enum)

```
article, note, idea, voice_memo, url, document, conversation_extract,
bookmark, training_data, social_save, calendar_event, calendar_pattern,
key_date, video, discussion, pdf, code, social, recipe, fitness, email,
financial_report, commit, listening_history, viewing_history,
health_activity, travel_booking, reference
```

### Item Statuses (ItemStatus Enum)

| Status | Meaning |
|--------|---------|
| `pending` | Passive capture awaiting full processing (no embeddings yet) |
| `active` | Fully processed and searchable |
| `archived` | Soft-deleted (excluded from search) |

---

## Processing Pipeline

The full pipeline is orchestrated by `pipeline.py::process_capture()`. Steps run in a specific order with concurrent execution where possible.

### Step-by-Step Flow

```
1. DUPLICATE CHECK
   - If source contains "://" (URL), check if already saved
   - If duplicate found, boost access count and return existing item

2. CONTENT EXTRACTION (extract.py)
   - URLs: fetch via httpx, parse with readability-lxml
   - YouTube: extract title + description via oEmbed
   - Reddit: extract post body
   - PDFs: text extraction
   - Plain text: use directly

3. TITLE GENERATION
   - Use extracted title, or generate via Claude API
   - Fallback: first 100 chars of content

4. CONCURRENT PROCESSING (asyncio.gather)
   a. SUMMARISATION (summarise.py)
      - Claude API: "Summarise in 2-3 sentences, focus on key insight"
      - Fallback: first paragraph or first 200 chars

   b. TOPIC EXTRACTION (tag.py)
      - Claude API: content-type-aware tagging prompt
      - 3-8 tags per item from known domain taxonomy
      - Fallback: keyword-based matching against known tags

   c. STRUCTURED EXTRACTION (extract_structured.py)
      - Claude API: extract facts (strings) and concepts (label/type/detail)
      - Content-type-specific prompts (email, health, financial, etc.)
      - Up to 12 facts, 5 concepts per item
      - Skipped for listening_history and viewing_history types

5. CHUNKING (chunk.py)
   - Split into ~300-word segments with 50-word overlap
   - Smart break detection: paragraph > sentence > clause > whitespace
   - Title prepended to each chunk for embedding context

6. EMBEDDING GENERATION (embed.py)
   - Batch request to HuggingFace gte-base model
   - Fallback: concurrent individual requests
   - 60-second TTL in-memory cache (MD5-keyed)
   - On failure: item saved as "pending" for later reprocessing

7. DATABASE STORAGE (db.py)
   - Insert knowledge_item with all metadata
   - Insert knowledge_chunks with embeddings
   - If embedding failed: set status to "pending"

8. CONNECTION DISCOVERY (connections.py)
   - Search for similar existing items
   - Create connections where similarity > 0.72
   - Classify as: semantic, topic_overlap, or cross_domain
```

### Batch Pipeline

For seed imports, `prepare_capture()` runs steps 1-5 without embedding, returning a `PreparedItem`. Embeddings are then generated in efficient batches, reducing API calls. This is used by the incremental seed process.

### Passive Capture Pipeline

Lightweight path via `process_passive_capture()`:
- No Claude API calls (no summary, no AI tagging)
- Uses keyword-based fallback for topics
- Status set to `pending` (no embeddings)
- Upgraded to full items by `reprocess_pending_items()` every 6 hours

---

## Embedding Strategy

### Model

- **Model**: `thenlper/gte-base` (768 dimensions)
- **Provider**: HuggingFace Inference API via `router.huggingface.co`
- **Note**: The Supabase Edge Function `embed` was planned but never deployed. The `CLAUDE.md` memory entry about gte-small (384-dim) is outdated -- the actual config uses gte-base (768-dim).

### Implementation Details

| Parameter | Value |
|-----------|-------|
| Dimensions | 768 |
| Text limit | 8,000 chars (truncated) |
| Single timeout | 60 seconds |
| Batch timeout | 120 seconds |
| Max retries | 5 (exponential backoff + jitter) |
| Max concurrent | 5 (semaphore-limited) |
| Cache TTL | 60 seconds (MD5-keyed, max 100 entries) |

### Retry Strategy

- **429 (rate limit)**: Respects `Retry-After` header, exponential backoff
- **502/503 (gateway/cold start)**: Sends `wait_for_model: true` on retry after 503; uses `estimated_time` from response body
- **402 (credits exhausted)**: Immediate failure with actionable error message
- **Jitter**: +/-25% on all retry delays to prevent thundering herd
- **Observability**: In-memory counters track ok/fail/retry/cache stats via `get_embedding_stats()`

---

## Search System

### Hybrid Search (db.py::hybrid_search)

The primary search function combines two strategies:

```
1. VECTOR (SEMANTIC) SEARCH
   - Generate query embedding via gte-base
   - Call search_knowledge RPC (cosine similarity on knowledge_chunks)
   - Group results by parent item
   - Filter: min_similarity (default 0.75), min_decay (default 0.2)

2. KEYWORD FALLBACK
   - Triggered when: zero vector results OR best similarity < 0.80
   - Uses keyword_search_knowledge RPC (PostgreSQL tsvector/tsquery)
   - No embedding needed -- purely text-based
   - Merges unique results with vector results

3. MMR RE-RANKING (Maximal Marginal Relevance)
   - Balances relevance with diversity
   - score = 0.7 * similarity - 0.3 * max_topic_overlap_with_selected
   - Topic overlap measured via Jaccard similarity on tag arrays
   - Prevents returning 5 results all about the same subtopic
```

### Search RPC Functions (Supabase)

| RPC | Purpose |
|-----|---------|
| `search_knowledge` | Vector similarity search on knowledge_chunks |
| `keyword_search_knowledge` | Full-text search via tsvector/tsquery |
| `boost_item_access` | Atomic access count increment + decay recalculation |
| `get_orphaned_items` | Active items with zero chunks (unsearchable) |
| `get_decay_distribution` | Decay score bucketing for health reports |
| `get_connection_coverage` | Connection stats for health reports |

### Search Scoring

Results are ranked by `weighted_score`:

```
weighted_score = best_similarity * decay_score * base_priority
```

Where:
- `best_similarity` = highest cosine similarity among matching chunks
- `decay_score` = time-decay with access boost (see next section)
- `base_priority` = capture type priority (explicit=1.0, seed=0.8, passive=0.3)

---

## Decay and Relevance Model

Implemented in `decay.py`. Every knowledge item has a `decay_score` that decreases over time but gets boosted when accessed.

### Formula

```
base_decay = 0.5 ^ (days_since_last_access / 90)
access_boost = 1 + log2(access_count + 1)
final_score = base_priority * base_decay * access_boost
```

### Parameters

| Parameter | Value | Effect |
|-----------|-------|--------|
| Half-life | 90 days | Score halves every 90 days without access |
| Access boost factor | log2(n+1) | 10 accesses = 3.5x boost, 100 = 6.7x boost |
| Search min decay | 0.2 | Items below this are excluded from search |
| Fading threshold | 0.3 | Items below this are flagged in weekly digest |

### Decay Lifecycle

1. **New item**: decay_score = base_priority (1.0 for explicit, 0.8 for seed)
2. **Each access**: access_count incremented, decay recalculated with new timestamp
3. **Over time**: score decays exponentially toward 0
4. **Below 0.2**: excluded from search results (effectively invisible)
5. **Archived**: removed from search entirely

---

## Connection Discovery

Implemented in `connections.py`. Automatically discovers relationships between knowledge items when new content is saved.

### Connection Types

| Type | How Detected | Value |
|------|-------------|-------|
| `semantic` | High embedding similarity between chunks (>0.72) | Standard |
| `topic_overlap` | Shared topic tags (Jaccard similarity) | Standard |
| `cross_domain` | Different domain groups but semantically related | Highest -- surfaces unexpected relationships |

### Domain Groups

```python
DOMAIN_GROUPS = {
    'business': {'hadley-bricks', 'ebay', 'bricklink', 'brick-owl', 'amazon', 'finance', ...},
    'lego':     {'lego', 'lego-investing', 'retired-sets', 'minifigures', ...},
    'fitness':  {'running', 'marathon', 'training', 'nutrition', 'garmin'},
    'family':   {'family', 'max', 'emmie', 'abby', 'japan-trip', 'recipe', ...},
    'tech':     {'tech', 'development', 'peterbot', 'familyfuel'},
}
```

Cross-domain connections (e.g. a fitness insight that relates to a LEGO business decision) are the most valuable and are highlighted in weekly digests.

### Discovery Process

1. When a new item is saved, search for similar existing items
2. For each match above the similarity threshold (0.72):
   - Determine connection type based on topic group overlap
   - Store connection with description and similarity score
3. New connections are flagged as `surfaced=false` until shown to user
4. Weekly digest surfaces up to 5 unsurfaced connections

---

## Capture Flows

### 1. Explicit Capture (User-Initiated)

Triggered by:
- `save_to_brain` MCP tool (from Claude Desktop or Claude Code)
- `POST /brain/save` Hadley API endpoint
- Peter auto-saving substantial content

Flow: Full pipeline (`process_capture` with `CaptureType.EXPLICIT`, priority 1.0)

### 2. Passive Capture (Auto-Detected)

Triggered by:
- URLs shared in Discord conversations (excluding Discord, localhost, tenor, giphy)
- Messages containing signal phrases: "idea:", "note to self", "don't forget", "remember to", etc.
- Filtered: questions and commands to Peter are excluded

Flow: Lightweight pipeline (`process_passive_capture`, priority 0.3, status `pending`)

### 3. Seed Import (Bulk)

Triggered by:
- Incremental seed job (daily at 1am UK)
- Manual seed runs via CLI

Flow: Batch pipeline (`prepare_capture` + batch embeddings, `CaptureType.SEED`, priority 0.8)

### 4. Reprocess Pending (Background)

Triggered by: Scheduled job (every 6 hours)

Flow: Takes `pending` items, runs full summarisation/tagging/embedding, promotes to `active`

### Passive Detection Rules

Messages are captured passively only if:
1. They contain a URL (excluding Discord, localhost, GIF services)
2. OR they contain a signal phrase AND are at least 5 words long
3. AND they do not match exclude patterns (questions like "what is", "how do i", etc.)
4. AND they are not commands (starting with `!`, `/`, or addressed to Peter)

---

## Seed Adapters

Import data from external sources into the knowledge base. Located in `domains/second_brain/seed/adapters/`.

### Available Adapters

| Adapter | Source System | Content Type | What It Imports |
|---------|--------------|-------------|-----------------|
| `CalendarEventsAdapter` | `seed:gcal` | calendar_event | Google Calendar events |
| `EmailImportAdapter` | `seed:email` | email | Gmail emails |
| `HadleyBricksEmailAdapter` | `seed:email` | email | Hadley Bricks business emails |
| `GitHubProjectsAdapter` | `seed:github` | code/commit | Repository activity, PRs, commits |
| `GarminActivitiesAdapter` | `seed:garmin` | fitness | Running, cycling, workout activities |
| `GarminHealthAdapter` | `seed:garmin-health` | health_activity | Sleep, body composition, health metrics |
| `WithingsAdapter` | `seed:withings` | health_activity | Withings scale/health device data |
| `RecipeAdapter` | `seed:familyfuel` | recipe | Saved recipes from Family Fuel |
| `FinanceSummaryAdapter` | `seed:finance` | financial_report | Financial data summaries |
| `SpotifyListeningAdapter` | `seed:spotify` | listening_history | Spotify listening data |
| `NetflixViewingAdapter` | `seed:netflix` | viewing_history | Netflix viewing history |
| `TravelBookingAdapter` | `seed:travel` | travel_booking | Travel bookings and plans |
| `BookmarksAdapter` | `seed:bookmarks` | bookmark | Saved bookmarks |
| `ClaudeHistoryAdapter` | `seed:claude` | conversation_extract | Claude Desktop conversation history |
| `ClaudeCodeHistoryAdapter` | `seed:claude-code` | conversation_extract | Claude Code session history |
| `EmailLinkScraperAdapter` | `seed:email` | article | Links extracted from emails |
| `PeterInteractionsAdapter` | `seed:peter` | conversation_extract | Peter Discord interactions |
| `RedditAdapter` | `seed:reddit` | discussion | Reddit saved posts/comments |
| `SchoolAdapter` | `seed:school` | reference | School-related data |

### Incremental Seed Schedule

Runs daily at 1am UK via the bot scheduler:

| Source | Items per run | Lookback |
|--------|--------------|----------|
| Calendar events | 50 | ~5 weeks |
| Emails | 100 | ~5 weeks |
| GitHub projects | 30 | Recent activity |
| Garmin activities | 30 | ~1 week |

---

## MCP Servers

### Second Brain MCP (`mcp_servers/second_brain_mcp.py`)

Exposes 6 tools to Claude Desktop and Claude Code via MCP protocol.

| Tool | Type | Parameters | Description |
|------|------|-----------|-------------|
| `search_knowledge` | Read | `query`, `limit` (5), `min_similarity` (0.7) | Semantic + keyword hybrid search |
| `get_recent_items` | Read | `limit` (10), `days_back` (7) | Browse items by date |
| `browse_topics` | Read | none | List all topics with item counts |
| `get_item_detail` | Read | `item_id` (UUID) | Full text, summary, facts, concepts, connections |
| `list_items` | Read | `limit`, `offset`, `content_type`, `topic`, `sort_by`, `order` | Paginated browse with filters |
| `save_to_brain` | Write | `content`, `note`, `tags` | Save URL or text through full pipeline |

**Search tool behaviour**: Uses `hybrid_search` (vector first, keyword fallback). Returns full chunk content for each match, with facts and concepts. Access count is boosted for viewed items via `get_item_detail`.

### Financial Data MCP (`mcp_servers/financial_data_mcp.py`)

Separate MCP server for personal finance and Hadley Bricks business data. 11 tools:

| Tool | Purpose |
|------|---------|
| `get_net_worth` | Net worth across all accounts |
| `get_budget_status` | Budget vs actual spending |
| `get_spending_by_category` | Spending breakdown |
| `get_savings_rate` | Savings rate calculation |
| `get_fire_status` | FIRE progress tracking |
| `find_recurring_transactions` | Subscription detection |
| `search_transactions_tool` | Transaction search |
| `get_transactions_by_category` | Category drill-down |
| `get_business_pnl` | Hadley Bricks P&L |
| `get_platform_revenue` | Revenue by platform (eBay, Amazon, BrickLink, Brick Owl) |
| `get_financial_health` | Comprehensive financial overview |

### MCP Config Locations

| Environment | Config File |
|------------|-------------|
| Windows (Claude Desktop) | `~/.claude.json` + `.mcp.json` |
| WSL (Peterbot) | `/home/chris_hadley/.claude.json` |

---

## Hadley API Endpoints

REST endpoints on port 8100 for external access to the Second Brain.

### GET /brain/search

Semantic search across the knowledge base.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string (required) | -- | Search query |
| `limit` | int | 5 (max 20) | Max results |
| `min_similarity` | float | 0.75 (0-1) | Minimum similarity |

Response includes: id, title, summary, source, topics, similarity, weighted_score, excerpts, content_type, created_at.

### POST /brain/save

Save content to the knowledge base.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | URL or text content |
| `note` | string | No | Personal annotation |
| `tags` | string | No | Comma-separated tags |

### GET /brain/stats

Returns total item count, top 20 topics with counts, and 5 most recent items.

### DELETE /brain/item/{item_id}

Soft-delete (archive) a knowledge item by UUID.

---

## Health Monitoring

Implemented in `health.py`. Provides comprehensive diagnostics via `get_health_report()`.

### Health Report Contents

| Metric | Source | Warning Threshold |
|--------|--------|-------------------|
| Pending items (embedding failures) | Direct query | > 0 |
| Orphaned items (active but zero chunks) | `get_orphaned_items` RPC | > 0 |
| Decay distribution (below 0.2 / 0.2-0.5 / above 0.5) | `get_decay_distribution` RPC | > 50% below 0.2 |
| Embedding failure rate (session) | In-memory counters | > 10% |
| Connection coverage | `get_connection_coverage` RPC | Informational |
| Items created in last 7 days | Direct query | Informational |
| Most accessed item this week | Direct query | Informational |

### Reporting Formats

- **Daily** (`format_daily_discord`): Single line if healthy, warnings list if issues detected
- **Weekly** (`format_weekly_discord`): Full breakdown with decay distribution, connection coverage, embedding pipeline stats, recent captures sample, and fading items

### Scheduled Checks

- **Daily health check**: Runs via system-health skill at 06:50 UK
- **Weekly digest**: Runs Sunday 9:00 AM via knowledge-digest skill

---

## Weekly Digest

Generated by `digest.py::generate_weekly_digest()`. Produces a `DigestData` object containing:

| Component | Description |
|-----------|-------------|
| `new_items` | All items created in the past 7 days |
| `new_connections` | Up to 5 unsurfaced connections |
| `fading_items` | Up to 5 items falling below relevance threshold |
| `most_accessed_item` | Most accessed item this week |
| `total_items` | Total active item count |
| `total_connections` | Total connection count |

The digest is formatted for Discord and also available as structured data via `get_digest_for_skill()` for the weekly-knowledge-digest scheduled skill.

---

## Contextual Surfacing

Implemented in `surfacing.py`. Automatically injects relevant knowledge into Peter's response context when users send messages.

### Flow

```
1. should_surface(message)
   - Skip: < 3 words, greetings, commands (!, /, @)

2. hybrid_search(message, min_similarity=0.75, min_decay=0.2)
   - Returns up to 3 most relevant items

3. boost_access() for each surfaced item

4. format_context_for_claude(results)
   - Generates markdown context block with:
     - Title and similarity percentage
     - Summary
     - Best matching excerpt (if different from summary)
     - Source URL
     - Key facts (up to 3)
     - Topic tags
   - Instruction: "Reference this knowledge naturally if relevant"
   - Instruction: "Don't mention 'Second Brain' explicitly unless asked"
```

### Surfacing Limits

| Parameter | Value |
|-----------|-------|
| Max context items | 3 |
| Min similarity | 0.75 |
| Min decay score | 0.2 |
| Min message length | 3 words |

---

## Configuration Reference

All constants defined in `domains/second_brain/config.py`.

### Chunking

| Constant | Value | Description |
|----------|-------|-------------|
| `CHUNK_SIZE` | 300 | Words per chunk |
| `CHUNK_OVERLAP` | 50 | Word overlap between chunks |
| `MAX_CHUNKS_PER_ITEM` | 40 | Max chunks (~12,000 words) |
| `MIN_CONTENT_WORDS` | 10 | Reject trivially short content |
| `MAX_CONTENT_WORDS` | 10,000 | Truncate with note |

### Embeddings

| Constant | Value | Description |
|----------|-------|-------------|
| `EMBEDDING_MODEL` | `gte-base` | HuggingFace model name |
| `EMBEDDING_DIMENSIONS` | 768 | Vector dimensions |
| `EMBEDDING_TEXT_LIMIT` | 8,000 | Max chars before truncation |
| `EMBEDDING_MAX_RETRIES` | 5 | Retry attempts |
| `EMBEDDING_RETRY_BASE_DELAY` | 2.0s | Base exponential backoff |
| `EMBEDDING_MAX_CONCURRENT` | 5 | Concurrent request limit |

### Search and Similarity

| Constant | Value | Description |
|----------|-------|-------------|
| `SIMILARITY_THRESHOLD` | 0.75 | Min for contextual surfacing |
| `CONNECTION_THRESHOLD` | 0.72 | Min for connection discovery |
| `SEARCH_MIN_DECAY` | 0.2 | Skip heavily decayed items |
| `MAX_SEARCH_RESULTS` | 10 | Max search results |
| `MAX_CHUNKS_PER_SEARCH` | 20 | Max chunk matches per search |
| `MMR_LAMBDA` | 0.7 | 70% relevance, 30% diversity |
| `KEYWORD_FALLBACK_THRESHOLD` | 0.80 | Trigger keyword search below this |

### Decay

| Constant | Value | Description |
|----------|-------|-------------|
| `DECAY_HALF_LIFE_DAYS` | 90 | Score halves every 90 days |
| `ACCESS_BOOST_FACTOR` | 0.2 | log2(access+1) multiplier |

### Priority Levels

| Constant | Value | Capture Type |
|----------|-------|-------------|
| `PRIORITY_EXPLICIT` | 1.0 | User-initiated saves |
| `PRIORITY_SEED` | 0.8 | Bulk imports |
| `PRIORITY_PASSIVE` | 0.3 | Auto-detected |

### Structured Extraction

| Constant | Value | Description |
|----------|-------|-------------|
| `STRUCTURED_EXTRACTION_TIMEOUT` | 30s | Claude API timeout |
| `MAX_FACTS_PER_ITEM` | 12 | Max factual statements |
| `MAX_CONCEPTS_PER_ITEM` | 5 | Max concept extractions |

### Known Domain Tags

Organised into groups for context-aware tagging:

| Group | Tags |
|-------|------|
| business | hadley-bricks, ebay, bricklink, brick-owl, amazon, bricqer, shopify |
| lego | lego, lego-investing, retired-sets, minifigures, lego-sorting |
| fitness | running, marathon, training, nutrition, garmin, parkrun, race |
| family | family, max, emmie, abby, parenting |
| travel | japan-trip, travel, flight, accommodation, holiday |
| tech | tech, development, peterbot, familyfuel, second-brain, automation |
| finance | finance, tax, self-employment, budget, net-worth, investing |
| health | health, medical, nhs, dental, withings, sleep |
| school | school, stocks-green, homework, term-dates, parents-evening |
| home | home, property, maintenance, garden, car |
| entertainment | spotify, music, netflix, tv, film, podcast |
| food | recipe, cooking, meal-planning, restaurant |

### Source System Identifiers

```python
SOURCE_DISCORD    = "discord"
SOURCE_GITHUB     = "seed:github"
SOURCE_GCAL       = "seed:gcal"
SOURCE_EMAIL      = "seed:email"
SOURCE_GARMIN     = "seed:garmin"
SOURCE_GARMIN_HEALTH = "seed:garmin-health"
SOURCE_SPOTIFY    = "seed:spotify"
SOURCE_NETFLIX    = "seed:netflix"
SOURCE_TRAVEL     = "seed:travel"
SOURCE_FINANCE    = "seed:finance"
SOURCE_FAMILYFUEL = "seed:familyfuel"
SOURCE_WITHINGS   = "seed:withings"
SOURCE_REDDIT     = "seed:reddit"
SOURCE_PETER      = "seed:peter"
SOURCE_SCHOOL     = "seed:school"
SOURCE_CLAUDE     = "seed:claude"
SOURCE_CLAUDE_CODE = "seed:claude-code"
SOURCE_BOOKMARKS  = "seed:bookmarks"
```

### Health Monitoring Thresholds

| Constant | Value | Description |
|----------|-------|-------------|
| `HEALTH_PENDING_WARN` | 0 | Warn if any pending items |
| `HEALTH_ORPHANED_WARN` | 0 | Warn if any orphaned items |
| `HEALTH_DECAY_CRITICAL_PCT` | 50% | Warn if >50% below search threshold |
| `HEALTH_EMBED_FAIL_RATE` | 10% | Warn if >10% embedding failures |

---

## File Reference

### Core Pipeline (`domains/second_brain/`)

| File | Purpose |
|------|---------|
| `config.py` | All configuration constants, known tags, `call_claude()` helper |
| `types.py` | Data classes: KnowledgeItem, KnowledgeChunk, KnowledgeConnection, SearchResult, etc. |
| `pipeline.py` | Full processing pipeline: `process_capture()`, `process_passive_capture()`, `reprocess_pending_items()`, batch `prepare_capture()` |
| `db.py` | Supabase database layer: CRUD, semantic_search, keyword_search, hybrid_search, MMR, access boost |
| `embed.py` | Embedding generation via HuggingFace gte-base with retry/cache |
| `extract.py` | Content extraction from URLs (readability-lxml, YouTube, Reddit, PDF) and plain text |
| `extract_structured.py` | AI-powered fact/concept extraction with content-type-specific prompts |
| `summarise.py` | AI summarisation (2-3 sentences) via Claude API |
| `tag.py` | AI topic tagging (3-8 tags) with known domain taxonomy |
| `chunk.py` | Text chunking (~300 words, 50 overlap, smart break detection) |
| `decay.py` | Time-decay scoring with access boost formula |
| `connections.py` | Connection discovery: semantic, topic_overlap, cross_domain |
| `surfacing.py` | Contextual knowledge injection into Peter's responses |
| `passive.py` | Passive capture detection (URLs and idea signal phrases) |
| `digest.py` | Weekly knowledge digest generation and formatting |
| `health.py` | Health monitoring: pending items, orphans, decay distribution, embedding stats |
| `conversation.py` | Conversational retrieval interface |
| `admin.py` | Administrative functions |
| `commands.py` | CLI commands for management |
| `audit_report.py` | Data audit reporting |

### Seed Adapters (`domains/second_brain/seed/adapters/`)

See [Seed Adapters](#seed-adapters) section for the complete list of 20 adapters.

### MCP Servers (`mcp_servers/`)

| File | Purpose |
|------|---------|
| `second_brain_mcp.py` | MCP server with 6 knowledge tools |
| `financial_data_mcp.py` | MCP server with 11 financial tools |
| `financial_data/` | Query modules: config, supabase_client, personal_finance, business_finance, formatters |

### Hadley API Integration

| File | Endpoints |
|------|-----------|
| `hadley_api/main.py` | `/brain/search`, `/brain/save`, `/brain/stats`, `/brain/item/{id}` |

### Infrastructure

| Component | Description |
|-----------|-------------|
| Supabase project | `modjoikyuhqzouxvieua` |
| pgvector | 0.8.0 (768-dim vectors) |
| Hadley API | Port 8100 (NSSM service `HadleyAPI`) |
| Claude CLI | Used via `/claude/extract` proxy for summarisation/tagging |
| HuggingFace | `router.huggingface.co` for gte-base embeddings (requires HF_TOKEN) |
