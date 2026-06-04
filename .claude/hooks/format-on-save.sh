#!/usr/bin/env bash
# PostToolUse hook for Edit / Write / MultiEdit.
#
# Best-effort format-on-save:
#   - Python files: ruff check --fix + ruff format, IF a project venv has ruff
#   - TS / TSX / JS / JSON / CSS / MD: prettier, IF the frontend has it installed
#
# Design rules for this hook:
#   1. NEVER block (exit 0 always — formatter failures must not break a
#      productive edit loop).
#   2. NEVER install anything (silently skip if tools aren't on disk).
#   3. NEVER touch files outside the project root.
#   4. Stay quiet on stdout/stderr unless something the user should see
#      happened (a real formatter error). Claude pipes hook stderr into its
#      next turn, and noisy hooks turn into context-window pollution.
#
# If you don't want auto-formatting at all, comment out the PostToolUse
# block in .claude/settings.json — this script is opt-in by hook config,
# not by code presence.

set +e   # we want to keep going past errors and always exit 0
payload="$(cat)"

file="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("file_path", ""), end="")
except Exception:
    print("", end="")
')"

# Nothing to format. (Notebook edits, MultiEdit summaries with no path, etc.)
[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

# Resolve repo root via git, fall back to CWD. Refuse to format files
# outside the repo — defense against a hook running on something unexpected.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
case "$file" in
    "$repo_root"/*) ;;  # ok
    /*) exit 0 ;;       # absolute path outside repo — skip
esac

case "$file" in
    *.py)
        ruff_bin="$repo_root/backend/.venv/bin/ruff"
        if [ -x "$ruff_bin" ]; then
            "$ruff_bin" check --fix --quiet "$file" 2>/dev/null
            "$ruff_bin" format --quiet "$file" 2>/dev/null
        fi
        ;;
    *.ts|*.tsx|*.js|*.jsx|*.json|*.css|*.md)
        prettier_bin="$repo_root/frontend/node_modules/.bin/prettier"
        if [ -x "$prettier_bin" ]; then
            (cd "$repo_root/frontend" && "$prettier_bin" --write --log-level=warn "$file") 2>/dev/null
        fi
        ;;
esac

exit 0
