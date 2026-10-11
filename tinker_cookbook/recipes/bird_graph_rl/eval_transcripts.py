"""Full, verbatim agent transcripts for a few chosen questions, for the write-up.

The evaluation harness keeps only queries, rows and the final answer. This runs the same agent
(same system prompt, tool, renderer, temperature and limits as ``baseline_eval``) on a handful of
questions and writes every message of every attempt — the model's reasoning, each tool call and
each tool result — to one JSON file, alongside the same scores the harness computes.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import chz
import tinker
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.recipes.bird_graph_rl.baseline_eval import (
    SCORE_ROW_CAP, SYSTEM_PROMPT, CypherTool, load_generated, load_references, question_text, score_rows)
from tinker_cookbook.renderers import get_renderer
from tinker_cookbook.renderers.base import Message
from tinker_cookbook.rl.rollout_limits import RolloutLimits
from tinker_cookbook.rl.rollout_runner import run_rollout
from tinker_cookbook.tool_use import build_agent_tool_env


@chz.chz
class Config:
    base_model: str = "Qwen/Qwen3.5-9B"
    models: str = ""            # comma-separated label=model_path pairs; "untrained=" means the base model
    human_ids: str = ""         # comma-separated question ids from the 186
    generated_ids: str = ""     # comma-separated instance ids from a generated file
    generated_path: str = "~/bird_rl_runs/datagen_v3/all_questions.jsonl"
    generated_split: str = "heldout_structure"
    reference_uri: str = ""
    samples: int = 4
    out_path: str = "~/bird_rl_runs/blog_transcripts.json"
    env_file: str = ".env"
    max_turns: int = 8
    max_tokens: int = 8192
    max_trajectory_tokens: int = 56 * 1024
    max_sampled_tokens: int = 16 * 1024
    temperature: float = 1.0


async def main(cfg: Config) -> None:
    load_dotenv(cfg.env_file, override=True)
    refs: list[dict[str, Any]] = []
    if cfg.human_ids:
        want = set(cfg.human_ids.split(","))
        refs += [dict(r, source="human") for r in load_references(cfg.reference_uri, "corrected_20251106") if str(r["question_id"]) in want]
    if cfg.generated_ids:
        want = set(cfg.generated_ids.split(","))
        refs += [dict(r, source="generated") for r in load_generated(cfg.generated_path, cfg.generated_split) if r["question_id"] in want]
    renderer_name = model_info.get_recommended_renderer_name(cfg.base_model)
    renderer = get_renderer(renderer_name, tokenizer_utils.get_tokenizer(cfg.base_model))
    service = tinker.ServiceClient()
    driver = AsyncGraphDatabase.driver(os.environ["BIRD_NEO4J_URI"], auth=(os.environ["BIRD_NEO4J_USER"], os.environ["BIRD_NEO4J_PASSWORD"]))
    out: list[dict[str, Any]] = []

    async def attempt(label: str, client: Any, ref: dict[str, Any], k: int) -> None:
        tool = CypherTool(driver, "neo4j")
        captured: dict[str, list[Message]] = {}
        messages = renderer.create_conversation_prefix_with_tools(tools=[tool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT) + [
            {"role": "user", "content": question_text(ref)}]

        async def reward_fn(history: list[Message]) -> tuple[float, dict[str, float]]:
            captured["history"] = history
            return 0.0, {}

        env = build_agent_tool_env(renderer=renderer, tools=[tool.run_cypher], initial_messages=messages, reward_fn=reward_fn,
                                   max_turns=cfg.max_turns, max_trajectory_tokens=cfg.max_trajectory_tokens)
        policy = TinkerTokenCompleter(client, max_tokens=cfg.max_tokens, temperature=cfg.temperature)
        traj = await run_rollout(policy, env, limits=RolloutLimits(max_turns=cfg.max_turns, max_trajectory_tokens=cfg.max_trajectory_tokens, max_sampled_tokens=cfg.max_sampled_tokens))
        ok = [e for e in tool.log if e["ok"]]
        final_query = ok[-1]["query"] if ok else ""
        rows = await tool.execute(final_query, SCORE_ROW_CAP) if final_query else []
        scores = score_rows(rows, ref) if final_query else {"correct": 0.0, "lenient": 0.0}
        history = captured.get("history", [])
        out.append({"model": label, "question_id": str(ref["question_id"]), "source": ref["source"], "sample": k,
                    "question": ref["question"], "hint": ref.get("evidence", ""), "reference_rows": (ref.get("rows") or [])[:20],
                    "correct": scores["correct"], "lenient": scores["lenient"], "turns": len(traj.transitions),
                    "stop_reason": str(getattr(traj, "stop_reason", "") or ""), "queries": tool.log, "final_query": final_query,
                    "final_rows": [[str(v) for v in r] for r in rows[:20]],
                    "system_prompt": SYSTEM_PROMPT, "messages": history[len(messages) - 1:]})
        print(f"{label} q{ref['question_id']} s{k} correct={scores['correct']} lenient={scores['lenient']} turns={len(traj.transitions)}", flush=True)

    jobs = []
    for pair in cfg.models.split(","):
        label, path = pair.split("=", 1)
        client = await (service.create_sampling_client_async(model_path=path) if path else service.create_sampling_client_async(base_model=cfg.base_model))
        jobs += [attempt(label, client, ref, k) for ref in refs for k in range(1, cfg.samples + 1)]
    await asyncio.gather(*jobs)
    await driver.close()
    Path(os.path.expanduser(cfg.out_path)).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    print("wrote", len(out), "transcripts")


if __name__ == "__main__":
    asyncio.run(main(chz.entrypoint(Config)))
