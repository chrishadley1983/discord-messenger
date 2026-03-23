"""Embedding generation for Second Brain.

Primary: HuggingFace Inference API (gte-base via router.huggingface.co)
Note: Supabase Edge Function was planned but never deployed — skipped entirely.

Raises EmbeddingError on failure — callers decide how to handle.
"""

import asyncio
import hashlib
import os
import random
import time
from dataclasses import dataclass

import httpx

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


# HuggingFace Inference API (primary)
HF_INFERENCE_URL = "https://router.huggingface.co/hf-inference/models/thenlper/gte-base/pipeline/feature-extraction"
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
# Core embedding functions
# ---------------------------------------------------------------------------

async def generate_embedding(text: str) -> list[float]:
    """Generate embedding for a single text.

    Uses HuggingFace Inference API with retry/backoff.
    60-second TTL cache avoids duplicate API calls.

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

    # HuggingFace Inference API (primary — Edge Function not deployed)
    if HF_TOKEN:
        async with _semaphore:
            try:
                data = await _hf_request_with_retry(
                    payload={"inputs": text},
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
                logger.warning(f"HuggingFace embedding failed: {e}")

    raise EmbeddingError(
        f"Embedding failed for text ({len(text)} chars): {text[:60]}..."
    )


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts.

    Tries HuggingFace batch first, falls back to concurrent singles.

    Raises:
        EmbeddingError: If any embedding in the batch fails.
    """
    if not texts:
        return []

    # Truncate texts
    texts = [t[:EMBEDDING_TEXT_LIMIT] if len(t) > EMBEDDING_TEXT_LIMIT else t for t in texts]

    # 1. Try HuggingFace batch (primary — Edge Function not deployed)
    if HF_TOKEN:
        try:
            data = await _hf_request_with_retry(
                payload={"inputs": texts},
                timeout=EMBEDDING_BATCH_TIMEOUT,
                context=f"batch ({len(texts)} texts)",
            )
            if isinstance(data, list) and len(data) == len(texts):
                _stats.hf_batch_ok += 1
                return data
        except Exception as e:
            _stats.hf_batch_fail += 1
            logger.warning(f"HF batch failed ({len(texts)} texts), falling back to concurrent singles: {e}")

    # 2. Concurrent single fallback
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
    """Make HuggingFace API request with retries and exponential backoff + jitter.

    Retries on: 429 (rate limit), 502/503 (gateway/model loading),
    network timeouts, connection errors.
    Non-retryable: 402 (credits exhausted), 4xx (client errors).

    Best practices applied:
    - wait_for_model only sent on retry after 503 (not on first attempt)
    - 503 estimated_time from response body used to set retry delay
    - Jitter added to prevent thundering herd during morning burst
    - 402 detected and raised immediately (monthly credit limit)
    """
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    last_error = None
    got_503 = False

    for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
        try:
            client = _get_http_client()

            # Only send wait_for_model on retry after a 503 (model cold start)
            req_payload = dict(payload)
            if got_503:
                req_payload["options"] = {"wait_for_model": True}

            response = await client.post(
                HF_INFERENCE_URL,
                headers=headers,
                json=req_payload,
                timeout=timeout,
            )

            # 402 = monthly credits exhausted — not retryable
            if response.status_code == 402:
                raise EmbeddingError(
                    f"HuggingFace free tier credits exhausted (402). "
                    f"Check usage at huggingface.co/settings/billing"
                )

            if response.status_code in (429, 502, 503):
                # Base delay with exponential backoff
                delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))

                # 503: check estimated_time in response body for model loading
                if response.status_code == 503:
                    got_503 = True
                    try:
                        body = response.json()
                        estimated = body.get("estimated_time")
                        if estimated and isinstance(estimated, (int, float)):
                            delay = max(delay, estimated)
                    except Exception:
                        pass

                # 429: respect Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, int(retry_after))

                # Add jitter (±25%) to prevent thundering herd
                delay *= 1.0 + random.uniform(-0.25, 0.25)

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
            delay *= 1.0 + random.uniform(-0.25, 0.25)
            logger.warning(
                f"HF {context}: timeout on attempt {attempt}/{EMBEDDING_MAX_RETRIES}, "
                f"retrying in {delay:.1f}s"
            )
            last_error = e
            await asyncio.sleep(delay)

        except httpx.ConnectError as e:
            _stats.retries += 1
            delay = EMBEDDING_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            delay *= 1.0 + random.uniform(-0.25, 0.25)
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
