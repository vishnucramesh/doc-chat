"""Tests for the pure-logic half of context-window expansion.

We don't test the DB-touching path — that needs a real Postgres and is
covered by the (manual) eval harness. What we DO test is `_desired_indexes`
and `_merge_to_windows`, the two pure functions that determine which chunks
get fetched and how they're grouped into windows. Those are where regressions
would silently change retrieval quality, so they earn unit tests.
"""

from __future__ import annotations

from app.services.retrieval import (
    ContextWindow,
    RetrievedChunk,
    _desired_indexes,
    _merge_to_windows,
)


def _core(
    chunk_index: int,
    doc_id: str = "doc-a",
    chunk_id: str | None = None,
    *,
    page: int | None = ...,  # type: ignore[assignment]
    content: str | None = None,
) -> RetrievedChunk:
    # NOTE: when a fetched row's id matches a core's chunk_id, _merge_to_windows
    # uses the CORE's data (cores are authoritative from match_chunks). So if a
    # test wants the merged window to show specific page/content for that chunk,
    # set them here on the core, not on the row.
    return RetrievedChunk(
        chunk_id=chunk_id or f"{doc_id}-{chunk_index}",
        document_id=doc_id,
        filename=f"{doc_id}.pdf",
        page=chunk_index if page is ... else page,
        content=content if content is not None else f"chunk {chunk_index}",
        chunk_index=chunk_index,
        rrf_score=1.0 / (chunk_index + 1),
        is_core=True,
    )


# Sentinel so callers can pass `page=None` explicitly (text files) without it
# being treated as "use the default of chunk_index".
_UNSET = object()


def _row(chunk_id: str, chunk_index: int, page=_UNSET, content: str | None = None):
    return {
        "id": chunk_id,
        "chunk_index": chunk_index,
        "page": chunk_index if page is _UNSET else page,
        "content": content if content is not None else f"chunk {chunk_index}",
    }


# ─── _desired_indexes ─────────────────────────────────────────────────────


def test_desired_indexes_single_core_pm1():
    """One core at index 5, W=1 → {4, 5, 6}."""
    assert _desired_indexes([_core(5)], neighbor_window=1) == {4, 5, 6}


def test_desired_indexes_two_cores_overlapping_neighbors_dedupe():
    """Cores at 4 and 5, W=1 → {3, 4, 5, 6} (NOT {3,4,5,4,5,6} — set dedupes)."""
    assert _desired_indexes([_core(4), _core(5)], neighbor_window=1) == {3, 4, 5, 6}


def test_desired_indexes_zero_window_returns_only_cores():
    """W=0 means no neighbor expansion — just the cores themselves."""
    assert _desired_indexes([_core(3), _core(7)], neighbor_window=0) == {3, 7}


def test_desired_indexes_clamped_at_zero():
    """chunk_index can't go negative — neighbors below 0 are dropped."""
    # Core at index 0, W=2 would naively want {-2,-1,0,1,2}, but indexes
    # must be >= 0. Result is {0, 1, 2}.
    assert _desired_indexes([_core(0)], neighbor_window=2) == {0, 1, 2}


# ─── _merge_to_windows ────────────────────────────────────────────────────


def test_merge_single_core_becomes_one_window():
    cores = [_core(5)]
    fetched = [_row("doc-a-4", 4), _row("doc-a-5", 5), _row("doc-a-6", 6)]
    windows = _merge_to_windows(
        document_id="doc-a",
        filename="doc-a.pdf",
        cores_by_id={c.chunk_id: c for c in cores},
        fetched_rows=fetched,
    )
    assert len(windows) == 1
    w = windows[0]
    assert [c.chunk_index for c in w.chunks] == [4, 5, 6]
    # The core in the middle is marked is_core; the neighbors are not.
    assert [c.is_core for c in w.chunks] == [False, True, False]
    assert w.primary_chunk_id == "doc-a-5"
    assert w.pages == [4, 5, 6]


def test_merge_adjacent_cores_collapse_into_one_window():
    """Cores at 4 and 5 with W=1 → neighbors at 3 and 6 → contiguous run [3,4,5,6]
    — should produce ONE window, not two with shared neighbor."""
    cores = [_core(4), _core(5)]
    fetched = [
        _row("doc-a-3", 3),
        _row("doc-a-4", 4),
        _row("doc-a-5", 5),
        _row("doc-a-6", 6),
    ]
    windows = _merge_to_windows(
        document_id="doc-a",
        filename="doc-a.pdf",
        cores_by_id={c.chunk_id: c for c in cores},
        fetched_rows=fetched,
    )
    assert len(windows) == 1
    assert [c.chunk_index for c in windows[0].chunks] == [3, 4, 5, 6]
    assert len(windows[0].core_chunks) == 2


def test_merge_distant_cores_create_separate_windows():
    """Cores at 3 and 7 with W=1 → neighbors {2,3,4} and {6,7,8} — two windows
    because there's a gap between index 4 and 6."""
    cores = [_core(3), _core(7)]
    fetched = [
        _row("doc-a-2", 2),
        _row("doc-a-3", 3),
        _row("doc-a-4", 4),
        _row("doc-a-6", 6),
        _row("doc-a-7", 7),
        _row("doc-a-8", 8),
    ]
    windows = _merge_to_windows(
        document_id="doc-a",
        filename="doc-a.pdf",
        cores_by_id={c.chunk_id: c for c in cores},
        fetched_rows=fetched,
    )
    assert len(windows) == 2
    assert [c.chunk_index for c in windows[0].chunks] == [2, 3, 4]
    assert [c.chunk_index for c in windows[1].chunks] == [6, 7, 8]


def test_merge_window_text_concatenates_with_paragraph_break():
    # Core content set explicitly so the merged window matches the assertion —
    # the merge function preserves core data over row data when they collide.
    cores = [_core(2, content="Second chunk.")]
    fetched = [
        _row("doc-a-1", 1, content="First chunk."),
        _row("doc-a-2", 2, content="Second chunk."),
        _row("doc-a-3", 3, content="Third chunk."),
    ]
    [w] = _merge_to_windows(
        document_id="doc-a",
        filename="doc-a.pdf",
        cores_by_id={c.chunk_id: c for c in cores},
        fetched_rows=fetched,
    )
    assert w.text == "First chunk.\n\nSecond chunk.\n\nThird chunk."


def test_merge_pages_handles_missing_page():
    """Text files have no real page numbers — a None page should be dropped
    from the pages list, not crash."""
    cores = [_core(1, page=None)]  # core must also have page=None for this scenario
    fetched = [
        _row("doc-a-0", 0, page=None, content="a"),
        _row("doc-a-1", 1, page=None, content="b"),
    ]
    [w] = _merge_to_windows(
        document_id="doc-a",
        filename="notes.txt",
        cores_by_id={c.chunk_id: c for c in cores},
        fetched_rows=fetched,
    )
    assert w.pages == []


def test_merge_primary_chunk_picks_highest_scoring_core():
    """Window contains two cores with different RRF scores — primary_chunk_id
    must be the one with the higher score."""
    high = RetrievedChunk(
        chunk_id="high",
        document_id="doc-a",
        filename="doc-a.pdf",
        page=5,
        content="c",
        chunk_index=5,
        rrf_score=0.9,
        is_core=True,
    )
    low = RetrievedChunk(
        chunk_id="low",
        document_id="doc-a",
        filename="doc-a.pdf",
        page=6,
        content="d",
        chunk_index=6,
        rrf_score=0.1,
        is_core=True,
    )
    fetched = [
        _row("high", 5),
        _row("low", 6),
    ]
    [w] = _merge_to_windows(
        document_id="doc-a",
        filename="doc-a.pdf",
        cores_by_id={"high": high, "low": low},
        fetched_rows=fetched,
    )
    assert w.primary_chunk_id == "high"


def test_context_window_properties():
    """Smoke-test the dataclass properties so a regression in any of them
    fails loudly."""
    chunks = [
        RetrievedChunk(
            chunk_id=f"c{i}",
            document_id="d",
            filename="f.pdf",
            page=i,
            content=f"x{i}",
            chunk_index=i,
            is_core=(i == 1),
            rrf_score=0.5 if i == 1 else 0.0,
        )
        for i in (0, 1, 2)
    ]
    w = ContextWindow(document_id="d", filename="f.pdf", chunks=chunks)
    assert w.text == "x0\n\nx1\n\nx2"
    assert w.pages == [0, 1, 2]
    assert [c.chunk_id for c in w.core_chunks] == ["c1"]
    assert w.primary_chunk_id == "c1"
    assert w.core_rrf_score == 0.5
