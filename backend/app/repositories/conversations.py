"""Data access for the `conversations` table."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.supabase import _exec, admin_client

_FIELDS = "id, title, created_at, updated_at"


async def list_for_user(user_id: str, *, limit: int = 50) -> list[dict]:
    sb = admin_client()
    return (
        await _exec(
            sb.table("conversations")
            .select(_FIELDS)
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(limit)
        )
    ).data or []


async def create(user_id: str, title: str) -> dict:
    sb = admin_client()
    rows = (
        await _exec(
            sb.table("conversations").insert({"user_id": user_id, "title": title})
        )
    ).data
    return rows[0]


async def get_owned(conversation_id: str, user_id: str) -> dict | None:
    """Return the conversation if it belongs to `user_id`, else None.

    Doubles as the ownership check before attaching messages or streaming.
    """
    sb = admin_client()
    rows = (
        await _exec(
            sb.table("conversations")
            .select(_FIELDS)
            .eq("id", conversation_id)
            .eq("user_id", user_id)
        )
    ).data
    return rows[0] if rows else None


async def delete(conversation_id: str, user_id: str) -> None:
    sb = admin_client()
    await _exec(
        sb.table("conversations")
        .delete()
        .eq("id", conversation_id)
        .eq("user_id", user_id)
    )


async def touch(conversation_id: str, user_id: str) -> None:
    """Bump `updated_at` so the conversation floats to the top of the list.

    ISO timestamp explicitly — PostgREST does NOT evaluate SQL function
    strings, so passing "now()" as a value would insert the literal text.
    """
    sb = admin_client()
    await _exec(
        sb.table("conversations")
        .update({"updated_at": datetime.now(UTC).isoformat()})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
    )
