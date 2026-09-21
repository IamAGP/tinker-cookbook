"""Zero-shot baseline: can a model answer BIRD's questions by writing Cypher against the graph?

Scoring follows BIRD's execution-accuracy idea: after each rollout, the model's last successful
Cypher query is re-executed without a row cap and its result rows are compared with the rows
produced by executing BIRD's gold SQL on the original SQLite file. No gold Cypher is needed.

Operational guarantees (see JOURNAL.md, E2 preflight):
- one timestamped progress line per finished question, with running accuracy and running cost;
- one JSON line appended per question to ``<log_path>/results.jsonl``; a rerun skips finished ids;
- per-question memory only; tool output truncated before it enters the conversation;
- a live token meter converts to dollars with the published prices, and new questions stop
  being started once the estimate crosses ``budget_usd`` (the watchdog for a billed run).

Usage:
    uv run python -m tinker_cookbook.recipes.bird_graph_rl.baseline_eval \\
        reference_uri=s3://<bucket>/codebase_community/gold/reference_answers.json \\
        log_path=~/bird_rl_runs/e2_qwen3_8_27b limit=10
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

import boto3
import chz
import tinker
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.renderers import get_renderer, get_text_content
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.rollout_limits import RolloutLimits
from tinker_cookbook.rl.rollout_runner import run_rollout
from tinker_cookbook.tool_use import ToolResult, build_agent_tool_env, simple_tool_result, tool
from tinker_cookbook.tool_use.tools import error_tool_result
from tinker_cookbook.utils.git_rev import recipe_user_metadata

logger = logging.getLogger(__name__)

# Published per-million-token prices (tinker-docs models page, read 2026-09-21).
PRICES_PER_M: dict[str, dict[str, float]] = {
    "Qwen/Qwen3.8-27B": {"prefill": 1.86, "cached_prefill": 0.372, "sample": 5.595},
}
WRITE_KEYWORDS = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b", re.I)
STRING_LITERALS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
TOOL_ROW_CAP = 50            # rows shown to the model
TOOL_CHAR_CAP = 6000         # characters shown to the model
SCORE_ROW_CAP = 25_000       # rows fetched when re-executing the final query for scoring

SYSTEM_PROMPT = """You answer questions about a Stack Exchange community (statistics Q&A) by querying a Neo4j graph with the run_cypher tool.

Graph schema:
(:User {userId, displayName, reputation, creationDate, lastAccessDate, websiteUrl, location, aboutMe, views, upVotes, downVotes, accountId, age, profileImageUrl})
(:Post {postId, postTypeId, creationDate, score, viewCount, body, title, lastActivityDate, lastEditDate, communityOwnedDate, closedDate, answerCount, commentCount, favoriteCount, ownerDisplayName, lastEditorDisplayName})
  Posts also carry a second label: :Question (postTypeId 1) or :Answer (postTypeId 2).
(:Comment {commentId, score, text, creationDate, userDisplayName})
(:Vote {voteId, voteTypeId, creationDate, bountyAmount})
(:PostHistory {postHistoryId, postHistoryTypeId, revisionGuid, creationDate, text, comment, userDisplayName})
(:Tag {tagId, tagName, count})
(:Badge {name})

Relationships:
(:User)-[:OWNS]->(:Post)                      the author of the post
(:User)-[:LAST_EDITED]->(:Post)
(:Answer)-[:ANSWERS]->(:Question)
(:Question)-[:ACCEPTED]->(:Answer)
(:Post)-[:TAGGED]->(:Tag)
(:Tag)-[:HAS_EXCERPT]->(:Post)   (:Tag)-[:HAS_WIKI]->(:Post)
(:Post)-[:LINKS_TO {postLinkId, linkTypeId, creationDate}]->(:Post)
(:User)-[:WROTE]->(:Comment)-[:ON_POST]->(:Post)
(:User)-[:CAST]->(:Vote)-[:ON_POST]->(:Post)
(:User)-[:MADE]->(:PostHistory)-[:REVISES]->(:Post)
(:User)-[:EARNED {badgeId, date}]->(:Badge)

Conventions:
- creationDate and similar are LOCAL DATETIME values (Vote.creationDate is a DATE). Filter a year with `x.creationDate.year = 2010`.
- Missing values are absent (null), never empty strings.
- Counter properties (answerCount, commentCount, favoriteCount, viewCount, Tag.count, User.upVotes) are stored values; use them when a question refers to them.
- displayName is not unique.

Work step by step: query the graph, inspect the rows, and refine if needed. The rows returned by your LAST successful query are taken as your answer, so make that final query return exactly what the question asks for, with no extra columns. Then reply with a short final answer."""


# ----------------------------------------------------------------------------- scoring


_DT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?$")


def normalize_value(v: Any) -> str:
    """Canonical string for comparing a SQLite value with a Neo4j value."""
    if v is None:
        return "∅"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        f = float(v)
        if math.isnan(f):
            return "nan"
        return f"{round(f, 2):g}" if f != int(f) else str(int(f))
    s = str(v).strip()
    m = _DT.match(s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    try:
        f = float(s)
        if s.lower() not in ("inf", "-inf", "nan", "infinity"):
            return f"{round(f, 2):g}" if f != int(f) else str(int(f))
    except ValueError:
        pass
    return s


def row_key(row: list[Any]) -> tuple[str, ...]:
    """Column-order-insensitive key: Cypher RETURN order is the model's choice."""
    return tuple(sorted(normalize_value(v) for v in row))


def score_rows(model_rows: list[list[Any]], ref: dict[str, Any]) -> dict[str, float]:
    """Strict: identical multiset of rows. Lenient: same row count and every reference value present."""
    ref_rows: list[list[Any]] = ref.get("rows") or []
    ref_n: int = int(ref.get("n_rows", len(ref_rows)))
    truncated = bool(ref.get("truncated"))
    got = [row_key(r) for r in model_rows]
    want = [row_key(r) for r in ref_rows]
    if truncated:
        # Reference holds only the first 200 rows: require the full count plus containment.
        got_set = set(got)
        strict = len(model_rows) == ref_n and all(w in got_set for w in want)
    else:
        strict = sorted(got) == sorted(want)
    want_vals = {v for r in want for v in r}
    got_vals = {v for r in got for v in r}
    lenient = len(model_rows) == ref_n and want_vals <= got_vals
    return {"correct": float(strict), "lenient": float(lenient or strict),
            "reference_truncated": float(truncated)}


# ----------------------------------------------------------------------------- tool


class CypherTool:
    """Read-only Cypher tool. The server has no RBAC, so read-only is enforced here:
    write keywords are rejected and every query runs inside a read transaction."""

    def __init__(self, driver: Any, database: str) -> None:
        self._driver = driver
        self._database = database
        self.log: list[dict[str, Any]] = []

    async def execute(self, query: str, row_cap: int) -> list[list[Any]]:
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

    @tool
    async def run_cypher(
        self,
        query: Annotated[str, "A read-only Cypher query against the Stack Exchange graph"],
    ) -> ToolResult:
        """Execute a read-only Cypher query and return up to 50 result rows as JSON."""
        # Second layer only: the server itself rejects writes inside read transactions
        # (Neo.ClientError.Statement.AccessMode, verified). String literals are stripped first so
        # a search for, e.g., 'data set' is not mistaken for a SET clause.
        if WRITE_KEYWORDS.search(STRING_LITERALS.sub("''", query)):
            self.log.append({"query": query, "ok": False, "error": "write_blocked"})
            return error_tool_result("Only read queries are allowed.", name="run_cypher",
                                     error_type="write_blocked")
        try:
            rows = await self.execute(query, TOOL_ROW_CAP + 1)
        except Exception as e:  # noqa: BLE001 - the model must see the database error text
            self.log.append({"query": query, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
            return error_tool_result(f"{type(e).__name__}: {e}"[:1500], name="run_cypher",
                                     error_type="cypher_error")
        shown = rows[:TOOL_ROW_CAP]
        text = json.dumps(shown, default=str, ensure_ascii=False)
        if len(rows) > TOOL_ROW_CAP:
            text += f"\n[showing first {TOOL_ROW_CAP} rows; more exist]"
        if len(text) > TOOL_CHAR_CAP:
            text = text[:TOOL_CHAR_CAP] + "... [truncated]"
        self.log.append({"query": query, "ok": True, "n_rows_preview": len(rows)})
        return simple_tool_result(text, name="run_cypher", metrics={"rows_returned": float(len(shown))})


# ----------------------------------------------------------------------------- config


@chz.chz
class Config:
    base_model: str = "Qwen/Qwen3.8-27B"
    renderer_name: str | None = None          # None -> model_info recommended default
    reference_uri: str = ""                   # s3://bucket/key of reference_answers.json
    gold_set: str = "corrected_20251106"
    log_path: str = "~/bird_rl_runs/e2_baseline"
    env_file: str = ".env"
    neo4j_database: str = "neo4j"
    max_turns: int = 8
    max_tokens: int = 8192                    # per sampling turn; reasoning renderers think first
    max_trajectory_tokens: int = 56 * 1024    # model context is 64K
    max_sampled_tokens: int = 16 * 1024       # per-question cap on generated tokens (cost guard)
    temperature: float = 1.0                  # the temperature RL will sample at
    concurrency: int = 16
    limit: int = 0                            # 0 = all questions
    budget_usd: float = 40.0                  # stop starting new questions past this estimate


def load_references(uri: str, gold_set: str) -> list[dict[str, Any]]:
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
    return json.loads(body)["results"][gold_set]


def question_text(ref: dict[str, Any]) -> str:
    evidence = (ref.get("evidence") or "").strip()
    return f"{ref['question']}\n\nHint: {evidence}" if evidence else ref["question"]


class CostMeter:
    """Running dollar estimate. Prompt tokens are priced at the uncached prefill rate, so this
    is an upper bound; the billing API reports the cached/uncached split hours later."""

    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices
        self.prompt_tokens = 0
        self.sampled_tokens = 0

    def add(self, prompt_tokens: int, sampled_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.sampled_tokens += sampled_tokens

    @property
    def usd(self) -> float:
        return (self.prompt_tokens * self.prices["prefill"] + self.sampled_tokens * self.prices["sample"]) / 1e6


# ----------------------------------------------------------------------------- main


async def main(cfg: Config) -> None:
    load_dotenv(cfg.env_file, override=True)
    log_dir = Path(os.path.expanduser(cfg.log_path))
    log_dir.mkdir(parents=True, exist_ok=True)
    results_path = log_dir / "results.jsonl"
    done_ids = {json.loads(l)["question_id"] for l in results_path.open()} if results_path.exists() else set()

    refs = load_references(cfg.reference_uri, cfg.gold_set)
    if cfg.limit:
        refs = refs[: cfg.limit]
    todo = [r for r in refs if r["question_id"] not in done_ids]

    renderer_name = cfg.renderer_name or model_info.get_recommended_renderer_name(cfg.base_model)
    prices = PRICES_PER_M[cfg.base_model]
    run_meta = {"experiment": "E2-baseline", "model": cfg.base_model, "renderer": renderer_name,
                "temperature": cfg.temperature, "max_turns": cfg.max_turns, "max_tokens": cfg.max_tokens, "max_sampled_tokens": cfg.max_sampled_tokens,
                "questions_total": len(refs), "already_done": len(done_ids),
                "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (log_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=1))
    print(f"[{time.strftime('%H:%M:%S')}] {run_meta}", flush=True)

    # Session tagging follows upstream (recipe_user_metadata adds the git revision); the extra keys
    # let billing usage for this run be filtered out of the org-wide report later.
    service = tinker.ServiceClient(user_metadata={**recipe_user_metadata("bird_graph_rl_baseline"),
                                                  "project": "bird-rl", "experiment": "E2-baseline",
                                                  "model": cfg.base_model})
    sampling_client = await service.create_sampling_client_async(base_model=cfg.base_model)
    policy = TinkerTokenCompleter(sampling_client, max_tokens=cfg.max_tokens, temperature=cfg.temperature)
    renderer = get_renderer(renderer_name, tokenizer_utils.get_tokenizer(cfg.base_model))

    # BIRD_NEO4J_* on purpose: the repo .env also holds NEO4J_* for an unrelated cloud instance.
    driver = AsyncGraphDatabase.driver(os.environ["BIRD_NEO4J_URI"],
                                       auth=(os.environ["BIRD_NEO4J_USER"], os.environ["BIRD_NEO4J_PASSWORD"]))
    await driver.verify_connectivity()
    meter = CostMeter(prices)
    semaphore = asyncio.Semaphore(cfg.concurrency)
    write_lock = asyncio.Lock()
    finished: list[dict[str, Any]] = []
    t_start = time.time()
    stopped_for_budget = 0

    async def run_one(ref: dict[str, Any]) -> None:
        nonlocal stopped_for_budget
        async with semaphore:
            if meter.usd >= cfg.budget_usd:
                stopped_for_budget += 1
                return
            t0 = time.time()
            ctool = CypherTool(driver, cfg.neo4j_database)
            captured: dict[str, list[Message]] = {}
            messages = renderer.create_conversation_prefix_with_tools(
                tools=[ctool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT
            ) + [{"role": "user", "content": question_text(ref)}]

            async def reward_fn(history: list[Message]) -> tuple[float, dict[str, float]]:
                captured["history"] = history
                return 0.0, {}

            env = build_agent_tool_env(
                renderer=renderer, tools=[ctool.run_cypher], initial_messages=messages,
                reward_fn=reward_fn, max_turns=cfg.max_turns,
                max_trajectory_tokens=cfg.max_trajectory_tokens,
            )
            # Per-episode budgets via the upstream runner. No wall-clock timeouts on sampling:
            # the SDK retries and detects stuck requests itself (repo CLAUDE.md, pitfall 2).
            limits = RolloutLimits(max_turns=cfg.max_turns, max_trajectory_tokens=cfg.max_trajectory_tokens,
                                   max_sampled_tokens=cfg.max_sampled_tokens)
            error = ""
            try:
                trajectory = await run_rollout(policy, env, limits=limits)
                transitions = trajectory.transitions
                stop_reason = str(getattr(trajectory, "stop_reason", "") or "")
            except Exception as e:  # noqa: BLE001 - record and continue; one failure must not end the run
                transitions, error, stop_reason = [], f"{type(e).__name__}: {e}"[:300], "exception"

            prompt_tokens = sum(t.ob.length for t in transitions)
            sampled_tokens = sum(len(t.ac.tokens) for t in transitions)
            meter.add(prompt_tokens, sampled_tokens)

            successes = [entry for entry in ctool.log if entry["ok"]]
            final_query = successes[-1]["query"] if successes else ""
            model_rows: list[list[Any]] = []
            rescore_error = ""
            if final_query:
                try:
                    model_rows = await ctool.execute(final_query, SCORE_ROW_CAP)
                except Exception as e:  # noqa: BLE001
                    rescore_error = f"{type(e).__name__}: {e}"[:300]
            scores = score_rows(model_rows, ref) if final_query else {
                "correct": 0.0, "lenient": 0.0, "reference_truncated": float(bool(ref.get("truncated")))}

            history = captured.get("history", [])
            final_text = next((get_text_content(m) for m in reversed(history) if m.get("role") == "assistant"), "")
            record = {
                "question_id": ref["question_id"], "difficulty": ref.get("difficulty"),
                "question": ref["question"], **scores,
                "no_query": float(not ctool.log), "n_queries": len(ctool.log),
                "n_query_errors": sum(1 for e in ctool.log if not e["ok"]),
                "turns": len(transitions), "stop_reason": stop_reason, "final_query": final_query,
                "n_model_rows": len(model_rows), "n_reference_rows": ref.get("n_rows"),
                "model_rows_preview": [[str(v) for v in r] for r in model_rows[:5]],
                "reference_rows_preview": (ref.get("rows") or [])[:5],
                "queries": ctool.log, "final_text": final_text[:2000],
                "prompt_tokens": prompt_tokens, "sampled_tokens": sampled_tokens,
                "est_usd_upper": round((prompt_tokens * prices["prefill"] + sampled_tokens * prices["sample"]) / 1e6, 5),
                "seconds": round(time.time() - t0, 1), "error": error, "rescore_error": rescore_error,
            }
            async with write_lock:
                with results_path.open("a") as f:
                    f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
                finished.append(record)
                n = len(finished)
                acc = sum(r["correct"] for r in finished) / n
                print(f"[{time.strftime('%H:%M:%S')}] {n}/{len(todo)} q{ref['question_id']} "
                      f"{ref.get('difficulty','?')[:4]} correct={int(scores['correct'])} "
                      f"turns={len(transitions)} tok={prompt_tokens}+{sampled_tokens} "
                      f"| running acc={acc:.3f} est=${meter.usd:.2f} elapsed={time.time()-t_start:.0f}s",
                      flush=True)

    await asyncio.gather(*(run_one(r) for r in todo))
    await driver.close()

    all_rows = [json.loads(l) for l in results_path.open()]
    by_diff: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_rows:
        by_diff[r.get("difficulty") or "?"].append(r)

    def mean(rows: list[dict[str, Any]], key: str) -> float:
        return sum(float(r.get(key, 0)) for r in rows) / len(rows) if rows else 0.0

    summary = {
        **run_meta, "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_scored": len(all_rows), "skipped_for_budget": stopped_for_budget,
        "this_run_prompt_tokens": meter.prompt_tokens, "this_run_sampled_tokens": meter.sampled_tokens,
        "this_run_est_usd_upper": round(meter.usd, 2),
        "by_difficulty": {d: {"n": len(rs), "correct": round(mean(rs, "correct"), 3),
                              "lenient": round(mean(rs, "lenient"), 3), "no_query": round(mean(rs, "no_query"), 3),
                              "turns": round(mean(rs, "turns"), 2)} for d, rs in sorted(by_diff.items())},
        "overall": {"n": len(all_rows), "correct": round(mean(all_rows, "correct"), 3),
                    "lenient": round(mean(all_rows, "lenient"), 3), "no_query": round(mean(all_rows, "no_query"), 3),
                    "turns": round(mean(all_rows, "turns"), 2),
                    "mean_prompt_tokens": round(mean(all_rows, "prompt_tokens")),
                    "mean_sampled_tokens": round(mean(all_rows, "sampled_tokens")),
                    "mean_est_usd_upper": round(mean(all_rows, "est_usd_upper"), 4)},
    }
    (log_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    asyncio.run(main(chz.entrypoint(Config)))
