"""initial schema (pgvector, RLS, hybrid-search RPC, storage bucket)

Revision ID: 0001_init
Revises:
Create Date: 2026-06-03 22:00:00.000000

Why everything is `op.execute()` instead of `op.create_table()`:
the schema is heavy on Postgres-specific features that SQLAlchemy doesn't
have first-class support for — pgvector's `vector(N)`, a `tsvector` column
that is `generated always as ... stored`, an SQL function (`match_chunks`),
RLS policies, and a Supabase Storage bucket + policy. Mixing one or two
`op.create_table()` calls in among nine `op.execute()` blocks would obscure
the fact that this migration is fundamentally "apply these SQL statements
in order, and rely on Postgres to keep them transactional."

Assumes the database is a Supabase project (the `auth.users` and `storage.*`
schemas are pre-provisioned by Supabase). Running this against a plain
Postgres will fail at the auth.users foreign keys.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── extensions ────────────────────────────────────────────────────────
    op.execute("create extension if not exists pgcrypto")
    op.execute("create extension if not exists vector")

    # ─── documents ─────────────────────────────────────────────────────────
    op.execute(
        """
        create table public.documents (
          id            uuid primary key default gen_random_uuid(),
          user_id       uuid not null references auth.users(id) on delete cascade,
          filename      text not null,
          storage_path  text not null,
          content_type  text,
          size_bytes    bigint,
          page_count    integer,
          chunk_count   integer not null default 0,
          status        text not null default 'pending'
                        check (status in ('pending','processing','ready','failed')),
          error         text,
          created_at    timestamptz not null default now()
        )
        """
    )
    op.execute("create index documents_user_idx on public.documents (user_id, created_at desc)")

    # ─── chunks ────────────────────────────────────────────────────────────
    # vector(1024) matches nvidia/nv-embedqa-e5-v5. If you change embedding
    # model, update both this column dim AND the ivfflat index in a new
    # revision — see rag-reviewer agent's "embedding-dimension mismatch" check.
    op.execute(
        """
        create table public.chunks (
          id            uuid primary key default gen_random_uuid(),
          document_id   uuid not null references public.documents(id) on delete cascade,
          user_id       uuid not null references auth.users(id) on delete cascade,
          content       text not null,
          page          integer,
          chunk_index   integer not null,
          token_count   integer,
          embedding     vector(1024),
          tsv           tsvector generated always as (to_tsvector('english', content)) stored,
          created_at    timestamptz not null default now()
        )
        """
    )
    op.execute("create index chunks_doc_idx on public.chunks (document_id, chunk_index)")
    op.execute("create index chunks_tsv_idx on public.chunks using gin (tsv)")
    # ivfflat with lists=100 is fine up to ~100k chunks. Re-tune for prod scale
    # (rule of thumb: lists ≈ sqrt(rows)). For >1M rows, switch to HNSW.
    op.execute(
        """
        create index chunks_embedding_idx on public.chunks
          using ivfflat (embedding vector_cosine_ops) with (lists = 100)
        """
    )

    # ─── conversations + messages ──────────────────────────────────────────
    op.execute(
        """
        create table public.conversations (
          id          uuid primary key default gen_random_uuid(),
          user_id     uuid not null references auth.users(id) on delete cascade,
          title       text,
          created_at  timestamptz not null default now(),
          updated_at  timestamptz not null default now()
        )
        """
    )
    op.execute(
        "create index conversations_user_idx on public.conversations (user_id, updated_at desc)"
    )
    op.execute(
        """
        create table public.messages (
          id              uuid primary key default gen_random_uuid(),
          conversation_id uuid not null references public.conversations(id) on delete cascade,
          user_id         uuid not null references auth.users(id) on delete cascade,
          role            text not null check (role in ('user','assistant','system')),
          content         text not null,
          citations       jsonb,
          prompt_tokens   integer,
          completion_tokens integer,
          retrieval_ms    integer,
          generation_ms   integer,
          created_at      timestamptz not null default now()
        )
        """
    )
    op.execute("create index messages_conv_idx on public.messages (conversation_id, created_at)")

    # ─── hybrid retrieval RPC ──────────────────────────────────────────────
    # Reciprocal Rank Fusion of vector + lexical search, k=60 from Cormack et
    # al. (the value works well without tuning).
    op.execute(
        """
        create or replace function public.match_chunks(
          p_user_id    uuid,
          p_query_emb  vector(1024),
          p_query_text text,
          p_doc_ids    uuid[] default null,
          p_match_k    int    default 8,
          p_pool_k     int    default 40
        )
        returns table (
          chunk_id     uuid,
          document_id  uuid,
          filename     text,
          page         integer,
          content      text,
          vector_score float,
          lexical_score float,
          rrf_score    float
        )
        language sql stable as $$
          with vec as (
            select c.id, c.document_id, c.page, c.content,
                   1 - (c.embedding <=> p_query_emb) as score,
                   row_number() over (order by c.embedding <=> p_query_emb) as rank
            from public.chunks c
            where c.user_id = p_user_id
              and (p_doc_ids is null or c.document_id = any (p_doc_ids))
              and c.embedding is not null
            order by c.embedding <=> p_query_emb
            limit p_pool_k
          ),
          lex as (
            select c.id, c.document_id, c.page, c.content,
                   ts_rank(c.tsv, plainto_tsquery('english', p_query_text)) as score,
                   row_number() over (
                     order by ts_rank(c.tsv, plainto_tsquery('english', p_query_text)) desc
                   ) as rank
            from public.chunks c
            where c.user_id = p_user_id
              and (p_doc_ids is null or c.document_id = any (p_doc_ids))
              and c.tsv @@ plainto_tsquery('english', p_query_text)
            limit p_pool_k
          ),
          merged as (
            select coalesce(v.id, l.id) as id,
                   coalesce(v.document_id, l.document_id) as document_id,
                   coalesce(v.page, l.page) as page,
                   coalesce(v.content, l.content) as content,
                   coalesce(v.score, 0) as vector_score,
                   coalesce(l.score, 0) as lexical_score,
                   (case when v.rank is not null then 1.0 / (60 + v.rank) else 0 end)
                     + (case when l.rank is not null then 1.0 / (60 + l.rank) else 0 end) as rrf
            from vec v
            full outer join lex l on v.id = l.id
          )
          select m.id, m.document_id, d.filename, m.page, m.content,
                 m.vector_score, m.lexical_score, m.rrf
          from merged m
          join public.documents d on d.id = m.document_id
          order by m.rrf desc
          limit p_match_k;
        $$
        """
    )

    # ─── Row-Level Security ────────────────────────────────────────────────
    # Backend queries use the service-role key, which BYPASSES these policies
    # by design. The policies exist to protect the anon-key path (e.g. future
    # supabase-js queries from the browser) — for the backend's path, every
    # query must add an explicit user_id filter or it will leak across tenants.
    for tbl in ("documents", "chunks", "conversations", "messages"):
        op.execute(f"alter table public.{tbl} enable row level security")
        op.execute(
            f'create policy "own_{tbl}" on public.{tbl} '
            f"for all using (auth.uid() = user_id) "
            f"with check (auth.uid() = user_id)"
        )

    # ─── Storage bucket + RLS ──────────────────────────────────────────────
    # Private bucket; the backend uses the service role to read/write. The
    # RLS policy is here mostly to make `select` from the JS client safe if a
    # future feature lets users open the raw file directly.
    op.execute(
        """
        insert into storage.buckets (id, name, public)
        values ('documents', 'documents', false)
        on conflict (id) do nothing
        """
    )
    op.execute(
        """
        create policy "own_files_select" on storage.objects
          for select using (
            bucket_id = 'documents'
            and (auth.uid())::text = (storage.foldername(name))[1]
          )
        """
    )


def downgrade() -> None:
    # Reverse order. We leave the pgvector + pgcrypto extensions in place
    # because other projects in the same database might rely on them — let
    # an operator remove them by hand if truly desired.
    op.execute('drop policy if exists "own_files_select" on storage.objects')
    op.execute("delete from storage.buckets where id = 'documents'")

    for tbl in ("messages", "conversations", "chunks", "documents"):
        op.execute(f'drop policy if exists "own_{tbl}" on public.{tbl}')

    op.execute("drop function if exists public.match_chunks(uuid, vector, text, uuid[], int, int)")

    op.execute("drop table if exists public.messages")
    op.execute("drop table if exists public.conversations")
    op.execute("drop table if exists public.chunks")
    op.execute("drop table if exists public.documents")
