"""Embedding generation for Second Brain.

Fallback chain:
1. Supabase Edge Function (gte-small, deployed, zero external dependency)
2. HuggingFace Inference API (requires HF_TOKEN env var)

Raises EmbeddingError on failure — callers decide how to handle.
"""

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger
from .config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_TEXT_LIMIT,
    EMBEDDING_SINGLE_TIMEOUT,
    EMBEDDING_BATCH_TIMEOUT,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_RETRY_BASE_DELAY,
    EMBEDDING_MAX_CONCURRENT,
)


# HuggingFace Inference API (fallback)
HF_INFERENCE_URL = "https://router.huggingface.co/hf-inference/models/thenlper/gte-small/pipeline/feature-extraction"
HF_TOKEN = os.getenv("HF_TOKEN")

# Rate limiting semaphore for concurrent requests
_semaphore = asyncio.Semaphore(EMBEDDING_MAX_CONCURRENT)

# Shared httpx client (avoids creating a new TCP connection per request)
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create a shared httpx client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=60)
    return _http_client


# Simple TTL cache for query embeddings (avoids duplicate API calls within 60s)
_CACHE_TTL = 60  # seconds
_embedding_cache: dict[str, tuple[float, list[float]]] = {}


class EmbeddingError(Exception):
    """Raised when embedding generation fails after all retries."""
    pass


# ---------------------------------------------------------------------------
# Observability counters
# ---------------------------------------------------------------------------

@dataclass
class _EmbeddingStats:
    edge_ok: int = 0
    edge_fail: int = 0
    hf_single_ok: int = 0
    hf_batch_ok: int = 0
    hf_single_fail: int = 0
    hf_batch_fail: int = 0
    retries: int = 0
    sequential_fallbacks: int = 0
    cache_hits: int = 0

_stats = _EmbeddingStats()


def get_embedding_stats() -> dict:
    """Return current embedding pipeline counters."""
    return {
        "edge_ok": _stats.edge_ok,
        "edge_fail": _stats.edge_fail,
        "hf_single_ok": _stats.hf_single_ok,
        "hf_batch_ok": _stats.hf_batch_ok,
        "hf_single_fail": _stats.hf_single_fail,
        "hf_batch_fail": _stats.hf_batch_fail,
        "retries": _stats.retries,
        "sequential_fallbacks": _stats.sequential_fallbacks,
        "cache_hits": _stats.cache_hits,
        "cache_size": len(_embedding_cache),
    }


def reset_embedding_stats() -> None:
    """Reset counters, cache, and HTTP client (useful for tests)."""
    global _stats, _http_client
    _stats = _EmbeddingStats()
    _embedding_cache.clear()
    if _http_client and not _http_client.is_closed:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_http_client.aclose())
        except RuntimeError:
            pass  # No running loop — client will be GC'd
    _http_client = None


# ---------------------------------------------------------------------------
# Supabase Edge Function (primary)
# ---------------------------------------------------------------------------

async def _embed_via_edge_function(text: str) -> list[float] | None:
    """Generate embedding via Supabase Edge Function.

    Returns None on failure (caller falls through to HuggingFace).
    """
    try:
        client = _get_http_client()
        response = await client.post(
            f"{SUPABASE_URL}/functions/v1/embed",
            headers={
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={"text": text},
            timeout=30,
        )
        if response.status_code == 404:
            logger.debug("Edge Function /embed not deployed")
            return None
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if embedding and len(embedding) == EMBEDDING_DIMENSIONS:
            _stats.edge_ok += 1
            return embedding
        logger.warning(f"Edge Function returned unexpected shape: {len(embedding) if embedding else 'None'}")
        return None
    except Exception as e:
        _stats.edge_fail += 1
        logger.debug(f"Edge Function embedding failed: {e}")
        return None


async def _embed_batch_via_edge_function(texts: list[str]) -> list[list[float]] | None:
    """Generate embeddings for batch via Edge Function (sequential, one at a time).

    Edge Function doesn't support batch natively, so we run concurrent requests.
    Returns None if any single embedding fails.
    """
    async def _one(text: str) -> list[float] | None:
        async with _semaphore:
            return await _embed_via_edge_function(text)

    results = await asyncio.gather(*[_one(t) for t in texts])

    # Check all succeeded
    embeddings = []
    for r in results:
        if r is None:
            return None  # Fall through to HuggingFace batch
        embeddings.append(r)
    return embeddings


# ---------------------------------------------------------------------------
# Core embedding functions
# ---------------------------------------------------------------------------

async def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text.

    Chain: Edge Function -> HuggingFace -> EmbeddingError.
    Uses a 60-second TTL cache to avoid duplicate API calls.

    Raises:
        EmbeddingError: If all methods fail.
    """
    text = text[:EMBEDDING_TEXT_LIMIT] if len(text) > EMBEDDING_TEXT_LIMIT else text

    # Check cache (use hash to avoid storing full text as key)
    cache_key = hashlib.md5(text.encode()).hexdigest()
    cached = _embedding_cache.get(cache_key)
    if cached:
        ts, vec = cached
        if time.monotonic() - ts < _CACHE_TTL:
            _stats.cache_hits += 1
            return vec
        else:
            del _embedding_cache[cache_key]

    # 1. Try Supabase Edge Function (primary)
    embedding = await _embed_via_edge_function(text)
    if embedding:
        _cache_put(cache_key, embedding)
        return embedding

    # 2. Try HuggingFace (fallback)
    if HF_TOKEN:
        async with _semaphore:
            try:
                data = await _hf_request_with_retry(
                    payload={"inputs": text, "options": {"wait_for_model": True}},
                    timeout=EMBEDDING_SINGLE_TIMEOUT,
                    context=f"single ({len(text)} chars)",
                )
                if isinstance(data, list) and len(data) > 0:
                    vec = data[0] if isinstance(data[0], list) else data
                    if len(vec) == EMBEDDING_DIMENSIONS:
                        _stats.hf_single_ok += 1
                        _cache_put(cache_key, vec)
                        return vec
            except Exception as e:
                _stats.hf_single_fail += 1
                logger.warning(f"HuggingFace fallback failed: {e}")

    raise EmbeddingError(
        f"All embedding methods failed for text ({len(text)} chars): {text[:60]}..."
    )


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts.

    Chain: Edge Function (concurrent) -> HuggingFace batch -> concurrent singles.

    Raises:
        EmbeddingError: If any embedding in the batch fails.
    """
    if not texts:
        return []

    # Truncate texts
    texts = [t[:EMBEDDING_TEXT_LIMIT] if len(t) > EMBEDDING_TEXT_LIMIT else t for t in texts]

    # 1. Try Edge Function (concurrent individual calls)
    edge_results = await _embed_batch_via_edge_function(texts)
    if edge_results:
        return edge_results

    # 2. Try HuggingFace batch
    if HF_TOKEN:
        try:
            data = await _hf_request_with_retry(
                payload={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=EMBEDDING_BATCH_TIMEOUT,
                context=f"batch ({len(texts)} texts)",
            )
            if isinstance(data, list) and len(data) == len(texts):
                _stats.hf_batch_ok += 1
                return data
        except Exception as e:
            _stats.hf_batch_fail += 1
            logger.warning(f"HF batch failed ({len(texts)} texts), falling back to concurrent singles: {e}")

    # 3. Concurrent single fallback (tries Edge first, then HF per text)
    _stats.sequential_fallbacks += 1
    logger.info(f"Concurrent single fallback for {len(texts)} embeddings")

    results = await asyncio.gather(
        *[generate_embedding(t) for t in texts],
        return_exceptions=True,
    )

    embeddings = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            raise EmbeddingError(
                f"Failed to embed chunk {i}/{len(texts)} "
                f"({len(texts[i])} chars): {result}"
            )
        embeddings.append(result)

    return embeddings


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------

def _cache_put(key: str, vec: list[float]) -> None:
    """Store embedding in TTL cache, evicting oldest if full."""
    _embedding_cache[key] = (time.monotonic(), vec)
    if len(_embedding_cache) > 100:
        # Python dicts maintain insertion order — pop the first (oldest inserted) key
        oldest_key = next(iter(_embedding_cache))
        del _embedding_cache[oldest_key]


# ---------------------------------------------------------------------------
# HuggingFace request with retry + exponential backoff
# ---------------------------------------------------------------------------

async def _hf_request_with_retry(
    payload: dict,
    timeout: int,
    context: str,
) -> list:
    """Make HuggingFace API request with retries and exponential backoff.

    Retries on: 429 (rate limit), 502/503 (gateway/model loading),
    network timeouts, connection errors.
    """
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    last_error = None

    for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
        try:
            client = _get_http_client()
            response = await client.post(
                HF_INFERENCE_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if response.status_code in (429, 502, 503):
                delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, int(retry_after))
                _stats.retries += 1
                logger.warning(
                    f"HF {context}: {response.status_code} on attempt {attempt}/{EMBEDDING_MAX_RETRIES}, "
                    f"retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException as e:
            _stats.retries += 1
            delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"HF {context}: timeout on attempt {attempt}/{EMBEDDING_MAX_RETRIES}, "
                f"retrying in {delay:.1f}s"
            )
            last_error = e
            await asyncio.sleep(delay)

        except httpx.ConnectError as e:
            _stats.retries += 1
            delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                f"HF {context}: connection error on attempt {attempt}/{EMBEDDING_MAX_RETRIES}, "
                f"retrying in {delay:.1f}s — {e}"
            )
            last_error = e
            await asyncio.sleep(delay)

        except httpx.HTTPStatusError as e:
            _stats.hf_single_fail += 1
            logger.error(
                f"HF {context}: HTTP {e.response.status_code} — "
                f"body: {e.response.text[:200]}"
            )
            raise EmbeddingError(
                f"HuggingFace API error {e.response.status_code}: {e.response.text[:200]}"
            ) from e

    raise EmbeddingError(
        f"HuggingFace embedding failed after {EMBEDDING_MAX_RETRIES} attempts "
        f"for {context}: {last_error}"
    )
