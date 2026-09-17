"""Build ChromaDB index from legal QA dataset passages.

Downloads isaacus/legal-rag-qa from HuggingFace, embeds the
corpus passages using AWS Bedrock Titan, and upserts them into
a local ChromaDB persistent collection.

Run this ONCE before training:
    python -m tinker_cookbook.recipes.legal_rl.build_index

Required env vars:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION

No ChromaDB server needed — uses PersistentClient (in-process).

Token/character limits (from official AWS docs):
    - amazon.titan-embed-text-v2:0 supports up to 8,192 tokens OR 50,000 characters
    - count_tokens API is NOT supported for Titan embedding models
    - AWS recommendation: segment documents into logical segments (paragraphs/sections)
    - We use 40,000 chars as a conservative safe limit (below the 50,000 char hard limit)
      and split on paragraph boundaries as AWS recommends
"""

import asyncio
import logging

import chromadb
from datasets import load_dataset

from tinker_cookbook.recipes.legal_rl.embedding import get_bedrock_client, get_bedrock_embedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHROMA_PATH = "/tmp/legal_chroma_db"
COLLECTION_NAME = "legal_passages"
HF_DATASET_ID = "isaacus/legal-rag-qa"
BATCH_SIZE = 5

# Chunk size chosen for RETRIEVAL quality + context efficiency, not just the
# embedding token cap. ~1,500 chars ≈ ~375 tokens, so n_results=3 retrieval is
# ~1.1k tokens (vs ~15k with the old 20k-char chunks) — no context overflow, and
# more precise retrieval (a relevant paragraph, not a whole document blob).
# AWS guidance: segment at logical paragraph boundaries.
MAX_CHARS = 1_500


def split_into_chunks(text: str, passage_id: str) -> list[tuple[str, str]]:
    """Split a passage into chunks within MAX_CHARS using paragraph boundaries.

    AWS recommends segmenting at logical boundaries (paragraphs/sections).
    count_tokens API is not supported for Titan embedding models, so we
    use the 40,000 char limit (conservative below the 50,000 char hard limit).

    Returns list of (chunk_id, chunk_text) tuples.
    """
    if len(text) <= MAX_CHARS:
        return [(passage_id, text)]

    # Split on paragraph boundaries first, then sentences as fallback
    paragraphs = text.split("\n\n")
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    current_len = 0
    chunk_idx = 0

    for para in paragraphs:
        if current_len + len(para) > MAX_CHARS and current:
            chunk_text = "\n\n".join(current)
            chunks.append((f"{passage_id}_chunk{chunk_idx}", chunk_text))
            current = [para]
            current_len = len(para)
            chunk_idx += 1
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunk_text = "\n\n".join(current)
        chunk_id = f"{passage_id}_chunk{chunk_idx}" if chunk_idx > 0 else passage_id
        chunks.append((chunk_id, chunk_text))

    logger.info(f"Passage {passage_id} ({len(text)} chars) → {len(chunks)} chunks")
    return chunks


async def build_index() -> None:
    logger.info(f"Loading corpus from: {HF_DATASET_ID} (corpus config)")
    ds = load_dataset(HF_DATASET_ID, "corpus", split="test")

    # Extract and chunk passages
    passages: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []

    for row in ds:
        text = row.get("text", "").strip()
        if not text:
            continue
        row_id = str(row["id"])
        title = str(row.get("title", ""))

        chunks = split_into_chunks(text, row_id)
        for chunk_id, chunk_text in chunks:
            passages.append(chunk_text)
            ids.append(chunk_id)
            metadatas.append({"id": row_id, "title": title, "text": chunk_text})

    logger.info(f"Total chunks to embed: {len(passages)}")

    # Persistent in-process ChromaDB client
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        logger.info(f"Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(f"Created collection: {COLLECTION_NAME}")

    bedrock_client = get_bedrock_client()
    total = len(passages)

    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch_passages = passages[start:end]
        batch_ids = ids[start:end]
        batch_metadatas = metadatas[start:end]

        logger.info(f"Embedding chunks {start + 1}-{end}/{total}...")
        embeddings = await get_bedrock_embedding(bedrock_client, batch_passages)

        collection.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_passages,
            metadatas=batch_metadatas,
        )

    count = collection.count()
    logger.info(f"Done. Collection '{COLLECTION_NAME}' has {count} chunks.")
    logger.info(f"Index saved at: {CHROMA_PATH}")


if __name__ == "__main__":
    asyncio.run(build_index())
