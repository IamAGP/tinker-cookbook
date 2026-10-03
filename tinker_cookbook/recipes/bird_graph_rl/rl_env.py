"""RL environment: a Cypher-writing agent rewarded by executing its own final query.

Mirrors the upstream tool-use RL recipe (``recipes/search_tool/search_env.py``): one
``EnvGroupBuilder`` per training question, ``group_size`` rollouts of the same question per group,
each rollout an ``AgentToolMessageEnv`` built by ``build_agent_tool_env``.

The environment is deliberately the baseline harness with the scorer swapped for a reward:
same system prompt, same tool, same row and character caps, same turn and trajectory limits.
Training and evaluation therefore cannot drift apart, and another platform can reuse this
module unchanged by swapping only the service client.

Reward (``reward.partial_credit``): row-level F1 between the rows returned by the rollout's last
successful query, re-executed without the display cap, and the instance's reference rows. It is
1.0 only for a strictly correct answer and 0.0 when no query succeeded. Range [0, 1].
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

import chz
from dotenv import load_dotenv
from neo4j import AsyncDriver, AsyncGraphDatabase, unit_of_work

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.recipes.bird_graph_rl.baseline_eval import (
    SCORE_ROW_CAP,
    SYSTEM_PROMPT,
    CypherTool,
)
from tinker_cookbook.recipes.bird_graph_rl.reward import partial_credit
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.types import Env, EnvGroupBuilder, RLDataset, RLDatasetBuilder
from tinker_cookbook.tool_use import build_agent_tool_env


class GraphQADatum(TypedDict):
    """One training or validation question with its execution-verified answer."""

    instance_id: str
    question: str
    hint: str  # "" when the question carries none
    rows: list[list[Any]]  # complete reference rows
    n_rows: int
    structure_id: str
    hops: int
    split: str


def load_instances(path: str, split: str) -> list[GraphQADatum]:
    """Read a JSONL file of ``GraphQADatum`` and keep one split."""
    data: list[GraphQADatum] = []
    with Path(path).expanduser().open() as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                if d["split"] == split:
                    data.append(d)
    return data


def prompt_text(datum: GraphQADatum) -> str:
    """Same user-turn format as the evaluation harness: question, then an optional hint."""
    hint = (datum.get("hint") or "").strip()
    return f"{datum['question']}\n\nHint: {hint}" if hint else datum["question"]


MAX_CONCURRENT_QUERIES = 24
_DRIVERS: dict[str, AsyncDriver] = {}


def get_driver(env_file: str) -> AsyncDriver:
    """One shared async driver per process; builders hold only configuration, never a driver."""
    load_dotenv(env_file, override=False)
    uri = os.environ["BIRD_NEO4J_URI"]
    if uri not in _DRIVERS:
        # The pool is the concurrency limit on the database: a training batch can issue well over a
        # hundred queries at once against a single local instance. Excess queries wait here for a
        # connection instead of timing out inside the database, where a timeout would reach the
        # model as an error and change its reward. The server-side transaction timeout only starts
        # once a query actually runs.
        _DRIVERS[uri] = AsyncGraphDatabase.driver(
            uri,
            auth=(os.environ["BIRD_NEO4J_USER"], os.environ["BIRD_NEO4J_PASSWORD"]),
            max_connection_pool_size=MAX_CONCURRENT_QUERIES,
            connection_acquisition_timeout=1800,
        )
    return _DRIVERS[uri]


TRAIN_QUERY_TIMEOUT_S = 45.0


class TrainingCypherTool(CypherTool):
    """The evaluation tool with a shorter per-query limit, for training only.

    In a synchronous training step every rollout waits for the slowest one, and a single
    pathological query (an unindexed join, a Cartesian product) runs to the database's 120 s
    limit. Measured over the first run's 6,424 calls, the slowest successful query took 23.8 s
    and nothing finished between 30 s and the limit, so 45 s changes no outcome: the same queries
    fail with the same kind of error, sooner. Evaluation keeps the 120 s limit, where every
    baseline was measured.
    """

    async def execute(self, query: str, row_cap: int) -> list[list[Any]]:
        @unit_of_work(timeout=TRAIN_QUERY_TIMEOUT_S)
        async def work(tx: Any) -> list[list[Any]]:
            result = await tx.run(query)
            rows: list[list[Any]] = []
            async for record in result:
                rows.append(list(record.values()))
                if len(rows) >= row_cap:
                    break
            return rows

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(work)


class ExecutionReward:
    """Grades one rollout from the queries its own tool instance recorded."""

    def __init__(self, tool: CypherTool, datum: GraphQADatum) -> None:
        self._tool = tool
        self._ref = {"rows": datum["rows"], "n_rows": datum["n_rows"], "truncated": False}

    async def __call__(self, history: list[Message]) -> tuple[float, dict[str, float]]:
        log = self._tool.log
        successes = [entry for entry in log if entry["ok"]]
        metrics = {
            "n_queries": float(len(log)),
            "n_query_errors": float(sum(1 for entry in log if not entry["ok"])),
            "no_query": float(not log),
        }
        if not successes:
            return 0.0, {**metrics, "correct": 0.0, "partial_credit": 0.0, "rescore_failed": 0.0}
        try:
            rows = await self._tool.execute(successes[-1]["query"], SCORE_ROW_CAP)
        except Exception:  # noqa: BLE001 - a query that ran once but fails on re-execution earns nothing
            return 0.0, {**metrics, "correct": 0.0, "partial_credit": 0.0, "rescore_failed": 1.0}
        graded = partial_credit(rows, self._ref)
        return graded["reward"], {
            **metrics,
            "correct": graded["strict"],
            "partial_credit": graded["reward"],
            "rescore_failed": 0.0,
        }


class GraphEnvGroupBuilder(EnvGroupBuilder):
    """``group_size`` independent rollouts of one question."""

    def __init__(
        self,
        datum: GraphQADatum,
        model_name: str,
        renderer_name: str | None,
        group_size: int,
        max_turns: int,
        max_trajectory_tokens: int,
        env_file: str,
        database: str,
    ) -> None:
        self.datum = datum
        self.model_name = model_name
        self.renderer_name = renderer_name
        self.group_size = group_size
        self.max_turns = max_turns
        self.max_trajectory_tokens = max_trajectory_tokens
        self.env_file = env_file
        self.database = database

    async def make_envs(self) -> Sequence[Env]:
        tokenizer = tokenizer_utils.get_tokenizer(self.model_name)
        renderer = get_renderer(
            self.renderer_name or model_info.get_recommended_renderer_name(self.model_name), tokenizer
        )
        driver = get_driver(self.env_file)
        envs: list[Env] = []
        for _ in range(self.group_size):
            # The tool records the queries of one rollout, so each rollout gets its own instance.
            tool = TrainingCypherTool(driver, self.database)
            messages = renderer.create_conversation_prefix_with_tools(
                tools=[tool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT
            ) + [{"role": "user", "content": prompt_text(self.datum)}]
            envs.append(
                build_agent_tool_env(
                    renderer=renderer,
                    tools=[tool.run_cypher],
                    initial_messages=messages,
                    reward_fn=ExecutionReward(tool, self.datum),
                    max_turns=self.max_turns,
                    max_trajectory_tokens=self.max_trajectory_tokens,
                    # Keep the reward on [0, 1]: a malformed or over-long rollout earns 0, not a penalty.
                    failed_parse_reward=0.0,
                    context_overflow_reward=0.0,
                )
            )
        return envs

    def logging_tags(self) -> list[str]:
        return [self.datum["split"], f"hops{self.datum['hops']}"]


class GraphRLDataset(RLDataset):
    def __init__(self, builders: list[GraphEnvGroupBuilder], batch_size: int) -> None:
        self.builders = builders
        self.batch_size = batch_size

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        start = index * self.batch_size
        return self.builders[start : start + self.batch_size]

    def __len__(self) -> int:
        return len(self.builders) // self.batch_size


@chz.chz
class GraphQADatasetBuilder(RLDatasetBuilder):
    """Training groups from one split of an instances file; optional validation split."""

    instances_path: str
    model_name_for_tokenizer: str
    batch_size: int  # question groups per training iteration
    group_size: int  # rollouts per question
    renderer_name: str | None = None
    train_split: str = "train"
    test_split: str | None = None
    test_size: int = 64
    n_epochs: int = 1
    max_turns: int = 8
    max_trajectory_tokens: int = 56 * 1024
    env_file: str = ".env"
    database: str = "neo4j"
    seed: int = 0

    def _builders(self, data: list[GraphQADatum], group_size: int) -> list[GraphEnvGroupBuilder]:
        return [
            GraphEnvGroupBuilder(
                datum=d,
                model_name=self.model_name_for_tokenizer,
                renderer_name=self.renderer_name,
                group_size=group_size,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
                env_file=self.env_file,
                database=self.database,
            )
            for d in data
        ]

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        rng = random.Random(self.seed)
        train: list[GraphQADatum] = []
        for _ in range(self.n_epochs):
            epoch = load_instances(self.instances_path, self.train_split)
            rng.shuffle(epoch)
            train.extend(epoch)
        train_set = GraphRLDataset(self._builders(train, self.group_size), self.batch_size)
        test_set: RLDataset | None = None
        if self.test_split is not None:
            held = load_instances(self.instances_path, self.test_split)
            random.Random(self.seed).shuffle(held)
            held = held[: self.test_size]
            test_set = GraphRLDataset(self._builders(held, 1), max(1, len(held)))
        return train_set, test_set
