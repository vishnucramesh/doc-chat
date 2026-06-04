"""Streaming chat endpoint.

The wire format is Server-Sent Events. Each `data:` line is a JSON object with
a `type` field — `meta` (citations + conversation id, sent first), `token`
(streamed text chunk), `done` (final stats), or `error`. The frontend assembles
the full answer client-side from `token` events.

We persist the user message before streaming and the assistant message after
streaming completes — if the stream dies mid-flight, the user's question is
still saved so they can retry without losing it.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import AuthUser, require_user
from app.observability import new_request_id
from app.prompts.system import build_messages, render_context
from app.repositories import conversations, messages
from app.schemas import ChatRequest
from app.services.llm import stream_chat
from app.services.retrieval import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])

# Hard cap on conversation history we pass to the LLM. Older turns are dropped,
# not summarized — explicitly out of scope for this build.
MAX_HISTORY_TURNS = 8


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(req: ChatRequest, user: AuthUser = Depends(require_user)):
    # Resolve or create the conversation up-front so we can attach messages
    # before we stream anything.
    if req.conversation_id:
        if not await conversations.get_owned(req.conversation_id, user.id):
            raise HTTPException(404, "conversation not found")
        conv_id = req.conversation_id
    else:
        title = req.message.strip().splitlines()[0][:80]
        conv_id = (await conversations.create(user.id, title))["id"]

    # Save user message immediately.
    await messages.add_user_message(conv_id, user.id, req.message)

    request_id = new_request_id()

    async def event_stream() -> AsyncIterator[str]:
        try:
            t_retrieve = time.perf_counter()
            windows = await retrieve(
                user_id=user.id,
                query=req.message,
                document_ids=req.document_ids,
                top_k=req.top_k,
            )
            retrieval_ms = int((time.perf_counter() - t_retrieve) * 1000)
            rendered = render_context(windows)

            # Send meta first so the UI can render citation chips alongside the
            # streaming answer.
            yield _sse(
                {
                    "type": "meta",
                    "conversation_id": conv_id,
                    "request_id": request_id,
                    "citations": rendered.citations,
                    "retrieval_ms": retrieval_ms,
                    "retrieved_count": len(windows),
                }
            )

            # Pull the most recent N turns to maintain context across requests.
            # +1 row so we can drop the user message we just inserted (it's the
            # head when sorted newest-first) and still get MAX_HISTORY_TURNS*2.
            history_rows = await messages.recent_history(
                conv_id, user.id, limit=MAX_HISTORY_TURNS * 2 + 1
            )
            # Newest first → drop the just-inserted user message → reverse to
            # chronological order.
            history_rows = list(reversed(history_rows[1:]))
            history = [{"role": h["role"], "content": h["content"]} for h in history_rows]

            llm_messages = build_messages(
                question=req.message, rendered=rendered, history=history
            )

            t_gen = time.perf_counter()
            buf: list[str] = []
            async for token in stream_chat(llm_messages):
                buf.append(token)
                yield _sse({"type": "token", "text": token})
            generation_ms = int((time.perf_counter() - t_gen) * 1000)
            full_text = "".join(buf).strip() or (
                "I don't have enough information in the provided documents to answer that."
            )

            await messages.add_assistant_message(
                conv_id,
                user.id,
                content=full_text,
                citations=rendered.citations,
                retrieval_ms=retrieval_ms,
                generation_ms=generation_ms,
            )
            await conversations.touch(conv_id, user.id)

            yield _sse(
                {
                    "type": "done",
                    "retrieval_ms": retrieval_ms,
                    "generation_ms": generation_ms,
                }
            )
        except Exception as e:  # noqa: BLE001
            # The frontend renders an inline error bubble; we deliberately do
            # not leak stack traces to the client.
            yield _sse({"type": "error", "message": str(e)[:200]})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
