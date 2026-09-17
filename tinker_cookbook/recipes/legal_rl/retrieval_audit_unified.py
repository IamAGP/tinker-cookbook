"""Retrieval audit for the UNIFIED index (the gap A1 didn't cover).

A1 audited the old single-source index. This audits the unified index
(12,430 chunks, 3 sources) used by Exp 5+. Maps each question's ground-truth
passage into the unified id space and measures recall@k with the literal
question as the query (isolating the retriever, not the agent's query).

Gold-id mapping per source (must match build_unified_index / legal_data ids):
  - legal-rag-qa:   relevant_passages -> "rqa:<id>"
  - legal-rag-bench: relevant_passage_id -> "rb:<id>"
  - open-australian: gold = its own source.text -> "oa:<row-index>" (with the
    SAME dedup as iter_passages, so dup texts map to their first occurrence).

Reports recall@k overall AND per source.

Run:
    python -m tinker_cookbook.recipes.legal_rl.retrieval_audit_unified per_source=60

Required env: AWS_*.
"""

import asyncio
import logging

import chromadb
import chz
from datasets import load_dataset

from tinker_cookbook.recipes.legal_rl.build_unified_index import CHROMA_PATH, COLLECTION_NAME
from tinker_cookbook.recipes.legal_rl.embedding import get_bedrock_client, get_bedrock_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@chz.chz
class CLIConfig:
    per_source: int = 60  # questions sampled per source (balanced estimate)
    ks: tuple[int, ...] = (1, 3, 5, 10)
    max_query_chars: int = 40_000
    seed: int = 11


def _build_qa_with_gold(per_source: int, seed: int) -> list[dict]:
    """Return [{question, gold_ids:set[str], source}] across the 3 sources."""
    import random

    rng = random.Random(seed)
    items: list[dict] = []

    # legal-rag-qa
    ds = load_dataset("isaacus/legal-rag-qa", "qa", split="test")
    rows = list(ds)
    rng.shuffle(rows)
    for r in rows[:per_source]:
        gold = {f"rqa:{p}" for p in r["relevant_passages"]}
        items.append({"question": r["question"], "gold_ids": gold, "source": "legal-rag-qa"})

    # legal-rag-bench
    ds = load_dataset("isaacus/legal-rag-bench", "qa", split="test")
    rows = list(ds)
    rng.shuffle(rows)
    for r in rows[:per_source]:
        items.append(
            {
                "question": r["question"],
                "gold_ids": {f"rb:{r['relevant_passage_id']}"},
                "source": "legal-rag-bench",
            }
        )

    # open-australian — build text->uid with the SAME dedup as iter_passages
    oa = load_dataset("isaacus/open-australian-legal-qa", "default", split="train")
    text_to_uid: dict[str, str] = {}
    seen: set[str] = set()
    for i, r in enumerate(oa):
        t = (r["source"]["text"] or "").strip()
        if t and t not in seen:
            seen.add(t)
            text_to_uid[t] = f"oa:{i}"
    oa_rows = list(enumerate(oa))
    rng.shuffle(oa_rows)
    for _, r in oa_rows[:per_source]:
        t = (r["source"]["text"] or "").strip()
        uid = text_to_uid.get(t)
        if uid:
            items.append(
                {"question": r["question"], "gold_ids": {uid}, "source": "open-australian-legal-qa"}
            )
    return items


async def cli_main(config: CLIConfig) -> None:
    qa = _build_qa_with_gold(config.per_source, config.seed)
    logger.info(f"Auditing {len(qa)} questions across 3 sources on unified index")

    collection = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION_NAME)
    logger.info(f"Unified collection '{COLLECTION_NAME}': {collection.count()} chunks")
    bedrock = get_bedrock_client()
    max_k = max(config.ks)

    # hits[source][k] and overall
    from collections import defaultdict

    hits = defaultdict(lambda: {k: 0 for k in config.ks})
    totals = defaultdict(int)

    for i, item in enumerate(qa):
        emb = await get_bedrock_embedding(bedrock, [item["question"][: config.max_query_chars]])
        res = collection.query(query_embeddings=emb, n_results=max_k, include=["metadatas"])
        retrieved = [str(m.get("id", "")) for m in (res["metadatas"][0] or [])]
        first_hit = next(
            (r for r, pid in enumerate(retrieved, 1) if pid in item["gold_ids"]), -1
        )
        src = item["source"]
        totals[src] += 1
        totals["ALL"] += 1
        for k in config.ks:
            if first_hit != -1 and first_hit <= k:
                hits[src][k] += 1
                hits["ALL"][k] += 1
        if (i + 1) % 50 == 0:
            logger.info(f"  {i + 1}/{len(qa)}")

    print("\n" + "=" * 80)
    print("UNIFIED INDEX RETRIEVAL AUDIT (literal question as query)")
    print("=" * 80)
    for src in ["ALL", "legal-rag-qa", "legal-rag-bench", "open-australian-legal-qa"]:
        n = totals.get(src, 0)
        if not n:
            continue
        line = f"{src:<26} n={n:<4}"
        for k in config.ks:
            line += f"  r@{k}={hits[src][k]/n:.3f}"
        print(line)
    print("=" * 80)
    print("Read: r@3 is what the agent uses (n_results=3). Low per-source r@3 →")
    print("that source's passages are hard to retrieve (chunking/embedding/granularity).")


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
