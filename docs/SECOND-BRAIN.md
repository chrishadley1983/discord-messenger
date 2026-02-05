# Second Brain Peter — Specification

> **Purpose:** Peter's external knowledge store — explicitly saved content and passively captured context, retrievable via semantic search and surfaced proactively.  
> **Referenced by:** CLAUDE.md  
> **Companion to:** peterbot-mem (episodic memory about Chris) — this system remembers STUFF, peterbot-mem remembers YOU.  
> **Storage:** Supabase + pgvector  
> **Input channel:** Discord only  

---

## 1. Problem Statement

### 1.1 The Gap in Existing Tools

Tools like Readwise, Notion, Obsidian, Mem.ai, and NotebookLM are generic containers. They don't know about Hadley Bricks, the kids, running goals, the Japan trip, or eBay inventory. They can't connect "that article about LEGO investing" to actual sales data, or surface "your note about altitude training" because Amsterdam Marathon is coming up.

### 1.2 The Peter Difference

Peter already knows Chris's life — family, business, health, calendar, email, finances, projects. A knowledge store built on top of this context is fundamentally different from a generic PKM tool. Peter can:

1. **Connect domains** — "This article relates to your actual eBay sales"
2. **Act on knowledge** — "Want me to update your listing based on this?"
3. **Surface proactively** — relevant items before Chris asks
4. **Understand context** — "Hadley Bricks" and "VDOT 47" mean something to Peter

---

## 2. Relationship to peterbot-mem

These are **separate but connected** systems:

```
┌─────────────────────────────────────────────────────────────────┐
│                     PETER'S MEMORY SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │     peterbot-mem        │    │      Second Brain           │ │
│  │   (already exists)      │    │      (this spec)            │ │
│  ├─────────────────────────┤    ├─────────────────────────────┤ │
│  │                         │    │                             │ │
│  │ • Chris runs Hadley     │    │ • Article: LEGO investing   │ │
│  │ • Prefers concise       │    │ • Note: Bundle pricing idea │ │
│  │ • Kids: Max, Emmie      │    │ • Highlight: eBay fees 2026 │ │
│  │ • Training for marathon │    │ • Voice memo: Japan hotel   │ │
│  │                         │    │                             │ │
│  │ Auto-injected into      │    │ Retrieved on-demand via     │ │
│  │ every conversation      │    │ semantic search + proactive │ │
│  └────────────┬────────────┘    └──────────────┬──────────────┘ │
│               │                                │                 │
│               └────────────┬───────────────────┘                 │
│                            │                                     │
│                            ▼                                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   INTEGRATION LAYER                        │  │
│  │                                                            │  │
│  │  peterbot-mem references Second Brain:                     │  │
│  │  "Chris saved an article about altitude training"          │  │
│  │                                                            │  │
│  │  Second Brain queries use peterbot-mem context:            │  │
│  │  "Find items related to Hadley Bricks" (knows what that is)│  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

| Aspect | peterbot-mem | Second Brain |
|--------|-------------|--------------|
| **What it stores** | Observations FROM conversations | External content TO retrieve |
| **Source** | Peter learns from chatting | Chris explicitly saves or passively mentions |
| **Example** | "Chris prefers concise responses" | "Article about LEGO investing" |
| **Retrieval** | Auto-injected into context | On-demand search + proactive surfacing |
| **Purpose** | Peter remembers YOU | Peter remembers STUFF |
| **Storage** | SQLite + ChromaDB | Supabase + pgvector |

**They are complementary, not competing.**

---

## 3. Capture Model — Two Tiers

### 3.1 Explicit Saves (High Priority)

Triggered by `!save` command or natural language ("Peter, save this", "remember this").

**Processing pipeline:**
1. Extract content (URL → fetch + parse, text → store as-is)
2. AI summarise (2-3 sentence summary)
3. Auto-tag (topic extraction)
4. Chunk (split into ~300 word segments)
5. Embed (generate pgvector embeddings per chunk)
6. Store with high retrieval priority

**Examples:**
```
Chris: !save https://brickeconomy.com/article/lego-investing-2026
Chris: Peter, save this — I think we should offer bundle discounts on BrickLink for 3+ sets
Chris: !save Just had an idea while running — what if we used heat acclimation instead of altitude tents
```

**Peter's response to explicit save:**
```
📚 Saved: 'LEGO Investing: Why Retired Sets Beat the Stock Market'

Summary: Analysis of LEGO secondary market returns, showing retired 
sets averaging 11% annual appreciation. UCS and Star Wars themes 
outperform.

Tagged: #lego #investing #retired-sets
Connected to: Your inventory (2 sealed 75192 copies)
```

### 3.2 Passive Captures (Low Priority)

Automatically captured when Chris pastes URLs or mentions ideas naturally in conversation — without explicitly asking Peter to save them.

**Processing pipeline:**
1. Detect URL or idea-like content in message
2. Store raw content with basic metadata (timestamp, source message)
3. **No chunking, no embedding, no AI summarisation** — lightweight only
4. Lower retrieval priority than explicit saves

**Promotion:** If a passive capture matches a later search query, Peter can say:
```
"You mentioned this on 15th Jan — want me to properly save it?"
```

On confirmation, the passive capture gets promoted to a full explicit save with the complete processing pipeline.

### 3.3 Detection Rules for Passive Capture

```typescript
interface PassiveCaptureDetector {
  // URLs pasted in conversation (not inside a !save command)
  urls: RegExp;           // https?://... patterns
  
  // Idea-like phrases
  ideaSignals: string[];  // "what if", "I think we should", "idea:", 
                          // "thought:", "we could", "maybe we should",
                          // "note to self", "don't forget"
  
  // Exclude: questions, commands to Peter, casual chat
  excludePatterns: string[];  // "what is", "can you", "how do I"
}
```

### 3.4 Input Channel

**Discord only.** No email integration, no browser extension, no external endpoints. If Chris wants Peter to know about something, he tells him in Discord.

---

## 4. Data Model

### 4.1 Schema

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Parent items: articles, notes, voice memos, ideas
CREATE TABLE knowledge_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type TEXT NOT NULL,          -- 'article', 'note', 'idea', 'voice_memo', 'url'
    capture_type TEXT NOT NULL,          -- 'explicit', 'passive', or 'seed'
    title TEXT,
    source_url TEXT,
    source_message_id TEXT,              -- Discord message ID that triggered capture
    source_system TEXT,                  -- 'discord', 'seed:github', 'seed:claude', 'seed:gemini',
                                        -- 'seed:gdrive', 'seed:gcal', 'seed:email', 'seed:bookmarks',
                                        -- 'seed:garmin', 'seed:instagram'
    full_text TEXT,                      -- Complete content (for reading later)
    summary TEXT,                        -- AI-generated 2-3 sentences (explicit only)
    topics TEXT[],                       -- Auto-extracted tags
    
    -- Retrieval priority & decay
    base_priority FLOAT DEFAULT 1.0,    -- 1.0 for explicit, 0.3 for passive
    last_accessed_at TIMESTAMPTZ,       -- Boosted when retrieved
    access_count INT DEFAULT 0,         -- Times retrieved
    decay_score FLOAT DEFAULT 1.0,      -- Computed: decays over time, boosted on access
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    promoted_at TIMESTAMPTZ,            -- When passive was promoted to explicit
    
    -- Status
    status TEXT DEFAULT 'active'        -- 'active', 'archived'
);

-- Searchable chunks with embeddings (explicit saves only)
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,               -- Chunk text (~300 words)
    embedding VECTOR(1536),              -- OpenAI text-embedding-3-small
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast similarity search
CREATE INDEX knowledge_chunks_embedding_idx 
ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for decay queries
CREATE INDEX knowledge_items_decay_idx 
ON knowledge_items (decay_score DESC, status);

-- Index for topic filtering
CREATE INDEX knowledge_items_topics_idx 
ON knowledge_items USING gin (topics);

-- Connection discovery log
CREATE TABLE knowledge_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_a_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    item_b_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    connection_type TEXT NOT NULL,        -- 'semantic', 'topic_overlap', 'cross_domain'
    description TEXT,                     -- AI-generated description of the connection
    similarity_score FLOAT,
    surfaced BOOLEAN DEFAULT false,       -- Has this been shown to Chris?
    surfaced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(item_a_id, item_b_id)
);
```

### 4.2 Embedding Model

- **Model:** OpenAI `text-embedding-3-small` (1536 dimensions)
- **Cost:** ~$0.00002 per chunk. A 5-chunk article = $0.0001. Negligible.
- **Alternative:** Switch to local model later if costs become relevant (unlikely)

### 4.3 Chunking Strategy

```typescript
interface ChunkConfig {
  maxTokens: 300;         // ~300 words per chunk
  overlapTokens: 50;      // 50-word overlap between chunks for context
  splitPriority: [         // Same philosophy as RESPONSE.md chunker
    'paragraph',           // Split on double newline first
    'sentence',            // Then sentence boundaries
    'whitespace'           // Last resort
  ];
}
```

---

## 5. Processing Pipeline

### 5.1 Explicit Save Pipeline

```
Discord message with !save or "save this"
         │
         ▼
┌─────────────────────────┐
│  1. EXTRACT              │
│  URL → fetch + readability parse (strip nav/ads/boilerplate)
│  Text → store as-is     │
│  Voice → transcribe     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. SUMMARISE            │
│  Claude API → 2-3 sentence summary
│  Extract title if not provided
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  3. TAG                  │
│  Claude API → extract 3-8 topic tags
│  Match against known domains:
│    hadley-bricks, running, family,
│    japan-trip, tech, finance, lego
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  4. CHUNK                │
│  Split full_text into ~300 word segments
│  50-word overlap between chunks
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  5. EMBED                │
│  OpenAI text-embedding-3-small
│  Generate embedding per chunk
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  6. STORE                │
│  knowledge_items: parent record
│  knowledge_chunks: embedded segments
│  base_priority: 1.0 (explicit)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  7. CONNECT              │
│  Search existing chunks for semantic matches
│  Store connections above threshold (0.8)
│  Check cross-domain connections
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  8. RESPOND              │
│  Discord reply with:
│  - Summary
│  - Tags
│  - Connections found (if any)
└─────────────────────────┘
```

### 5.2 Passive Capture Pipeline

```
Discord message with URL or idea-like content
         │
         ▼
┌─────────────────────────┐
│  1. DETECT               │
│  URL regex or idea signal phrases
│  Exclude questions/commands
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. STORE (lightweight)  │
│  knowledge_items record only
│  No chunks, no embeddings
│  capture_type: 'passive'
│  base_priority: 0.3
└─────────────────────────┘
             │
             ▼
         (no response — silent capture)
```

### 5.3 Promotion Pipeline (passive → explicit)

When a passive capture matches a search query or Peter decides to surface it:

```
Peter: "You mentioned this on 15th Jan — want me to properly save it?"
Chris: "Yeah, save that"
         │
         ▼
Run full explicit pipeline (5.1) on the passive item
Set promoted_at timestamp
Update base_priority to 1.0
```

---

## 6. Retrieval — Semantic Search

### 6.1 Search Flow

```
Chris: "What do I know about Star Wars LEGO value?"
         │
         ▼
┌─────────────────────────┐
│  1. EMBED QUERY          │
│  Convert question to 1536-dim vector
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. SIMILARITY SEARCH    │
│  Find top-N chunks by cosine similarity
│  Filter: status = 'active'
│  Weight by: similarity × decay_score × base_priority
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  3. GROUP BY PARENT      │
│  Aggregate chunks → parent items
│  Rank parents by best chunk score
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  4. ENRICH               │
│  Pull peterbot-mem context for relevant domains
│  e.g. "Hadley Bricks" → knows what it is
│  Add cross-references from knowledge_connections
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  5. BOOST ACCESS         │
│  Update last_accessed_at and access_count
│  Recalculate decay_score for retrieved items
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  6. RESPOND              │
│  Natural language summary of findings
│  Cite sources and dates
│  Mention connections if relevant
└─────────────────────────┘
```

### 6.2 Search SQL

```sql
-- Semantic search with decay weighting
WITH query_embedding AS (
    SELECT $1::vector AS embedding
),
ranked_chunks AS (
    SELECT 
        kc.id,
        kc.parent_id,
        kc.content,
        ki.title,
        ki.summary,
        ki.source_url,
        ki.topics,
        ki.created_at,
        ki.decay_score,
        ki.base_priority,
        1 - (kc.embedding <=> (SELECT embedding FROM query_embedding)) AS similarity
    FROM knowledge_chunks kc
    JOIN knowledge_items ki ON kc.parent_id = ki.id
    WHERE ki.status = 'active'
    ORDER BY similarity * ki.decay_score * ki.base_priority DESC
    LIMIT 20
)
SELECT 
    parent_id,
    title,
    summary,
    source_url,
    topics,
    created_at,
    MAX(similarity) AS best_similarity,
    ARRAY_AGG(content ORDER BY similarity DESC) AS relevant_chunks
FROM ranked_chunks
GROUP BY parent_id, title, summary, source_url, topics, created_at
ORDER BY MAX(similarity * decay_score * base_priority) DESC
LIMIT 10;
```

### 6.3 Recall Command

```
Chris: !recall Star Wars LEGO value
Chris: What do I know about altitude training?
Chris: Peter, find that article about eBay fees
```

Peter responds naturally:

```
Found 3 relevant items:

1. **LEGO Investing: Why Retired Sets Beat the Stock Market**
   Saved: Dec 2025 · Source: BrickEconomy
   UCS Star Wars sets appreciate 11% annually, outperforming the S&P 500.

2. **Your note: Bundle pricing idea**
   Saved: Jan 2026
   Star Wars sets have highest margin in your inventory — consider 
   bundling for higher AOV.

3. **eBay Spring Seller Update 2026**
   Saved: Feb 2026 · Source: eBay Seller Centre
   International fees increasing 0.5% in March — relevant to your 
   EU expansion notes.
```

---

## 7. Decay Model

### 7.1 Decay Formula

```typescript
function calculateDecayScore(item: KnowledgeItem): number {
  const daysSinceCreated = daysBetween(item.created_at, now());
  const daysSinceAccessed = item.last_accessed_at 
    ? daysBetween(item.last_accessed_at, now())
    : daysSinceCreated;
  
  // Base decay: halves every 90 days without access
  const halfLife = 90; // days
  const timeDecay = Math.pow(0.5, daysSinceAccessed / halfLife);
  
  // Access boost: each access adds a multiplier
  const accessBoost = 1 + (Math.log2(item.access_count + 1) * 0.2);
  
  // Priority multiplier
  const priorityMultiplier = item.base_priority; // 1.0 explicit, 0.3 passive
  
  return timeDecay * accessBoost * priorityMultiplier;
}
```

### 7.2 Decay Behaviour

- **New explicit save:** decay_score = 1.0 (full priority)
- **After 90 days unaccessed:** decay_score ≈ 0.5
- **After 180 days unaccessed:** decay_score ≈ 0.25
- **Accessed once at 90 days:** decay_score resets and boosts (access_count multiplier)
- **Passive captures:** start at 0.3, decay faster
- **Nothing is ever deleted** — just ranked lower

### 7.3 Decay Refresh Job

Run daily (or on each retrieval):

```sql
UPDATE knowledge_items
SET decay_score = calculate_decay(created_at, last_accessed_at, access_count, base_priority)
WHERE status = 'active';
```

---

## 8. Connection Discovery

### 8.1 When Connections Are Discovered

1. **On save** — when a new explicit item is saved, search existing items for semantic matches above 0.8 similarity
2. **On scheduled scan** — weekly background job compares recent items against the full knowledge base
3. **Cross-domain** — specifically look for connections between different topic domains (e.g., a running article connecting to a business note)

### 8.2 Connection Types

```typescript
type ConnectionType = 
  | 'semantic'        // High embedding similarity between chunks
  | 'topic_overlap'   // Shared tags/topics
  | 'cross_domain';   // Different domains but related (most valuable)
```

### 8.3 Connection Discovery Logic

```typescript
async function discoverConnections(newItem: KnowledgeItem): Promise<void> {
  // Get embeddings for new item's chunks
  const newChunks = await getChunks(newItem.id);
  
  for (const chunk of newChunks) {
    // Find similar chunks from OTHER items
    const matches = await semanticSearch(chunk.embedding, {
      excludeParent: newItem.id,
      minSimilarity: 0.8,
      limit: 5
    });
    
    for (const match of matches) {
      // Check if connection already exists
      const exists = await connectionExists(newItem.id, match.parent_id);
      if (exists) continue;
      
      // Determine connection type
      const sharedTopics = intersection(newItem.topics, match.parent.topics);
      const sameDomain = sharedTopics.length > 0;
      const type: ConnectionType = sameDomain ? 'topic_overlap' : 'cross_domain';
      
      // Generate connection description via Claude
      const description = await generateConnectionDescription(
        newItem.summary,
        match.parent.summary,
        chunk.content,
        match.content
      );
      
      await storeConnection({
        item_a_id: newItem.id,
        item_b_id: match.parent_id,
        connection_type: type,
        description,
        similarity_score: match.similarity
      });
    }
  }
}
```

### 8.4 Cross-Domain Connections (The Gold)

The most valuable connections are between different life domains:

- **LEGO article** ↔ **eBay sales data** → "This pricing trend matches your inventory"
- **Running article on heat acclimation** ↔ **Amsterdam Marathon goal** → "Relevant to your October race"
- **eBay fees article** ↔ **EU expansion note** → "New fees affect your Germany plan"
- **Japan travel article** ↔ **Family calendar** → "Trip is 8 weeks away"

These require peterbot-mem context to understand the domains. The integration layer queries peterbot-mem for domain knowledge when evaluating connections.

---

## 9. Proactive Surfacing

### 9.1 Weekly Digest — Sunday Evening

A scheduled proactive message summarising the week's knowledge activity:

```
📚 **Weekly Knowledge Digest**

**Saved this week:** 4 items
- LEGO 42100 price analysis (article)
- Bundle discount idea (note)
- eBay Spring Seller Update (article)
- Japan rail pass comparison (article)

**Connections discovered:**
🔗 Your bundle discount idea connects to the eBay fees update — 
   new fees may affect margin calculations for bundled international orders.

**Fading items** (not accessed in 60+ days):
⏳ 'Altitude training for marathon runners' — saved Nov 2025
   Still relevant? Amsterdam is 8 months away.
⏳ 'BrickLink store optimisation tips' — saved Oct 2025
   React ✅ to keep, ❌ to archive.

-# Sunday 19:00 • Knowledge digest
```

### 9.2 Contextual Surfacing — During Conversation

When Chris asks Peter something and a saved knowledge item is relevant, Peter weaves it in naturally:

```
Chris: What should I price the Liebherr at?

Peter: Based on current eBay listings, the 42100 is going for £380-£450 
sealed. You saved an article last week from BrickEconomy showing 8% YoY 
appreciation on Technic sets — might be worth holding if you're not in 
a rush.
```

**Implementation:** During normal response generation, Peter runs a lightweight semantic search against the knowledge base using the user's query. If a match scores above 0.75, include it in context for the response.

### 9.3 Contextual Surfacing Logic

```typescript
async function getRelevantKnowledge(userMessage: string): Promise<KnowledgeItem[]> {
  // Only search explicit saves and promoted passives
  const results = await semanticSearch(userMessage, {
    minSimilarity: 0.75,
    minDecayScore: 0.2,     // Skip heavily decayed items
    captureType: ['explicit'],
    limit: 3
  });
  
  // Boost accessed items
  for (const result of results) {
    await boostAccess(result.parent_id);
  }
  
  return results;
}
```

This function is called during Peter's normal response flow. Results are injected into the CC context alongside peterbot-mem observations.

### 9.4 Fading Item Nudges

Items approaching low decay scores (< 0.3) that have known connections to active topics get a nudge in the weekly digest:

```typescript
async function findFadingButRelevant(): Promise<KnowledgeItem[]> {
  // Items with low decay but connected to active topics
  return await query(`
    SELECT ki.* FROM knowledge_items ki
    JOIN knowledge_connections kc ON ki.id = kc.item_a_id OR ki.id = kc.item_b_id
    WHERE ki.decay_score < 0.3
    AND ki.decay_score > 0.05  -- Not completely dead
    AND ki.status = 'active'
    AND EXISTS (
      -- Connected to something recently accessed
      SELECT 1 FROM knowledge_items ki2
      WHERE (ki2.id = kc.item_a_id OR ki2.id = kc.item_b_id)
      AND ki2.id != ki.id
      AND ki2.last_accessed_at > now() - interval '30 days'
    )
    ORDER BY ki.decay_score ASC
    LIMIT 5
  `);
}
```

---

## 10. URL Content Extraction

### 10.1 Extraction Pipeline

When Chris saves a URL, extract readable content:

```typescript
async function extractUrlContent(url: string): Promise<ExtractedContent> {
  // 1. Fetch the page
  const html = await fetch(url).then(r => r.text());
  
  // 2. Use readability to strip nav/ads/boilerplate
  const readable = new Readability(new JSDOM(html).window.document).parse();
  
  // 3. Fall back to basic HTML-to-text if readability fails
  if (!readable || !readable.textContent) {
    return { title: url, text: htmlToText(html), source: url };
  }
  
  return {
    title: readable.title,
    text: readable.textContent,
    source: url,
    excerpt: readable.excerpt,
    siteName: readable.siteName
  };
}
```

### 10.2 Supported Content Types

| Type | Handling |
|------|----------|
| Web articles | Readability parse → full text extraction |
| Reddit/forum posts | Extract post + top comments |
| YouTube | Extract title + description (transcript if available via API) |
| PDF links | Download + text extraction |
| Twitter/X | Extract tweet text + media description |
| Plain text | Store as-is |

### 10.3 Content Size Limits

- **Max content:** 10,000 words per item (truncate with note)
- **Max chunks:** 40 per item (covers ~12,000 words with overlap)
- **Min content:** 10 words (reject trivially short content)

---

## 11. AI Summarisation & Tagging

### 11.1 Summarisation Prompt

```
Summarise this content in 2-3 sentences. Focus on the key insight 
or actionable information. Be specific — include numbers, names, 
and dates where relevant.

Content: {extracted_text}
```

### 11.2 Tagging Prompt

```
Extract 3-8 topic tags for this content. Use lowercase, hyphenated tags.
Prefer these known domains when applicable:
- hadley-bricks, ebay, bricklink, brick-owl, amazon
- lego, lego-investing, retired-sets, minifigures
- running, marathon, training, nutrition, garmin
- family, max, emmie, abby, japan-trip
- tech, development, peterbot, familyfuel
- finance, tax, self-employment

Content: {extracted_text}

Return as JSON array: ["tag1", "tag2", ...]
```

### 11.3 Connection Description Prompt

```
These two knowledge items appear to be connected. Describe the 
connection in one sentence, focusing on why this is useful or 
actionable for the person who saved them.

Item A: {summary_a}
Item B: {summary_b}
Matching excerpts: {chunk_a} ↔ {chunk_b}

Connection: 
```

---

## 12. Discord Commands & Interaction

### 12.1 Save Commands

```
!save <url>                          → Full save with URL extraction
!save <text>                         → Save as note
Peter, save this: <content>          → Natural language save
Peter, remember this: <content>      → Natural language save
```

### 12.2 Recall Commands

```
!recall <query>                      → Semantic search
What do I know about <topic>?        → Natural language search
Peter, find that article about <x>   → Natural language search
```

### 12.3 Management Commands

```
!knowledge                           → Stats: total items, recent saves, fading items
!knowledge topics                    → List all topics with counts
!knowledge recent                    → Last 10 saves
!knowledge archive <id>              → Manually archive an item
!knowledge promote <id>              → Promote passive capture to explicit
```

### 12.4 Response Formatting

All Second Brain responses follow RESPONSE.md pipeline rules. Specifically:

- Save confirmations: plain text with emoji prefix (📚, 💡, 🔗)
- Search results: numbered list with title, date, source, relevant excerpt
- Weekly digest: proactive message format per RESPONSE.md Section 11
- Connections: inline mentions during natural conversation

---

## 13. Weekly Digest Skill

### 13.1 Schedule

Sunday evening, 19:00 UK time. Delivered as a proactive Discord message.

### 13.2 Digest Contents

1. **Items saved this week** — count + titles
2. **Connections discovered** — new links between items (prioritise cross-domain)
3. **Fading items** — items with decay_score < 0.3 that are connected to active topics
4. **Knowledge stats** — total items, total connections, most-accessed item this week

### 13.3 Digest Generation

```typescript
async function generateWeeklyDigest(): Promise<string> {
  const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  
  // Items saved this week
  const newItems = await getItemsSince(weekAgo);
  
  // Connections discovered this week
  const newConnections = await getConnectionsSince(weekAgo);
  // Filter to unsurfaced connections only
  const unsurfacedConnections = newConnections.filter(c => !c.surfaced);
  
  // Fading but relevant items
  const fadingItems = await findFadingButRelevant();
  
  // Generate natural language digest via Claude
  const digest = await generateDigestMessage({
    newItems,
    connections: unsurfacedConnections,
    fadingItems,
    totalItems: await getTotalActiveCount(),
    totalConnections: await getTotalConnectionCount()
  });
  
  // Mark connections as surfaced
  for (const conn of unsurfacedConnections) {
    await markSurfaced(conn.id);
  }
  
  return digest;
}
```

---

## 14. Contextual Surfacing Integration

### 14.1 Where It Hooks In

During Peter's normal response generation flow, before sending the prompt to CC:

```
User message arrives
       │
       ▼
┌──────────────────┐
│ peterbot-mem     │ ← Existing: inject observations about Chris
│ context injection│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Second Brain     │ ← NEW: search knowledge base for relevant items
│ context injection│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Send to CC       │ ← Combined context: peterbot-mem + relevant knowledge
└──────────────────┘
```

### 14.2 Context Injection Format

```
[KNOWLEDGE CONTEXT]
The following items from Chris's knowledge base may be relevant:

1. "LEGO Investing: Why Retired Sets Beat the Stock Market" (saved Dec 2025)
   Key excerpt: "UCS Star Wars sets appreciate 11% annually..."
   
2. "Bundle discount idea" (note, Jan 2026)
   "Consider offering bundle discounts on BrickLink for 3+ sets to increase AOV"

Use these naturally in your response if relevant. Don't force them in if they're not useful.
[/KNOWLEDGE CONTEXT]
```

### 14.3 Performance Considerations

- Semantic search adds ~200-500ms to response time
- Only run when query has substantive content (skip for "hi", "thanks", "ok")
- Cache recent query embeddings to avoid re-embedding similar questions
- Max 3 knowledge items injected per response to avoid context bloat

---

## 15. Relationship to Existing Files

### 15.1 What Goes Where

| File | Second Brain Content |
|------|---------------------|
| **CLAUDE.md** | Single reference: `@SECOND-BRAIN.md governs knowledge capture and retrieval` |
| **petersoul.md** | None — personality/tone only |
| **RESPONSE.md** | Formatting rules for knowledge-related Discord messages |
| **SECOND-BRAIN.md** (this file) | ALL knowledge capture, storage, retrieval, surfacing logic |

### 15.2 CLAUDE.md Reference

```markdown
## Second Brain
@SECOND-BRAIN.md governs knowledge capture, storage, and retrieval.
When Chris saves content or asks "what do I know about X", follow SECOND-BRAIN.md.
Contextual surfacing runs automatically on each response — check knowledge base for relevant items.
```

---

## 16. Seed Import — Bootstrapping the Knowledge Base

Starting from zero means weeks of organic `!save` usage before retrieval has anything meaningful to search against. Seeding the knowledge base with existing high-signal content gives immediate value and properly stress-tests the full pipeline.

### 16.1 Seed Sources

#### Source 1: GitHub Repos

**What to index:**
- README.md files across all repos
- CLAUDE.md files (operational knowledge)
- PRDs and spec documents (Hadley Bricks 903-line PRD, feature specs)
- petersoul.md, RESPONSE.md, SECOND-BRAIN.md
- Agent spec files (Define Done, Feature Spec, Build Feature, Verify Done)
- FamilyFuel feature specs (Products, Staples Engine, Export & Share, Inventory)
- GitHub issue descriptions and comments

**What to skip:**
- Source code (.ts, .tsx, .css, .js)
- Config files (package.json, tsconfig, .env.example)
- Lock files, node_modules, build output
- Migration SQL files
- Test files

**Extraction strategy:**
```typescript
// Use GitHub API to crawl repos
// Filter: *.md, *.txt, docs/**
// Exclude: node_modules, dist, .next, *.test.*, *.spec.*
// Each qualifying file → one knowledge_item with content_type 'document'
// Tag with repo name + inferred domain
```

**Estimated yield:** 50-100 high-quality documents

#### Source 2: Past Claude Conversations

The richest source. Months of strategic thinking about Hadley Bricks, detailed project specs, tax research, trip planning — already in Chris's own words, already refined through back-and-forth.

**What to index:**
- Conversations with substantive content (strategy, planning, research, specs)
- Key decisions and rationale
- Research findings (tax, Japan trip, LEGO market)

**What to skip:**
- Quick one-off questions ("what's the syntax for X")
- Pure code generation sessions (value is in the output, not the chat)
- Conversations that led to saved specs (spec itself is the artefact)

**Extraction strategy:**
```typescript
// Export via Claude conversation history / API
// Filter conversations by length (>10 messages = likely substantive)
// For each qualifying conversation:
//   - Generate a title + summary via Claude
//   - Extract key decisions, insights, research findings
//   - Store as content_type 'conversation_extract'
//   - Tag with detected domains
// DON'T store raw conversation — extract the KNOWLEDGE from it
```

**Estimated yield:** 100-200 knowledge items

#### Source 3: Gemini History

Same logic as Claude conversations — a parallel repository of thinking and research that's currently siloed.

**What to index:**
- Substantive research and planning conversations
- Any topics not covered in Claude history

**What to skip:**
- Duplicated topics already covered in Claude conversations
- Quick factual queries

**Extraction strategy:**
```typescript
// Export via Google Takeout → Gemini activity
// Parse exported JSON/HTML
// Same filtering as Claude: length-based, then AI extraction
// Store as content_type 'conversation_extract'
// De-duplicate against Claude conversation extracts (topic overlap check)
```

**Estimated yield:** 30-80 knowledge items

#### Source 4: Browser Bookmarks

Years of curated links. Folder names are free topic tags.

**What to index:**
- All bookmarked URLs with titles
- Folder hierarchy as topic tags
- Optionally: fetch and extract content from still-live URLs

**What to skip:**
- Dead links (404s) — store metadata only, flag as dead
- Generic bookmarks (Google, Gmail, etc.)

**Extraction strategy:**
```typescript
// Export bookmarks as HTML (Chrome: chrome://bookmarks → export)
// Parse HTML → extract URL, title, folder path
// Folder path → topic tags (e.g., "LEGO/Investing" → ['lego', 'investing'])
// Phase 1: Store metadata only (URL, title, tags) — lightweight
// Phase 2: Optionally batch-fetch live URLs for full content extraction
// Store as content_type 'bookmark'
```

**Estimated yield:** 200-500+ items (metadata), subset with full content

#### Source 5: Garmin Training History

Key milestones and patterns, not every run.

**What to index:**
- Race results (times, distances, conditions)
- PB history (5K, 10K, half, marathon)
- Training plan structures and phases
- Key workouts (tempo targets, interval sessions)
- Weekly/monthly mileage trends
- VDOT progression over time

**What to skip:**
- Individual easy runs
- GPS data / route maps
- Heart rate zone data (too granular)

**Extraction strategy:**
```typescript
// Export via Garmin Connect export or Garmin API
// Filter: activities tagged as races, PBs, or structured workouts
// Generate monthly/quarterly summaries via Claude:
//   "Oct 2025: 120km total, PB 5K 21:00, VDOT moved from 45 to 47"
// Store as content_type 'training_data'
// Tag with: #running, #garmin, plus event-specific tags
```

**Estimated yield:** 20-40 milestone items + 12-24 monthly summaries

#### Source 6: Instagram Saved Posts

Saved posts are curated — Chris saved them for a reason.

**What to index:**
- Saved post content (caption text, image descriptions)
- Collections/folders as topic tags (if organised)
- Links embedded in posts

**What to skip:**
- Reels saved purely for entertainment
- Posts where the value is the image and there's no extractable text

**Extraction strategy:**
```typescript
// Export via Instagram data download (Settings → Your Activity → Download)
// Parse saved_posts.json from export
// For each saved post:
//   - Extract caption text
//   - If image-only: generate description via vision model or skip
//   - Detect topic from caption + any hashtags
//   - Store as content_type 'social_save'
// Tag with: detected topics + any collection names
```

**Estimated yield:** 30-100 items (highly variable based on save habits)

#### Source 7: Email — One-Off Scan

Single comprehensive scan for structured data across multiple categories. Not ongoing monitoring.

**Category A: Bookings & Travel**
- Flight bookings and confirmations
- Hotel reservations
- Event tickets (concerts, experiences)
- Japan trip bookings specifically
- Trainline / rail bookings

**Category B: Purchases & Receipts**
- Major purchases (especially LEGO stock for resale)
- LEGO.com orders (personal collection + Hadley Bricks)
- Amazon/eBay purchases
- Subscription confirmations and renewal notices
- Software/tool purchases (API services, hosting)

**Category C: Tax-Relevant Expenses**
- Business expense receipts (LEGO stock, packaging, shipping supplies)
- Software subscriptions (tools used for Hadley Bricks)
- Mileage-related correspondence
- HMRC correspondence and Making Tax Digital notifications
- Accountant/tax advisor communications

**Category D: eBay/Amazon Seller Notifications**
- Policy change announcements
- Fee structure updates
- Performance review summaries
- Account milestone notifications
- Seller programme invitations

**Category E: Family & Kids**
- School communications (term dates, parents evenings, reports)
- Club/activity registrations and schedules
- Medical/dental appointment confirmations
- Vaccination records (especially Japan-trip related travel jabs)
- Childcare arrangements

**Category F: Race Entries & Fitness**
- Race entry confirmations (parkrun, 10K, half, marathon)
- Event logistics (start times, parking, kit collection)
- Garmin/Strava account notifications
- Running club communications

**Category G: Insurance & Renewals**
- Car, home, business insurance policies and renewal dates
- MOT/service reminders
- Breakdown cover
- Annual subscription renewals (dates + amounts)

**What to skip:**
- Marketing emails and newsletters
- Delivery tracking notifications (ephemeral)
- Social media notifications
- Bank statements (query from source directly)
- Personal correspondence
- Spam / promotional

**Extraction strategy:**
```typescript
// Use Gmail API (already available via Peter's MCP tools)
// 
// CATEGORY A — Bookings & Travel
// "subject:(booking OR confirmation OR reservation) newer_than:2y"
// "subject:(flight OR hotel OR airbnb) newer_than:2y"
// "from:(booking.com OR airbnb OR skyscanner OR trainline OR ba.com) newer_than:2y"
//
// CATEGORY B — Purchases & Receipts
// "subject:(order confirmation OR receipt OR invoice) newer_than:2y"
// "from:(ebay OR amazon OR lego.com) subject:(order OR confirmation) newer_than:2y"
//
// CATEGORY C — Tax & Expenses
// "from:(hmrc OR gov.uk) newer_than:3y"
// "subject:(receipt OR invoice) from:(shopify OR stripe OR paypal) newer_than:2y"
// "subject:(subscription OR renewal) newer_than:1y"
//
// CATEGORY D — Seller Notifications
// "from:(ebay.co.uk OR sellercentral.amazon.co.uk) subject:(update OR policy OR fee) newer_than:2y"
//
// CATEGORY E — Family & Kids
// "from:(*school*) newer_than:2y"
// "subject:(parents evening OR term dates OR school) newer_than:2y"
// "subject:(appointment OR vaccination OR dental OR doctor) newer_than:2y"
//
// CATEGORY F — Race Entries
// "subject:(entry OR registration) (run OR race OR marathon OR parkrun) newer_than:2y"
//
// CATEGORY G — Insurance & Renewals
// "subject:(renewal OR policy) (insurance OR cover) newer_than:2y"
// "subject:(MOT OR service) newer_than:1y"
//
// For each matching email:
//   - Extract structured data per category:
//     Bookings: date, vendor, amount, reference, destination
//     Purchases: item, amount, vendor, order number
//     Tax: type, amount, tax year, reference
//     Seller: platform, change type, effective date
//     Family: event, date, child name, location
//     Race: event name, date, distance, location
//     Insurance: policy type, renewal date, premium, provider
//   - Generate natural language summary
//   - Store with appropriate content_type and tags
//
// ONE-OFF ONLY — no ongoing email monitoring
// Run once during seed import, never again
```

**Estimated yield:** 150-400 items (expanded categories over 2-3 years)

#### Source 8: Google Calendar — Historical Events

Calendar history provides pattern recognition, travel context, recurring commitments, and key dates.

**What to index:**
- **Recurring events** — who Chris meets regularly, standing commitments, kids activities
- **Travel events** — past trips, flights, hotel stays (context for "last time you went to X")
- **Kids activities** — clubs, lessons, play dates, school events, sports fixtures
- **Race events** — parkruns, 10Ks, half marathons, marathons (connects to Garmin data)
- **Business milestones** — when each platform went live, key meetings, deadlines
- **Family events** — birthdays, anniversaries, celebrations (Peter should know these)
- **Medical/dental** — appointment history, check-up patterns
- **Seasonal patterns** — school holidays, half terms, busy eBay periods (Q4 surge)

**What to skip:**
- Daily standup-type recurring meetings (too granular)
- Cancelled events
- All-day placeholder events with no content
- Events older than 3 years (diminishing relevance)

**Extraction strategy:**
```typescript
// Use Google Calendar API (already available via Peter's MCP tools)
//
// Phase 1: Extract raw events
// - Pull all events from last 3 years
// - Include: summary, description, location, start/end, recurrence, attendees
//
// Phase 2: Categorise and cluster
// For each event, classify into:
//   'travel', 'family', 'kids_activity', 'race', 'business',
//   'medical', 'social', 'recurring'
//
// Phase 3: Smart aggregation (don't store every individual occurrence)
// RECURRING events → store as ONE item with pattern:
//   "Max has football practice every Tuesday 4:30-5:30 at Tonbridge FC"
//   "Weekly parkrun - Saturday 9:00, Tonbridge"
//   NOT 52 individual parkrun entries
//
// ONE-OFF events → store individually:
//   "Amsterdam Marathon - 18 Oct 2026"
//   "Japan trip - 3-19 Apr 2026"
//   "Parents evening - 12 Mar 2026, 6:30pm"
//
// Phase 4: Extract key dates
// Birthdays, anniversaries, annual events → store as content_type 'key_date'
// with recurrence metadata so Peter knows they repeat yearly
//
// Phase 5: Pattern analysis
// Generate summary insights via Claude:
//   "Q4 2025: 47 eBay-related events (busiest quarter)"
//   "Max activities: football (Tue), swimming (Thu), cubs (Wed)"
//   "Average 2 race events per month May-Oct"
//
// Store patterns as content_type 'calendar_pattern'
// Store individual events as content_type 'calendar_event'
// Store key dates as content_type 'key_date'
// Tag with: detected categories + attendee names + locations
```

**Estimated yield:** 50-100 items (after smart aggregation — NOT one per event)

#### Source 10: Google Drive Documents

Business planning docs, spreadsheets with analysis, meeting notes.

**What to index:**
- Business planning documents
- Hadley Bricks strategy docs and spreadsheets
- Tax planning documents
- Any research or analysis docs

**What to skip:**
- Auto-generated files (Google Forms responses etc.)
- Shared docs from others (unless actively used)
- Duplicate content already in GitHub repos

**Extraction strategy:**
```typescript
// Use Google Drive API (already available via Peter's MCP tools)
// Search: owned docs modified in last 2 years
// Filter by: Google Docs, Sheets (key tabs/summaries only), PDFs
// For each qualifying doc:
//   - Extract text content via Drive API
//   - Generate summary + tags
//   - Store as content_type 'document'
//   - De-duplicate against GitHub repo content
```

**Estimated yield:** 20-50 items

### 16.2 Import Pipeline

All seed sources feed through the same explicit save pipeline (Section 5.1), with additions for batch processing:

```
Source export / API fetch
         │
         ▼
┌─────────────────────────┐
│  1. SOURCE ADAPTER       │
│  Parse source-specific format (JSON, HTML, API response)
│  Normalise to: { title, content, source, sourceTags }
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  2. DEDUPLICATION        │
│  Check title + content hash against existing items
│  Skip exact duplicates
│  Flag near-duplicates for review
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  3. BATCH PROCESS        │
│  Run through standard pipeline: summarise → tag → chunk → embed
│  Rate-limited to avoid API throttling
│  Batch embeddings where possible (OpenAI supports batch)
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  4. STORE                │
│  All items stored as capture_type: 'seed'
│  base_priority: 0.8 (between explicit 1.0 and passive 0.3)
│  source field tracks origin: 'seed:github', 'seed:claude', etc.
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  5. CONNECTION DISCOVERY │
│  Run after all items imported
│  Batch connection scan across full knowledge base
│  This is where the magic happens — cross-source connections
└─────────────────────────┘
```

### 16.3 Import Order

Run in this order to maximise connection discovery:

| Order | Source | Rationale |
|-------|--------|-----------|
| 1 | GitHub repos | Foundation — project specs, PRDs, agent docs |
| 2 | Claude conversations | Richest source — strategy, research, decisions |
| 3 | Gemini history | Fill gaps from Claude, de-duplicate |
| 4 | Google Drive | Business docs, planning, analysis |
| 5 | Google Calendar | Patterns, key dates, recurring commitments, travel history |
| 6 | Email (one-off) | Bookings, purchases, tax, school, insurance, seller updates |
| 7 | Browser bookmarks | Broad coverage, metadata-first |
| 8 | Garmin training | Milestones, PBs, monthly summaries |
| 9 | Instagram saved | Curated saves, variable quality |

### 16.4 Seed Import Metrics

After import, report:

```
📊 Second Brain Seed Import Complete

Sources imported:
  GitHub repos:          87 items (14 repos)
  Claude conversations: 156 items (extracted from 340 chats)
  Gemini history:        52 items (extracted from 180 chats)
  Google Drive:          34 items
  Google Calendar:       73 items (42 events, 15 patterns, 16 key dates)
  Email (one-off):      247 items (89 bookings, 62 purchases, 38 tax, 
                                   24 school, 18 seller, 16 other)
  Browser bookmarks:    312 items (47 with full content)
  Garmin training:       28 items
  Instagram saved:       43 items

Total: 1,032 knowledge items, 4,128 chunks, 2,461 connections discovered

Top connections:
🔗 Japan trip bookings ↔ Japan research conversations (31 links)
🔗 Hadley Bricks PRD ↔ eBay strategy chats ↔ seller fee updates (24 links)
🔗 Running PBs ↔ training plans ↔ race calendar entries (19 links)
🔗 School term dates ↔ family calendar patterns ↔ Japan trip dates (14 links)
🔗 Insurance renewals ↔ calendar reminders ↔ tax expense records (11 links)

Embedding cost: ~$0.10
```

### 16.5 Capture Type Extension

Update the `capture_type` field to support seed imports:

```sql
-- capture_type values:
-- 'explicit'  — user !save command (base_priority 1.0)
-- 'passive'   — auto-detected URL/idea (base_priority 0.3)
-- 'seed'      — bulk import during bootstrap (base_priority 0.8)
```

Seed items can be promoted to explicit (priority 1.0) when accessed, same as passive items.

### 16.6 Source Metadata Extension

Add source tracking to knowledge_items:

```sql
-- Add to knowledge_items table
ALTER TABLE knowledge_items ADD COLUMN source_system TEXT;
-- Values: 'discord', 'seed:github', 'seed:claude', 'seed:gemini',
--         'seed:gdrive', 'seed:gcal', 'seed:email', 'seed:bookmarks', 
--         'seed:garmin', 'seed:instagram'
```

---

## 17. Implementation Priority

| Phase | Scope | Effort | Dependencies |
|-------|-------|--------|-------------|
| **P0: Schema & Tables** | Create Supabase tables, enable pgvector, create indexes, add source_system column | Small | Supabase access |
| **P0.5: Seed Import** | Build source adapters, batch pipeline, import all 8 sources, run connection discovery | Large | P0, OpenAI API key, source exports |
| **P1: Explicit Save** | `!save` command, URL extraction, summarisation, chunking, embedding, storage | Medium | P0, OpenAI API key |
| **P2: Basic Recall** | `!recall` command, semantic search, response formatting | Medium | P0, P1 |
| **P3: Passive Capture** | Auto-detect URLs/ideas, lightweight storage, promotion flow | Small | P0 |
| **P4: Decay Model** | Decay calculation, access boosting, daily refresh job | Small | P0 |
| **P5: Connection Discovery** | On-save connection search, cross-domain detection, connection storage | Medium | P1 |
| **P6: Contextual Surfacing** | Hook into response flow, inject relevant knowledge, access boosting | Medium | P2 |
| **P7: Weekly Digest** | Sunday evening proactive message, fading item nudges | Medium | P4, P5 |
| **P8: Management Commands** | `!knowledge` stats, topic list, archive, promote | Small | P0, P3 |
| **P9: Testing** | Unit tests per component, integration tests, live validation | Large | All |

**Note:** P0.5 is deliberately early — seeding the knowledge base before building the Discord commands means P2 (recall) has real data to test against from day one. The seed import also validates the entire processing pipeline at scale before it goes live.

---

## 18. Testing Strategy

### 17.1 Unit Tests

```
tests/
  second-brain/
    capture.test.ts          # Explicit + passive detection
    extraction.test.ts       # URL content extraction
    chunking.test.ts         # Text chunking logic
    embedding.test.ts        # Embedding generation + storage
    search.test.ts           # Semantic search accuracy
    decay.test.ts            # Decay score calculation
    connections.test.ts      # Connection discovery logic
    digest.test.ts           # Weekly digest generation
    promotion.test.ts        # Passive → explicit promotion
    seed-import.test.ts      # Seed import pipeline + source adapters
    integration.test.ts      # Full pipeline tests
```

### 17.2 Key Test Scenarios

| Scenario | Validates |
|----------|-----------|
| Save a URL, recall it by topic | Full pipeline works |
| Save 3 related items, check connections found | Connection discovery |
| Save item, wait 90 days (mocked), check decay_score ≈ 0.5 | Decay model |
| Access a decayed item, verify score rebounds | Access boosting |
| Paste URL without !save, verify passive capture | Passive detection |
| Promote passive capture, verify chunks + embeddings created | Promotion flow |
| Ask question with relevant saved item, verify it appears in context | Contextual surfacing |
| Generate digest with fading items, verify format | Weekly digest |
| Save items across domains, verify cross-domain connection | Cross-domain intelligence |
| Import GitHub repo, verify markdown files extracted and code files skipped | Seed import filtering |
| Import Claude conversations, verify extraction not raw storage | Conversation extraction |
| Import from 2+ sources, verify cross-source connections discovered | Seed connection discovery |
| Import duplicate content from Claude + Gemini, verify de-duplication | Seed de-duplication |
| Verify seed items have base_priority 0.8 | Seed priority weighting |
| Import bookmarks, verify folder names become tags | Bookmark tag extraction |
| Import email bookings, verify structured data extracted | Email one-off scan |
| Import email across all 7 categories, verify correct content_type per category | Email category classification |
| Import calendar, verify recurring events aggregated not duplicated | Calendar smart aggregation |
| Import calendar, verify birthdays stored as key_date with recurrence | Calendar key dates |
| Import calendar + Garmin, verify race events connect to training data | Cross-source calendar-Garmin links |
| Import calendar + email, verify school events connect to school emails | Cross-source calendar-email links |

### 17.3 Live Validation

After deployment, manually test:
1. Save 5 real articles across different topics
2. Save 3 ideas/notes
3. Verify `!recall` returns sensible results
4. Check connections are discovered
5. Wait for Sunday digest
6. Verify contextual surfacing during normal conversation

---

## 19. Open Decisions for Implementation

These can be decided during build:

1. **Readability library** — `@mozilla/readability` (Node.js) or Python `readability-lxml`?
2. **Embedding batching** — batch chunk embeddings in one API call or one-by-one?
3. **CC prompt injection position** — knowledge context before or after peterbot-mem observations?
4. **Digest reaction handling** — ✅/❌ on fading items: archive immediately or flag for review?
5. **Passive capture rate limiting** — max captures per hour to avoid noise from link-heavy conversations?

---

## Appendix A: Example Interactions

### A.1 Quick Capture (Note)

```
Chris: !save Just had a thought — what if we offered bundle discounts 
on BrickLink for customers who buy 3+ sets? Might increase AOV.

Peter: 💡 Saved: 'Bundle discount idea for BrickLink'
Tagged: #hadley-bricks #pricing #bricklink
Connected to: 'eBay Spring Seller Update 2026' (pricing strategy overlap)
```

### A.2 Article Save with Context

```
Chris: !save https://brickeconomy.com/set/75192

Peter: 📚 Saved: 'LEGO 75192 Millennium Falcon — Price Guide'

Summary: Current value £649, up 8% YoY. Peak demand Nov-Dec. 
Sellers averaging 14 days to sale.

Tagged: #lego #lego-investing #star-wars #retired-sets
Connected to: Your inventory (you own 2 sealed copies)

💰 Quick insight: Your copies are worth ~£1,298 total.
```

### A.3 Knowledge Query

```
Chris: What do I know about altitude and marathon training?

Peter: Found 3 items:

1. **Podcast note** (Jan 2025, Snipd)
   Live high, train low is optimal but impractical. Heat acclimation 
   may be more accessible.

2. **Article highlight** (Dec 2024, Readwise)
   Amsterdam is below sea level — no altitude factor. Focus on flat 
   course pacing.

3. **Your note** (Oct 2024)
   "Consider altitude tent rental if serious about sub-3:30"

These connect to your Amsterdam Marathon goal (Oct 2026). Your current 
VDOT (47) projects a 3:31 marathon.
```

### A.4 Contextual Surfacing (Unprompted)

```
Chris: What should I price the Liebherr at?

Peter: Based on current eBay listings, the 42100 is going for £380-£450 
sealed. You saved an article last week from BrickEconomy showing 8% YoY 
appreciation on Technic sets — might be worth holding if you're not in 
a rush.
```

### A.5 Proactive Connection (in Monday briefing)

```
🔗 New connection discovered:

Yesterday you saved an article about eBay's Spring Seller Update — 
international fees increasing 0.5% in March.

This connects to your note from November about expanding to eBay Germany 
for Star Wars sets. You might want to factor new fees into pricing 
before expanding.
```

### A.6 Fading Item Nudge (in weekly digest)

```
⏳ Fading items:

'Altitude training for marathon runners' — saved Nov 2025, not accessed 
in 67 days. Still relevant? Amsterdam is 8 months away.

React ✅ to keep, ❌ to archive.
```
