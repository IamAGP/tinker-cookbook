"""Failure-mode diagnosis — why does the base agent get held-out questions wrong?

Buckets each WRONG answer into:
  - RETRIEVAL failure: the passages the agent retrieved do NOT contain the info
    needed to answer  → a process/retrieval reward (Fork 1) could help.
  - REASONING failure: the retrieved passages DO contain the info, but the agent
    still answered wrong → tool-use RL can't fix this (Fork 2 / harder task).

Uses the strong judge for two calls per wrong item: (1) correctness,
(2) retrieval-sufficiency (does retrieved text support the reference answer?).
This sidesteps cross-source gold-passage-id plumbing — it asks the judge whether
what the agent ACTUALLY retrieved was sufficient.

Run:
    python -m tinker_cookbook.recipes.legal_rl.diagnose_failures use_unified=True \
        base_model=Qwen/Qwen3-30B-A3B-Instruct-2507 \
        judge_model=Qwen/Qwen3-235B-A22B-Instruct-2507 sample=40

Required env: TINKER_API_KEY, AWS_*.
"""

import asyncio
import json
import random

import chz
import tinker

from tinker_cookbook import model_info, tokenizer_utils
from tinker_cookbook.completers import TinkerMessageCompleter, TinkerTokenCompleter
from tinker_cookbook.recipes.legal_rl.legal_env import LEGAL_TASK_INSTRUCTIONS, load_legal_dataset
from tinker_cookbook.recipes.legal_rl.tools import ChromaTool, LLMJudgeReward, RetrievalConfig
from tinker_cookbook.renderers import get_renderer, get_text_content
from tinker_cookbook.rl.rollouts import do_single_rollout
from tinker_cookbook.tool_use import build_agent_tool_env

SUFFICIENCY_PROMPT = """You are assessing whether retrieved passages contain enough \
information to answer a legal question correctly.

QUESTION:
{question}

REFERENCE ANSWER (ground truth):
{reference}

PASSAGES THE AGENT RETRIEVED:
{retrieved}

Do the retrieved passages contain the information needed to produce the reference \
answer? Respond with EXACTLY one line:
VERDICT: SUFFICIENT     — the passages contain the needed information
VERDICT: INSUFFICIENT   — the passages do NOT contain the needed information"""


@chz.chz
class CLIConfig:
    base_model: str = "Qwen/Qwen3-30B-A3B-Instruct-2507"
    model_path: str | None = None
    judge_model: str = "Qwen/Qwen3-235B-A22B-Instruct-2507"
    judge_max_tokens: int = 64
    use_unified: bool = False
    eval_frac: float = 0.1
    sample: int = 40
    seed: int = 7
    n_results: int = 3
    max_turns: int = 5
    max_tokens: int = 1024
    max_trajectory_tokens: int = 32 * 1024
    aws_region: str = "us-east-1"
    concurrency: int = 6
    out_path: str = "/Users/adithyagiridharan/Desktop/legal_rl_runs/failure_diagnosis.json"


def _retrieved_text(history: list) -> str:
    parts = []
    for msg in history:
        if msg.get("role") == "tool":
            c = msg.get("content")
            parts.append(get_text_content(msg) if isinstance(c, list) else str(c))
    return "\n\n".join(parts)


async def cli_main(config: CLIConfig) -> None:
    if config.use_unified:
        from tinker_cookbook.recipes.legal_rl.build_unified_index import (
            CHROMA_PATH as UP, COLLECTION_NAME as UC,
        )
        from tinker_cookbook.recipes.legal_rl.legal_data import ALL_SOURCES
        sources, chroma_path, collection_name = ALL_SOURCES, UP, UC
    else:
        sources, chroma_path, collection_name = None, "/tmp/legal_chroma_db", "legal_passages"

    data = load_legal_dataset(split_role="eval", eval_frac=config.eval_frac, sources=sources)
    random.Random(config.seed).shuffle(data)
    data = data[: config.sample]
    label = config.model_path or f"{config.base_model} (base)"
    print(f"Diagnosing {len(data)} held-out questions | model: {label}")

    svc = tinker.ServiceClient()
    sc = (
        svc.create_sampling_client(model_path=config.model_path)
        if config.model_path
        else svc.create_sampling_client(base_model=config.base_model)
    )
    policy = TinkerTokenCompleter(sc, max_tokens=config.max_tokens)
    tok = tokenizer_utils.get_tokenizer(config.base_model)
    renderer = get_renderer(model_info.get_recommended_renderer_name(config.base_model), tok)

    judge_sc = svc.create_sampling_client(base_model=config.judge_model)
    judge_renderer = get_renderer(
        model_info.get_recommended_renderer_name(config.judge_model),
        tokenizer_utils.get_tokenizer(config.judge_model),
    )
    judge = TinkerMessageCompleter(
        judge_sc, judge_renderer, max_tokens=config.judge_max_tokens, temperature=0.0
    )

    tool = ChromaTool.build(
        chroma_path=chroma_path, collection_name=collection_name,
        aws_region=config.aws_region, retrieval_config=RetrievalConfig(n_results=config.n_results),
    )
    sem = asyncio.Semaphore(config.concurrency)

    async def diagnose_one(datum) -> dict:
        msgs = renderer.create_conversation_prefix_with_tools(
            tools=[tool.search.to_spec()], system_prompt=LEGAL_TASK_INSTRUCTIONS
        ) + [{"role": "user", "content": datum["question"]}]
        reward_fn = LLMJudgeReward(gold_answers=datum["answer"], judge_completer=judge)
        env = build_agent_tool_env(
            renderer=renderer, tools=[tool.search], initial_messages=msgs,
            reward_fn=reward_fn, max_turns=config.max_turns,
            max_trajectory_tokens=config.max_trajectory_tokens,
        )
        async def judge_sufficiency(retrieved_text: str) -> bool:
            prompt = SUFFICIENCY_PROMPT.format(
                question=datum["question"][:4000],
                reference="\n--OR--\n".join(datum["answer"])[:4000],
                retrieved=(retrieved_text or "(no passages retrieved)")[:8000],
            )
            reply = await judge([{"role": "user", "content": prompt}])
            up = get_text_content(reply).upper()
            return "INSUFFICIENT" not in up and "SUFFICIENT" in up

        async with sem:
            traj = await do_single_rollout(policy, env)
            m = traj.transitions[-1].metrics if traj.transitions else {}
            correct = m.get("correct", 0.0)
            agent_retrieved = _retrieved_text(env.message_env.history)
            bucket = "correct"
            if correct < 1.0:
                agent_sufficient = await judge_sufficiency(agent_retrieved)
                if agent_sufficient:
                    # Had the info, still wrong → reasoning.
                    bucket = "reasoning_failure"
                else:
                    # Agent didn't retrieve the info. Was that the agent's QUERY,
                    # or the retriever's ceiling? Re-retrieve with the LITERAL
                    # question (best-case query) and re-check sufficiency.
                    emb = await tool._get_embeddings([datum["question"]])
                    docs = await tool._query_chroma(emb)
                    literal_retrieved = "\n\n".join(docs[0]) if docs else ""
                    literal_sufficient = await judge_sufficiency(literal_retrieved)
                    bucket = (
                        "agent_query_failure" if literal_sufficient else "retriever_ceiling"
                    )
        return {
            "question": datum["question"][:200],
            "correct": correct,
            "bucket": bucket,
            "n_retrieved_chars": len(agent_retrieved),
            "turns": len(traj.transitions),
        }

    results = await asyncio.gather(*[diagnose_one(d) for d in data])

    n = len(results)
    correct = sum(1 for r in results if r["bucket"] == "correct")
    reas = sum(1 for r in results if r["bucket"] == "reasoning_failure")
    aq = sum(1 for r in results if r["bucket"] == "agent_query_failure")
    ceil = sum(1 for r in results if r["bucket"] == "retriever_ceiling")
    wrong = reas + aq + ceil

    def pct(x):
        return f"{x/wrong:.1%}" if wrong else "n/a"

    print("\n" + "=" * 80)
    print("FAILURE-MODE DIAGNOSIS (3-way)")
    print("=" * 80)
    print(f"Model: {label} | sample: {n} held-out questions")
    print(f"  correct: {correct}/{n} ({correct/n:.1%})  |  WRONG: {wrong}/{n}")
    if wrong:
        print(f"    reasoning_failure:   {reas}/{wrong} ({pct(reas)})  info retrieved, still wrong → tool-RL can't fix")
        print(f"    agent_query_failure: {aq}/{wrong} ({pct(aq)})  agent's query missed it, but literal-Q retrieves it → Fork 1 (process/query reward)")
        print(f"    retriever_ceiling:   {ceil}/{wrong} ({pct(ceil)})  even literal-Q can't retrieve it → infra, not RL")
    print("=" * 80)
    print("Fork decision:")
    print("  - high agent_query_failure → Fork 1 (process/query reward) is well-targeted: RL can teach better queries")
    print("  - high reasoning_failure   → Fork 2 (harder/headroom task); tool-use RL won't help")
    print("  - high retriever_ceiling   → fix retrieval infra (chunking/embeddings/n_results), not RL")

    with open(config.out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nPer-question detail saved: {config.out_path}")


if __name__ == "__main__":
    asyncio.run(cli_main(chz.entrypoint(CLIConfig)))
