# CLAUDE.md

Project memory for Claude Code. Auto-loaded into every session in this repo.

Kept deliberately short — it competes with the user's prompt for context. If
a fact is visible in the codebase (file names, function signatures, what tests
exist), don't repeat it here. **Only invariants, things the assistant has
gotten wrong before, and project-specific conventions.**

If you find yourself wanting to add multi-paragraph explanations, put them in
`README.md` (long-form reasoning) or the file's own header comment (local
context). Link to them from here, don't inline them.

---

## What this is

doc-chat — a RAG app. PDFs in, cited answers out. See [`README.md`](./README.md)
for architecture and the reasoning behind every meaningful decision. Stack:
FastAPI · Supabase (Postgres+pgvector+Auth+Storage) · React/Vite/TS · NVIDIA
NIM (Nemotron + nv-embedqa).

## Always

- **Filter every DB query by JWT-derived `user.id` *explicitly*.** The
  service-role client we use bypasses RLS by design, so this filter is the
  ONLY thing keeping tenants apart. A query without it is a guaranteed
  cross-tenant leak. DB access lives in
  [`backend/app/repositories/`](backend/app/repositories/) (one module per
  table) — every method takes `user_id` and applies `.eq("user_id", …)`; keep
  it that way. See
  [`backend/app/services/supabase.py`](backend/app/services/supabase.py)
  for the full reasoning.
- **Use the admin client for backend DB ops.** There is intentionally no
  per-request user-scoped client.
- **Chunks must not cross page boundaries.** `chunk_pages()` enforces it.
  Crossing pages breaks citation page-numbers, which users notice and metrics
  don't.
- **Embed dim changes are three-way.** If you change the embedding model:
  `config.py:embed_dim`, the `vector(N)` column type, AND the `ivfflat`
  index must all agree. The schema lives in
  `backend/migrations/versions/*_init.py` (Alembic); change it by writing
  a NEW revision, not by editing the initial one. No automatic check
  exists; the failure mode is silent retrieval garbage.
- **Schema changes go through Alembic.** Never run SQL directly against
  the Supabase DB. `alembic revision -m "..."` → fill in upgrade/downgrade
  → `alembic upgrade head`. `backend/fly.toml` is set up so this would
  run automatically on each deploy (`release_command`), once the app is
  actually deployed.
- **Use `structlog` from [`observability.py`](backend/app/observability.py).**
  Never `print()`.
- **Reply with a verdict when the user asks "do you think it works?"** Don't
  re-ask — give a recommendation with one line of reasoning.

## Never

- **Don't pass unescaped model output to `rehype-raw`.** Rendering does use
  `rehype-raw`, but only because `prepareContent()` in
  [`frontend/src/lib/markdown.ts`](frontend/src/lib/markdown.ts) escapes raw
  `< > &` FIRST, then injects the `<cite>` citation sentinels — so the only
  HTML `rehype-raw` ever sees is ours. That ordering is the safety boundary
  (covered by `markdown.test.ts`). Don't reorder it, and don't feed raw model
  text to `rehype-raw` anywhere else.
- **Don't add LangChain / LlamaIndex / similar framework dependencies.**
  Staying framework-light is a deliberate, explained choice — see
  `docs/decisions.md`. If you think it's now warranted, write a
  one-paragraph case in the PR.
- **Don't add retry/backoff at more than one layer.** NIM calls already
  retry via `tenacity` in `embeddings.py`; don't double-wrap at callsites.
- **Don't write tests for trivial glue.** Test logic (chunker, prompts,
  retrieval merge), not framework wiring (FastAPI route registration,
  Pydantic field aliases).
- **Don't auto-summarize the PR or diff at the end of every response.** The
  user reads the diff. End with what changed and what's next, nothing more.
- **Don't commit `.env`, `.env.local`, or generated `dist/` / `.venv/`.**
  Already in `.gitignore`; just don't add exceptions.

## Common commands

```bash
# Migrations (run from backend/) — see backend/Makefile
make migration name="add foo"          # generate revision
make migrate                           # apply pending migrations
make migrate-status                    # current revision vs head

# Backend (run from backend/) — deps managed by uv against pyproject.toml + uv.lock
uv sync --extra dev                    # install / update deps
.venv/bin/pytest -q                    # tests
.venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m eval.run_eval --dataset eval/dataset.example.jsonl --user-id <uuid>

# Frontend (run from frontend/)
npm run dev
npm run typecheck
npm run build

# One-stop check pipeline:
/check          # custom command in .claude/commands/check.md

# Eval after retrieval/chunking/prompt changes:
/eval <user-uuid>
```

## Subagents

Each has a single, narrow scope; they explicitly defer to one another. Don't
ask one to do the other's job.

- **`rag-reviewer`** — proactively use after edits to `retrieval.py`,
  `chunking.py`, `system.py`, `embeddings.py`, the migration's
  `match_chunks` RPC, or the citation renderer (`lib/markdown.ts` +
  `MessageBubble.tsx`). Looks for citation correctness, embedding-dim
  coupling, chunking invariants, retrieval-without-eval.
- **`security-reviewer`** — proactively use after edits to auth (`deps.py`),
  any router taking user input, file upload, DB queries, CORS, or secret
  handling. Looks for IDOR / cross-tenant leaks, JWT verification
  regressions, upload safety, secret exposure, SQL injection, CORS
  misconfiguration, prompt-injection exfiltration vectors.

## Hooks (in `.claude/settings.json`)

- **`guard-env.sh`** (PreToolUse on `Bash`) blocks any command touching
  `.env*` files. The permission deny-list covers `Read`/`Edit`/`Write` on
  `.env` already; the Bash tool is the backdoor this closes.
- **`format-on-save.sh`** (PostToolUse on `Edit|Write|MultiEdit`) runs
  `ruff` on `.py` and `prettier` on `.ts`/`.tsx`/`.json`/`.css`/`.md`,
  IF those tools exist locally. Never blocks. Skip-if-absent is deliberate
  — it avoids breaking environments without the toolchain.

## Project shape (just enough to navigate)

```
backend/app/         FastAPI: routers (HTTP/SSE) → services (RAG logic)
                     → repositories (user_id-scoped DB) → supabase admin client
backend/migrations/  Alembic schema history (pgvector + RLS + match_chunks RPC)
frontend/src/        React/Vite: components (chat UI, SSE consumer)
                     + lib (api client, citation rendering)
backend/eval/        retrieval + answer-quality harness (recall@k, MRR)
```

## Pointers (read these before reinventing)

- `docs/decisions.md` — chunking, embedding, retrieval, LLM, guardrails
  reasoning. Most "should we do X?" questions are answered there.
- README "What's next" / "Possible improvements" — the backlog. Pull from
  these before inventing new work.
- `docs/architecture.md` — diagrams + request flows.
- `.claude/README.md` — what's in this AI-tooling directory and why.
