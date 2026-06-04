# `.claude/` — committed AI tooling

This directory is the *team-shared* configuration for Claude Code (the CLI
coding assistant). Everything here is checked in deliberately so that anyone
working on the repo gets the same guardrails, the same shortcuts, and the same
mental model of how the project is set up — without having to read every file
to figure it out.

If you've never seen this directory before: it's the equivalent of a
`.editorconfig` or a `Makefile` for AI-assisted development.

## What's in here

| File | Purpose |
|---|---|
| `../CLAUDE.md` | Loaded into every session. Invariants, "always / never", commands. |
| `settings.json` | Team-wide permissions + hooks. Committed. |
| `settings.local.json` | Per-developer overrides. **Gitignored** — don't commit. |
| `commands/check.md` | `/check` — runs the full test + typecheck + build pipeline. |
| `commands/eval.md` | `/eval <user-uuid>` — runs the RAG eval harness. |
| `agents/rag-reviewer.md` | Focused subagent: RAG-specific review (citations, embedding dims, chunking, eval). |
| `agents/security-reviewer.md` | Focused subagent: web-app security review (IDOR, JWT, upload safety, secrets, CORS). |
| `hooks/guard-env.sh` | PreToolUse: blocks any Bash command touching `.env*` files. |
| `hooks/format-on-save.sh` | PostToolUse: best-effort `ruff` / `prettier` after edits. Never blocks. |

## Design philosophy

A few rules I follow when configuring an AI coding assistant on a real project:

1. **Encode invariants once, in `CLAUDE.md`** — not in every prompt. The whole
   point of project memory is that the assistant doesn't have to relearn
   things like "always filter by user_id" every conversation.
2. **Keep `CLAUDE.md` short.** It competes with the user's prompt for context.
   Long memory files train the assistant to skim them; short focused ones get
   followed.
3. **Settings are allow-lists, not deny-lists.** It's easier to add a safe
   command than to enumerate every dangerous one. The default in Claude Code
   is "ask first"; we only pre-approve commands that are clearly safe.
4. **Hooks are minimal and defensive by default.** Two are wired in:
   - **`guard-env.sh` (PreToolUse on Bash)** closes a real gap. The
     permission deny-list covers `Read` / `Edit` / `Write` on `.env`,
     but the Bash tool is a backdoor: `cat .env` and `grep KEY .env` would
     otherwise sail through. This hook inspects the actual command string
     and blocks `.env*` references with `exit 2`, which Claude Code treats
     as a hard block and feeds the message back to the model.
   - **`format-on-save.sh` (PostToolUse on Edit/Write/MultiEdit)** is
     best-effort and never blocks. If `backend/.venv/bin/ruff` exists, it
     formats Python; if `frontend/node_modules/.bin/prettier` exists, it
     formats TS/JSON/MD/CSS. If neither is installed, it's a no-op. The
     trade-off vs. "no formatter hook" is that with the graceful-fallback
     pattern, the formatter only runs when the developer's environment is
     actually set up to support it — which is what you want.
5. **No `Stop` or `Notification` hooks.** Considered them. `Stop` running
   `/check` automatically sounds nice but creates a noisy feedback loop;
   it's better to let the developer trigger it. `Notification` is a
   personal-preference thing, not a project concern.
6. **Custom slash commands replace bash aliases.** Where a team has a workflow
   they run often (here: "run all the checks" and "run the RAG eval"), make
   it a single command, not a 4-step bash incantation in the README.
7. **Subagents are for *focused* review, not general help.** `rag-reviewer`
   and `security-reviewer` each have a single, narrow scope and explicitly
   defer to each other. Single-purpose agents stay useful as the codebase
   grows; "do everything" agents drift into uselessness. Adding a third
   should require a clearly distinct scope — don't bloat for completeness.

## Do's and don'ts working with the assistant on this repo

(See README §"How I used AI tools" for the longer version. This is the
operational checklist.)

**Do:**
- Decide architecture yourself; ask the assistant to flesh out individual
  files.
- Run `/check` before declaring anything done.
- Run `/eval <uuid>` after touching retrieval, chunking, prompts, or
  embedding models.
- Use the `rag-reviewer` subagent before merging changes to retrieval,
  chunking, prompts, or embeddings.
- Use the `security-reviewer` subagent before merging changes to auth,
  file upload, DB queries, CORS, or any endpoint that takes user input.
- Read every line before you commit it. The assistant is a typing aid, not
  an authority.

**Don't:**
- Let the assistant write the README's reasoning sections for you. The
  recruiting brief asks specifically for *your* voice.
- Accept "looks plausible" code in auth, SQL filters, or storage paths.
  Re-derive these.
- Auto-allow destructive operations (`rm -rf`, `git push --force`,
  `git reset --hard`) in `settings.json`. They're not there for a reason.
- Skip the eval after a retrieval change just because the unit tests pass.
  Unit tests prove the code runs; the eval is the only signal for whether
  retrieval got *worse*.
