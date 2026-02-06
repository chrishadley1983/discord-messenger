"""Embedding generation for Second Brain.

Uses multiple fallback strategies:
1. Supabase Edge Function (deployed, runs gte-small natively)
2. Supabase RPC with ai extension (if enabled)
3. HuggingFace Inference API (requires HF_TOKEN env var)
4. Zero vector (last resort - search won't work well)
"""

import os

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger
from .config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL


# HuggingFace Inference API (requires auth since 2026)
HF_INFERENCE_URL = "https://router.huggingface.co/hf-inference/models/thenlper/gte-small"
HF_TOKEN = os.getenv("HF_TOKEN")


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding using best available method.

    Tries in order:
    1. Supabase Edge Function
    2. Supabase RPC
    3. HuggingFace Inference API
    4. Zero vector fallback
    """
    # Truncate very long text to avoid issues
    text = text[:8000] if len(text) > 8000 else text

    # Try Supabase Edge Function first
    try:
        embedding = await _embed_via_edge_function(text)
        if embedding and len(embedding) == EMBEDDING_DIMENSIONS:
            return embedding
    except Exception as e:
        logger.debug(f"Edge function embedding failed: {e}")

    # Try Supabase RPC
    try:
        embedding = await _embed_via_rpc(text)
        if embedding and len(embedding) == EMBEDDING_DIMENSIONS:
            return embedding
    except Exception as e:
        logger.debug(f"RPC embedding failed: {e}")

    # Try HuggingFace Inference API
    try:
        embedding = await _embed_via_huggingface(text)
        if embedding and len(embedding) == EMBEDDING_DIMENSIONS:
            return embedding
    except Exception as e:
        logger.debug(f"HuggingFace embedding failed: {e}")

    # Last resort: zero vector
    logger.warning(f"All embedding methods failed, returning zero vector for: {text[:50]}...")
    return [0.0] * EMBEDDING_DIMENSIONS


async def _embed_via_edge_function(text: str) -> list[float] | None:
    """Generate embedding via Supabase Edge Function."""
    async with httpx.AsyncClient() as client:
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
            return None
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")


async def _embed_via_rpc(text: str) -> list[float] | None:
    """Generate embedding via Supabase RPC function."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/generate_embedding",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={"input_text": text},
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        return response.json()


async def _embed_via_huggingface(text: str) -> list[float] | None:
    """Generate embedding via HuggingFace Inference API (requires HF_TOKEN)."""
    if not HF_TOKEN:
        return None
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        response = await client.post(
            HF_INFERENCE_URL,
            headers=headers,
            json={"inputs": text, "options": {"wait_for_model": True}},
            timeout=60,  # HF can be slow on cold start
        )

        if response.status_code == 503:
            # Model loading, retry once
            logger.debug("HuggingFace model loading, retrying...")
            import asyncio
            await asyncio.sleep(5)
            response = await client.post(
                HF_INFERENCE_URL,
                headers=headers,
                json={"inputs": text, "options": {"wait_for_model": True}},
                timeout=60,
            )

        response.raise_for_status()
        data = response.json()

        # HuggingFace returns [[embedding]] for single input
        if isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], list):
                return data[0]
            return data
        return None


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts.

    Uses HuggingFace batch API when possible for efficiency.
    """
    if not texts:
        return []

    # Try HuggingFace batch first (most efficient)
    try:
        embeddings = await _embed_batch_huggingface(texts)
        if embeddings and len(embeddings) == len(texts):
            return embeddings
    except Exception as e:
        logger.debug(f"HuggingFace batch embedding failed: {e}")

    # Fall back to sequential
    logger.debug(f"Falling back to sequential embedding for {len(texts)} texts")
    embeddings = []
    for text in texts:
        emb = await generate_embedding(text)
        embeddings.append(emb)
    return embeddings


async def _embed_batch_huggingface(texts: list[str]) -> list[list[float]] | None:
    """Generate embeddings for batch via HuggingFace."""
    if not HF_TOKEN:
        return None
    # Truncate texts
    texts = [t[:8000] if len(t) > 8000 else t for t in texts]

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            HF_INFERENCE_URL,
            headers=headers,
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=120,  # Longer timeout for batch
        )

        if response.status_code == 503:
            import asyncio
            await asyncio.sleep(5)
            response = await client.post(
                HF_INFERENCE_URL,
                headers=headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=120,
            )

        response.raise_for_status()
        data = response.json()

        # Should return list of embeddings
        if isinstance(data, list) and len(data) == len(texts):
            return data
        return None
