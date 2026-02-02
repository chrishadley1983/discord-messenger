# Second Brain Implementation Blockers

## Active Blockers

### B1: Supabase Embedding Function Setup
**Status:** Needs verification
**Impact:** Phase 1 (embedding generation)

The migration includes a `generate_embedding()` function that uses `ai.embed()`. This requires:
1. Supabase AI extension to be enabled on the project
2. OR deploy a Supabase Edge Function for embeddings
3. OR use Hugging Face Inference API as fallback

**Resolution options:**
1. Run `CREATE EXTENSION IF NOT EXISTS ai;` in Supabase SQL editor
2. Deploy edge function at `supabase/functions/embed/index.ts`
3. Use HuggingFace gte-small model via their free inference API

**Workaround:** The db.py module has fallback to return zero vectors, which allows testing other functionality but won't produce meaningful search results.

---

## Resolved Blockers

### B0: OpenAI API Key (RESOLVED)
**Resolution:** Using Supabase's built-in gte-small model instead of OpenAI
- Zero API cost
- 384 dimensions (vs 1536 for OpenAI)
- No external API key needed

---

## Notes

- Migration file: `migrations/002_create_second_brain_tables.sql`
- Run migration manually in Supabase SQL Editor before testing
- The `search_knowledge` RPC function handles semantic search with decay weighting
