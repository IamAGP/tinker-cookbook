"""AWS Bedrock embedding utilities for legal RL recipe.

Replaces Gemini/Vertex AI from search_tool/embedding.py.
Uses amazon.titan-embed-text-v2:0 via boto3 + asyncio.to_thread.

Required env vars:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION  (e.g. us-east-1)
"""

import asyncio
import json
import logging

import boto3

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_DELAY = 1.0

BEDROCK_MODEL_ID = "amazon.titan-embed-text-v2:0"
DEFAULT_EMBEDDING_DIM = 1024


def get_bedrock_client(region_name: str | None = None) -> boto3.client:
    """Build a boto3 bedrock-runtime client.

    Reads credentials from env vars:
        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION.
    """
    return boto3.client("bedrock-runtime", region_name=region_name)


def _embed_single_sync(
    client: boto3.client,
    text: str,
    embedding_dim: int,
) -> list[float]:
    """Synchronous single-text embedding call to Bedrock Titan."""
    body = json.dumps({"inputText": text, "dimensions": embedding_dim, "normalize": True})
    response = client.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
    result = json.loads(response["body"].read())
    return result["embedding"]


async def get_bedrock_embedding(
    client: boto3.client,
    texts: list[str],
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    max_retries: int = MAX_RETRIES,
    retry_delay: float = RETRY_DELAY,
) -> list[list[float]]:
    """Get embeddings from AWS Bedrock Titan for a list of texts.

    Mirrors the contract of search_tool/embedding.py::get_gemini_embedding:
        - Input:  list[str]
        - Output: list[list[float]], same length as input
        - Async:  yes (uses asyncio.to_thread for boto3 sync calls)

    Args:
        client: boto3 bedrock-runtime client from get_bedrock_client().
        texts: List of strings to embed.
        embedding_dim: Output dimension (256, 512, or 1024). Default 1024.
        max_retries: Retry attempts per text on failure.
        retry_delay: Base delay between retries (exponential backoff).
    """
    if not texts:
        raise ValueError("No texts provided for embedding generation")

    for i, text in enumerate(texts):
        if not isinstance(text, str):
            raise ValueError(f"Text at index {i} is not a string: {type(text)}")
        if not text.strip():
            raise ValueError(f"Text at index {i} is empty or whitespace only")

    async def embed_one(text: str) -> list[float]:
        for attempt in range(max_retries):
            try:
                return await asyncio.to_thread(_embed_single_sync, client, text, embedding_dim)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = retry_delay * (1.5**attempt)
                    logger.error(
                        f"Bedrock embed attempt {attempt + 1}/{max_retries} failed: {e!r}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"All {max_retries} attempts failed for text: {e!r}")
                    raise
        raise RuntimeError("Unexpected error in retry logic")

    embeddings = await asyncio.gather(*[embed_one(t) for t in texts])
    return list(embeddings)
