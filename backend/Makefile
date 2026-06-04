# doc-chat backend — task runner.
#
# Lives in backend/ so every target runs in the directory that owns
# pyproject.toml, the venv, and the migrations. Run as `make <target>` from
# this folder, or `make -C backend <target>` from the repo root.
#
# Convention (Django / Rails / Phoenix): `migrate` (verb) APPLIES; `migration`
# (noun) CREATES one. `migrations` is a plural alias because that's how
# people commonly type it.
#
# All Alembic targets use the project venv created by `uv sync --extra dev`
# — run that once before invoking these.

SHELL       := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

ALEMBIC := .venv/bin/alembic

.DEFAULT_GOAL := help

.PHONY: help migrate migration migrations migrate-status migrate-down migrate-sql

help: ## Show available targets.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m [name=\"…\"]\n\nTargets:\n"} \
	      /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─── migrations ──────────────────────────────────────────────────────────────
# `_require-venv` is a tiny precondition so a fresh checkout fails with a
# pointer to `uv sync` rather than a cryptic "alembic: not found".
_require-venv:
	@test -x $(ALEMBIC) || { \
		echo "error: $(ALEMBIC) not found — run 'uv sync --extra dev' first"; \
		exit 1; \
	}

migrate: _require-venv ## Apply all pending migrations (alembic upgrade head).
	$(ALEMBIC) upgrade head

# Singular `migration` is canonical (one revision per invocation). `migrations`
# is an alias because that's how people commonly type it.
migration: _require-venv ## Generate a new revision. Usage: make migration name="add foo to bar"
	@if [ -z "$(name)" ]; then \
		echo "error: missing 'name'. Usage:"; \
		echo "  make migration name=\"add foo to bar\""; \
		exit 1; \
	fi
	$(ALEMBIC) revision -m "$(name)"

migrations: migration ## Alias for `migration`.

migrate-status: _require-venv ## Print the current DB revision and registered head.
	@$(ALEMBIC) current && $(ALEMBIC) heads

migrate-down: _require-venv ## Roll back one migration (alembic downgrade -1).
	$(ALEMBIC) downgrade -1

migrate-sql: _require-venv ## Render upgrade SQL to stdout WITHOUT applying it (review before deploy).
	@$(ALEMBIC) upgrade head --sql
