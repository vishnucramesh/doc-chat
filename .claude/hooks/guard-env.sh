#!/usr/bin/env bash
# PreToolUse hook for the Bash tool.
#
# Why this exists: the Read / Edit / Write permission deny-list in
# settings.json keeps Claude away from .env files via the dedicated file
# tools, but the Bash tool is a backdoor — `cat .env`, `grep KEY .env`,
# `echo "$X" >> .env` would all bypass those denies. This hook closes the
# gap by inspecting the bash command string itself.
#
# Claude Code hook protocol:
#   - stdin is a JSON object with tool_name + tool_input
#   - exit 0 => allow; exit 2 => block, stderr is fed back to the assistant
#   - any other non-zero exit is a soft error and does NOT block
#
# Keep this script dependency-free: bash + python3 only. Both are present
# on every dev machine we care about.

set -euo pipefail

payload="$(cat)"

# Pull the bash command. Default to empty string on any parse failure so a
# malformed payload doesn't crash the hook and silently disable the guard.
cmd="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get("tool_input", {}).get("command", ""), end="")
except Exception:
    print("", end="")
')"

# Look for a .env reference as a path component: whitespace / quote / redirect
# / pipe boundary, then `.env`, then end-of-token or a dot (.env.local, etc.).
# This intentionally won't match an inline literal like the string "ENVIRONMENT"
# inside a heredoc — we accept that small gap to keep the regex tight.
if printf '%s' "$cmd" | grep -qE '(^|[[:space:]"'\''/<>;|&(\`])\.env(\.[a-z]+)?([[:space:]"'\''<>;|&)\`]|$)'; then
    cat >&2 <<EOF
blocked: this Bash command appears to touch a .env file.

  command: $cmd

If you genuinely need to inspect or modify env files, do it yourself
outside of Claude — secrets should never round-trip through the
assistant's context.
EOF
    exit 2
fi

exit 0
