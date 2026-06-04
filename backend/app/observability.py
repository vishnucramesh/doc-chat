"""Minimal structured logging.

Real observability (distributed tracing, metrics, an error tracker) belongs in
production; for this build we go as far as the three things below, and call
out what's deliberately missing so a reviewer doesn't have to infer.

What IS here:
  - **structlog configured for JSON output at startup** (`configure_logging`).
    All `log.info(...)` calls render as JSON to stdout — easy to ship to any
    aggregator (CloudWatch, Loki, Stackdriver) without code changes.
  - **A per-request id helper** (`new_request_id`) used by the chat endpoint
    to label each request, sent back to the client in the SSE `meta` event
    so a browser-side trace can be correlated with backend logs by id.
  - **Per-message latency persisted on `messages` rows** (`retrieval_ms`,
    `generation_ms`) — written by `routers/chat.py`. Queryable directly via
    SQL, which beats standing up a metrics store at this scale.

What's NOT here (and would be the next steps):
  - LLM token usage. The schema has `prompt_tokens` / `completion_tokens`
    columns reserved, but populating them requires
    `stream_options={"include_usage": True}` on the NIM stream and capturing
    the final usage chunk; not wired up.
  - Distributed tracing (OpenTelemetry).
  - Error tracking (Sentry, etc.).
  - Binding `request_id` into structlog's context vars so it shows up on
    every log line automatically. Currently it's generated and emitted to
    the client but not threaded into log calls.
"""

from __future__ import annotations

import logging
import sys
import uuid

import structlog

_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
    _configured = True


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]
