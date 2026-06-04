"""Data access for the `messages` table."""

from __future__ import annotations

from typing import Any

from app.services.supabase import _exec, admin_client


async def add_user_message(conversation_id: str, user_id: str, content: str) -> None:
    sb = admin_client()
    await _exec(
        sb.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "user",
                "content": content,
            }
        )
    )


async def add_assistant_message(
    conversation_id: str,
    user_id: str,
    *,
    content: str,
    citations: Any,
    retrieval_ms: int,
    generation_ms: int,
) -> None:
    sb = admin_client()
    await _exec(
        sb.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": "assistant",
                "content": content,
                "citations": citations,
                "retrieval_ms": retrieval_ms,
                "generation_ms": generation_ms,
            }
        )
    )


async def list_for_conversation(conversation_id: str, user_id: str) -> list[dict]:
    """Full message thread in chronological order — for the detail view."""
    sb = admin_client()
    return (
        await _exec(
            sb.table("messages")
            .select("id, role, content, citations, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
        )
    ).data or []


async def recent_history(
    conversation_id: str, user_id: str, *, limit: int
) -> list[dict]:
    """Most-recent messages, newest first (caller reverses to chronological).

    Ordered DESC + LIMIT so we get the *latest* turns; an ASC + LIMIT would
    silently return the oldest turns and degrade long conversations. System
    messages are excluded from the history we feed back to the model.
    """
    sb = admin_client()
    return (
        await _exec(
            sb.table("messages")
            .select("role, content, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .neq("role", "system")
            .order("created_at", desc=True)
            .limit(limit)
        )
    ).data or []
