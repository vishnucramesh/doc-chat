"""Retrieval — embed the question, fetch top-K via hybrid RRF, expand into
windows of adjacent chunks for narrative continuity.

The hybrid (vector + lexical) merge happens in Postgres — see the
`match_chunks` function defined in the Alembic migrations under
`backend/migrations/versions/`. Doing it server-side keeps a single network
round-trip and lets the planner push predicates into the ivfflat + GIN
indexes; doing it in Python would mean pulling two pools of candidate chunks
across the wire (with their full text) and merging here.

After the top-K hits come back, we run a SECOND query that fetches the
neighboring chunks (±N from each hit, same document) and merge into
"context windows" — see `_merge_to_windows`. Why: static chunk-per-block
retrieval often gives the LLM a passage that starts mid-thought ("...as
described above, this means X"). With windowing, the model sees a few
sentences of lead-in and follow-through, which is where most of the
continuity wins come from. The cost is ~2-3× prompt size; configurable
via `RETRIEVAL_NEIGHBOR_WINDOW` (set to 0 to disable).

Citations still anchor to the originally retrieved chunk (the "core" of the
window) so users see what the retriever actually scored highly — neighbors
are context for the LLM, not surfaced as separate sources in the UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.services.embeddings import embed_query
from app.services.supabase import _exec, admin_client

log = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A single chunk — either a core retrieval hit or a neighbor pulled in
    for window expansion. `is_core=True` means the retriever actually scored
    this chunk; False means it was added for context only."""

    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    content: str
    chunk_index: int
    vector_score: float = 0.0
    lexical_score: float = 0.0
    rrf_score: float = 0.0
    is_core: bool = True


@dataclass
class ContextWindow:
    """A contiguous run of chunks from one document, ordered by chunk_index.

    A window holds at least one core chunk (otherwise it wouldn't have been
    fetched). It may also contain neighbor chunks pulled in for continuity.
    When rendered into a prompt, the whole window becomes ONE numbered
    context block.
    """

    document_id: str
    filename: str
    chunks: list[RetrievedChunk] = field(default_factory=list)

    @property
    def text(self) -> str:
        # Paragraph break between chunks — preserves readability even if a
        # chunker boundary fell mid-paragraph.
        return "\n\n".join(c.content for c in self.chunks)

    @property
    def pages(self) -> list[int]:
        return sorted({c.page for c in self.chunks if c.page is not None})

    @property
    def core_chunks(self) -> list[RetrievedChunk]:
        return [c for c in self.chunks if c.is_core]

    @property
    def primary_chunk_id(self) -> str:
        """The "best" core chunk in this window — used as the citation anchor
        (the chunk the user sees if they click the citation chip)."""
        cores = self.core_chunks
        if not cores:
            # Shouldn't happen — _merge_to_windows guarantees at least one
            # core — but fall back gracefully rather than IndexError.
            return self.chunks[0].chunk_id
        return max(cores, key=lambda c: c.rrf_score).chunk_id

    @property
    def core_rrf_score(self) -> float:
        return max((c.rrf_score for c in self.core_chunks), default=0.0)


# ─── Pure-logic helpers (testable without DB) ─────────────────────────────


def _desired_indexes(cores: list[RetrievedChunk], neighbor_window: int) -> set[int]:
    """Given a list of core chunks from ONE document, return every chunk_index
    we need to fetch (cores + their ± neighbor_window neighbors).

    chunk_index is clamped at 0 — there's no chunk -1.
    """
    out: set[int] = set()
    for c in cores:
        low = max(0, c.chunk_index - neighbor_window)
        high = c.chunk_index + neighbor_window
        out.update(range(low, high + 1))
    return out


def _merge_to_windows(
    *,
    document_id: str,
    filename: str,
    cores_by_id: dict[str, RetrievedChunk],
    fetched_rows: list[dict[str, Any]],
) -> list[ContextWindow]:
    """Given fetched chunk rows for a single document, group adjacent
    chunk_indexes into windows.

    `cores_by_id` lets us preserve the original RetrievedChunk (with scores
    and is_core=True) for chunks that were retrieval hits; everything else
    becomes a neighbor with is_core=False.

    Pure function — no DB, no IO. Tested directly.
    """
    chunks: list[RetrievedChunk] = []
    for row in fetched_rows:
        chunk_id = row["id"]
        if chunk_id in cores_by_id:
            chunks.append(cores_by_id[chunk_id])
        else:
            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    filename=filename,
                    page=row.get("page"),
                    content=row["content"],
                    chunk_index=row["chunk_index"],
                    is_core=False,
                )
            )

    chunks.sort(key=lambda c: c.chunk_index)

    # Group into contiguous runs. Two chunks are in the same run iff their
    # chunk_index differs by exactly 1.
    runs: list[list[RetrievedChunk]] = []
    current: list[RetrievedChunk] = []
    for ch in chunks:
        if not current or ch.chunk_index == current[-1].chunk_index + 1:
            current.append(ch)
        else:
            runs.append(current)
            current = [ch]
    if current:
        runs.append(current)

    return [ContextWindow(document_id=document_id, filename=filename, chunks=run) for run in runs]


# ─── Public retrieval ─────────────────────────────────────────────────────


async def retrieve(
    *,
    user_id: str,
    query: str,
    document_ids: list[str] | None = None,
    top_k: int | None = None,
    neighbor_window: int | None = None,
) -> list[ContextWindow]:
    settings = get_settings()
    if not query.strip():
        return []

    W = neighbor_window if neighbor_window is not None else settings.retrieval_neighbor_window

    emb = await embed_query(query)
    sb = admin_client()
    resp = await _exec(
        sb.rpc(
            "match_chunks",
            {
                "p_user_id": user_id,
                "p_query_emb": emb,
                "p_query_text": query,
                "p_doc_ids": document_ids,
                "p_match_k": top_k or settings.retrieval_top_k,
                "p_pool_k": settings.retrieval_pool_k,
            },
        )
    )
    rows = resp.data or []
    if not rows:
        return []

    cores: list[RetrievedChunk] = [
        RetrievedChunk(
            chunk_id=r["chunk_id"],
            document_id=r["document_id"],
            filename=r["filename"],
            page=r.get("page"),
            content=r["content"],
            chunk_index=r["chunk_index"],
            vector_score=float(r.get("vector_score") or 0.0),
            lexical_score=float(r.get("lexical_score") or 0.0),
            rrf_score=float(r.get("rrf_score") or 0.0),
            is_core=True,
        )
        for r in rows
    ]

    # Window expansion disabled — each core becomes its own single-chunk window.
    if W <= 0:
        return [
            ContextWindow(document_id=c.document_id, filename=c.filename, chunks=[c]) for c in cores
        ]

    # Group cores by document so we can issue one neighbor-fetch per document.
    by_doc: dict[str, list[RetrievedChunk]] = {}
    for c in cores:
        by_doc.setdefault(c.document_id, []).append(c)

    windows: list[ContextWindow] = []
    for doc_id, doc_cores in by_doc.items():
        indexes = sorted(_desired_indexes(doc_cores, W))
        filename = doc_cores[0].filename
        fetched = (
            await _exec(
                sb.table("chunks")
                .select("id, chunk_index, page, content")
                .eq("user_id", user_id)
                .eq("document_id", doc_id)
                .in_("chunk_index", indexes)
                .order("chunk_index")
            )
        ).data or []
        windows.extend(
            _merge_to_windows(
                document_id=doc_id,
                filename=filename,
                cores_by_id={c.chunk_id: c for c in doc_cores},
                fetched_rows=fetched,
            )
        )

    # Order by the best RRF score among each window's core chunks — strong
    # hits first, regardless of which document they came from.
    windows.sort(key=lambda w: w.core_rrf_score, reverse=True)
    return windows
