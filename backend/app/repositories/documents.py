"""Data access for the `documents` and `chunks` tables.

Covers both the request path (list/upload/delete from `routers/documents.py`)
and the background ingestion path (status transitions + chunk inserts from
`services/ingestion.py`), so every query against these two tables lives here.
"""

from __future__ import annotations

from typing import Any

from app.services.supabase import _exec, admin_client

# Chunk-insert batch size. Supabase Postgres caps payloads around 5MB; 100 rows
# of 1024-d float embeddings stays safely under that.
_CHUNK_BATCH = 100

_LIST_FIELDS = (
    "id, filename, status, chunk_count, page_count, "
    "size_bytes, content_type, error, created_at"
)


# ── request path ────────────────────────────────────────────────────────────


async def list_for_user(user_id: str) -> list[dict]:
    sb = admin_client()
    return (
        await _exec(
            sb.table("documents")
            .select(_LIST_FIELDS)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
        )
    ).data or []


async def insert_pending(
    user_id: str,
    *,
    filename: str,
    storage_path: str,
    content_type: str | None,
    size_bytes: int,
) -> dict:
    sb = admin_client()
    rows = (
        await _exec(
            sb.table("documents").insert(
                {
                    "user_id": user_id,
                    "filename": filename,
                    "storage_path": storage_path,
                    "content_type": content_type,
                    "size_bytes": size_bytes,
                    "status": "pending",
                }
            )
        )
    ).data
    return rows[0]


async def get_storage_path(document_id: str, user_id: str) -> str | None:
    sb = admin_client()
    rows = (
        await _exec(
            sb.table("documents")
            .select("storage_path")
            .eq("id", document_id)
            .eq("user_id", user_id)
        )
    ).data
    return rows[0]["storage_path"] if rows else None


async def delete(document_id: str, user_id: str) -> None:
    sb = admin_client()
    await _exec(
        sb.table("documents").delete().eq("id", document_id).eq("user_id", user_id)
    )


# ── ingestion path ──────────────────────────────────────────────────────────


async def get_for_ingest(document_id: str, user_id: str) -> dict | None:
    sb = admin_client()
    return (
        await _exec(
            sb.table("documents")
            .select("storage_path, content_type, filename")
            .eq("id", document_id)
            .eq("user_id", user_id)
            .single()
        )
    ).data


async def mark_processing(document_id: str, user_id: str) -> None:
    sb = admin_client()
    await _exec(
        sb.table("documents")
        .update({"status": "processing"})
        .eq("id", document_id)
        .eq("user_id", user_id)
    )


async def mark_ready(
    document_id: str, user_id: str, *, chunk_count: int, page_count: int
) -> None:
    sb = admin_client()
    await _exec(
        sb.table("documents")
        .update(
            {
                "status": "ready",
                "chunk_count": chunk_count,
                "page_count": page_count,
                "error": None,
            }
        )
        .eq("id", document_id)
        .eq("user_id", user_id)
    )


async def mark_failed(document_id: str, user_id: str, *, error: str) -> None:
    sb = admin_client()
    await _exec(
        sb.table("documents")
        .update({"status": "failed", "error": error[:500]})
        .eq("id", document_id)
        .eq("user_id", user_id)
    )


async def insert_chunks(rows: list[dict[str, Any]]) -> None:
    """Insert chunk rows in batches to stay under the payload cap."""
    sb = admin_client()
    for i in range(0, len(rows), _CHUNK_BATCH):
        await _exec(sb.table("chunks").insert(rows[i : i + _CHUNK_BATCH]))
