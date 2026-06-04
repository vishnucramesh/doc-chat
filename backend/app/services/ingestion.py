"""End-to-end ingestion: storage object → parsed pages → chunks → embeddings → DB rows.

Runs as a FastAPI BackgroundTask so the HTTP upload returns immediately with a
`pending` document row. The frontend polls the document's `status` field.

Failure mode: any exception flips status to 'failed' and records the error
string. We do NOT delete the storage object on failure — keeping the raw bytes
makes re-ingestion trivial after a fix.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.repositories import documents as documents_repo
from app.services.chunking import Chunk, chunk_pages
from app.services.embeddings import embed_batch
from app.services.parsing import parse_pdf, parse_text
from app.services.supabase import admin_client

log = logging.getLogger(__name__)


async def ingest_document(*, document_id: str, user_id: str) -> None:
    settings = get_settings()
    sb = admin_client()
    try:
        await documents_repo.mark_processing(document_id, user_id)

        doc = await documents_repo.get_for_ingest(document_id, user_id)
        if not doc:
            raise RuntimeError(f"document {document_id} disappeared mid-ingest")

        # The supabase-py storage API is sync — wrap the blocking download
        # so we don't stall the event loop during ingestion.
        raw = await asyncio.to_thread(
            sb.storage.from_(settings.supabase_storage_bucket).download,
            doc["storage_path"],
        )
        if not raw:
            raise RuntimeError("empty download from storage")

        content_type: str = doc.get("content_type") or ""
        filename: str = doc.get("filename") or ""
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            pages = parse_pdf(raw)
        else:
            pages = parse_text(raw)

        chunks: list[Chunk] = chunk_pages(
            pages,
            target=settings.chunk_target_tokens,
            overlap=settings.chunk_overlap_tokens,
        )
        # Empty-document edge case: write 0 chunks and mark ready so the UI
        # doesn't sit at "processing" forever.
        if not chunks:
            await documents_repo.mark_ready(
                document_id, user_id, chunk_count=0, page_count=len(pages)
            )
            return

        embeddings = await embed_batch([c.text for c in chunks], input_type="passage")
        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"embedding count {len(embeddings)} != chunk count {len(chunks)}"
            )

        rows: list[dict[str, Any]] = [
            {
                "document_id": document_id,
                "user_id": user_id,
                "content": c.text,
                "page": c.page,
                "chunk_index": i,
                "token_count": c.token_count,
                "embedding": e,
            }
            for i, (c, e) in enumerate(zip(chunks, embeddings, strict=True))
        ]

        await documents_repo.insert_chunks(rows)
        await documents_repo.mark_ready(
            document_id, user_id, chunk_count=len(chunks), page_count=len(pages)
        )
        log.info(
            "ingested document",
            extra={"document_id": document_id, "chunks": len(chunks), "pages": len(pages)},
        )
    except Exception as e:
        log.exception("ingestion failed for %s", document_id)
        try:
            await documents_repo.mark_failed(document_id, user_id, error=str(e))
        except Exception:
            # If the status update itself fails, log it and move on. A doc
            # stuck in 'processing' is recoverable via the manual cleanup script.
            log.exception("failed to mark document %s as failed", document_id)
