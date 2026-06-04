from __future__ import annotations

from app.prompts.system import SYSTEM_PROMPT, build_messages, render_context
from app.services.retrieval import ContextWindow, RetrievedChunk


def _window(n: int, *, doc_id: str = "doc-{i}", filename: str = "file-{i}.pdf") -> ContextWindow:
    """One-chunk window with deterministic content/pages — exercising the
    single-chunk degenerate case of the windowing pipeline."""
    c = RetrievedChunk(
        chunk_id=f"chunk-{n}",
        document_id=doc_id.format(i=n),
        filename=filename.format(i=n),
        page=n + 1,
        content=f"This is the content of chunk {n}.",
        chunk_index=n,
        rrf_score=0.8,
        is_core=True,
    )
    return ContextWindow(document_id=c.document_id, filename=c.filename, chunks=[c])


def _windows(n: int) -> list[ContextWindow]:
    return [_window(i) for i in range(n)]


def test_render_context_numbers_blocks_from_one():
    rendered = render_context(_windows(3))
    assert rendered.text.startswith("[1]")
    assert "[3]" in rendered.text
    assert len(rendered.citations) == 3
    assert rendered.citations[0]["n"] == 1
    assert rendered.citations[0]["chunk_id"] == "chunk-0"
    # Citation shape changed: page → pages array.
    assert rendered.citations[0]["pages"] == [1]


def test_build_messages_includes_system_and_question():
    rendered = render_context(_windows(2))
    msgs = build_messages(question="what is X?", rendered=rendered, history=[])
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[-1]["role"] == "user"
    assert "what is X?" in msgs[-1]["content"]
    assert "[1]" in msgs[-1]["content"]


def test_no_context_emits_explicit_no_match_instruction():
    rendered = render_context([])
    msgs = build_messages(question="anything", rendered=rendered, history=[])
    user_content = msgs[-1]["content"]
    assert "No documents matched" in user_content
    assert "enough information" in user_content.lower()


def test_history_is_inserted_between_system_and_final_user():
    rendered = render_context(_windows(1))
    history = [
        {"role": "user", "content": "prev question"},
        {"role": "assistant", "content": "prev answer"},
    ]
    msgs = build_messages(question="follow-up", rendered=rendered, history=history)
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]


def test_multi_page_window_renders_page_range():
    """A window spanning multiple pages must render 'pages N–M', not 'page N'.
    This is the user-visible payoff of windowing — citations now accurately
    reflect the span of source material the LLM saw."""
    chunks = [
        RetrievedChunk(
            chunk_id=f"c{i}",
            document_id="d",
            filename="report.pdf",
            page=i,
            content=f"text{i}",
            chunk_index=i,
            is_core=(i == 4),
            rrf_score=0.5 if i == 4 else 0.0,
        )
        for i in (3, 4, 5)
    ]
    w = ContextWindow(document_id="d", filename="report.pdf", chunks=chunks)
    rendered = render_context([w])
    assert "report.pdf, pages 3–5" in rendered.text
    assert rendered.citations[0]["pages"] == [3, 4, 5]
    assert rendered.citations[0]["chunk_id"] == "c4"  # the core, not c3 or c5


def test_single_page_window_renders_single_page():
    """Defensive — make sure we didn't regress the common single-page case."""
    w = _window(2)
    rendered = render_context([w])
    assert "file-2.pdf, page 3" in rendered.text


def test_textfile_window_with_no_pages_renders_filename_only():
    """A .txt file has all chunks at page=None — header should just be the
    filename, no trailing page label."""
    chunks = [
        RetrievedChunk(
            chunk_id="c",
            document_id="d",
            filename="notes.txt",
            page=None,
            content="hello",
            chunk_index=0,
            is_core=True,
        )
    ]
    w = ContextWindow(document_id="d", filename="notes.txt", chunks=chunks)
    rendered = render_context([w])
    assert "[1] notes.txt\nhello" in rendered.text
    assert rendered.citations[0]["pages"] == []
