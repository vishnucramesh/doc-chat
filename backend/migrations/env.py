"""Alembic environment.

Design notes:

1. **One source of truth for the DB URL.** We read it from the same pydantic
   `Settings` class the runtime app uses, rather than from `alembic.ini`.
   That removes a whole class of "the migrations are pointed at the wrong
   database" mistakes — if the app starts, Alembic has the right URL.

2. **No `target_metadata`** (so no autogenerate). The schema contains a
   pgvector column, a generated `tsvector` column, an RPC function, RLS
   policies, and a Supabase storage bucket — none of which round-trip
   through SQLAlchemy reflection cleanly. Hand-written migrations are the
   honest model here; autogenerate would produce convincing-looking SQL
   that silently omits half the schema. If we ever add domain tables that
   ARE pure-SQLAlchemy, we can flip this to a partial-metadata approach.

3. **Sync driver on purpose.** psycopg2 keeps env.py readable and avoids
   pulling asyncpg + an event loop just to apply migrations once per deploy.
   The runtime app stays async and talks to Postgres over PostgREST anyway.

Revision-ID length: the default `alembic_version.version_num` column is
`VARCHAR(32)`. Keep revision IDs short — e.g. `0002_chunk_idx_rpc`, not
`0002_match_chunks_returns_chunk_index` (the latter overflows and the
migration fails on the version-bump UPDATE, not on the DDL itself).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app.*` importable when running `alembic ...` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402

config = context.config

# Set the DB URL from Settings — overrides whatever (blank) value is in
# alembic.ini. Settings reads from backend/.env via pydantic-settings.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Generate SQL without a DB connection. Used by `alembic upgrade head --sql`."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # we open exactly one connection — no pooling needed
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
