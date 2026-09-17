"""ChromaDB search tool and reward function for legal RL recipe.

Uses ChromaDB (local) + AWS Bedrock Titan embeddings.

Required env vars:
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION
"""

from __future__ import annotations

import asyncio
import logging
import re
import string
from dataclasses import dataclass
from functools import reduce
from typing import Annotated

import chromadb
import chz

from tinker_cookbook.completers import MessageCompleter
from tinker_cookbook.recipes.legal_rl.embedding import (
    DEFAULT_EMBEDDING_DIM,
    get_bedrock_client,
    get_bedrock_embedding,
)
from tinker_cookbook.renderers import get_text_content
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.tool_use import ToolResult, simple_tool_result, tool

logger = logging.getLogger(__name__)

_CONNECTION_SEMAPHORE = asyncio.Semaphore(128)


def normalize_answer(s: str) -> str:
    """Normalize answer: lowercase, remove punctuation, articles, fix whitespace."""

    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def remove_punc(text: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in text if ch not in exclude)

    transformations = [str.lower, remove_punc, remove_articles, white_space_fix]
    return reduce(lambda text, fn: fn(text), transformations, s)


@chz.chz
class EmbeddingConfig:
    embedding_dim: int = DEFAULT_EMBEDDING_DIM


@chz.chz
class RetrievalConfig:
    n_results: int = 3
    embedding_config: EmbeddingConfig = EmbeddingConfig()


class ChromaTool:
    """Search tool using local ChromaDB PersistentClient + AWS Bedrock Titan embeddings.

    Pickle support: boto3 client and ChromaDB collection are not pickle-safe.
    __getstate__ excludes them; _ensure_clients() lazily reconnects after
    deserialization. Use ChromaTool.build() so connection params are stored.
    """

    def __init__(
        self,
        chroma_path: str,
        collection_name: str,
        retrieval_config: RetrievalConfig,
        max_retries: int,
        aws_region: str | None = None,
        disabled: bool = False,
        # Live clients — excluded from pickle.
        _collection=None,
        _bedrock_client=None,
    ):
        self._chroma_path = chroma_path
        self._collection_name = collection_name
        self._retrieval_config = retrieval_config
        self._max_retries = max_retries
        self._aws_region = aws_region
        # When True, search() returns nothing — used for the grounding probe
        # (measure whether the model can answer without retrieval = memorization).
        self._disabled = disabled
        self._collection = _collection
        self._bedrock_client = _bedrock_client

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state["_collection"] = None
        state["_bedrock_client"] = None
        return state

    def _ensure_clients(self):
        if self._collection is None:
            chroma_client = chromadb.PersistentClient(path=self._chroma_path)
            self._collection = chroma_client.get_collection(self._collection_name)
        if self._bedrock_client is None:
            self._bedrock_client = get_bedrock_client(region_name=self._aws_region)
        return self._collection, self._bedrock_client

    @staticmethod
    def build(
        chroma_path: str,
        collection_name: str,
        aws_region: str,
        retrieval_config: RetrievalConfig = RetrievalConfig(),
        max_retries: int = 10,
        disabled: bool = False,
    ) -> ChromaTool:
        """Factory — stores connection params for pickle support."""
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_collection(collection_name)
        bedrock_client = get_bedrock_client(region_name=aws_region)
        return ChromaTool(
            chroma_path=chroma_path,
            collection_name=collection_name,
            retrieval_config=retrieval_config,
            max_retries=max_retries,
            aws_region=aws_region,
            disabled=disabled,
            _collection=collection,
            _bedrock_client=bedrock_client,
        )

    async def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        _, bedrock_client = self._ensure_clients()
        return await get_bedrock_embedding(
            bedrock_client,
            texts,
            embedding_dim=self._retrieval_config.embedding_config.embedding_dim,
            max_retries=self._max_retries,
        )

    async def _query_chroma(self, embeddings: list[list[float]]) -> list[list[str]]:
        collection, _ = self._ensure_clients()
        for attempt in range(self._max_retries):
            try:
                results = await asyncio.to_thread(
                    collection.query,
                    query_embeddings=embeddings,
                    n_results=self._retrieval_config.n_results,
                )
                documents_list = results["documents"] or []
                return [list(docs) for docs in documents_list]
            except Exception as e:
                if attempt < self._max_retries - 1:
                    wait = 1.0 * (1.5**attempt)
                    logger.error(f"ChromaDB query attempt {attempt + 1}/{self._max_retries} failed: {e}. Retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise RuntimeError("All ChromaDB query attempts failed")

    @tool
    async def search(
        self,
        query_list: Annotated[
            list[str],
            "A list of fully-formed semantic queries. Returns relevant legal document passages for each query.",
        ],
    ) -> ToolResult:
        """Search legal documents for relevant passages based on the given queries."""
        if self._disabled:
            # Grounding probe: tool present but returns nothing, so we can measure
            # whether the model answers from retrieval or from parametric memory.
            return simple_tool_result(
                "No relevant documents were found for your queries."
            )
        async with _CONNECTION_SEMAPHORE:
            embeddings = await self._get_embeddings(query_list)
            results_per_query = await self._query_chroma(embeddings)

        message_content = ""
        for query, documents in zip(query_list, results_per_query):
            message_content += f"Query: {query}\n"
            for doc_i, doc in enumerate(documents):
                message_content += f"Document {doc_i + 1}:\n{doc}\n"

        return simple_tool_result(message_content)


@dataclass
class TextAnswerReward:
    """Reward function for legal QA.

    formula: format_coef * (correct_format - 1) + correct_answer

    correct_format: model response contains "Answer:" prefix
    correct_answer: normalized model answer matches any gold answer
    """

    gold_answers: list[str]
    format_coef: float = 0.1

    async def __call__(self, history: list[Message]) -> tuple[float, dict[str, float]]:
        final_message = None
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                final_message = msg
                break

        if final_message is None:
            return 0.0, {"format": 0.0, "correct": 0.0}

        content = get_text_content(final_message)
        correct_format = float(self._extract_answer(content) is not None)
        correct_answer = float(self._check_answer(content))
        reward = self.format_coef * (correct_format - 1) + correct_answer
        return reward, {"format": correct_format, "correct": correct_answer}

    def _extract_answer(self, text: str) -> str | None:
        if "Answer:" not in text:
            return None
        parts = text.split("Answer:")
        if len(parts) != 2:
            return None
        return parts[1].strip()

    def _check_answer(self, text: str) -> bool:
        model_answer = self._extract_answer(text)
        if model_answer is None or not self.gold_answers:
            return False
        for gold in self.gold_answers:
            if normalize_answer(model_answer) == normalize_answer(gold):
                return True
        return False


JUDGE_PROMPT_TEMPLATE = """You are a strict legal answer grader. Compare a CANDIDATE answer \
against the REFERENCE answer for a legal question. Decide whether the candidate conveys the \
same legal conclusion and key reasoning as the reference. Ignore differences in wording, \
length, formatting, or style — judge only the legal substance.

QUESTION:
{question}

REFERENCE ANSWER:
{reference}

CANDIDATE ANSWER:
{candidate}

Respond with EXACTLY one line, nothing else:
VERDICT: CORRECT     — candidate matches the reference's legal conclusion and key reasoning
VERDICT: PARTIAL     — candidate reaches the right conclusion but misses or misstates key reasoning
VERDICT: INCORRECT   — candidate reaches a wrong, unsupported, or missing conclusion"""


@dataclass
class LLMJudgeReward:
    """Model-based reward: a frozen judge LLM grades semantic correctness.

    Replaces exact string match (TextAnswerReward) which scored substantively
    correct long-form legal answers as wrong. The judge reads (question,
    reference, candidate) and returns a graded verdict:

        CORRECT   -> 1.0
        PARTIAL   -> 0.5
        INCORRECT -> 0.0  (also the fallback for an unparseable verdict)

    The judge is a *frozen base model* (independent of the training checkpoint),
    so the policy cannot game its own judge as it trains.

    reward = judge_score   (format is logged as a metric but NOT rewarded, to
    avoid the format-hacking failure observed with the exact-match reward).
    """

    gold_answers: list[str]
    judge_completer: MessageCompleter
    judge_max_chars: int = 4000  # cap candidate/reference length fed to the judge

    async def __call__(self, history: list[Message]) -> tuple[float, dict[str, float]]:
        question = self._extract_question(history)
        final_message = None
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                final_message = msg
                break

        if final_message is None or not self.gold_answers:
            return 0.0, {"format": 0.0, "correct": 0.0, "judge_score": 0.0}

        content = get_text_content(final_message)
        had_format = float("Answer:" in content)
        candidate = self._answer_text(content)
        reference = "\n--- OR ---\n".join(self.gold_answers)

        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=question[: self.judge_max_chars],
            reference=reference[: self.judge_max_chars],
            candidate=candidate[: self.judge_max_chars],
        )
        judge_reply = await self.judge_completer([{"role": "user", "content": prompt}])
        score = self._parse_verdict(get_text_content(judge_reply))

        return score, {
            "format": had_format,
            "correct": 1.0 if score >= 1.0 else 0.0,
            "judge_score": score,
        }

    @staticmethod
    def _extract_question(history: list[Message]) -> str:
        for msg in history:
            if msg.get("role") == "user":
                return get_text_content(msg)
        return ""

    @staticmethod
    def _answer_text(content: str) -> str:
        # Prefer the text after "Answer:" if present, else the full message.
        if "Answer:" in content:
            return content.split("Answer:", 1)[1].strip()
        return content.strip()

    @staticmethod
    def _parse_verdict(reply: str) -> float:
        # Order matters: "INCORRECT" contains "CORRECT", so check it first.
        upper = reply.upper()
        if "PARTIAL" in upper:
            return 0.5
        if "INCORRECT" in upper:
            return 0.0
        if "CORRECT" in upper:
            return 1.0
        return 0.0
