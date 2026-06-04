"""Chunker tests — the algorithm has enough branches (paragraph / sentence /
word fallback, overlap, multi-page) that without tests, ingest regressions are
silent and only show up as worse retrieval. These are the cases I tripped over
while writing it.
"""

from __future__ import annotations

from app.services.chunking import chunk_pages, chunk_text, count_tokens


def test_short_text_fits_in_one_chunk():
    chunks = chunk_text("Hello world. This is short.", target=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].token_count == count_tokens(chunks[0].text)


def test_long_text_splits_and_overlaps():
    # ~3000 tokens of repeated paragraphs, each paragraph ~80 tokens.
    para = ("This is a paragraph that exists solely to test the chunker. " * 8).strip()
    text = "\n\n".join([para] * 30)
    chunks = chunk_text(text, target=400, overlap=60)

    assert len(chunks) > 1, "expected multiple chunks"
    # No chunk should massively exceed the target (allow some slack from overlap seeding).
    for c in chunks:
        assert c.token_count <= 600, f"chunk over budget: {c.token_count}"
    # Each adjacent pair should share at least one overlapping word — proves the
    # tail-overlap seeding actually fires.
    for a, b in zip(chunks, chunks[1:], strict=False):
        a_tail = set(a.text.split()[-15:])
        b_head = set(b.text.split()[:15])
        assert a_tail & b_head, "expected overlap between adjacent chunks"


def test_oversize_single_sentence_falls_back_to_word_split():
    # One giant "sentence" with no punctuation — should still chunk, not crash.
    text = " ".join(["banana"] * 2000)
    chunks = chunk_text(text, target=300, overlap=30)
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 400


def test_chunks_do_not_cross_pages():
    pages = [
        (1, "Page one talks about apples. " * 30),
        (2, "Page two talks about bananas. " * 30),
    ]
    chunks = chunk_pages(pages, target=200, overlap=20)
    p1 = [c for c in chunks if c.page == 1]
    p2 = [c for c in chunks if c.page == 2]
    assert p1 and p2
    # Sanity: a chunk tagged page 1 must not contain page-2 vocabulary.
    for c in p1:
        assert "bananas" not in c.text.lower()
    for c in p2:
        assert "apples" not in c.text.lower()


def test_empty_pages_are_dropped():
    chunks = chunk_pages([(1, ""), (2, "real content here"), (3, "   ")], target=100, overlap=10)
    assert all(c.page == 2 for c in chunks)
