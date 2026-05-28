"""
Neo4j Cricket KG environment for multi-turn RL.

The agent receives a cricket question and must answer it by calling:
  - get_schema()        → see node labels, relationship types, property keys
  - run_cypher(query)   → execute a Cypher query, get results back
  - final_answer(text)  → submit answer, ends episode, triggers reward

Reward = 0 if no DB query made (prevents reward hacking).
Otherwise: 0.4 (entity match) + 0.6 (number match) = 1.0 max.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Sequence

import chz
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import CypherSyntaxError, CypherTypeError, ClientError

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.types import Env, EnvGroupBuilder, RLDataset, RLDatasetBuilder
from tinker_cookbook.tool_use.agent_tool_message_env import RewardFn, build_agent_tool_env
from tinker_cookbook.tool_use.tools import error_tool_result, simple_tool_result, tool
from tinker_cookbook.tool_use.types import ToolResult

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a cricket data analyst with access to a Neo4j knowledge graph "
    "containing ball-by-ball IPL T20 data. "
    "Follow these steps strictly:\n"
    "1. Call get_schema to understand the graph structure before writing any query.\n"
    "2. Call run_cypher with a valid read-only Cypher query based on what the schema tells you.\n"
    "3. Once you have a result, you MUST call the final_answer tool to submit your answer. "
    "Do NOT write the answer as plain text or XML tags. "
    "You MUST use the final_answer tool call — no other format is accepted."
)

# Max rows returned by run_cypher to keep context manageable
MAX_CYPHER_ROWS = 20
# Max characters in a Cypher result string
MAX_RESULT_CHARS = 2000


# ---------------------------------------------------------------------------
# Neo4j schema cache — fetched once per driver, reused across episodes
# ---------------------------------------------------------------------------

_SCHEMA_CACHE: str | None = None


async def _fetch_schema(driver: AsyncDriver) -> str:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE

    async with driver.session() as session:
        # Node labels and their properties (sampled from actual data)
        nodes_result = await session.run("""
            CALL db.schema.nodeTypeProperties()
            YIELD nodeType, propertyName
            RETURN nodeType, collect(propertyName) AS properties
            ORDER BY nodeType
        """)
        nodes = await nodes_result.data()

        # Relationship types and their properties
        rels_result = await session.run("""
            CALL db.schema.relTypeProperties()
            YIELD relType, propertyName
            RETURN relType, collect(propertyName) AS properties
            ORDER BY relType
        """)
        rels = await rels_result.data()

        # Relationship endpoints: which node label connects to which
        endpoints_result = await session.run("""
            MATCH (a)-[r]->(b)
            WITH type(r) AS relType, labels(a)[0] AS fromLabel, labels(b)[0] AS toLabel
            RETURN DISTINCT relType, fromLabel, toLabel
            ORDER BY relType
        """)
        endpoints = await endpoints_result.data()

        # Constraints (uniqueness, node key, etc.)
        # YIELD must come before WHERE in SHOW commands
        constraints_result = await session.run("""
            SHOW CONSTRAINTS
            YIELD name, type, entityType, labelsOrTypes, properties
            WHERE entityType IN ['NODE', 'RELATIONSHIP']
            RETURN name, type, entityType, labelsOrTypes, properties
            ORDER BY entityType, labelsOrTypes
        """)
        constraints = await constraints_result.data()

        # Indexes (excluding auto-created LOOKUP indexes)
        # YIELD must come before WHERE in SHOW commands
        indexes_result = await session.run("""
            SHOW INDEXES
            YIELD name, type, state, entityType, labelsOrTypes, properties
            WHERE type <> 'LOOKUP'
            RETURN name, type, state, entityType, labelsOrTypes, properties
            ORDER BY entityType, labelsOrTypes
        """)
        indexes = await indexes_result.data()

    # ── Build schema string ────────────────────────────────────────────────────

    # Build property lookup by relType for the endpoints section
    rel_props: dict[str, list[str]] = {
        row["relType"]: row["properties"] for row in rels
    }

    lines = ["=== NODE LABELS AND PROPERTIES ==="]
    for row in nodes:
        props = ", ".join(row["properties"]) if row["properties"] else "none"
        lines.append(f"  {row['nodeType']}  properties: {props}")

    lines.append("\n=== RELATIONSHIP TYPES (fromLabel)-[:TYPE]->(toLabel) ===")
    for row in endpoints:
        rel_type = row["relType"]
        props = ", ".join(rel_props.get(rel_type, [])) or "none"
        lines.append(
            f"  (:{row['fromLabel']})-[:{rel_type}]->(:{row['toLabel']})"
            f"  properties: {props}"
        )

    if constraints:
        lines.append("\n=== CONSTRAINTS ===")
        for row in constraints:
            labels = ", ".join(row["labelsOrTypes"])
            props = ", ".join(row["properties"])
            lines.append(f"  {row['type']} on {row['entityType']} {labels} ({props})")

    if indexes:
        lines.append("\n=== INDEXES ===")
        for row in indexes:
            labels = ", ".join(row["labelsOrTypes"])
            props = ", ".join(row["properties"])
            state = row["state"]
            lines.append(
                f"  {row['type']} [{state}] on {row['entityType']} {labels} ({props})"
            )

    _SCHEMA_CACHE = "\n".join(lines)
    return _SCHEMA_CACHE


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class Neo4jTools:
    """
    Three tools the agent can call:
      get_schema   → understand the KG structure
      run_cypher   → execute a read query
      final_answer → submit the answer and end the episode
    """

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver
        self._final_answer: str | None = None

    @tool
    async def get_schema(self) -> ToolResult:
        """Get all node labels, relationship types, and their properties in the cricket KG."""
        try:
            schema = await _fetch_schema(self._driver)
            return simple_tool_result(schema, name="get_schema")
        except Exception as e:
            return error_tool_result(str(e), name="get_schema")

    @tool
    async def run_cypher(
        self,
        query: Annotated[str, "A read-only Cypher query to run against the cricket KG"],
    ) -> ToolResult:
        """Execute a Cypher query against the cricket knowledge graph and return the results."""
        # Block write operations
        normalized = query.strip().upper()
        for keyword in ("CREATE", "MERGE", "DELETE", "SET", "REMOVE", "DROP"):
            if re.search(rf"\b{keyword}\b", normalized):
                return error_tool_result(
                    "Only read queries are allowed. Remove write operations.",
                    name="run_cypher",
                    error_type="write_blocked",
                )

        try:
            async with self._driver.session() as session:
                result = await session.run(query)
                rows = await result.data()

            rows = rows[:MAX_CYPHER_ROWS]
            text = json.dumps(rows, default=str, ensure_ascii=False)
            if len(text) > MAX_RESULT_CHARS:
                text = text[:MAX_RESULT_CHARS] + "... [truncated]"

            return simple_tool_result(
                text,
                name="run_cypher",
                metrics={"rows_returned": float(len(rows))},
            )
        except (CypherSyntaxError, CypherTypeError, ClientError) as e:
            return error_tool_result(str(e), name="run_cypher", error_type="cypher_error")
        except Exception as e:
            return error_tool_result(str(e), name="run_cypher", error_type="execution_error")

    @tool
    async def final_answer(
        self,
        answer: Annotated[str, "Your final answer to the cricket question"],
    ) -> ToolResult:
        """Submit your final answer. This ends the episode."""
        self._final_answer = answer
        return simple_tool_result(
            "Answer recorded.",
            name="final_answer",
            should_stop=True,
        )


# ---------------------------------------------------------------------------
# Reward function
# ---------------------------------------------------------------------------

def _extract_number(text: str) -> str | None:
    """Pull the first integer or decimal from a string."""
    m = re.search(r"\d+(?:\.\d+)?", text)
    return m.group() if m else None


def _normalise(text: str) -> str:
    return text.lower().strip()


def compute_reward(
    final_answer: str | None,
    ground_truth: str,
    used_db: bool,
) -> tuple[float, dict[str, float]]:
    """
    Reward is zero unless the model queried the DB (prevents reward hacking).
    When DB was used:
      0.4 — answer contains the correct entity name (e.g. "DA Warner")
      0.6 — answer also contains the correct stat number (e.g. "692")
      ----
      1.0 — full credit

    All checks are case-insensitive.
    Entity match uses the first two words of ground truth as a soft name signal.
    Number match requires exact numeric match.
    """
    if not used_db:
        return 0.0, {"reward/no_db_query": 1.0}

    if final_answer is None:
        return 0.0, {"reward/no_answer": 1.0}

    fa = _normalise(final_answer)
    gt = _normalise(ground_truth)

    # Number must match exactly
    gt_number = _extract_number(gt)
    fa_number = _extract_number(fa)
    number_match = gt_number is not None and gt_number == fa_number

    # Entity: first two words of ground truth (covers "da warner", "b kumar", "mi" etc.)
    gt_words = gt.split()
    gt_entity = " ".join(gt_words[:2]) if len(gt_words) >= 2 else gt_words[0] if gt_words else ""
    entity_match = gt_entity in fa

    reward = (0.4 if entity_match else 0.0) + (0.6 if number_match else 0.0)
    metrics = {
        "reward/number_match": float(number_match),
        "reward/entity_match": float(entity_match),
    }
    return reward, metrics


def _serialize_history(history: list[Message]) -> list[dict]:
    """Serialize message history to plain dicts for JSON logging."""
    result = []
    for msg in history:
        entry: dict[str, Any] = {"role": msg.get("role", "unknown")}
        if msg.get("content"):
            entry["content"] = str(msg["content"])
        if msg.get("tool_calls"):
            entry["tool_calls"] = [
                {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in msg["tool_calls"]
            ]
        if msg.get("tool_call_id"):
            entry["tool_call_id"] = msg["tool_call_id"]
            entry["tool_result"] = str(msg.get("content", ""))
        result.append(entry)
    return result


def make_reward_fn(question: str, ground_truth: str, conv_log_path: Path | None) -> RewardFn:
    async def reward_fn(history: list[Message]) -> tuple[float, dict[str, float]]:
        # Check if model used the DB (called run_cypher at least once)
        used_db = False
        final_answer_text: str | None = None

        for msg in history:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if tc.function.name == "run_cypher":
                        used_db = True
                    if tc.function.name == "final_answer":
                        try:
                            args = json.loads(tc.function.arguments)
                            final_answer_text = args.get("answer")
                        except (json.JSONDecodeError, AttributeError):
                            pass

        reward, metrics = compute_reward(final_answer_text, ground_truth, used_db)

        # Write full conversation to log file for later inspection
        if conv_log_path is not None:
            try:
                record = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "question": question,
                    "ground_truth": ground_truth,
                    "final_answer": final_answer_text,
                    "used_db": used_db,
                    "reward": reward,
                    "entity_match": metrics.get("reward/entity_match", 0.0),
                    "number_match": metrics.get("reward/number_match", 0.0),
                    "turns": sum(1 for m in history if m.get("role") == "assistant"),
                    "history": _serialize_history(history),
                }
                with open(conv_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as exc:
                logger.warning("Failed to write conversation log: %s", exc)

        return reward, metrics

    return reward_fn


# ---------------------------------------------------------------------------
# Dataset item
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CricketQuestion:
    question: str
    answer: str       # ground truth — only used by reward function
    category: str
    season: int | None


# ---------------------------------------------------------------------------
# EnvGroupBuilder
# ---------------------------------------------------------------------------

class CricketKGEnvGroupBuilder(EnvGroupBuilder):
    """Creates a group of Neo4j environments for one cricket question."""

    def __init__(
        self,
        question: CricketQuestion,
        driver: AsyncDriver,
        model_name: str,
        renderer_name: str | None,
        group_size: int,
        max_turns: int = 8,
        max_trajectory_tokens: int = 16 * 1024,
        conv_log_path: Path | None = None,
    ) -> None:
        self.question = question
        self.driver = driver
        self.model_name = model_name
        self.renderer_name = renderer_name
        self.group_size = group_size
        self.max_turns = max_turns
        self.max_trajectory_tokens = max_trajectory_tokens
        self.conv_log_path = conv_log_path

    def _build_initial_messages(self, tools: Neo4jTools, renderer: Any) -> list[Message]:
        tool_specs = [tools.get_schema.to_spec(), tools.run_cypher.to_spec(), tools.final_answer.to_spec()]
        prefix = renderer.create_conversation_prefix_with_tools(
            tools=tool_specs,
            system_prompt=SYSTEM_PROMPT,
        )
        return prefix + [{"role": "user", "content": self.question.question}]

    async def make_envs(self) -> Sequence[Env]:
        tokenizer = tokenizer_utils.get_tokenizer(self.model_name)
        renderer_name = self.renderer_name or model_info.get_recommended_renderer_name(self.model_name)
        renderer = get_renderer(renderer_name, tokenizer)

        envs = []
        for _ in range(self.group_size):
            neo4j_tools = Neo4jTools(driver=self.driver)
            initial_messages = self._build_initial_messages(neo4j_tools, renderer)
            reward_fn = make_reward_fn(
                question=self.question.question,
                ground_truth=self.question.answer,
                conv_log_path=self.conv_log_path,
            )

            env = build_agent_tool_env(
                renderer=renderer,
                tools=[neo4j_tools.get_schema, neo4j_tools.run_cypher, neo4j_tools.final_answer],
                initial_messages=initial_messages,
                reward_fn=reward_fn,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
            )
            envs.append(env)
        return envs

    async def compute_group_rewards(self, trajectory_group, env_group):
        return [(0.0, {}) for _ in trajectory_group]

    def logging_tags(self) -> list[str]:
        return ["cricket_kg", self.question.category]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class CricketKGDataset(RLDataset):
    def __init__(self, builders: list[CricketKGEnvGroupBuilder], batch_size: int) -> None:
        self._builders = builders
        self._batch_size = batch_size
        # Shuffled order — reshuffled on each full pass
        self._order: list[int] = list(range(len(builders)))
        random.shuffle(self._order)
        self._epoch = 0

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        n = len(self._builders)
        batches_per_epoch = (n + self._batch_size - 1) // self._batch_size
        epoch = index // batches_per_epoch
        local_idx = index % batches_per_epoch

        # Reshuffle at the start of each new epoch
        if epoch != self._epoch:
            self._epoch = epoch
            self._order = list(range(n))
            random.shuffle(self._order)
            logger.debug("CricketKGDataset: starting epoch %d (reshuffled %d questions)", epoch, n)

        start = local_idx * self._batch_size
        indices = self._order[start : start + self._batch_size]
        return [self._builders[i] for i in indices]

    def __len__(self) -> int:
        # Return a large number so the training loop uses max_steps to stop, not dataset length
        return 10_000


# ---------------------------------------------------------------------------
# DatasetBuilder
# ---------------------------------------------------------------------------

@chz.chz
class CricketKGDatasetBuilder(RLDatasetBuilder):
    """
    Loads cricket Q&A pairs from a JSON file and builds an RL dataset.

    The JSON file is produced by generate_questions.py.
    Each entry must have: question, answer, category, season.
    """

    questions_path: str
    model_name: str
    batch_size: int
    group_size: int
    renderer_name: str | None = None
    max_turns: int = 8
    max_trajectory_tokens: int = 16 * 1024
    categories: list[str] | None = None   # filter by category; None = all
    max_questions: int | None = None       # cap dataset size for smoke tests
    log_path: str | None = None            # directory for conversations.jsonl

    def _load_questions(self) -> list[CricketQuestion]:
        data = json.loads(Path(self.questions_path).read_text(encoding="utf-8"))
        questions = []
        for item in data:
            if self.categories and item["category"] not in self.categories:
                continue
            questions.append(CricketQuestion(
                question=item["question"],
                answer=item["answer"],
                category=item["category"],
                season=item.get("season"),
            ))
        if self.max_questions:
            questions = questions[: self.max_questions]
        return questions

    def _make_driver(self) -> AsyncDriver:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD")
        if not uri or not password:
            raise RuntimeError("NEO4J_URI and NEO4J_PASSWORD must be set in .env")
        return AsyncGraphDatabase.driver(uri, auth=(user, password))

    def _make_builders(
        self,
        questions: list[CricketQuestion],
        driver: AsyncDriver,
        group_size: int,
        conv_log_path: Path | None,
    ) -> list[CricketKGEnvGroupBuilder]:
        return [
            CricketKGEnvGroupBuilder(
                question=q,
                driver=driver,
                model_name=self.model_name,
                renderer_name=self.renderer_name,
                group_size=group_size,
                max_turns=self.max_turns,
                max_trajectory_tokens=self.max_trajectory_tokens,
                conv_log_path=conv_log_path,
            )
            for q in questions
        ]

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        questions = self._load_questions()
        logger.info("Loaded %d cricket questions", len(questions))

        driver = self._make_driver()

        conv_log_path: Path | None = None
        if self.log_path:
            conv_log_path = Path(self.log_path) / "conversations.jsonl"
            conv_log_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Conversation log: %s", conv_log_path)

        train_builders = self._make_builders(questions, driver, self.group_size, conv_log_path)
        eval_builders = self._make_builders(questions[:self.batch_size], driver, group_size=1, conv_log_path=None)

        return (
            CricketKGDataset(train_builders, self.batch_size),
            CricketKGDataset(eval_builders, self.batch_size),
        )
