"""Unified legal dataset — combines multiple authentic legal QA + corpus sources
into one RAG-RL dataset: a single QA pool + a single retrieval corpus.

Single source of truth for both the index builder (`build_unified_index.py`) and
the environment loader (`legal_env.py`), so the source list is defined once.

Verified source schemas (inspected 2026-06-06):
  - isaacus/legal-rag-qa  (US criminal law, CC-BY-NC-SA-3.0)
      qa config:     question, answer (str), relevant_passages (list)
      corpus config: id, section, title, text                       [190 passages]
  - isaacus/legal-rag-bench  (AU/Victoria criminal law, CC-BY-NC-4.0)
      qa config:     id, question, answer (str), relevant_passage_id
      corpus config: id, title, text, footnotes                     [4,876 passages]
  - isaacus/open-australian-legal-qa  (AU broad case law, CC-BY-4.0)
      default split: question, answer (str), text, prompt,
                     source{version_id, citation, text, jurisdiction, ...}
                     (retrieval passages = source.text per QA)       [2,124 QA / 2,121 uniq]

Combining these makes the task MULTI-JURISDICTION legal QA (US + Australian).
"""

from __future__ import annotations

from typing import Iterator, TypedDict

from datasets import load_dataset

# All sources included by default. Override with a subset if desired.
ALL_SOURCES: list[str] = [
    "legal-rag-qa",
    "legal-rag-bench",
    "open-australian-legal-qa",
]


class QAItem(TypedDict):
    question: str
    answer: list[str]  # wrapped in list for reward matching
    source: str  # which dataset it came from (for logging/tags)


class Passage(TypedDict):
    id: str  # unified id, prefixed by source to avoid collisions
    title: str
    text: str


def load_qa(sources: list[str] | None = None) -> list[QAItem]:
    """Load and normalize QA pairs from the given sources into one pool."""
    sources = sources or ALL_SOURCES
    pool: list[QAItem] = []

    if "legal-rag-qa" in sources:
        ds = load_dataset("isaacus/legal-rag-qa", "qa", split="test")
        for r in ds:
            pool.append({"question": r["question"], "answer": [r["answer"]], "source": "legal-rag-qa"})

    if "legal-rag-bench" in sources:
        ds = load_dataset("isaacus/legal-rag-bench", "qa", split="test")
        for r in ds:
            pool.append(
                {"question": r["question"], "answer": [r["answer"]], "source": "legal-rag-bench"}
            )

    if "open-australian-legal-qa" in sources:
        ds = load_dataset("isaacus/open-australian-legal-qa", "default", split="train")
        for r in ds:
            pool.append(
                {
                    "question": r["question"],
                    "answer": [r["answer"]],
                    "source": "open-australian-legal-qa",
                }
            )

    return pool


def iter_passages(sources: list[str] | None = None) -> Iterator[Passage]:
    """Yield retrieval passages from the given sources, ids prefixed by source.

    open-australian-legal-qa has no corpus config; its passages are the unique
    `source.text` chunks attached to each QA.
    """
    sources = sources or ALL_SOURCES

    if "legal-rag-qa" in sources:
        ds = load_dataset("isaacus/legal-rag-qa", "corpus", split="test")
        for r in ds:
            text = (r.get("text") or "").strip()
            if text:
                yield {"id": f"rqa:{r['id']}", "title": str(r.get("title", "")), "text": text}

    if "legal-rag-bench" in sources:
        ds = load_dataset("isaacus/legal-rag-bench", "corpus", split="test")
        for r in ds:
            text = (r.get("text") or "").strip()
            if text:
                yield {"id": f"rb:{r['id']}", "title": str(r.get("title", "")), "text": text}

    if "open-australian-legal-qa" in sources:
        ds = load_dataset("isaacus/open-australian-legal-qa", "default", split="train")
        seen: set[str] = set()
        for i, r in enumerate(ds):
            src = r["source"]
            text = (src.get("text") or "").strip()
            if text and text not in seen:
                seen.add(text)
                yield {"id": f"oa:{i}", "title": str(src.get("citation", "")), "text": text}
