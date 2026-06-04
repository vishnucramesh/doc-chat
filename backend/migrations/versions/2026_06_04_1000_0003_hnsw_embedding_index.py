"""Swap the chunk embedding index from ivfflat to HNSW

Revision ID: 0003_hnsw_embedding_index
Revises: 0002_match_chunks_chunk_idx
Create Date: 2026-06-04 10:00:00.000000

Why: ivfflat is an APPROXIMATE index that partitions vectors into `lists`
clusters and, at query time, only scans `probes` of them (default 1). With a
small corpus the clusters are mostly empty, so a query whose nearest cluster
happens to hold none of the relevant chunks gets ZERO vector hits — which makes
`match_chunks` return nothing and the chat wrongly answer "I don't have enough
information…". We hit this for real: with ~5 chunks, lists=100/probes=1
returned 0 rows for some perfectly answerable questions (probes=100 returned
all 5, confirming it was index recall, not the data).

HNSW (pgvector ≥0.5; we run 0.8) gives near-perfect recall out of the box with
no lists/probes tuning, and scales to large corpora — so it's the right index
for both the demo-sized and production cases. This was already the planned
upgrade (README "What's next", docs/decisions.md).

m=16, ef_construction=64 are pgvector's defaults — good general-purpose values.
Query-time recall is governed by `hnsw.ef_search` (default 40), which needs no
change here.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_hnsw_embedding_index"
down_revision: str | None = "0002_match_chunks_chunk_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("drop index if exists chunks_embedding_idx")
    op.execute(
        """
        create index chunks_embedding_idx on public.chunks
          using hnsw (embedding vector_cosine_ops) with (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("drop index if exists chunks_embedding_idx")
    op.execute(
        """
        create index chunks_embedding_idx on public.chunks
          using ivfflat (embedding vector_cosine_ops) with (lists = 100)
        """
    )
