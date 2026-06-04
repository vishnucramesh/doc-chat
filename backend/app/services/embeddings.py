"""NVIDIA NIM embeddings via the OpenAI-compatible endpoint.

The NIM `/v1/embeddings` endpoint accepts the same shape as OpenAI's but expects
the model name to be a full HF-style path (e.g. `nvidia/nv-embedqa-e5-v5`) and
supports an `input_type` extension that materially affects retrieval quality —
"passage" when embedding documents at ingest time, "query" when embedding the
user's question at retrieval time. We pass it as `extra_body` so the OpenAI SDK
forwards it verbatim.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import openai
from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

InputType = Literal["passage", "query"]


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Cached AsyncOpenAI client. One instance per process so the underlying
    httpx connection pool is reused across calls — without the cache, each
    embed call created a fresh client and paid TCP+TLS handshake costs."""
    s = get_settings()
    return AsyncOpenAI(api_key=s.nvidia_api_key, base_url=s.nvidia_api_base)


# Errors worth retrying — transient network / server-side issues. We
# deliberately exclude `openai.AuthenticationError` (config bug — retrying
# won't help) and `openai.BadRequestError` (malformed input — also a bug).
# Catching `Exception` (the previous behavior) hid real bugs behind 4
# retries and burned NIM credits on calls that could never succeed.
_RETRYABLE = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)


async def embed_batch(texts: list[str], *, input_type: InputType) -> list[list[float]]:
    """Embed a list of strings. Empty list short-circuits to avoid a useless API call."""
    if not texts:
        return []
    settings = get_settings()
    client = _client()

    # NIM caps batch size around 96 inputs per call for embedqa models. Be safe
    # and chunk at 32 — keeps individual requests small enough to retry cheaply.
    BATCH = 32
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        ):
            with attempt:
                resp = await client.embeddings.create(
                    model=settings.nvidia_embed_model,
                    input=batch,
                    extra_body={"input_type": input_type, "truncate": "END"},
                )
                out.extend([d.embedding for d in resp.data])
    return out


async def embed_query(text: str) -> list[float]:
    [vec] = await embed_batch([text], input_type="query")
    return vec
