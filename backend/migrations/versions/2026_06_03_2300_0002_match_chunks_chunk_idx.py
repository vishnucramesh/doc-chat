"""match_chunks RPC returns chunk_index

Revision ID: 0002_match_chunks_chunk_idx
Revises: 0001_init
Create Date: 2026-06-03 23:00:00.000000

The retrieval layer now expands each top-K hit into a "context window" — the
hit plus its ±N neighboring chunks from the same document — so the LLM sees
narrative continuity around the passage that scored highest. To compute the
neighbor set, retrieval.py needs each hit's `chunk_index`. The RPC didn't
return it before; this revision adds it.

Why a new revision instead of editing 0001: applied migrations are forward-
only. CLAUDE.md spells this out. Even for an un-deployed app, holding the
discipline now means we don't accidentally normalize "just edit the initial
revision" later.

Postgres requires DROP FUNCTION before re-CREATE when the return-table shape
changes — CREATE OR REPLACE alone can't change the column list.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_match_chunks_chunk_idx"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_BODY = """
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
  chunk_index  integer,
  filename     text,
  page         integer,
  content      text,
  vector_score float,
  lexical_score float,
  rrf_score    float
)
language sql stable as $$
  with vec as (
    select c.id, c.document_id, c.chunk_index, c.page, c.content,
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
    select c.id, c.document_id, c.chunk_index, c.page, c.content,
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
           coalesce(v.chunk_index, l.chunk_index) as chunk_index,
           coalesce(v.page, l.page) as page,
           coalesce(v.content, l.content) as content,
           coalesce(v.score, 0) as vector_score,
           coalesce(l.score, 0) as lexical_score,
           (case when v.rank is not null then 1.0 / (60 + v.rank) else 0 end)
             + (case when l.rank is not null then 1.0 / (60 + l.rank) else 0 end) as rrf
    from vec v
    full outer join lex l on v.id = l.id
  )
  select m.id, m.document_id, m.chunk_index, d.filename, m.page, m.content,
         m.vector_score, m.lexical_score, m.rrf
  from merged m
  join public.documents d on d.id = m.document_id
  order by m.rrf desc
  limit p_match_k;
$$
"""

_OLD_BODY = """
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


def upgrade() -> None:
    op.execute("drop function if exists public.match_chunks(uuid, vector, text, uuid[], int, int)")
    op.execute(_NEW_BODY)


def downgrade() -> None:
    op.execute("drop function if exists public.match_chunks(uuid, vector, text, uuid[], int, int)")
    op.execute(_OLD_BODY)
