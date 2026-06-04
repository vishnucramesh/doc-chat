# Eval harness

A small, opinionated harness — emphasis on **small**. Three goals:

1. **Catch retrieval regressions** when chunking, embedding model, or RRF
   parameters change. Measured with `recall@k` and `mrr` over a hand-written
   golden set.
2. **Spot-check answer quality** on the same set with a single end-to-end
   correctness probe: does the assistant's answer contain the expected
   substring AND cite at least one of the expected sources?
3. **Stay runnable on a laptop in under a minute** so nobody skips it.

This is not a benchmark. Real evaluation in production needs:

- A larger, distribution-matched dataset (think hundreds of questions, ideally
  drawn from real user logs and re-labeled periodically).
- An LLM-judge for answer faithfulness, not just substring match.
- Per-feature slicing (single-doc vs multi-doc, short vs long, etc.).
- CI gates that fail PRs when metrics regress past a threshold.

See `dataset.example.jsonl` for the format. Replace it with questions about
your own documents before running.

## Run

```bash
# from repo root
cd backend
.venv/bin/python -m eval.run_eval --dataset eval/dataset.example.jsonl --user-id <uuid>
```

The `--user-id` must own the documents referenced in the dataset — the harness
uses the production retrieval path, scoped by user as in the real app.

## Output

JSON written to stdout plus a one-line summary on stderr. The summary is
what you should plot over time.
