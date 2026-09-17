"""Watch the full agent trajectory on a single question.

Runs a model (base or a trained checkpoint) as the Cypher agent and prints the
ENTIRE loop — each assistant reasoning/answer turn, every run_cypher tool call
with its arguments, and every DB result — ending with the final answer.

Examples:
  # trained step-60 checkpoint (default) on a custom question
  python -m tinker_cookbook.recipes.cricket_kg_rl.inspect_trajectory \
      question="How many sixes did MS Dhoni hit against YS Chahal?"

  # the base model instead (no checkpoint)
  python -m tinker_cookbook.recipes.cricket_kg_rl.inspect_trajectory \
      model_path=null question="..."

  # pull a question straight from the eval set (shows gold + score too)
  python -m tinker_cookbook.recipes.cricket_kg_rl.inspect_trajectory eval_index=0
"""

from __future__ import annotations

import asyncio
import json

import chz
import tinker

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.recipes.cricket_kg_rl.baseline_eval import (
    CREDS_FILE,
    SYSTEM_PROMPT,
    CypherTool,
    score,
)
from tinker_cookbook.renderers import get_renderer, get_text_content
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import build_agent_tool_env

# The R1 final (step-60) checkpoint — override with model_path=... or model_path=null
DEFAULT_CKPT = "tinker://1fd2153b-e9ea-5cf6-832a-7a193838666e:train:0/sampler_weights/000060"
EVAL_PATH = "/Users/adithyagiridharan/Desktop/PythonProjects/cricket-analytics/data/gold/eval.jsonl"

DIV = "─" * 80


def _print_history(history: list[dict]) -> None:
    turn = 0
    for m in history:
        role = m.get("role")
        if role == "system":
            print(f"{DIV}\n[SYSTEM PROMPT]  (schema + instructions; {len(get_text_content(m))} chars, hidden)")
            continue
        if role == "user":
            print(f"{DIV}\n👤 USER\n{get_text_content(m)}")
            continue
        if role == "assistant":
            turn += 1
            text = get_text_content(m).strip()
            tcs = m.get("tool_calls") or []
            print(f"{DIV}\n🤖 ASSISTANT — turn {turn}")
            if text:
                print(f"  reasoning/answer:\n    " + text.replace("\n", "\n    "))
            for tc in tcs:
                name = tc.function.name
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                q = args.get("query") if isinstance(args, dict) else args
                print(f"  🔧 TOOL CALL → {name}(")
                print("       " + str(q).replace("\n", "\n       "))
                print("     )")
            continue
        if role == "tool":
            res = get_text_content(m)
            shown = res if len(res) < 600 else res[:600] + " …[truncated]"
            print(f"  📊 DB RESULT:\n     " + shown.replace("\n", "\n     "))
            continue


@chz.chz
class CLIConfig:
    base_model: str = "Qwen/Qwen3.5-9B"
    model_path: str | None = DEFAULT_CKPT   # set to null for the base model
    question: str | None = None
    eval_index: int | None = None           # pull question (+gold) from eval.jsonl
    max_turns: int = 6
    max_tokens: int = 1024
    temperature: float = 0.0                # greedy → deterministic, easy to read


async def cli_main(cfg: CLIConfig) -> None:
    gold = None
    if cfg.eval_index is not None:
        rows = [json.loads(l) for l in open(EVAL_PATH) if l.strip()]
        gold = rows[cfg.eval_index]
        question = gold["question"]
    elif cfg.question:
        question = cfg.question
    else:
        question = "How many runs has V Kohli scored off JJ Bumrah, and how many times has Bumrah dismissed him?"

    label = cfg.model_path or f"{cfg.base_model} (base)"
    print(f"MODEL: {label}\nQUESTION: {question}")

    svc = tinker.ServiceClient()
    sc = (svc.create_sampling_client(model_path=cfg.model_path) if cfg.model_path
          else svc.create_sampling_client(base_model=cfg.base_model))
    policy = TinkerTokenCompleter(sc, max_tokens=cfg.max_tokens, temperature=cfg.temperature)
    tok = tokenizer_utils.get_tokenizer(cfg.base_model)
    renderer = get_renderer(model_info.get_recommended_renderer_name(cfg.base_model), tok)
    ctool = CypherTool(CREDS_FILE)

    msgs = renderer.create_conversation_prefix_with_tools(
        tools=[ctool.run_cypher.to_spec()], system_prompt=SYSTEM_PROMPT
    ) + [{"role": "user", "content": question}]

    captured: list[dict] = []

    async def reward_fn(history):
        captured.clear()
        captured.extend(history)
        if gold is not None:
            s = score(history, gold)
            return s["correct"], s
        return 0.0, {}

    env = build_agent_tool_env(
        renderer=renderer, tools=[ctool.run_cypher], initial_messages=msgs,
        reward_fn=reward_fn, max_turns=cfg.max_turns, max_trajectory_tokens=32 * 1024,
    )
    await do_single_rollout(policy, env)

    _print_history(captured)
    print(DIV)
    if gold is not None:
        s = score(captured, gold)
        print(f"GOLD: {gold.get('gold_answer')}  | entities={gold.get('entities')} numbers={gold.get('numbers')}")
        print(f"SCORE: correct={s['correct']} entity={s['entity']} number={s['number']}  (difficulty={gold.get('difficulty')})")
    print(DIV)


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
