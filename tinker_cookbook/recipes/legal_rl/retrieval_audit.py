"""Retrieval audit — does the RAG retriever surface the ground-truth passage?

Tests the hypothesis "retrieval may be broken" with an exact, objective metric.
The `qa` config of isaacus/legal-rag-qa gives `relevant_passages` (the
ground-truth corpus passage id(s) that answer each question). We embed each
question with the SAME Titan + ChromaDB stack the agent uses, retrieve top-k,
map retrieved chunks back to their source passage id, and check whether the
ground-truth passage is in the retrieved set.

This isolates the RETRIEVER (query = the literal question), separate from the
agent's query-formulation skill. If recall is low even with the literal
question, the retriever itself is broken (embeddings/index/chunking). If recall
is high here but the agent still fails in practice, the problem is the agent's
queries, not the retriever.

Precondition (verified separately): all 138 questions have their relevant
passage present in the index, so any miss is a retrieval-quality miss, not
missing data.

Run:
    python -m tinker_cookbook.recipes.legal_rl.retrieval_audit

Required env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
"""

import asyncio
import logging

import chromadb
import chz
from datasets import load_dataset

from tinker_cookbook.recipes.legal_rl.embedding import get_bedrock_client, get_bedrock_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@chz.chz
class CLIConfig:
    chroma_path: str = "/tmp/legal_chroma_db"
    collection_name: str = "legal_passages"
    hf_dataset_id: str = "isaacus/legal-rag-qa"
    ks: tuple[int, ...] = (1, 3, 5, 10)  # recall@k cutoffs to report
    max_query_chars: int = 40_000  # Titan input cap guard
    num_examples_to_show: int = 8  # print this many hit/miss transcripts


async def cli_main(config: CLIConfig) -> None:
    qa = load_dataset(config.hf_dataset_id, "qa", split="test")
    logger.info(f"Loaded {len(qa)} QA pairs")

    collection = chromadb.PersistentClient(path=config.chroma_path).get_collection(
        config.collection_name
    )
    logger.info(f"Collection '{config.collection_name}' has {collection.count()} chunks")

    bedrock = get_bedrock_client()
    max_k = max(config.ks)

    # For each question: embed, retrieve top max_k chunks, map to source passage ids.
    hits_at_k = {k: 0 for k in config.ks}
    rank_of_first_hit: list[int] = []  # rank (1-based) of first relevant chunk; -1 if miss
    examples: list[dict] = []

    for i, row in enumerate(qa):
        question = row["question"][: config.max_query_chars]
        gold = row["relevant_passages"]
        gold_ids = {str(g) for g in (gold if isinstance(gold, list) else [gold])}

        emb = await get_bedrock_embedding(bedrock, [question])
        result = collection.query(query_embeddings=emb, n_results=max_k, include=["metadatas"])

        # Ordered list of source passage ids for the retrieved chunks
        retrieved_pids = [str(m.get("id", "")) for m in (result["metadatas"][0] or [])]

        # Rank of first chunk whose source passage is a gold passage
        first_hit = next((r for r, pid in enumerate(retrieved_pids, 1) if pid in gold_ids), -1)
        rank_of_first_hit.append(first_hit)

        for k in config.ks:
            if first_hit != -1 and first_hit <= k:
                hits_at_k[k] += 1

        if len(examples) < config.num_examples_to_show:
            examples.append(
                {
                    "qid": row["id"],
                    "gold": sorted(gold_ids),
                    "top": retrieved_pids[: max(config.ks)],
                    "first_hit_rank": first_hit,
                }
            )

        if (i + 1) % 25 == 0:
            logger.info(f"  audited {i + 1}/{len(qa)}")

    n = len(qa)

    print("\n" + "=" * 90)
    print("RETRIEVAL AUDIT — query = literal question, retriever = Titan + ChromaDB")
    print("=" * 90)
    print(f"Questions: {n}  |  Ground-truth passages all present in index: yes")
    print("-" * 90)
    for k in config.ks:
        rec = hits_at_k[k] / n
        print(f"  recall@{k:<2}: {rec:.3f}  ({hits_at_k[k]}/{n} questions had a relevant passage in top-{k})")
    mrr = sum(1.0 / r for r in rank_of_first_hit if r != -1) / n
    misses = sum(1 for r in rank_of_first_hit if r == -1)
    print(f"  MRR     : {mrr:.3f}  (mean reciprocal rank of first relevant chunk)")
    print(f"  total misses (no relevant passage in top-{max_k}): {misses}/{n}")
    print("-" * 90)
    print(f"Sample retrievals (first {len(examples)}):")
    for ex in examples:
        status = f"HIT@{ex['first_hit_rank']}" if ex["first_hit_rank"] != -1 else "MISS"
        print(f"\n  [{status}] {ex['qid']}")
        print(f"    gold passage(s): {ex['gold']}")
        print(f"    top retrieved : {ex['top']}")
    print("=" * 90)
    print("\nInterpretation guide:")
    print("  - High recall@3 (agent uses n_results=3) → retriever is fine; suspect agent queries / memorization.")
    print("  - Low recall@3 but ok recall@10 → retriever ranks poorly; raise n_results or improve embeddings.")
    print("  - Low recall@10 → retriever/index/chunking is broken; fix before rewarding retrieval.")


if __name__ == "__main__":
    config = chz.entrypoint(CLIConfig)
    asyncio.run(cli_main(config))
