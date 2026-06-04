"""Document CRUD + upload.

Upload flow: multipart file → upload bytes to Supabase Storage under a
user-scoped path → insert a `pending` document row → schedule the ingest
pipeline as a BackgroundTask. Returning before ingest finishes keeps the UI
responsive; the frontend polls `GET /documents` to see status flip to `ready`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.config import get_settings
from app.deps import AuthUser, require_user
from app.repositories import documents as documents_repo
from app.schemas import DocumentOut
from app.services.ingestion import ingest_document
from app.services.supabase import admin_client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

MAX_BYTES = 20 * 1024 * 1024  # 20MB — generous for text PDFs
ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}
# Pre-formatted for the user-facing error message — never recomputed per request.
_ALLOWED_LABEL = ", ".join(sorted(s.lstrip(".").upper() for s in ALLOWED_SUFFIXES))


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: AuthUser = Depends(require_user)):
    return await documents_repo.list_for_user(user.id)


@router.post("", response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_user),
):
    settings = get_settings()
    filename = file.filename or "untitled"
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        shown = suffix.lstrip(".").upper() if suffix else "this file type"
        raise HTTPException(
            400,
            f"Can't upload {shown}. Supported types: {_ALLOWED_LABEL}.",
        )

    data = await file.read()
    if len(data) > MAX_BYTES:
        size_mb = len(data) / (1024 * 1024)
        limit_mb = MAX_BYTES // (1024 * 1024)
        raise HTTPException(
            413,
            f"File is too large ({size_mb:.1f} MB). Max upload size is {limit_mb} MB.",
        )
    if not data:
        raise HTTPException(400, "That file is empty.")

    sb = admin_client()
    # user-scoped folder satisfies the storage RLS policy in the migration
    storage_path = f"{user.id}/{uuid.uuid4().hex}{suffix}"

    # Upload-then-insert with explicit cleanup on partial failure. Previously
    # an upload-OK + insert-FAIL left an orphan blob in storage with no DB row
    # pointing at it (no way to clean it up except a manual sweep).
    try:
        await asyncio.to_thread(
            sb.storage.from_(settings.supabase_storage_bucket).upload,
            path=storage_path,
            file=data,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as e:
        log.exception("storage upload failed for %s", filename)
        raise HTTPException(500, f"Failed to upload file: {str(e)[:200]}") from e

    try:
        doc = await documents_repo.insert_pending(
            user.id,
            filename=filename,
            storage_path=storage_path,
            content_type=file.content_type,
            size_bytes=len(data),
        )
    except Exception as e:
        # Roll back the storage upload so we don't leak a phantom blob.
        log.exception("documents insert failed for %s; rolling back storage upload", filename)
        try:
            await asyncio.to_thread(
                sb.storage.from_(settings.supabase_storage_bucket).remove,
                [storage_path],
            )
        except Exception:
            log.exception("storage rollback also failed for %s", storage_path)
        raise HTTPException(500, f"Failed to record upload: {str(e)[:200]}") from e

    background.add_task(ingest_document, document_id=doc["id"], user_id=user.id)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, user: AuthUser = Depends(require_user)):
    storage_path = await documents_repo.get_storage_path(document_id, user.id)
    if storage_path is None:
        raise HTTPException(404, "not found")
    settings = get_settings()
    try:
        await asyncio.to_thread(
            admin_client().storage.from_(settings.supabase_storage_bucket).remove,
            [storage_path],
        )
    except Exception:
        # Best-effort — the chunks/document rows are the source of truth. A
        # leftover storage object is recoverable; a partial DB delete is not.
        log.exception("storage cleanup failed for %s (continuing with DB delete)", document_id)
    await documents_repo.delete(document_id, user.id)
