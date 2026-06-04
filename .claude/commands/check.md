---
description: Run the full test, typecheck, and production build pipeline. Reports pass/fail without trying to fix anything.
---

Run every gate this repo has and report a compact summary at the end.

Steps (run in parallel where possible):

1. **Backend tests** — from `backend/`:
   ```bash
   .venv/bin/pytest -q
   ```
2. **Frontend typecheck** — from `frontend/`:
   ```bash
   npm run typecheck
   ```
3. **Frontend production build** — from `frontend/`:
   ```bash
   npm run build
   ```

Do not attempt to fix failures. Surface each failure with the offending
file:line where possible, then stop. A passing run should end with one line:
`✅ tests/typecheck/build all green`.

If `backend/.venv` doesn't exist, tell the user to set it up first — don't
silently fall back to system Python.
