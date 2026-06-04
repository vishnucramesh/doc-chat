"""Supabase client factory.

The backend uses ONE process-wide client created with the service-role key
(see `admin_client()`). Service-role queries **bypass Row-Level Security by
design** — so RLS is NOT what keeps tenants apart for queries from this
backend. The explicit `.eq("user_id", user.id)` filter we add to every query
(with `user.id` taken from the verified JWT in `app/deps.py`) is the actual
tenant boundary. A query that forgets that filter is a cross-tenant leak,
full stop; RLS will not save it.

RLS policies are still defined on every user-owned table, but for a different
reason: to protect the *anon-key* path (a future feature where the browser
queries Supabase directly via supabase-js, say). We don't expose that path
today — the frontend talks to FastAPI, which talks to Postgres — but the
policies stay so the data is safe by default if we ever do.

──────────────────────────────────────────────────────────────────────────
About `_exec`
──────────────────────────────────────────────────────────────────────────
supabase-py's `Client.execute()` is a SYNCHRONOUS HTTP call — it blocks the
thread for ~50-300ms per round-trip. Calling it directly inside an `async
def` handler freezes the FastAPI event loop and stalls every other in-flight
request until it returns. `_exec` runs the call on the default worker
thread pool via `asyncio.to_thread` so the event loop stays responsive.

Usage:
    rows = (await _exec(sb.table("documents").select("*").eq(...))).data

We could have switched to `supabase.AsyncClient` instead, but that's a wider
refactor (every `.execute()` call site changes shape) for the same outcome.
The wrapper keeps the disruption contained to this one helper.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def admin_client() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


async def _exec(builder: Any) -> Any:
    """Run a Supabase query builder's `.execute()` on a worker thread.

    `builder` is whatever `sb.table(...).select(...).eq(...)` returns — i.e.
    the chain just before `.execute()`. We call `.execute()` ourselves inside
    the thread so the HTTP request happens off the event loop.
    """
    return await asyncio.to_thread(builder.execute)
