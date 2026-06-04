---
description: Run the RAG eval harness against the example dataset. Pass the Supabase user UUID that owns the documents as the argument.
argument-hint: <supabase-user-uuid>
---

Run the eval harness for the supplied Supabase user UUID: `$ARGUMENTS`.

If `$ARGUMENTS` is empty, stop and ask the user for the UUID of the Supabase
account that owns the documents referenced by the example dataset. Do not
guess or use a placeholder.

Command:

```bash
cd backend && .venv/bin/python -m eval.run_eval \
    --dataset eval/dataset.example.jsonl \
    --user-id $ARGUMENTS
```

After it runs:

1. Show the summary line from stderr verbatim (the one starting with `n=`).
2. List any example where `hit=false` or `answer_ok=false`, with the
   question text and the first 120 chars of the returned answer.
3. If `recall@k < 0.8` or `answer_acc < 0.7`, treat the run as regressed
   and recommend specific next steps (re-check chunking, embedding model,
   prompt, top_k) without inventing new ones.

Do not invent a "good" baseline if there's nothing to compare against;
flag that the run is the new baseline.
