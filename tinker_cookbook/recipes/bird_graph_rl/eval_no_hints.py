"""The evaluation harness with the hint withheld: the model sees the question alone.

Used for one diagnostic — how much a model's accuracy depends on the hint. Everything else is
``baseline_eval`` unchanged, which is why this is a wrapper and not an option there.
"""

from __future__ import annotations

import asyncio
from typing import Any

import chz

from tinker_cookbook.recipes.bird_graph_rl import baseline_eval


def question_only(ref: dict[str, Any]) -> str:
    return ref["question"]


if __name__ == "__main__":
    baseline_eval.question_text = question_only
    asyncio.run(baseline_eval.main(chz.entrypoint(baseline_eval.Config)))
