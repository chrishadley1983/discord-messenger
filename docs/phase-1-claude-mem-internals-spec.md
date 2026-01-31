# Phase 1: Understand Claude-Mem Internals - Technical Spec

**Project:** Peterbot memory system  
**Purpose:** Fork claude-mem and map its architecture before modification  
**Prerequisite:** Phase 0 complete (claude-mem validated and working)  
**Time estimate:** 2-4 hours  
**Risk:** Low - reading and documenting, no code changes yet

---

## Objective

Understand exactly how claude-mem works so we can modify it for Peterbot. By the end of Phase 1, we should be able to answer:

1. Where are compression prompts and how do they work?
2. How does observation storage work (SQLite + ChromaDB)?
3. How does retrieval/search work?
4. Where are hooks defined and how do they capture data?
5. How does context injection work?

**Gate:** Can articulate exactly where and how to modify for Peterbot personality memory.

---

## Architecture Decisions (from planning)

These decisions are made. Phase 1 is about finding WHERE in claude-mem to implement them.

| Decision | What we need to find |
|----------|---------------------|
| Add observation categories (identity, preference, emotional, etc.) | Schema definition, storage layer |
| Implement supersede logic within categories | Storage layer, retrieval queries |
| Tiered retrieval (core + active + semantic + recent) | Retrieval/search functions |
| Modify compression to extract personality | Compression prompts |
| Change injection format | Context injection code |

---

## Step 1: Fork the Repository

```bash
cd ~/projects  # or wherever you keep forks
git clone https://github.com/thedotmack/claude-mem.git peterbot-mem
cd peterbot-mem
git remote rename origin upstream
# Create your own repo and add as origin when ready
```

Keep upstream remote so we can pull updates if needed.

---

## Step 2: Map the File Structure

Run this and document what each directory/file does:

```bash
tree -L 3 --dirsfirst
```

**Expected key locations (to verify):**

| Path | Expected purpose |
|------|------------------|
| `src/sdk/` | Agent SDK integration, compression |
| `src/sdk/prompts.ts` | Compression prompts (CRITICAL) |
| `src/worker/` | Background worker service |
| `src/mcp/` | MCP server tools (search, get_observations) |
| `src/db/` or `src/storage/` | SQLite + ChromaDB handling |
| `src/hooks/` | Claude Code hook definitions |
| `src/web/` or `src/viewer/` | Web UI at localhost:37777 |

**Task:** Create a file `ARCHITECTURE.md` in your fork documenting the actual structure.

---

## Step 3: Trace the Observation Flow

Follow a single observation from capture to storage:

### 3.1 Hook Trigger

Find where hooks are defined. Look for:
- `hooks.json` or similar config
- References to `post-tool-use`, `user-message` events
- Entry point when Claude Code does something

**Questions to answer:**
- What events trigger observation capture?
- What data is passed to the capture function?
- Where does the raw data go first?

### 3.2 Compression

Find the compression prompts in `src/sdk/prompts.ts` (or similar).

**Questions to answer:**
- What prompt extracts observations from raw data?
- What model is used? (Haiku? Sonnet?)
- What's the output format?
- How much raw context goes in vs compressed observation out?

**Document the actual prompt.** This is what we'll modify for personality extraction.

### 3.3 Storage

Find how compressed observations are stored.

**Questions to answer:**
- SQLite schema - what tables? what columns?
- Is there a `type` or `category` field already?
- How are embeddings generated for ChromaDB?
- What metadata is stored with each observation?

**Document the schema.** We need to know if we can add `category` or need to modify.

---

## Step 4: Trace the Retrieval Flow

Follow a search query from MCP tool to results:

### 4.1 MCP Tools

Find the MCP tool definitions. Look for:
- `search()` function
- `get_observations()` function
- Tool registration for Claude Code

**Questions to answer:**
- What parameters does search accept?
- How does it query ChromaDB (semantic)?
- How does it query SQLite (filters)?
- What's returned to Claude?

### 4.2 Context Injection

Find where/how context is injected at session start.

**Questions to answer:**
- What triggers injection? (session start hook?)
- How many observations are selected?
- What format are they injected in?
- Is there a system prompt modification?

**Document the injection format.** We'll modify this for our tiered approach.

---

## Step 5: Document Extension Points

Based on the above, identify exactly where we need to modify:

### For Observation Categories

```
File: _______________
Function: _______________
Current behaviour: _______________
Change needed: _______________
```

### For Supersede Logic

```
File: _______________
Function: _______________
Current behaviour: _______________
Change needed: _______________
```

### For Personality Extraction (compression prompts)

```
File: _______________
Prompt location: _______________
Current prompt extracts: _______________
Change needed: Add extraction for emotional, preference, identity, etc.
```

### For Tiered Retrieval

```
File: _______________
Function: _______________
Current behaviour: _______________
Change needed: Add core/active/semantic tiers
```

### For Injection Format

```
File: _______________
Function: _______________
Current format: _______________
Change needed: Structured [PETERBOT CONTEXT] format
```

---

## Step 6: Document Unknowns and Risks

Things we might discover that change our approach:

| Potential issue | Impact | Mitigation |
|-----------------|--------|------------|
| No category/type field in schema | Need migration | Add column, backfill existing |
| Compression prompt is complex/fragile | Risk breaking it | Test extensively in Phase 3 |
| ChromaDB tightly coupled | Hard to add separate collections | May need to filter in retrieval instead |
| Injection happens in Claude Code, not plugin | Can't modify format | May need different approach |

---

## Deliverables

By end of Phase 1, produce:

1. **ARCHITECTURE.md** - File structure and purpose of each component
2. **OBSERVATION_FLOW.md** - Traced path from capture → compress → store
3. **RETRIEVAL_FLOW.md** - Traced path from search → retrieve → inject
4. **EXTENSION_POINTS.md** - Exact files/functions to modify for each feature
5. **RISKS.md** - Anything discovered that changes our approach

These documents live in the forked repo and guide Phase 2-3.

---

## Checklist

| Task | Done |
|------|------|
| Fork repository | ⬜ |
| Map file structure | ⬜ |
| Find and document compression prompts | ⬜ |
| Find and document storage schema | ⬜ |
| Find and document hook definitions | ⬜ |
| Find and document MCP tools | ⬜ |
| Find and document context injection | ⬜ |
| Identify extension points for categories | ⬜ |
| Identify extension points for supersede | ⬜ |
| Identify extension points for tiered retrieval | ⬜ |
| Identify extension points for injection format | ⬜ |
| Document unknowns and risks | ⬜ |
| Create ARCHITECTURE.md | ⬜ |
| Create OBSERVATION_FLOW.md | ⬜ |
| Create RETRIEVAL_FLOW.md | ⬜ |
| Create EXTENSION_POINTS.md | ⬜ |

---

## Success Criteria

Phase 1 is complete when you can confidently say:

> "To add personality observation categories, I modify [FILE] at [FUNCTION]. 
> To change the compression prompt, I edit [FILE] at line [X].
> To implement tiered retrieval, I modify [FILE] at [FUNCTION].
> The main risks are [X, Y, Z] and we'll handle them by [approach]."

---

## Next Phase

**Phase 2: Design Interaction Memory Schema**

With internals understood, we design:
- Exact category taxonomy
- Supersede rules per category
- Database schema changes (if needed)
- Retrieval query design

Phase 1 findings directly inform Phase 2 decisions.
