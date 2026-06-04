# Decisions & trade-offs

The choices that matter, in short. The [README](../README.md) has the overview.

- **Models are free-tier picks, not commitments.** Everything goes through the
  OpenAI-compatible API, so any frontline model (OpenAI, Claude, Gemini, …)
  swaps in with a config + key change, no code change.
- **Chunks never cross page boundaries** — keeps citation page numbers honest.
  Chunking is hand-rolled (token-aware, recursive) because it's the biggest
  lever on retrieval.
- **Hybrid retrieval in one Postgres round-trip** — dense + lexical fused with
  RRF in the `match_chunks` RPC, so the indexes do the work, not Python. Dense
  alone misses exact strings; lexical alone misses paraphrase.
- **Citations can't be faked** — the model cites `[n]`, and the frontend drops
  any marker not in the returned source set.
- **Tenant isolation is an explicit `user_id` filter** from the verified JWT —
  the service-role client bypasses RLS, so that filter is the boundary.
- **Framework-light on purpose** — direct `openai` SDK + Postgres. LangChain /
  LlamaIndex earn their keep only once the pipeline goes agentic or multi-tool.
- **Ingestion is in-process + UI polling for now** — both are intentional
  simplifications. At scale, move ingestion onto a queue + dedicated worker
  (the fn already takes `document_id` + `user_id`, so only dispatch changes)
  and replace status polling with push (SSE / WebSocket / Supabase Realtime).
- **Migrations run manually for now** (`make migrate`). `fly.toml` already
  models a `release_command`; the better setup is a dedicated migration job in
  the deploy pipeline so schema changes apply automatically and never race the
  app rollout.
- **Other things to change at scale:** `ivfflat` → `HNSW` past ~10M chunks and
  a cross-encoder reranker.
