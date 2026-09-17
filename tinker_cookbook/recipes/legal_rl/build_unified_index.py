"""Build the UNIFIED ChromaDB index from all legal sources (see legal_data.py).

Aggregates retrieval passages from every configured source, chunks them
(~1,500 chars on paragraph boundaries), embeds with AWS Bedrock Titan, and
upserts into a persistent ChromaDB collection.

Run once before unified-data training:
    python -m tinker_cookbook.recipes.legal_rl.build_unified_index

Persistent path (survives reboot, unlike /tmp). No ChromaDB server needed.

Required env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
"""

import asyncio
import logging

import chromadb

from tinker_cookbook.recipes.legal_rl.embedding import get_bedrock_client, get_bedrock_embedding
from tinker_cookbook.recipes.legal_rl.legal_data import ALL_SOURCES, iter_passages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHROMA_PATH = "/Users/adithyagiridharan/Desktop/legal_rl_runs/chroma_unified"
COLLECTION_NAME = "legal_unified"
BATCH_SIZE = 5
MAX_CHARS = 1_500  # ~375 tokens/chunk → 3 retrieved ≈ 1.1k tokens (no overflow)


def split_into_chunks(text: str, passage_id: str) -> list[tuple[str, str]]:
    """Split on paragraph boundaries into <=MAX_CHARS chunks."""
    if len(text) <= MAX_CHARS:
        return [(passage_id, text)]
    paragraphs = text.split("\n\n")
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    cur_len = 0
    idx = 0
    for para in paragraphs:
        if cur_len + len(para) > MAX_CHARS and current:
            chunks.append((f"{passage_id}_c{idx}", "\n\n".join(current)))
            current, cur_len, idx = [para], len(para), idx + 1
        else:
            current.append(para)
            cur_len += len(para)
    if current:
        cid = f"{passage_id}_c{idx}" if idx > 0 else passage_id
        chunks.append((cid, "\n\n".join(current)))
    return chunks


async def build_index() -> None:
    logger.info(f"Aggregating passages from sources: {ALL_SOURCES}")
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []

    for p in iter_passages(ALL_SOURCES):
        for chunk_id, chunk_text in split_into_chunks(p["text"], p["id"]):
            ids.append(chunk_id)
            docs.append(chunk_text)
            metas.append({"id": p["id"], "title": p["title"], "text": chunk_text})

    logger.info(f"Total chunks to embed: {len(docs)}")

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info(f"Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    bedrock = get_bedrock_client()
    total = len(docs)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        embs = await get_bedrock_embedding(bedrock, docs[start:end])
        collection.upsert(
            ids=ids[start:end],
            embeddings=embs,
            documents=docs[start:end],
            metadatas=metas[start:end],
        )
        if (end) % 500 < BATCH_SIZE:
            logger.info(f"  embedded {end}/{total}")

    logger.info(f"Done. '{COLLECTION_NAME}' has {collection.count()} chunks at {CHROMA_PATH}")


if __name__ == "__main__":
    asyncio.run(build_index())
