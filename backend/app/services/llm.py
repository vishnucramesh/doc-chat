"""NVIDIA NIM chat completion via the OpenAI-compatible endpoint.

Exposes one helper — `stream_chat` — that yields plain text tokens as they
arrive. The caller is responsible for SSE framing; keeping that out of here
makes the function easy to unit-test and reusable from the eval harness, which
doesn't want SSE.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Cached AsyncOpenAI client — one instance per process so the httpx
    connection pool is reused across requests. Without this, every chat call
    created a fresh client and paid TCP+TLS handshake costs."""
    s = get_settings()
    return AsyncOpenAI(api_key=s.nvidia_api_key, base_url=s.nvidia_api_base)


async def stream_chat(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
) -> AsyncIterator[str]:
    """Yield assistant text tokens as they stream from NIM.

    Low temperature by default — RAG answers should stay close to the retrieved
    context, not improvise.
    """
    settings = get_settings()
    client = _client()
    stream = await client.chat.completions.create(
        model=settings.nvidia_chat_model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content


async def complete(messages: list[dict[str, Any]], *, temperature: float = 0.2) -> str:
    """Non-streaming variant — used by the eval harness."""
    parts: list[str] = []
    async for t in stream_chat(messages, temperature=temperature):
        parts.append(t)
    return "".join(parts)
