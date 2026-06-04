"""Run the eval set.

Reports retrieval metrics (recall@k, MRR) plus an end-to-end answer-correctness
probe. Deliberately tiny: prints a compact JSON blob to stdout and a one-line
summary to stderr. Both are easy to grep, diff between runs, and log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass

from app.config import get_settings
from app.prompts.system import build_messages, render_context
from app.services.llm import complete
from app.services.retrieval import retrieve


@dataclass
class Example:
    id: str
    question: str
    expected_substr: str
    expected_doc_filename: str | None = None


def load_dataset(path: str) -> list[Example]:
    out: list[Example] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            out.append(
                Example(
                    id=row["id"],
                    question=row["question"],
                    expected_substr=row["expected_substr"],
                    expected_doc_filename=row.get("expected_doc_filename"),
                )
            )
    return out


async def evaluate(dataset: list[Example], *, user_id: str, top_k: int) -> dict:
    settings = get_settings()
    per_example: list[dict] = []
    recall_hits = 0
    rr_sum = 0.0
    correct_answer = 0

    for ex in dataset:
        t0 = time.perf_counter()
        retrieved = await retrieve(user_id=user_id, query=ex.question, top_k=top_k)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        # Retrieval metrics — "expected doc was in top-k" + reciprocal rank.
        rank = None
        if ex.expected_doc_filename:
            for i, r in enumerate(retrieved, start=1):
                if r.filename == ex.expected_doc_filename:
                    rank = i
                    break
        hit = rank is not None
        recall_hits += 1 if hit else 0
        rr_sum += (1.0 / rank) if rank else 0.0

        # End-to-end probe.
        rendered = render_context(retrieved)
        msgs = build_messages(question=ex.question, rendered=rendered, history=[])
        answer = await complete(msgs)
        answer_ok = ex.expected_substr.lower() in answer.lower()
        if answer_ok:
            correct_answer += 1

        per_example.append(
            {
                "id": ex.id,
                "retrieval_ms": retrieval_ms,
                "retrieved": len(retrieved),
                "hit": hit,
                "rank": rank,
                "answer_ok": answer_ok,
                "answer": answer[:300],
            }
        )

    n = len(dataset)
    summary = {
        "n": n,
        "k": top_k,
        "recall@k": recall_hits / n if n else 0.0,
        "mrr": rr_sum / n if n else 0.0,
        "answer_acc": correct_answer / n if n else 0.0,
        "embed_model": settings.nvidia_embed_model,
        "chat_model": settings.nvidia_chat_model,
        "chunk_target_tokens": settings.chunk_target_tokens,
        "chunk_overlap_tokens": settings.chunk_overlap_tokens,
    }
    return {"summary": summary, "examples": per_example}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--k", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    k = args.k or settings.retrieval_top_k
    examples = load_dataset(args.dataset)
    if not examples:
        print("dataset is empty", file=sys.stderr)
        return 1

    result = asyncio.run(evaluate(examples, user_id=args.user_id, top_k=k))
    print(json.dumps(result, indent=2))

    s = result["summary"]
    print(
        f"n={s['n']} k={s['k']} recall@k={s['recall@k']:.2f} mrr={s['mrr']:.2f} "
        f"answer_acc={s['answer_acc']:.2f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
